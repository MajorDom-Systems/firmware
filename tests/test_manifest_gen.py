import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.common import ROOT
from tools.manifest_gen import ManifestError, generate, manifests

NOW = datetime(2026, 11, 19, tzinfo=UTC)
SHA = "a" * 64


def meta(version: str, family: str = "devrig-mg26", kind: str = "multipan") -> dict:
    package = f"{family}-{kind}"
    return {"package": package, "version": version, "family": family, "kind": kind, "summary": "s",
            "serial": {"baud": 115200, "flow": "none"}, "source": "staged",
            "files": {"gbl": {"name": f"{package}_{version}.gbl", "sha256": SHA, "size": 10}}}


def release(version: str, prerelease: bool = False, digest: str | None = SHA, **extra) -> dict:
    name = f"devrig-mg26-multipan_{version}.gbl"
    asset = {"name": name, "size": 10, "browser_download_url": f"https://example/{name}"}
    if digest:
        asset["digest"] = f"sha256:{digest}"
    return {"tag_name": f"devrig-mg26-multipan-v{version}", "prerelease": prerelease, "draft": False,
            "published_at": "2026-11-19T00:00:00Z", "html_url": "https://example/tag", "body": "",
            "assets": [asset], **extra}


def metas(*versions: str) -> dict[str, dict]:
    return {f"devrig-mg26-multipan-v{v}": meta(v) for v in versions}


def versions(doc: dict) -> list[str]:
    return [i["version"] for i in doc["firmware"].get("devrig-mg26", {}).get("multipan", [])]


def test_prerelease_only_in_dev_sorted_newest_first():
    out = manifests([release("1.0.0"), release("1.1.0", prerelease=True), release("1.0.10")], metas("1.0.0", "1.1.0", "1.0.10"), "t", NOW)
    assert versions(out["stable"]) == ["1.0.10", "1.0.0"]
    assert versions(out["dev"]) == ["1.1.0", "1.0.10", "1.0.0"]
    assert out["dev"]["firmware"]["devrig-mg26"]["multipan"][0]["stability"] == "dev"


def test_downgrade_policy_dev_only():
    out = manifests([], {}, "t", NOW)
    assert out["stable"]["policy"] == {"downgrade": False}
    assert out["dev"]["policy"] == {"downgrade": True}
    assert (out["dev"]["issued_at"], out["dev"]["expires_at"]) == ("2026-11-19T00:00:00Z", "2027-02-17T00:00:00Z")


def test_drafts_and_yanked_are_dropped():
    releases = [release("1.0.0", draft=True), release("1.0.1", body="---\nyanked: true\n---\nbad build")]
    out = manifests(releases, metas("1.0.0", "1.0.1"), "t", NOW)
    assert versions(out["dev"]) == []


def test_asset_digest_must_match_meta():
    with pytest.raises(ManifestError, match="differs"):
        manifests([release("1.0.0", digest="b" * 64)], metas("1.0.0"), "t", NOW)


def test_meta_sha_used_when_api_has_no_digest():
    out = manifests([release("1.0.0", digest=None)], metas("1.0.0"), "t", NOW)
    assert out["stable"]["firmware"]["devrig-mg26"]["multipan"][0]["files"]["gbl"]["sha256"] == SHA


def test_missing_gbl_or_meta_fails():
    with pytest.raises(ManifestError, match="missing"):
        manifests([release("1.0.0") | {"assets": []}], metas("1.0.0"), "t", NOW)
    with pytest.raises(ManifestError, match="no meta.json"):
        manifests([release("1.0.0")], {}, "t", NOW)


def test_generate_writes_site(tmp_path: Path):
    generate([release("1.0.0", prerelease=True)], metas("1.0.0"), tmp_path, NOW, root=ROOT)
    dev = json.loads((tmp_path / "v1/dev.json").read_text())
    targets = json.loads((tmp_path / "v1/targets.json").read_text())["targets"]
    assert versions(dev) == ["1.0.0"]
    assert dev["targets_sha256"] and json.loads((tmp_path / "v1/stable.json").read_text())["firmware"] == {}
    assert targets["majordom/hub-v1"]["board_json"] == "targets/majordom/hub-v1/board.json"
    assert (tmp_path / "v1/majordom/hub-v1/board.json").exists()
    index = (tmp_path / "index.html").read_text()
    assert "MajorDom CM4 dev rig (mg26)" in index and "{{" not in index
    assert "devrig-mg26-multipan 1.0.0 (dev)" in (tmp_path / "llms.txt").read_text()
