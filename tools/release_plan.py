"""Decide which packages to release, and optionally patch-bump them (per-package release plan, on package.toml).

A package is included when any of:
  * changed     - a file under its dir, or under its `builder/<name>`, changed since --base (CHANGELOG and docs excluded);
  * unreleased  - its package.toml version has no `<name>-v<version>` tag yet (first release or manual bump);
  * dispatched  - named in --dispatch (or --dispatch=all).
An already-released version is patch-bumped before the build; a manual bump is used as-is, never bumped twice.
Mirrors (`[source] type = "url"`) are never planned: they keep the upstream version and are listed from package.toml.

Prints the matrix as JSON and writes `matrix`/`any` to $GITHUB_OUTPUT when set. --apply-bumps rewrites the versions,
so one commit carries every bump before the parallel matrix runs.
"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from tools.common import ROOT, Package, load_package

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SRC_EXCLUDE = ("CHANGELOG", "README", "docs/")


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=cwd).stdout.strip()


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-+]", version)[:3])


def latest_tag(name: str, cwd: Path = ROOT) -> tuple[str | None, str | None]:
    tags = [t for t in git("tag", "-l", f"{name}-v*", cwd=cwd).splitlines() if t]
    if not tags:
        return None, None
    top = max(tags, key=lambda t: version_key(t.rsplit("-v", 1)[-1]))
    return top, top.rsplit("-v", 1)[-1]


def changed(package: Package, base: str, cwd: Path = ROOT) -> bool:
    dirs = [package.dir.relative_to(cwd).as_posix()] + ([f"builder/{package.builder}"] if package.builder else [])
    for rel_dir in dirs:
        for line in git("diff", "--name-only", f"{base}..HEAD", "--", rel_dir, cwd=cwd).splitlines():
            if line and not any(x in line[len(rel_dir) + 1:] for x in SRC_EXCLUDE):
                return True
    return False


def bump_patch(version: str) -> str:
    if not (m := re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", version)):
        raise ValueError(f"cannot patch-bump non-semver version {version!r}")
    return f"{m[1]}.{m[2]}.{int(m[3]) + 1}{m[4]}"


def apply_version(package_toml: Path, new: str):
    text = re.sub(r'(?m)^(version\s*=\s*")[^"]*(")', rf"\g<1>{new}\g<2>", package_toml.read_text(), count=1)
    package_toml.write_text(text)


def plan(packages_dir: Path, base: str, dispatch: set[str], apply_bumps: bool, cwd: Path = ROOT) -> list[dict]:
    matrix = []
    for package_toml in sorted(packages_dir.glob("*/package.toml")):
        package = load_package(package_toml.parent)
        if package.source["type"] != "build":
            continue
        tag, tag_version = latest_tag(package.name, cwd)
        selected = "all" in dispatch or package.name in dispatch
        if dispatch and not selected:
            continue
        if not (selected or tag_version != package.version or changed(package, base, cwd)):
            continue
        version, bumped = package.version, tag_version == package.version
        if bumped:
            version = bump_patch(version)
            if apply_bumps:
                apply_version(package_toml, version)
        matrix.append({
            "package": package.name,
            "dir": package.dir.relative_to(cwd).as_posix(),
            "version": version,
            "tag": f"{package.name}-v{version}",
            "prev_tag": tag or "",
            "bumped": bumped,
            "source": package.source["type"],
            "builder": package.builder or "",
            "sdk": package.data.get("sdk", {}).get("version", ""),
        })
    return matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages-dir", type=Path, default=ROOT / "packages")
    parser.add_argument("--base", default="", help="commit to diff against ('' = first run)")
    parser.add_argument("--dispatch", default="", help="'all', or comma-separated package names")
    parser.add_argument("--apply-bumps", action="store_true")
    args = parser.parse_args()

    dispatch = {s.strip() for s in args.dispatch.split(",") if s.strip()}
    out = {"include": plan(args.packages_dir.resolve(), args.base or EMPTY_TREE, dispatch, args.apply_bumps)}
    print(json.dumps(out, indent=2))
    if gh_out := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_out, "a") as f:
            f.write(f"matrix={json.dumps(out)}\nany={'true' if out['include'] else 'false'}\n")


if __name__ == "__main__":
    main()
