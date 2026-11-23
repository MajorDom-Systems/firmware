"""Assemble one package into dist/: the `.gbl`, `.meta.json`, `.cdx.json`.

Only `[source] type = "build"` packages: built by `builder/<name>` (package `[build] builder`) in CI, the output `.gbl`
passed with --file. Mirrors (`type = "url"`) are never re-hosted; the channel lists their upstream URL (tools/mirror.py).
"""

import argparse
import shutil
from pathlib import Path

from tools import meta
from tools.common import Package, load_package


class SourceError(RuntimeError):
    pass


def fetch(package: Package, dest: Path, built_file: Path | None = None) -> Path:
    if package.source["type"] != "build":
        raise SourceError(f"{package.name}: a {package.source['type']} mirror is not built or re-hosted")
    if not built_file:
        raise SourceError(f"{package.name}: pass the builder output with --file (builder/{package.builder})")
    if not built_file.exists():
        raise SourceError(f"{package.name}: built file {built_file} not found")
    shutil.copyfile(built_file, dest)
    return dest


def build(package: Package, out_dir: Path, built_file: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gbl = fetch(package, out_dir / package.asset(".gbl"), built_file)
    return [gbl, *meta.write(package, gbl, out_dir)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    parser.add_argument("--file", type=Path, help="the builder output of a build package")
    args = parser.parse_args()
    for path in build(load_package(args.package_dir), args.out, args.file):
        print(path)


if __name__ == "__main__":
    main()
