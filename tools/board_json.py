"""Generate a host-wired board's runtime `board.json` (installed by the OS image at /etc/majordom/board.json).

Hardware facts come from the board's slots (host pins, flow-control wiring, reset GPIO); firmware facts (baud, flow) from
the slot's `default` package. `driver` and `firmware` are the SDK's names for what the host runs against the default package's `protocol` (`DRIVERS`): the Hub
hands them to the SDK's `FixedRadio` as they are. Boards without host pins (USB sticks) have no board.json.
"""

import argparse
import json
from typing import Any

from tools.common import Package, board_id, load_boards, load_packages, revision, slot_packages

#: Package `protocol` → the SDK driver serving it and that driver's firmware name (its `Endpoint` of that protocol).
DRIVERS = {
    "ezsp": ("silabs", "zigbee-ncp"),
    "spinel": ("silabs", "thread-rcp"),
    "silabs-cpc": ("silabs", "multipan-rcp"),
    "zwave-serial-api": ("zwave", "zwave-serial-api"),
}


class BoardError(ValueError):
    pass


def has_board_json(board: dict[str, Any]) -> bool:
    return any("pins" in slot for slot in board["slots"].values())


def slot_entry(key: str, name: str, slot: dict[str, Any], packages: dict[str, Package]) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "path": slot["pins"]["uart"]}
    listed = slot_packages(key, name, slot, packages)
    if default := slot.get("default"):
        package = packages[default]
        serial, flow = package.data["serial"], package.data["serial"]["flow"] != "none"
        if flow and not slot.get("flow_control"):
            raise BoardError(f"{key}/{name}: {package.name} needs flow control the board does not wire")
        driver, firmware = DRIVERS[package.data["protocol"]]
        entry |= {"driver": driver, "firmware": firmware}
        params = {"baud": serial["baud"], "flow_control": flow}
    elif listed:  # nothing pre-flashed: the driver identifies what runs
        entry["driver"], params = DRIVERS[listed[0].data["protocol"]][0], {}
    else:
        raise BoardError(f"{key}/{name}: no firmware")
    if reset := slot.get("reset"):
        params["reset_gpio"] = reset["gpio"]
    return entry | {"params": params}


def board_json(key: str, board: dict[str, Any], packages: dict[str, Package]) -> dict[str, Any]:
    slots = [slot_entry(key, name, slot, packages) for name, slot in board["slots"].items() if "pins" in slot]
    return {"schema": 1, "board": board_id(key), "revision": revision(key), "slots": slots}


def dumps(doc: dict[str, Any]) -> str:
    """One slot per line, like the hand-written files."""
    slots = ",\n".join(f"    {json.dumps(s)}" for s in doc["slots"])
    head = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in doc.items() if k != "slots")
    return f'{{\n{head},\n  "slots": [\n{slots}\n  ]\n}}\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board", help="board key, e.g. majordom/proto-hub1-cm4-devkits/r1")
    args = parser.parse_args()
    boards = load_boards()
    if args.board not in boards or not has_board_json(boards[args.board]):
        raise SystemExit(f"{args.board}: no such host-wired board")
    print(dumps(board_json(args.board, boards[args.board], load_packages())), end="")


if __name__ == "__main__":
    main()
