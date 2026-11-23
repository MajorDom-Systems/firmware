"""Build one `[build] builder = "silabs-sisdk"` package inside the builder image: slc generate, config edits, make, GBL.

Package inputs (package.toml):
  [build] project       - `sdk:<path>` (an SDK sample app) or a path relative to the package dir
          with          - the board/part slc generates for (e.g. brd2713a)
          fw_type       - the GBL metadata `fw_type` flashers read
          cpc_security  - SL_CPC_SECURITY_ENABLED
  [build.pins]          - radio-chip side of the host UART: peripheral, tx, rx (e.g. "PA04")
  [serial] baud, flow   - host UART baud and flow control ("none" or "rtscts"); the Z-Wave Serial API takes 115200/none only
Writes <out>/<package>.gbl and <out>/<package>.s37. The GBL is assembled with pygbl (as Nabu Casa's builder does, no
Commander), but its program tags come from the .s37 like `commander gbl create --app`: the ELF also has a zero-filled
load segment over the bootloader region, which pygbl's ELF path would put into the image.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from pygbl import GBL3EraseProg, GBL3Image, GBL3Metadata, build_application_gbl3

SDK = Path(os.environ.get("SISDK", "/opt/sisdk"))
FLOW = {"none": "usartHwFlowControlNone", "rtscts": "usartHwFlowControlCtsAndRts"}


def set_defines(header: Path, defines: dict[str, str | int]):
    text = header.read_text()
    for name, value in defines.items():
        text, count = re.subn(rf"(?m)^(\s*#define\s+{name}\s+).*$", rf"\g<1>{value}", text)
        if count != 1:
            raise SystemExit(f"{header.name}: expected one #define {name}, found {count}")
    header.write_text(text)
    print(f"{header.name}: {defines}", flush=True)


def pin(name: str) -> tuple[str, int]:
    """"PA04" -> ("A", 4)."""
    if not (m := re.fullmatch(r"P([A-D])(\d{1,2})", name)):
        raise SystemExit(f"bad pin {name!r}, expected e.g. PA04")
    return m[1], int(m[2])


def pin_defines(prefix: str, pins: dict[str, str], port_format: str) -> dict[str, str | int]:
    """`[build.pins]` as the pin-tool defines of one UART config header (`<prefix>_TX_PORT`, `<prefix>_TX_PIN`, ...)."""
    defines: dict[str, str | int] = {}
    if peripheral := pins.get("peripheral"):
        defines |= {f"{prefix}_PERIPHERAL": peripheral, f"{prefix}_PERIPHERAL_NO": int(peripheral[-1])}
    for signal in ("tx", "rx", "cts", "rts"):
        if signal in pins:
            port, number = pin(pins[signal])
            defines |= {f"{prefix}_{signal.upper()}_PORT": port_format.format(port), f"{prefix}_{signal.upper()}_PIN": number}
    return defines


def configure(project_dir: Path, package: dict):
    """Apply the package's serial settings to the app's host UART: the CPC UART driver, or the Z-Wave Serial API UART."""
    build, serial = package["build"], package["serial"]
    config = project_dir / "config"
    pins = build.get("pins", {})
    if "cpc_security" in build:
        set_defines(config / "sl_cpc_security_config.h", {"SL_CPC_SECURITY_ENABLED": int(build["cpc_security"])})
    if (serial_api := config / "serial_api_config.h").exists():
        # The Serial API UART is fixed at 115200 8N1 without flow control (comm_interface.c); only its pins are config.
        if (serial["baud"], serial["flow"]) != (115200, "none"):
            raise SystemExit("the Z-Wave Serial API UART runs at 115200 without flow control only")
        set_defines(serial_api, pin_defines("SERIAL_API", pins, "SL_GPIO_PORT_{}"))
        return
    [uart] = config.glob("sl_cpc_drv_uart_usart_*_config.h")
    prefix = f"SL_CPC_DRV_UART_{uart.name.removeprefix('sl_cpc_drv_uart_usart_').removesuffix('_config.h').upper()}"
    defines: dict[str, str | int] = {f"{prefix}_BAUDRATE": serial["baud"], f"{prefix}_FLOW_CONTROL_TYPE": FLOW[serial["flow"]]}
    set_defines(uart, defines | pin_defines(prefix, pins, "gpioPort{}"))


def srec_segments(s37: Path) -> list[tuple[int, bytes]]:
    """Contiguous (address, data) runs of an S-record file's data records."""
    segments: list[tuple[int, bytearray]] = []
    for line in s37.read_text().split():
        if line[:2] not in ("S1", "S2", "S3"):
            continue
        record = bytes.fromhex(line[2:])
        width = int(line[1]) + 1
        address, data = int.from_bytes(record[1:1 + width], "big"), record[1 + width:-1]
        if segments and segments[-1][0] + len(segments[-1][1]) == address:
            segments[-1][1].extend(data)
        else:
            segments.append((address, bytearray(data)))
    return [(address, bytes(data)) for address, data in segments]


def app_gbl(elf: Path, s37: Path, metadata: bytes) -> bytes:
    with elf.open("rb") as f:
        image = build_application_gbl3(f)
    head = [t for t in image.tags if not isinstance(t, GBL3EraseProg)][:2]
    progs = [GBL3EraseProg(address=address, data=data) for address, data in srec_segments(s37)]
    for prog in progs:
        print(f"program tag {prog.address:#010x} {len(prog.data)} bytes", flush=True)
    image = GBL3Image(tags=[*head, *progs, GBL3Metadata(metadata=metadata)]).regenerate_crc()
    return image.serialize(block_size=4)


def run(*args: str | Path, cwd: Path | None = None):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, cwd=cwd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--work", type=Path, default=Path("/tmp/build"))
    args = parser.parse_args()

    package = tomllib.loads((args.package_dir / "package.toml").read_text())
    build = package["build"]
    if package["sdk"]["version"] != os.environ.get("SISDK_VERSION"):
        raise SystemExit(f"package wants SDK {package['sdk']['version']}, image has {os.environ.get('SISDK_VERSION')}")
    project = build["project"]
    slcp = SDK / project.removeprefix("sdk:") if project.startswith("sdk:") else args.package_dir.resolve() / project

    shutil.rmtree(args.work, ignore_errors=True)
    tool_paths = [f"--tool-path={p.parent}" for p in Path("/opt/silabs").glob("*/apack.json")]
    run("slc", "generate", "--sdk", SDK, "-p", slcp, "-d", args.work, "--with", build["with"], "-np", "-o", "makefile",
        "--toolchain-locations=gcc:/opt/gcc-arm", *tool_paths)
    configure(args.work, package)
    [makefile] = args.work.glob("*.Makefile")
    # Some apps (Z-Wave) declare a Commander post-build step (.slpb); the GBL is made below instead, so it is a no-op.
    run("make", "-f", makefile.name, f"-j{os.cpu_count()}", "POST_BUILD_EXE=true", cwd=args.work)

    name = makefile.name.removesuffix(".Makefile")
    elf = args.work / "build/debug" / f"{name}.out"
    metadata = {"metadata_version": 2, "sdk_version": package["sdk"]["version"], "fw_type": build.get("fw_type"),
                "fw_variant": None, "baudrate": package["serial"]["baud"]}
    gbl = app_gbl(elf, elf.with_suffix(".s37"), json.dumps(metadata, sort_keys=True).encode())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{package['name']}.gbl").write_bytes(gbl)
    shutil.copyfile(elf.with_suffix(".s37"), args.out / f"{package['name']}.s37")
    print(f"{package['name']}.gbl: {len(gbl)} bytes", flush=True)


if __name__ == "__main__":
    main()
