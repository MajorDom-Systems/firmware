"""Phase 1: release a staged package from a lab node (where the NAS is mounted) with the gh CLI.

Creates the `<name>-v<version>` tag on the current origin/develop commit as a pre-release (dev channel only).
Promotion to stable stays a manual `gh release edit <tag> --prerelease=false` after the cage test.
"""

import argparse
import subprocess
from pathlib import Path

from tools.build import build
from tools.common import REPO, load_package


def notes(package_dir: Path, version: str) -> str:
    changelog = (package_dir / "CHANGELOG.md").read_text() if (package_dir / "CHANGELOG.md").exists() else ""
    section = changelog.split(f"## {version}", 1)[-1].split("\n## ", 1)[0] if f"## {version}" in changelog else ""
    return section.strip() or f"{package_dir.name} {version}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--file", type=Path, help="override the staged file path")
    parser.add_argument("--target", default="develop", help="branch or commit to tag")
    parser.add_argument("--draft", action="store_true", help="create a draft release (not in any channel)")
    parser.add_argument("--dry-run", action="store_true", help="assemble dist/ and print the gh command only")
    args = parser.parse_args()

    package = load_package(args.package_dir)
    files = build(package, Path("dist"), args.file)
    command = ["gh", "release", "create", package.tag, "--repo", REPO, "--prerelease", "--target", args.target,
               "--title", f"{package.name} {package.version}", "--notes", notes(package.dir, package.version),
               *(["--draft"] if args.draft else []), *map(str, files)]
    print(" ".join(command))
    if not args.dry_run:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
