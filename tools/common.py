"""Shared loaders for boards and packages. Stdlib only, so workflows run the tools without installing anything."""

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

    @property
    def builder(self) -> str | None:
        return self.data.get("build", {}).get("builder")

    def asset(self, suffix: str) -> str:
        return f"{self.name}_{self.version}{suffix}"


def load_package(pkg_dir: Path) -> Package:
    return Package(pkg_dir, tomllib.loads((pkg_dir / "package.toml").read_text()))


def load_packages(packages_dir: Path = ROOT / "packages") -> dict[str, Package]:
    """Package name → package."""
    packages = (load_package(p.parent) for p in sorted(packages_dir.glob("*/package.toml")))
    return {package.name: package for package in packages}


def load_boards(boards_dir: Path = ROOT / "boards") -> dict[str, dict[str, Any]]:
    """`<vendor>/<board>[/r<N>]` → board.toml."""
    return {toml.parent.relative_to(boards_dir).as_posix(): tomllib.loads(toml.read_text())
            for toml in sorted(boards_dir.glob("**/board.toml"))}


def board_id(key: str) -> str:
    return key.split("/")[1]


def revision(key: str) -> int | None:
    parts = key.split("/")
    return int(parts[2].removeprefix("r")) if len(parts) == 3 else None


def is_proto(board_key: str) -> bool:
    """Dev-only boards (`proto-` prefix) stay off the public channel."""
    return board_id(board_key).startswith("proto-")


class SlotError(ValueError):
    pass


def slot_packages(key: str, name: str, slot: dict[str, Any], packages: dict[str, Package]) -> list[Package]:
    """The packages a slot lists, checked: each exists, all target one chip, `default` is one of them."""
    listed = slot.get("firmware", [])
    if missing := [p for p in listed if p not in packages]:
        raise SlotError(f"{key}/{name}: no such package {missing}")
    if len({packages[p].data["chip"] for p in listed}) > 1:
        raise SlotError(f"{key}/{name}: the listed packages target different chips")
    if "default" in slot and slot["default"] not in listed:
        raise SlotError(f"{key}/{name}: default {slot['default']!r} is not in its firmware list")
    return [packages[p] for p in listed]


def is_hidden(package: str, boards: dict[str, dict[str, Any]]) -> bool:
    """A package is public unless every board listing it is a dev-only `proto-` one."""
    listing = [key for key, board in boards.items()
               if any(package in slot.get("firmware", []) for slot in board["slots"].values())]
    return bool(listing) and all(map(is_proto, listing))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()
