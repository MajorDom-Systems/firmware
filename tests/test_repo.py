"""The committed catalogue is consistent: board names follow the convention, slots list real packages of one chip."""

import re

import pytest

from tools.board_json import DRIVERS, board_json, has_board_json
from tools.common import is_hidden, load_boards, load_packages, revision, slot_packages

BOARDS = load_boards()
PACKAGES = load_packages()
OWN_BOARD = re.compile(r"majordom/(proto-)?[a-z]+\d+-[a-z0-9]+(-[a-z0-9-]+)?/r\d+")
VENDOR_BOARD = re.compile(r"[a-z0-9]+/[a-z0-9-]+")
SLOT_KEYS = {"label", "pins", "flow_control", "reset", "bootloader", "flashers", "firmware", "default"}


@pytest.mark.parametrize("key", BOARDS)
def test_board_naming_and_slots(key):
    board = BOARDS[key]
    assert OWN_BOARD.fullmatch(key) if key.startswith("majordom/") else VENDOR_BOARD.fullmatch(key)
    if "revisions" in board:
        assert revision(key) in board["revisions"]
    for name, slot in board["slots"].items():
        assert set(slot) <= SLOT_KEYS, "a slot holds host wiring, its firmware list and a display label only"
        assert set(slot.get("pins", {})) <= {"uart", "tx", "rx", "cts", "rts"}, "only host pins belong to a board"
        slot_packages(key, name, slot, PACKAGES)
    if len(board["slots"]) == 1:
        assert not any("label" in slot for slot in board["slots"].values()), "a label tells apart slots of one board"


@pytest.mark.parametrize("package", PACKAGES.values(), ids=lambda p: p.name)
def test_package(package):
    data = package.data
    assert package.name == package.dir.name
    assert not {"board", "slot", "family", "kind", "runtime"} & set(data), "packages never name a board or slot"
    assert data["protocol"] in DRIVERS
    assert re.fullmatch(r"\d+\.\d+\.\d+", package.version)
    assert data["source"]["type"] in {"url", "build"}
    if data["source"]["type"] == "url":
        assert re.fullmatch(r"[0-9a-f]{64}", data["source"]["sha256"]) and data["source"]["size"] > 0
        assert data["source"].get("channel", "stable") in {"stable", "dev"}
    else:
        chip = data["chip"].lower().removeprefix("efr32")
        assert re.fullmatch(r"[a-z0-9]+-[a-z0-9]+(-[a-z0-9-]+)?", package.name), "<chip>-<app>[-<unique part>]"
        assert chip.startswith(package.name.split("-")[0]), "the name starts with the chip (ZGM230S -> zgm230)"
        assert (package.dir.parents[1] / "builder" / package.builder / "Dockerfile").exists()
    assert (package.dir / "CHANGELOG.md").exists()


@pytest.mark.parametrize("key", [k for k, b in BOARDS.items() if has_board_json(b)])
def test_board_json_generates(key):
    doc = board_json(key, BOARDS[key], PACKAGES)
    assert {slot["name"] for slot in doc["slots"]} == set(BOARDS[key]["slots"])


def test_identify_only_boards_list_no_firmware():
    for board in BOARDS.values():
        if board.get("identify_only"):
            assert not any(slot.get("firmware") for slot in board["slots"].values())


def test_package_visibility():
    assert is_hidden("mg26-multipan-pa04-pa05", BOARDS)
    assert not is_hidden("skyconnect-zigbee", BOARDS)
    assert not is_hidden("mg26-multipan-pa04-pa05", {"majordom/hub1-cm4/r1": BOARDS["majordom/proto-hub1-cm4-devkits/r1"]})


def test_shared_usb_ids_are_told_apart_by_product():
    """Boards sharing a VID:PID need distinct product names; known exception: the Aeotec and HomeSeer 0658:0200 sticks have no product string."""
    seen: dict[tuple[str, str], list[tuple[str, tuple[str, ...]]]] = {}
    for key, board in BOARDS.items():
        for rule in board["match"].get("usb", []):
            seen.setdefault((rule["vid"], rule["pid"]), []).append((key, tuple(rule.get("product", []))))
    for ids, owners in seen.items():
        if len(owners) > 1 and ids != ("0658", "0200"):
            products = [product for _, names in owners for product in names]
            assert all(names for _, names in owners), f"{ids} is shared: every rule needs a product"
            assert len(products) == len(set(products)), f"{ids}: duplicate product names"
