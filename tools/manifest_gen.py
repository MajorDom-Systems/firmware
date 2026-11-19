"""Generate the channel site from GitHub Releases: site/v1/{stable,dev,targets}.json, board.json copies, index.html, llms.txt.

Channel = the GitHub pre-release flag: every release is in dev.json, only full releases are in stable.json. Drafts are
skipped. A release whose notes carry the front-matter line `yanked: true` is dropped from both channels.
Downgrades are allowed on the dev channel only (`policy.downgrade`).
"""

import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tools.common import ROOT, load_targets

SITE_URL = "https://firmware.majordom.io"
VALIDITY = timedelta(days=90)
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
    keys = ("sdk", "stack", "protocol", "serial", "requires", "source", "target", "slot")
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


def manifests(releases: list[dict], metas: dict[str, dict], targets_sha256: str, now: datetime) -> dict[str, dict]:
    channels = {"stable": {}, "dev": {}}
    for release in releases:
        if release.get("draft") or YANKED.search(release.get("body") or ""):
            continue
        if not (meta := metas.get(release["tag_name"])):
            raise ManifestError(f"{release['tag_name']}: no meta.json")
        item = entry(release, meta)
        for channel in ("dev",) if release["prerelease"] else ("stable", "dev"):
            channels[channel].setdefault(meta["family"], {}).setdefault(meta["kind"], []).append(item)
    out = {}
    for channel, firmware in channels.items():
        for kinds in firmware.values():
            for items in kinds.values():
                items.sort(key=lambda i: tuple(int(x) for x in re.findall(r"\d+", i["version"])[:3]), reverse=True)
        out[channel] = {
            "schema": 1,
            "channel": channel,
            "issued_at": iso(now),
            "expires_at": iso(now + VALIDITY),
            "targets_sha256": targets_sha256,
            "policy": {"downgrade": channel == "dev"},
            "firmware": dict(sorted(firmware.items())),
        }
    return out


def render_index(dev: dict, targets: dict, template: str) -> str:
    families = {slot["firmware"]: f"{target['name']} ({slot_name})"
                for target in targets.values() for slot_name, slot in target.get("slots", {}).items() if "firmware" in slot}
    rows = []
    for family, kinds in dev["firmware"].items():
        for kind, items in kinds.items():
            for item in items:
                links = " ".join(f'<a href="{html.escape(f["url"])}">{key}</a>' for key, f in item["files"].items())
                serial = item.get("serial", {})
                rows.append(
                    f"<tr><td>{html.escape(families.get(family, family))}</td><td>{html.escape(kind)}</td>"
                    f"<td><a href=\"{html.escape(item['notes_url'])}\">{html.escape(item['version'])}</a></td>"
                    f"<td>{item['stability']}</td><td>{serial.get('baud', '')} {serial.get('flow', '')}</td>"
                    f"<td>{links}</td><td><code>{item['files']['gbl']['sha256']}</code></td></tr>")
    return template.replace("{{rows}}", "\n".join(rows) or '<tr><td colspan="7">No releases yet.</td></tr>') \
                   .replace("{{issued_at}}", dev["issued_at"])


def render_llms(dev: dict) -> str:
    lines = ["# MajorDom radio firmware", "",
             "> Signed firmware channel for MajorDom radios (Silicon Labs EFR32/ZGM230). Files are GitHub Release assets.", "",
             f"- Manifests: {SITE_URL}/v1/stable.json and {SITE_URL}/v1/dev.json, each with a minisign signature (.minisig)",
             f"- Targets: {SITE_URL}/v1/targets.json", "- Public key: https://github.com/MajorDom-Systems/firmware/blob/develop/keys/minisign.pub",
             "- Flash a .gbl over UART with universal-silabs-flasher or `cpcd -f`; a _full.s37 over SWD with `commander flash`.", "",
             "## Builds (dev channel)"]
    lines += [f"- {item['package']} {item['version']} ({item['stability']}): {item['files']['gbl']['url']}"
              for kinds in dev["firmware"].values() for items in kinds.values() for item in items]
    return "\n".join(lines) + "\n"


def generate(releases: list[dict], metas: dict[str, dict], out: Path, now: datetime, root: Path = ROOT):
    targets = load_targets(root / "targets")
    v1 = out / "v1"
    v1.mkdir(parents=True, exist_ok=True)
    targets_json = json.dumps({"schema": 1, "targets": targets}, indent=2, sort_keys=True) + "\n"
    (v1 / "targets.json").write_text(targets_json)
    for target in targets.values():
        if board := target.get("board_json"):
            dest = v1 / board.removeprefix("targets/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / board, dest)
    channels = manifests(releases, metas, hashlib.sha256(targets_json.encode()).hexdigest(), now)
    for channel, doc in channels.items():
        (v1 / f"{channel}.json").write_text(json.dumps(doc, indent=2) + "\n")
    template = (root / "site" / "index.template.html").read_text()
    (out / "index.html").write_text(render_index(channels["dev"], targets, template))
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
