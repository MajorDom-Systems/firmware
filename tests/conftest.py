import struct
import zlib
from pathlib import Path

import pytest

from tools.common import Package, load_package
from tools.meta import TAG_APPLICATION, TAG_END, TAG_HEADER, TAG_METADATA

PACKAGE_TOML = """\
name = "demo-mg26-multipan"
version = "1.0.0"
chip = "EFR32MG26"
protocol = "silabs-cpc"
summary = "Demo build."

[sdk]
name = "sisdk"
version = "2025.6.3"

[stack]
openthread = "2.7.3"

[serial]
baud = 115200
flow = "none"
"""


def tag(tag_id: int, body: bytes) -> bytes:
    return struct.pack("<II", tag_id, len(body)) + body


def make_gbl(app_type: int = 0b10, metadata: bytes | None = None, prog: bytes = b"\x00" * 4 + b"\xaa" * 28) -> bytes:
    data = tag(TAG_HEADER, struct.pack("<II", 0x03000000, 0))
    data += tag(TAG_APPLICATION, struct.pack("<III", app_type, 1, 0) + bytes(16))
    if metadata is not None:
        data += tag(TAG_METADATA, metadata)
    data += tag(0xFD0303FD, prog)
    data += struct.pack("<II", TAG_END, 4)
    return data + struct.pack("<I", zlib.crc32(data))


@pytest.fixture
def gbl_file(tmp_path: Path) -> Path:
    path = tmp_path / "app.gbl"
    path.write_bytes(make_gbl())
    return path


@pytest.fixture
def package(tmp_path: Path) -> Package:
    pkg_dir = tmp_path / "packages" / "demo-mg26-multipan"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "package.toml").write_text(PACKAGE_TOML)
    return load_package(pkg_dir)
