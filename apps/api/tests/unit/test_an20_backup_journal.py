"""GAK-405 (D47): scripts/backup.sh backs up the deletion journal with every dump."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "backup.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash needed")


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _run(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _stub(bin_dir / "pg_dump", "echo dump-bytes\n")
    _stub(
        bin_dir / "age",
        'while [[ $# -gt 0 ]]; do [[ "$1" == --output ]] && out="$2"; shift; done\ncat > "$out"\n',
    )
    backups = tmp_path / "backups"
    full_env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PGDATABASE": "x",
        "PGHOST": "localhost",
        "BACKUP_DIR": str(backups),
        "BACKUP_AGE_RECIPIENT": "age1test",
        **env,
    }
    return subprocess.run(  # noqa: S603 - fixed script path, stubbed environment
        ["bash", str(SCRIPT)],  # noqa: S607
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_journal_is_exported_encrypted_with_checksum(tmp_path: Path) -> None:
    journal = _stub(tmp_path / "journal.sh", 'echo \'{"version": 1, "entries": []}\'\n')
    result = _run(tmp_path, BACKUP_JOURNAL_CMD=str(journal))
    assert result.returncode == 0, result.stderr
    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    journal_files = [n for n in names if n.startswith("mhvp-deletions-")]
    assert any(n.endswith(".json.age") for n in journal_files)
    assert any(n.endswith(".json.age.sha256") for n in journal_files)
    assert not any(n.endswith(".json") for n in journal_files)  # never stored in clear text


def test_backup_without_journal_command_is_refused(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 3
    assert "journal" in result.stderr.lower()
    assert not list((tmp_path / "backups").glob("mhvp-*.dump*"))


def test_journal_can_be_skipped_only_on_purpose(tmp_path: Path) -> None:
    result = _run(tmp_path, BACKUP_SKIP_JOURNAL="1")
    assert result.returncode == 0, result.stderr
    assert not list((tmp_path / "backups").glob("mhvp-deletions-*"))


def test_failing_journal_export_fails_the_backup(tmp_path: Path) -> None:
    broken = _stub(tmp_path / "broken.sh", "exit 7\n")
    result = _run(tmp_path, BACKUP_JOURNAL_CMD=str(broken))
    assert result.returncode != 0
    assert not list((tmp_path / "backups").glob("mhvp-*"))  # no half written files of the run
