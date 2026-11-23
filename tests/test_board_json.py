from pathlib import Path

import pytest

from tests.conftest import PACKAGE_TOML
from tools.board_json import BoardError, board_json, dumps
from tools.common import SlotError, load_boards, load_package, load_packages

KEY = "majordom/proto-hub1-cm4-devkits/r1"
FIXTURE = Path(__file__).parent / "fixtures/proto-hub1-cm4-devkits-r1.board.json"


def board(**mg26) -> dict:
    board = load_boards()[KEY]
    return board | {"slots": board["slots"] | {"mg26": board["slots"]["mg26"] | mg26}}


def test_matches_the_former_hand_written_file_with_slots():
    assert dumps(board_json(KEY, load_boards()[KEY], load_packages())) == FIXTURE.read_text()


def test_driver_and_firmware_come_from_the_default_packages_protocol(tmp_path: Path):
    pkg_dir = tmp_path / "demo"
    pkg_dir.mkdir()
    (pkg_dir / "package.toml").write_text(PACKAGE_TOML.replace('"silabs-cpc"', '"spinel"'))
    demo = load_package(pkg_dir)
    doc = board_json(KEY, board(firmware=[demo.name], default=demo.name), load_packages() | {demo.name: demo})
    assert (doc["slots"][0]["driver"], doc["slots"][0]["firmware"]) == ("silabs", "thread-rcp")


def test_without_default_the_driver_identifies_the_firmware():
    mg26 = {k: v for k, v in load_boards()[KEY]["slots"]["mg26"].items() if k != "default"}
    doc = board_json(KEY, load_boards()[KEY] | {"slots": {"mg26": mg26}}, load_packages())
    assert doc["slots"] == [{"name": "mg26", "path": "/dev/ttyAMA3", "driver": "silabs",
                             "params": {"reset_gpio": "gpiochip0:23"}}]


def test_firmware_flow_control_needs_board_wiring(tmp_path: Path):
    pkg_dir = tmp_path / "demo"
    pkg_dir.mkdir()
    (pkg_dir / "package.toml").write_text(PACKAGE_TOML.replace('flow = "none"', 'flow = "rtscts"'))
    demo = load_package(pkg_dir)
    with pytest.raises(BoardError, match="flow control"):
        board_json(KEY, board(firmware=[demo.name], default=demo.name), {demo.name: demo})


@pytest.mark.parametrize(("mg26", "error"), [
    ({"firmware": ["nope"], "default": "nope"}, "no such package"),
    ({"firmware": ["mg26-multipan-pa04-pa05", "skyconnect-zigbee"]}, "different chips"),
    ({"default": "skyconnect-zigbee"}, "not in its firmware list"),
])
def test_slot_firmware_lists_are_checked(mg26: dict, error: str):
    with pytest.raises(SlotError, match=error):
        board_json(KEY, board(**mg26), load_packages())


def test_slot_without_firmware_fails():
    with pytest.raises(BoardError, match="no firmware"):
        board_json(KEY, load_boards()[KEY] | {"slots": {"zwave": {"pins": {"uart": "/dev/ttyAMA4"}}}}, {})
