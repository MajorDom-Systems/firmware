import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.common import ROOT, load_boards, load_packages
from tools.manifest_gen import ManifestError, generate
from tools.manifest_gen import manifests as make

NOW = datetime(2026, 11, 19, tzinfo=UTC)
SHA = "a" * 64


PACKAGE = "mg21-multipan"


def meta(version: str, package: str = PACKAGE) -> dict:
    return {"package": package, "version": version, "chip": "EFR32MG21", "protocol": "silabs-cpc", "summary": "s",
            "serial": {"baud": 115200, "flow": "none"}, "source": "build",
            "files": {"gbl": {"name": f"{package}_{version}.gbl", "sha256": SHA, "size": 10}}}


def release(version: str, prerelease: bool = False, digest: str | None = SHA, package: str = PACKAGE,
            **extra) -> dict:
    name = f"{package}_{version}.gbl"
    asset = {"name": name, "size": 10, "browser_download_url": f"https://example/{name}"}
    if digest:
        asset["digest"] = f"sha256:{digest}"
    return {"tag_name": f"{package}-v{version}", "prerelease": prerelease, "draft": False,
            "published_at": "2026-11-19T00:00:00Z", "html_url": "https://example/tag", "body": "",
            "assets": [asset], **extra}


def metas(*versions: str) -> dict[str, dict]:
    return {f"{PACKAGE}-v{v}": meta(v) for v in versions}


def versions(doc: dict, package: str = PACKAGE) -> list[str]:
    return [i["version"] for i in doc["firmware"].get(package, [])]


def manifests(releases: list[dict], metas: dict, packages: dict | None = None, boards: dict | None = None, **kw) -> dict:
    return make(releases, metas, packages or {}, boards or {}, "t", NOW, **kw)


def test_prerelease_only_in_dev_sorted_newest_first():
    out = manifests([release("1.0.0"), release("1.1.0", prerelease=True), release("1.0.10")], metas("1.0.0", "1.1.0", "1.0.10"))
    assert versions(out["stable"]) == ["1.0.10", "1.0.0"]
    assert versions(out["dev"]) == ["1.1.0", "1.0.10", "1.0.0"]
    assert out["dev"]["firmware"][PACKAGE][0]["stability"] == "dev"


def test_downgrade_policy_dev_only():
    out = manifests([], {})
    assert out["stable"]["policy"] == {"downgrade": False}
    assert out["dev"]["policy"] == {"downgrade": True}
    assert (out["dev"]["issued_at"], out["dev"]["expires_at"]) == ("2026-11-19T00:00:00Z", "2027-02-17T00:00:00Z")


def test_drafts_and_yanked_are_dropped():
    releases = [release("1.0.0", draft=True), release("1.0.1", body="---\nyanked: true\n---\nbad build")]
    out = manifests(releases, metas("1.0.0", "1.0.1"))
    assert versions(out["dev"]) == []


def test_asset_digest_must_match_meta():
    with pytest.raises(ManifestError, match="differs"):
        manifests([release("1.0.0", digest="b" * 64)], metas("1.0.0"))


def test_meta_sha_used_when_api_has_no_digest():
    out = manifests([release("1.0.0", digest=None)], metas("1.0.0"))
    assert out["stable"]["firmware"][PACKAGE][0]["files"]["gbl"]["sha256"] == SHA


def test_missing_gbl_or_meta_fails():
    with pytest.raises(ManifestError, match="missing"):
        manifests([release("1.0.0") | {"assets": []}], metas("1.0.0"))
    with pytest.raises(ManifestError, match="no meta.json"):
        manifests([release("1.0.0")], {})


def test_packages_only_proto_boards_list_stay_off_the_channel():
    rel = release("1.0.0", package="mg26-multipan-pa04-pa05")
    found = {rel["tag_name"]: meta("1.0.0", "mg26-multipan-pa04-pa05")}
    out = manifests([rel], found, boards=load_boards())
    assert out["stable"]["firmware"] == out["dev"]["firmware"] == {}
    hidden = manifests([rel], found, boards=load_boards(), hidden=True)
    assert versions(hidden["stable"], "mg26-multipan-pa04-pa05") == ["1.0.0"]


