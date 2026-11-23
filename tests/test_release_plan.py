import subprocess
from pathlib import Path

import pytest

from tests.conftest import PACKAGE_TOML
from tools.common import load_package
from tools.release_plan import EMPTY_TREE, bump_patch, plan


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "develop")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    pkg = tmp_path / "packages" / "demo-mg26-multipan"
    pkg.mkdir(parents=True)
    (pkg / "package.toml").write_text(PACKAGE_TOML)
    (pkg / "CHANGELOG.md").write_text("# demo\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def run(repo: Path, base: str = EMPTY_TREE, dispatch: set[str] | None = None, apply: bool = False) -> list[dict]:
    return plan(repo / "packages", base, dispatch or set(), apply, cwd=repo)


def test_first_release_uses_version_as_is(repo: Path):
    [item] = run(repo)
    assert (item["tag"], item["bumped"], item["prev_tag"]) == ("demo-mg26-multipan-v1.0.0", False, "")


def test_released_and_unchanged_is_skipped(repo: Path):
    git(repo, "tag", "demo-mg26-multipan-v1.0.0")
    assert run(repo, base=git(repo, "rev-parse", "HEAD")) == []


def test_changelog_only_change_is_skipped(repo: Path):
    git(repo, "tag", "demo-mg26-multipan-v1.0.0")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "packages/demo-mg26-multipan/CHANGELOG.md").write_text("# demo\n- note\n")
    git(repo, "commit", "-qam", "notes")
    assert run(repo, base=base) == []


def test_changed_released_package_is_bumped(repo: Path):
    git(repo, "tag", "demo-mg26-multipan-v1.0.0")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "packages/demo-mg26-multipan/build.yaml").write_text("slcp: rcp.slcp\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "build")
    [item] = run(repo, base=base, apply=True)
    assert (item["version"], item["bumped"], item["prev_tag"]) == ("1.0.1", True, "demo-mg26-multipan-v1.0.0")
    assert load_package(repo / "packages/demo-mg26-multipan").version == "1.0.1"


def test_dispatch_filters_and_forces(repo: Path):
    git(repo, "tag", "demo-mg26-multipan-v1.0.0")
    head = git(repo, "rev-parse", "HEAD")
    assert run(repo, base=head, dispatch={"other"}) == []
    assert run(repo, base=head, dispatch={"all"})[0]["version"] == "1.0.1"


def test_bump_patch():
    assert bump_patch("1.2.3") == "1.2.4"
    assert bump_patch("1.2.3-rc1") == "1.2.4-rc1"
    with pytest.raises(ValueError):
        bump_patch("7.4")


def test_builder_change_selects_its_packages(repo: Path):
    toml = repo / "packages/demo-mg26-multipan/package.toml"
    toml.write_text(toml.read_text() + '\n[build]\nbuilder = "silabs-sisdk"\n')
    git(repo, "commit", "-qam", "builder")
    git(repo, "tag", "demo-mg26-multipan-v1.0.0")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "builder/silabs-sisdk").mkdir(parents=True)
    (repo / "builder/silabs-sisdk/Dockerfile").write_text("FROM scratch\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "builder change")
    [item] = run(repo, base=base)
    assert (item["version"], item["builder"], item["sdk"]) == ("1.0.1", "silabs-sisdk", "2025.6.3")


def test_mirrors_are_never_planned_or_bumped(repo: Path):
    toml = repo / "packages/demo-mg26-multipan/package.toml"
    toml.write_text(toml.read_text() + f'\n[source]\ntype = "url"\nurl = "https://example/x.gbl"\nsha256 = "{"a" * 64}"\n')
    assert run(repo, dispatch={"all"}) == []
