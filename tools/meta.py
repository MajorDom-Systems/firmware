"""Read a Gecko Bootloader image (.gbl) and write `<asset>.meta.json` and the CycloneDX SBOM `<asset>.cdx.json`."""

import argparse
import json
import re
import struct
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.common import REPO, Package, load_package, sha256

TAG_HEADER = 0x03A617EB
TAG_APPLICATION = 0xF40A0AF4
TAG_BOOTLOADER = 0xF50909F5
TAG_METADATA = 0xF60808F6
TAG_END = 0xFC0404FC
TAG_PROGS = {0xFE0101FE, 0xFD0303FD}  # prog and erase&prog; compressed variants are not checked for zero runs
MAX_ZERO_RUN = 4096

# ApplicationData_t.type bits (Gecko Bootloader API, application_properties.h).
APP_TYPES = {0: "zigbee", 1: "thread", 2: "flex", 3: "bluetooth", 4: "mcu", 5: "bluetooth_app", 6: "bootloader", 7: "zwave"}


class GblError(ValueError):
    pass


@dataclass
class Gbl:
    header_version: int
    image_type: int
    app_types: list[str] = field(default_factory=list)
    app_version: int | None = None
    bootloader_version: int | None = None
    metadata: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    programs: list[list[int]] = field(default_factory=list)  # [address, size] per program tag
    max_zero_run: int = 0


def parse_gbl(data: bytes) -> Gbl:
    """Walks the tag list. The end tag's CRC32 covers every byte before the CRC itself.

    Commander and pygbl pad the image with 0xFF to a 4-byte boundary after the end tag.
    """
    if len(data) < 8 or struct.unpack_from("<I", data)[0] != TAG_HEADER:
        raise GblError("not a GBL: missing header tag")
    gbl: Gbl | None = None
    offset = 0
    while offset + 8 <= len(data):
        tag, length = struct.unpack_from("<II", data, offset)
        body = data[offset + 8:offset + 8 + length]
        if len(body) != length:
            raise GblError(f"truncated tag {tag:#010x} at {offset}")
        if tag == TAG_HEADER:
            gbl = Gbl(*struct.unpack_from("<II", body))
        elif gbl is None:
            raise GblError("header tag must come first")
        elif tag == TAG_APPLICATION:
            app_type, gbl.app_version = struct.unpack_from("<II", body)
            gbl.app_types = [name for bit, name in APP_TYPES.items() if app_type & (1 << bit)]
        elif tag == TAG_BOOTLOADER:
            gbl.bootloader_version = struct.unpack_from("<I", body)[0]
        elif tag in TAG_PROGS:
            gbl.programs.append([struct.unpack_from("<I", body)[0], length - 4])
            gbl.max_zero_run = max(gbl.max_zero_run, max(map(len, re.findall(rb"\x00+", body[4:])), default=0))
        elif tag == TAG_METADATA:
            try:
                gbl.metadata = json.loads(body)
            except ValueError:
                gbl.metadata = {"raw": body.hex()}
        gbl.tags.append(f"{tag:#010x}")
        offset += 8 + length
        if tag == TAG_END:
            if zlib.crc32(data[:offset - 4]) != struct.unpack_from("<I", body)[0]:
                raise GblError("CRC32 mismatch")
            if data[offset:] != b"\xff" * (-offset % 4):
                raise GblError("trailing bytes after the end tag")
            return gbl
    raise GblError("missing end tag")


def check_programs(gbl: Gbl, app_start: int):
    """An application GBL holds only the application: nothing below its start, no zero-filled gaps."""
    for address, size in gbl.programs:
        print(f"program tag {address:#010x} {size} bytes")
        if address < app_start:
            raise GblError(f"program tag at {address:#010x} starts below the application start {app_start:#010x}")
    if gbl.max_zero_run > MAX_ZERO_RUN:
        raise GblError(f"program data has a {gbl.max_zero_run}-byte zero run (filled gap?)")


def meta(package: Package, gbl_path: Path) -> dict[str, Any]:
    gbl = parse_gbl(gbl_path.read_bytes())
    if (app_start := package.data.get("build", {}).get("app_start")) is not None:
        check_programs(gbl, app_start)
    if gbl.metadata and (baud := gbl.metadata.get("baudrate")) and baud != package.data["serial"]["baud"]:
        raise GblError(f"GBL metadata baud {baud} differs from package.toml {package.data['serial']['baud']}")
    keys = ("chip", "license", "summary", "sdk", "stack", "protocol", "serial", "requires")
    return {
        "schema": 1,
        "package": package.name,
        "version": package.version,
        **{key: package.data[key] for key in keys if key in package.data},
        "source": package.source["type"],
        "files": {"gbl": {"name": gbl_path.name, "sha256": sha256(gbl_path), "size": gbl_path.stat().st_size}},
        "gbl": asdict(gbl),
    }


def cyclonedx(package: Package, gbl_path: Path) -> dict[str, Any]:
    components = [{"type": "library", "name": package.data["sdk"]["name"], "version": package.data["sdk"]["version"],
                   "supplier": {"name": "Silicon Laboratories"}, "licenses": [{"license": {"name": "MSLA"}}]}]
    components += [{"type": "library", "name": name, "version": str(version)}
                   for name, version in package.data.get("stack", {}).items()]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {
            "type": "firmware",
            "name": package.name,
            "version": package.version,
            "hashes": [{"alg": "SHA-256", "content": sha256(gbl_path)}],
            "externalReferences": [{"type": "vcs", "url": f"https://github.com/{REPO}"}],
        }},
        "components": components,
    }


def write(package: Package, gbl_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix, doc in ((".meta.json", meta(package, gbl_path)), (".cdx.json", cyclonedx(package, gbl_path))):
        path = out_dir / package.asset(suffix)
        path.write_text(json.dumps(doc, indent=2) + "\n")
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("gbl", type=Path)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    for path in write(load_package(args.package_dir), args.gbl, args.out):
        print(path)


if __name__ == "__main__":
    main()