def test_mirrors_come_from_package_toml_with_the_upstream_url_and_version():
    out = manifests([], {}, load_packages(), load_boards())
    assert out["stable"]["firmware"] == {}
    zigbee = out["dev"]["firmware"]["skyconnect-zigbee"][0]
    assert (zigbee["version"], zigbee["stability"], zigbee["protocol"]) == ("7.5.1", "dev", "ezsp")
    assert zigbee["files"]["gbl"] == {
        "url": "https://github.com/NabuCasa/silabs-firmware-builder/releases/download/v2026.02.23/skyconnect_zigbee_ncp_7.5.1.0.gbl",
        "size": 241512,
        "sha256": "5b9221fc1decb687cfe822de119443db06728a53a7ce465c7a14ef73c8e146ad",
    }
    assert zigbee["notes_url"] == "https://github.com/NabuCasa/silabs-firmware-builder/releases/tag/v2026.02.23"
    assert versions(out["dev"], "skyconnect-thread") == ["2.7.2"]


def test_generate_writes_site(tmp_path: Path):
    generate([release("1.0.0", prerelease=True)], metas("1.0.0"), tmp_path, NOW, root=ROOT)
    dev = json.loads((tmp_path / "v1/dev.json").read_text())
    boards = json.loads((tmp_path / "v1/boards.json").read_text())["boards"]
    assert versions(dev) == ["1.0.0"] and "skyconnect-zigbee" in dev["firmware"]
    assert "mg26-multipan-pa04-pa05" not in dev["firmware"]
    assert dev["boards_sha256"] and json.loads((tmp_path / "v1/stable.json").read_text())["firmware"] == {}
    assert boards["nabucasa/skyconnect"]["slots"]["radio"]["firmware"] == ["skyconnect-zigbee", "skyconnect-thread"]
    assert not any("proto-" in key for key in boards)
    assert not list((tmp_path / "v1").glob("**/board.json"))
    assert sorted(p.name for p in (tmp_path / "v1").iterdir()) == ["boards.json", "dev.json", "stable.json"]
    index = (tmp_path / "index.html").read_text()
    assert "Home Assistant SkyConnect / Connect ZBT-1 (radio)" in index and "{{" not in index
    assert 'href="v1/dev.json"' in index
    llms = (tmp_path / "llms.txt").read_text()
    assert f"{PACKAGE} 1.0.0 (dev)" in llms and "mg26-multipan-pa04-pa05" not in llms
    assert "https://majordom-systems.github.io/firmware/v1/stable.json" in llms and "majordom.io" not in llms


def test_index_hides_dev_entries_behind_the_show_dev_toggle(tmp_path: Path):
    rel = release("1.0.0", package="mg26-multipan-pa04-pa05")
    found = {rel["tag_name"]: meta("1.0.0", "mg26-multipan-pa04-pa05"), **metas("2.0.0")}
    generate([rel, release("2.0.0")], found, tmp_path, NOW, root=ROOT)
    index = (tmp_path / "index.html").read_text()
    rows = {re.search(r"<td>([^<]+)</td>", row)[1]: row for row in re.findall(r"<tr[^>]*><td>.*?</tr>", index)}
    assert rows["mg26-multipan-pa04-pa05"].startswith('<tr class="dev">')  # only a proto board lists it
    assert "MajorDom Hub 1 prototype" in rows["mg26-multipan-pa04-pa05"]
    assert rows["skyconnect-zigbee"].startswith('<tr class="dev">')  # on the dev channel only
    assert rows[PACKAGE].startswith("<tr><td>")
    assert 'id="show-dev"' in index and "body:not(:has(#show-dev:checked)) tr.dev { display: none; }" in index


def test_generate_publishes_board_json_of_public_host_wired_boards(tmp_path: Path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "site", root / "site")
    shutil.copytree(ROOT / "packages", root / "packages")
    shutil.copytree(ROOT / "boards/majordom/proto-hub1-cm4-devkits/r1", root / "boards/majordom/hub1-cm4/r1")
    generate([], {}, tmp_path / "out", NOW, root=root)
    doc = json.loads((tmp_path / "out/v1/majordom/hub1-cm4/r1/board.json").read_text())
    assert (doc["board"], doc["revision"]) == ("hub1-cm4", 1)
    assert [s["name"] for s in doc["slots"]] == ["mg26", "zwave"]
