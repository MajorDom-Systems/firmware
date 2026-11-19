"""Shared loaders for targets and packages. Stdlib only, so workflows run the tools without installing anything."""

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPO = "MajorDom-Systems/firmware"


@dataclass(frozen=True)
class Package:
    dir: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def tag(self) -> str:
        return f"{self.name}-v{self.version}"

    @property
    def source(self) -> dict[str, Any]:
        return self.data.get("source", {"type": "build"})

    def asset(self, suffix: str) -> str:
        return f"{self.name}_{self.version}{suffix}"


def load_package(pkg_dir: Path) -> Package:
    return Package(pkg_dir, tomllib.loads((pkg_dir / "package.toml").read_text()))


def load_packages(packages_dir: Path = ROOT / "packages") -> list[Package]:
    return [load_package(p.parent) for p in sorted(packages_dir.glob("*/package.toml"))]


def load_targets(targets_dir: Path = ROOT / "targets") -> dict[str, dict[str, Any]]:
    """`<vendor>/<target>` → target.toml, plus its board.json when the target is host-wired."""
    targets = {}
    for toml in sorted(targets_dir.glob("*/*/target.toml")):
        key = f"{toml.parent.parent.name}/{toml.parent.name}"
        target = tomllib.loads(toml.read_text())
        if (toml.parent / "board.json").exists():
            target["board_json"] = f"targets/{key}/board.json"
        targets[key] = target
    return targets


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()
