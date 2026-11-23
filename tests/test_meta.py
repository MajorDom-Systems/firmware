import json
import struct
from pathlib import Path

import pytest

from tests.conftest import make_gbl
from tools.common import Package, load_package, sha256
from tools.meta import GblError, check_programs, cyclonedx, meta, parse_gbl, write


def test_parses_application_tag():
    gbl = parse_gbl(make_gbl(app_type=0b11))
    assert gbl.app_types == ["zigbee", "thread"]
    assert gbl.app_version == 1
    assert gbl.metadata is None


def test_accepts_alignment_padding():
    data = make_gbl(metadata=b'{"baudrate": 115200}   ')
    assert len(data) % 4 == 3
    assert parse_gbl(data + b"\xff").metadata == {"baudrate": 115200}


def test_parses_json_metadata():
    assert parse_gbl(make_gbl(metadata=b'{"baudrate": 115200}')).metadata == {"baudrate": 115200}


@pytest.mark.parametrize(("data", "error"), [
    (b"\x00" * 16, "missing header"),
    (make_gbl()[:-14], "truncated"),
    (make_gbl()[:-4] + b"\x00\x00\x00\x00", "CRC32"),
    (make_gbl() + b"\x00", "trailing"),
    (make_gbl() + b"\xff" * 4, "trailing"),
], ids=["no-header", "truncated", "crc", "trailing", "padding-past-boundary"])
def test_rejects_broken_images(data: bytes, error: str):
    with pytest.raises(GblError, match=error):
        parse_gbl(data)


def test_meta_carries_package_facts(package: Package, gbl_file: Path):
    doc = meta(package, gbl_file)
    assert doc["package"] == "demo-mg26-multipan"
    assert (doc["chip"], doc["protocol"]) == ("EFR32MG26", "silabs-cpc")
    assert doc["files"]["gbl"] == {"name": "app.gbl", "sha256": sha256(gbl_file), "size": gbl_file.stat().st_size}
    assert doc["gbl"]["app_types"] == ["thread"]


def test_meta_rejects_baud_mismatch(package: Package, tmp_path: Path):
    path = tmp_path / "fast.gbl"
    path.write_bytes(make_gbl(metadata=b'{"baudrate": 460800}'))
    with pytest.raises(GblError, match="baud"):
        meta(package, path)


def test_cyclonedx_lists_sdk_and_stack(package: Package, gbl_file: Path):
    bom = cyclonedx(package, gbl_file)
    assert bom["metadata"]["component"]["hashes"][0]["content"] == sha256(gbl_file)
    assert [c["name"] for c in bom["components"]] == ["sisdk", "openthread"]


def test_write_names_assets(package: Package, gbl_file: Path, tmp_path: Path):
    paths = write(package, gbl_file, tmp_path / "dist")
    assert [p.name for p in paths] == ["demo-mg26-multipan_1.0.0.meta.json", "demo-mg26-multipan_1.0.0.cdx.json"]
    assert json.loads(paths[0].read_text())["version"] == "1.0.0"


def prog(address: int, data: bytes) -> bytes:
    return struct.pack("<I", address) + data


def test_records_program_tags():
    gbl = parse_gbl(make_gbl(prog=prog(0x08006000, b"\xaa" * 440)))
    assert gbl.programs == [[0x08006000, 440]]
    check_programs(gbl, 0x08006000)


@pytest.mark.parametrize(("data", "error"), [
    (prog(0x08000000, b"\xaa" * 64), "below the application start"),
    (prog(0x08006000, b"\xaa" * 2 + bytes(8192) + b"\xaa" * 2), "zero run"),
], ids=["below-app-start", "zero-gap"])
def test_rejects_bootloader_region_and_filled_gaps(data: bytes, error: str):
    with pytest.raises(GblError, match=error):
        check_programs(parse_gbl(make_gbl(prog=data)), 0x08006000)


def test_meta_checks_programs_against_app_start(package: Package, tmp_path: Path):
    toml = package.dir / "package.toml"
    toml.write_text(toml.read_text() + "\n[build]\napp_start = 0x08006000\n")
    path = tmp_path / "bad.gbl"
    path.write_bytes(make_gbl(prog=prog(0x08000000, bytes(25012))))
    with pytest.raises(GblError, match="below"):
        meta(load_package(package.dir), path)
