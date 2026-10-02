"""GAI-111, GAI-112, GAI-113, GAI-511: the version has one source (VERSION), the API reports
it, the three version files agree, and the release scripts behave."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import mhvp
from mhvp.core.config import Settings

ROOT = Path(__file__).resolve().parents[4]
# S607: resolve the interpreter of bash once, never rely on a bare name in subprocess calls.
BASH = shutil.which("bash") or "/bin/bash"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bump = _load("bump_version")
commits = _load("check_commits")


def test_version_file_changelog_and_changelog_ts_agree() -> None:
    assert bump.check(ROOT) == []


def test_first_changelog_entries_are_semver() -> None:
    assert bump.SEMVER.match(bump.read_version(ROOT))
    assert bump.changelog_md_first(ROOT) == bump.read_version(ROOT)
    assert bump.changelog_ts_first(ROOT) == bump.read_version(ROOT)


def test_api_reports_the_version_file_not_package_metadata() -> None:
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert mhvp.__version__ == expected


@pytest.mark.parametrize("placeholder", ["0.1.0", "", "  "])
def test_settings_ignore_legacy_placeholder(placeholder: str) -> None:
    assert Settings(app_version=placeholder).app_version == mhvp.__version__


def test_settings_keep_explicit_version() -> None:
    assert Settings(app_version="9.9.9").app_version == "9.9.9"


def test_bump_version_detects_a_mismatch_and_sets_all_files(tmp_path: Path) -> None:
    (tmp_path / "apps/web-crm/src/lib").mkdir(parents=True)
    (tmp_path / "apps/web-portal").mkdir(parents=True)
    (tmp_path / "apps/api").mkdir(parents=True)
    (tmp_path / "VERSION").write_text("1.2.3\n")
    (tmp_path / "CHANGELOG.md").write_text("# V\n\n## 1.2.3 (01.01.2026) x\n")
    (tmp_path / "apps/web-crm/src/lib/changelog.ts").write_text('  {\n    version: "1.2.2",\n')
    (tmp_path / "apps/api/pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    for app in ("web-crm", "web-portal"):
        (tmp_path / f"apps/{app}/package.json").write_text('{\n  "version": "0.1.0"\n}\n')
    assert any("changelog.ts" in p for p in bump.check(tmp_path))
    bump.bump("1.2.4", tmp_path)
    assert (tmp_path / "VERSION").read_text() == "1.2.4\n"
    assert 'version = "1.2.4"' in (tmp_path / "apps/api/pyproject.toml").read_text()
    for app in ("web-crm", "web-portal"):
        data = json.loads((tmp_path / f"apps/{app}/package.json").read_text())
        assert data["version"] == "1.2.4"
    with pytest.raises(SystemExit):
        bump.bump("1.2", tmp_path)


@pytest.mark.parametrize(
    "message",
    ["feat(api): neue Funktion", "fix: Korrektur", "chore(ci)!: Umbau", "Merge branch 'x'"],
)
def test_commit_headers_accepted(message: str) -> None:
    assert commits.check_message(message) is None


@pytest.mark.parametrize(
    "message", ["Update stuff", "feat:ohne Leerzeichen", "feat(API): Grossbuchstabe", "feat: "]
)
def test_commit_headers_rejected(message: str) -> None:
    assert commits.check_message(message) is not None


def test_commit_header_length_limit() -> None:
    assert commits.check_message("fix: " + "x" * 120) is not None


def test_restore_drill_script_test_passes() -> None:
    result = subprocess.run(  # noqa: S603
        [BASH, str(ROOT / "infra/scripts/tests/test-restore-drill.sh")],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
