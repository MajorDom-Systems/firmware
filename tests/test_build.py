from pathlib import Path

import pytest

from tools.build import SourceError, build
from tools.common import Package, load_package, sha256


def with_source(package: Package, source: str) -> Package:
    (package.dir / "package.toml").write_text((package.dir / "package.toml").read_text() + f"\n[source]\n{source}\n")
    return load_package(package.dir)


def test_mirrors_are_not_rehosted(package: Package, gbl_file: Path, tmp_path: Path):
    package = with_source(package, f'type = "url"\nurl = "{gbl_file.as_uri()}"\nsha256 = "{sha256(gbl_file)}"')
    with pytest.raises(SourceError, match="not built or re-hosted"):
        build(package, tmp_path / "dist")


def test_build_source_takes_the_builder_output(package: Package, gbl_file: Path, tmp_path: Path):
    paths = build(package, tmp_path / "dist", gbl_file)
    assert sha256(paths[0]) == sha256(gbl_file)


def test_build_source_needs_the_builder_output(package: Package, tmp_path: Path):
    with pytest.raises(SourceError, match="pass the builder output"):
        build(package, tmp_path / "dist")
    with pytest.raises(SourceError, match="not found"):
        build(package, tmp_path / "dist", tmp_path / "nope.gbl")
