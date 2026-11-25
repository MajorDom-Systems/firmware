"""Generate the channel site from GitHub Releases: site/v1/{stable,dev,boards}.json, generated board.json files, index.html, llms.txt.

Channel = the GitHub pre-release flag: every release is in dev.json, only full releases are in stable.json. Drafts are
skipped. A release whose notes carry the front-matter line `yanked: true` is dropped from both channels.
Mirrors (`[source] type = "url"`) have no release: their entry comes from package.toml and points at the upstream URL,
on the channel `[source] channel` names. Downgrades are allowed on the dev channel only (`policy.downgrade`).
Dev-only `proto-` boards stay off boards.json, and the packages only they list go to dev.json only, even as full releases;
index.html carries them hidden behind its "Show dev" toggle with the pre-releases.
"""

import argparse
import hashlib
import html
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tools import board_json
from tools.common import ROOT, Package, is_hidden, is_proto, load_boards, load_packages

SITE_URL = "https://majordom-systems.github.io/firmware"
VALIDITY = timedelta(days=90)
DEV_ROW = ' class="dev"'
YANKED = re.compile(r"(?m)^yanked:\s*true\s*$")


class ManifestError(ValueError):
    pass


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def entry(release: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """One manifest entry: build facts from meta.json, URLs from the release; sizes and hashes must agree."""
    assets = {asset["name"]: asset for asset in release["assets"]}
    files = {}
    for key, suffix in (("gbl", ".gbl"), ("s37_full", "_full.s37"), ("cdx", ".cdx.json")):
        name = f"{meta['package']}_{meta['version']}{suffix}"
        if not (asset := assets.get(name)):
            if key == "gbl":
                raise ManifestError(f"{release['tag_name']}: asset {name} missing")
            continue
        file = {"url": asset["browser_download_url"], "size": asset["size"]}
        if digest := asset.get("digest"):
            file["sha256"] = digest.removeprefix("sha256:")
        if known := meta["files"].get(key):
            if file.setdefault("sha256", known["sha256"]) != known["sha256"] or file["size"] != known["size"]:
                raise ManifestError(f"{release['tag_name']}: {name} differs from its meta.json")
        files[key] = file
    keys = ("chip", "sdk", "stack", "protocol", "serial", "requires", "source")
    return {
        "package": meta["package"],
        "version": meta["version"],
        "stability": "dev" if release["prerelease"] else "stable",
        "released_at": release["published_at"],
        **{key: meta[key] for key in keys if key in meta},
        "files": files,
        "notes_url": release["html_url"],
        "notes": meta.get("summary", ""),
    }


def mirror_entry(package: Package) -> dict[str, Any]:
    """A mirror's entry, straight from package.toml: the upstream URL as is, the upstream version."""
    source, data = package.source, package.data
    url = source["url"]
    keys = ("chip", "sdk", "stack", "protocol", "serial", "requires")
    return {
        "package": package.name,
        "version": package.version,
        "stability": source.get("channel", "stable"),
        **{key: data[key] for key in keys if key in data},
        "source": "url",
        "upstream": source.get("upstream", ""),
        "files": {"gbl": {"url": url, "size": source["size"], "sha256": source["sha256"]}},
        "notes_url": url.replace("/releases/download/", "/releases/tag/").rsplit("/", 1)[0] if "/releases/download/" in url else url,
        "notes": data.get("summary", ""),
    }


def manifests(releases: list[dict], metas: dict[str, dict], packages: dict[str, Package], boards: dict[str, dict],
              boards_sha256: str, now: datetime, hidden: bool = False) -> dict[str, dict]:
    """The channel documents; packages only proto boards list stay off stable unless `hidden` (the index page's view)."""
    channels: dict[str, dict[str, list]] = {"stable": {}, "dev": {}}
    items = []
    for release in releases:
        if release.get("draft") or YANKED.search(release.get("body") or ""):
            continue
        if not (meta := metas.get(release["tag_name"])):
            raise ManifestError(f"{release['tag_name']}: no meta.json")
        items.append(entry(release, meta))
    items += [mirror_entry(p) for p in packages.values() if p.source["type"] == "url"]
    for item in items:
        dev_only = item["stability"] == "dev" or (not hidden and is_hidden(item["package"], boards))
        for channel in ("dev",) if dev_only else ("stable", "dev"):
            channels[channel].setdefault(item["package"], []).append(item)
    out = {}
    for channel, firmware in channels.items():
        for found in firmware.values():
            found.sort(key=lambda i: tuple(int(x) for x in re.findall(r"\d+", i["version"])[:3]), reverse=True)
        out[channel] = {
            "schema": 1,
            "channel": channel,
            "issued_at": iso(now),
            "expires_at": iso(now + VALIDITY),
            "boards_sha256": boards_sha256,
            "policy": {"downgrade": channel == "dev"},
            "firmware": dict(sorted(firmware.items())),
        }
    return out


def render_index(dev: dict, boards: dict, template: str) -> str:
    """Every entry of the unfiltered dev view; those of proto-only packages and pre-releases carry `class="dev"`,
    hidden until the page's "Show dev" toggle is ticked."""
    rows = []
    for package, items in dev["firmware"].items():
        listing = ", ".join(f"{board['name']} ({name})" for board in boards.values()
                            for name, slot in board["slots"].items() if package in slot.get("firmware", []))
        for item in items:
            links = " ".join(f'<a href="{html.escape(f["url"])}">{key}</a>' for key, f in item["files"].items())
            serial = item.get("serial", {})
            dev_only = is_hidden(package, boards) or item["stability"] == "dev"
            rows.append(
                f"<tr{DEV_ROW if dev_only else ''}><td>{html.escape(package)}</td>"
                f"<td>{html.escape(listing)}</td><td>{html.escape(item.get('protocol', ''))}</td>"
                f"<td><a href=\"{html.escape(item['notes_url'])}\">{html.escape(item['version'])}</a></td>"
                f"<td>{item['stability']}</td><td>{serial.get('baud', '')} {serial.get('flow', '')}</td>"
                f"<td>{links}</td><td><code>{item['files']['gbl']['sha256']}</code></td></tr>")
    return template.replace("{{rows}}", "\n".join(rows)).replace("{{issued_at}}", dev["issued_at"])


def render_llms(dev: dict) -> str:
    lines = ["# MajorDom firmware", "",
             "> Signed firmware channel for MajorDom peripherals and supported devices (Silicon Labs EFR32/ZGM230). Files are GitHub Release assets, or pinned upstream URLs for mirrors.", "",
             f"- Manifests: {SITE_URL}/v1/stable.json and {SITE_URL}/v1/dev.json, each with a minisign signature (.minisig)",
             f"- Boards: {SITE_URL}/v1/boards.json", "- Public key: https://github.com/MajorDom-Systems/firmware/blob/develop/keys/minisign.pub",
             "- Flash a .gbl over UART with universal-silabs-flasher or `cpcd -f`; a _full.s37 over SWD with `commander flash`.", "",
             "## Builds (dev channel)"]
    lines += [f"- {item['package']} {item['version']} ({item['stability']}): {item['files']['gbl']['url']}"
              for items in dev["firmware"].values() for item in items]
    return "\n".join(lines) + "\n"


def generate(releases: list[dict], metas: dict[str, dict], out: Path, now: datetime, root: Path = ROOT):
    every_board = load_boards(root / "boards")
    boards = {key: board for key, board in every_board.items() if not is_proto(key)}
    packages = load_packages(root / "packages")
    v1 = out / "v1"
    v1.mkdir(parents=True, exist_ok=True)
    boards_json = json.dumps({"schema": 1, "boards": boards}, indent=2, sort_keys=True) + "\n"
    (v1 / "boards.json").write_text(boards_json)
    for key, board in boards.items():
        if board_json.has_board_json(board):
            dest = v1 / key / "board.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(board_json.dumps(board_json.board_json(key, board, packages)))
    boards_sha256 = hashlib.sha256(boards_json.encode()).hexdigest()
    channels = manifests(releases, metas, packages, every_board, boards_sha256, now)
    for channel, doc in channels.items():
        (v1 / f"{channel}.json").write_text(json.dumps(doc, indent=2) + "\n")
    template = (root / "site" / "index.template.html").read_text()
    everything = manifests(releases, metas, packages, every_board, boards_sha256, now, hidden=True)["dev"]
    (out / "index.html").write_text(render_index(everything, every_board, template))
    (out / "llms.txt").write_text(render_llms(channels["dev"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--releases", type=Path, required=True, help="JSON list from `gh api repos/:repo/releases`")
    parser.add_argument("--metas", type=Path, required=True, help="dir of downloaded *.meta.json, one per release")
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args()

    metas = {}
    for path in args.metas.glob("*.meta.json"):
        meta = json.loads(path.read_text())
        metas[f"{meta['package']}-v{meta['version']}"] = meta
    generate(json.loads(args.releases.read_text()), metas, args.out, datetime.now(UTC))


if __name__ == "__main__":
    main()
