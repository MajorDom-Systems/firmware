from pathlib import Path

import pytest

from tools.build import SourceError, build
from tools.common import Package, load_package, sha256


def with_source(package: Package, source: str) -> Package:
    (package.dir / "package.toml").write_text((package.dir / "package.toml").read_text() + f"\n[source]\n{source}\n")
    return load_package(package.dir)


def test_staged_source_is_verified_and_assembled(package: Package, gbl_file: Path, tmp_path: Path):
    package = with_source(package, f'type = "staged"\nsha256 = "{sha256(gbl_file)}"')
    paths = build(package, tmp_path / "dist", gbl_file)
    assert [p.name for p in paths] == [
        "demo-mg26-multipan_1.0.0.gbl", "demo-mg26-multipan_1.0.0.meta.json", "demo-mg26-multipan_1.0.0.cdx.json"]
    assert sha256(paths[0]) == sha256(gbl_file)


def test_sha_mismatch_fails_and_leaves_nothing(package: Package, gbl_file: Path, tmp_path: Path):
    package = with_source(package, f'type = "staged"\nsha256 = "{"0" * 64}"')
    with pytest.raises(SourceError, match="does not match"):
        build(package, tmp_path / "dist", gbl_file)
    assert not any((tmp_path / "dist").iterdir())


def test_missing_staged_file_fails_clearly(package: Package, tmp_path: Path):
    package = with_source(package, f'type = "staged"\nsha256 = "{"0" * 64}"')
    with pytest.raises(SourceError, match="not found"):
        build(package, tmp_path / "dist", tmp_path / "nope.gbl")


def test_staged_source_needs_its_file(package: Package, tmp_path: Path):
    package = with_source(package, f'type = "staged"\nsha256 = "{"0" * 64}"')
    with pytest.raises(SourceError, match="pass --file"):
        build(package, tmp_path / "dist")


def test_source_builds_are_phase_two(package: Package, tmp_path: Path):
    with pytest.raises(SourceError, match="builder image"):
        build(package, tmp_path / "dist")
