"""Assemble one package into dist/: the verified `.gbl` (plus `_full.s37` for source builds), `.meta.json`, `.cdx.json`.

Source types in package.toml `[source]`:
  * staged - a local build file given with --file, verified by sha256 (phase 1; GitHub runners have no copy, use publish_local);
  * url    - a mirrored third-party build, downloaded and verified by sha256;
  * build  - built from build.yaml inside the builder image (phase 2, not implemented yet).
"""

import argparse
import shutil
import urllib.request
from pathlib import Path

from tools import meta
from tools.common import Package, load_package, sha256


class SourceError(RuntimeError):
    pass


def fetch(package: Package, dest: Path, staged_file: Path | None = None) -> Path:
    source = package.source
    match source["type"]:
        case "staged":
            if not staged_file:
                raise SourceError(f"{package.name}: a staged package needs its build file, pass --file")
            if not staged_file.exists():
                raise SourceError(f"{package.name}: staged file {staged_file} not found")
            shutil.copyfile(staged_file, dest)
        case "url":
            with urllib.request.urlopen(source["url"], timeout=60) as response, dest.open("wb") as f:
                shutil.copyfileobj(response, f)
        case "build":
            raise SourceError(f"{package.name}: source builds need the builder image (phase 2)")
        case other:
            raise SourceError(f"{package.name}: unknown source type {other!r}")
    if (digest := sha256(dest)) != source["sha256"]:
        dest.unlink()
        raise SourceError(f"{package.name}: sha256 {digest} does not match package.toml {source['sha256']}")
    return dest


def build(package: Package, out_dir: Path, staged_file: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gbl = fetch(package, out_dir / package.asset(".gbl"), staged_file)
    return [gbl, *meta.write(package, gbl, out_dir)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    parser.add_argument("--file", type=Path, help="the build file of a staged package")
    args = parser.parse_args()
    for path in build(load_package(args.package_dir), args.out, args.file):
        print(path)


if __name__ == "__main__":
    main()
