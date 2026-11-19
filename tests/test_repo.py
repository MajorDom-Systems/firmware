"""The committed catalogue is consistent: every package points at a real target slot, every board.json at its slots."""

import json
import re

import pytest

from tools.common import ROOT, load_packages, load_targets

TARGETS = load_targets()
PACKAGES = load_packages()


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
def test_package_matches_its_target(package):
    data = package.data
    slot = TARGETS[data["target"]]["slots"][data["slot"]]
    assert slot["firmware"] == data["family"]
    assert package.name == f"{data['family']}-{data['kind']}" == package.dir.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", package.version)
    assert data["kind"] in {"zigbee", "thread", "multipan", "zwave", "bootloader"}
    if data["source"]["type"] != "build":
        assert re.fullmatch(r"[0-9a-f]{64}", data["source"]["sha256"])
    assert (package.dir / "CHANGELOG.md").exists()


@pytest.mark.parametrize("key", [k for k, t in TARGETS.items() if "board_json" in t])
def test_board_json_names_target_slots(key):
    board = json.loads((ROOT / TARGETS[key]["board_json"]).read_text())
    assert board["board"] == TARGETS[key]["id"] == key.split("/")[1]
    assert {radio["name"] for radio in board["radios"]} == set(TARGETS[key]["slots"])


def test_identify_only_targets_have_no_firmware():
    for target in TARGETS.values():
        if target.get("identify_only"):
            assert not any("firmware" in slot for slot in target["slots"].values())
