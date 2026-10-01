"""AE26 / AC11-01: pinned KoSIT validator download (scripts/kosit_fetch.sh, scripts/kosit.lock).

The fetch script is tested offline with ``file://`` archives and a private lock file: pinned
checksums are enforced before anything is unpacked, placeholders stop with a clear exit code,
CI variables override the lock only when they are not empty. The repository lock file, the
make targets and the CI job are checked for consistency. Nothing here uses the network."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FETCH = ROOT / "scripts" / "kosit_fetch.sh"
LOCK = ROOT / "scripts" / "kosit.lock"
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("unzip") is None or shutil.which("curl") is None,
    reason="bash, unzip and curl are required; not executed",
)

KEYS = ("KOSIT_JAR_URL", "KOSIT_JAR_SHA256", "KOSIT_CFG_URL", "KOSIT_CFG_SHA256")


def _parse_lock(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _archives(tmp_path: Path) -> tuple[Path, Path]:
    jar = tmp_path / "validator.zip"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("validationtool-9.9.9-standalone.jar", b"not a real jar")
        z.writestr("libs/dummy.jar", b"x")
    cfg = tmp_path / "config.zip"
    with zipfile.ZipFile(cfg, "w") as z:
        z.writestr("scenarios.xml", "<scenarios/>")
        z.writestr("resources/ubl/2.1/xsd/a.xsd", "<xs:schema/>")
    return jar, cfg


def _write_lock(tmp_path: Path, jar: Path, cfg: Path, **overrides: str) -> Path:
    values = {
        "KOSIT_JAR_URL": jar.as_uri(),
        "KOSIT_JAR_SHA256": _sha(jar),
        "KOSIT_CFG_URL": cfg.as_uri(),
        "KOSIT_CFG_SHA256": _sha(cfg),
        **overrides,
    }
    lock = tmp_path / "test.lock"
    lock.write_text("# test\n" + "".join(f"{k}={v}\n" for k, v in values.items()), "utf-8")
    return lock


def _run(lock: Path, target: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("KOSIT_", "MHVP_KOSIT"))}
    env.update({"KOSIT_LOCK": str(lock), "MHVP_KOSIT_DIR": str(target), **extra_env})
    return subprocess.run(  # noqa: S603
        [shutil.which("bash") or "/bin/bash", str(FETCH)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )


def test_repository_lock_has_four_https_pins() -> None:
    values = _parse_lock(LOCK)
    assert set(values) == set(KEYS)
    for key in ("KOSIT_JAR_URL", "KOSIT_CFG_URL"):
        assert values[key].startswith("https://github.com/itplr-kosit/"), key
    for key in ("KOSIT_JAR_SHA256", "KOSIT_CFG_SHA256"):
        assert re.fullmatch(r"[0-9a-f]{64}", values[key]), key


def test_ci_job_and_make_targets_use_the_repository_lock() -> None:
    ci = CI.read_text(encoding="utf-8")
    job = ci[ci.index("  xrechnung-kosit:") :]
    assert "scripts/kosit_fetch.sh" in job
    # variables are optional overrides: the job must not depend on them being set
    assert "vars.MHVP_KOSIT_ENABLED != 'false'" in job
    assert "sha256sum -c" not in job
    make = MAKEFILE.read_text(encoding="utf-8")
    for target in ("kosit-fetch:", "kosit-test:", "kosit-validate:"):
        assert re.search(rf"^{re.escape(target)}", make, re.MULTILINE), target
    assert "scripts/kosit_fetch.sh" in make


def test_fetch_unpacks_after_the_checksums_match_and_is_idempotent(tmp_path: Path) -> None:
    jar, cfg = _archives(tmp_path)
    lock = _write_lock(tmp_path, jar, cfg)
    target = tmp_path / "kosit"
    done = _run(lock, target)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().splitlines()[-1] == f"MHVP_KOSIT_DIR={target}"
    assert (target / "validationtool-9.9.9-standalone.jar").is_file()
    assert (target / "cfg" / "scenarios.xml").is_file()
    assert (target / ".pins").read_text("utf-8").split() == [_sha(jar), _sha(cfg)]
    jar.unlink()
    cfg.unlink()
    again = _run(lock, target)  # pins unchanged: no download needed
    assert again.returncode == 0, again.stderr
    assert "already present" in again.stderr


def test_checksum_mismatch_stops_before_unpacking(tmp_path: Path) -> None:
    jar, cfg = _archives(tmp_path)
    lock = _write_lock(tmp_path, jar, cfg, KOSIT_CFG_SHA256="0" * 64)
    target = tmp_path / "kosit"
    result = _run(lock, target)
    assert result.returncode == 4
    assert "checksum mismatch for config" in result.stderr
    assert not list(target.glob("validationtool-*"))
    assert not (target / "cfg").exists()


@pytest.mark.parametrize("bad", ["PLACEHOLDER", "", "abc123", "g" * 64])
def test_placeholder_or_malformed_pin_exits_with_3(tmp_path: Path, bad: str) -> None:
    jar, cfg = _archives(tmp_path)
    lock = _write_lock(tmp_path, jar, cfg, KOSIT_JAR_SHA256=bad)
    result = _run(lock, tmp_path / "kosit")
    assert result.returncode == 3
    assert "placeholder" in result.stderr


def test_download_failure_exits_with_5(tmp_path: Path) -> None:
    jar, cfg = _archives(tmp_path)
    lock = _write_lock(tmp_path, jar, cfg, KOSIT_JAR_URL=(tmp_path / "missing.zip").as_uri())
    result = _run(lock, tmp_path / "kosit")
    assert result.returncode == 5


def test_environment_overrides_lock_only_when_not_empty(tmp_path: Path) -> None:
    jar, cfg = _archives(tmp_path)
    lock = _write_lock(tmp_path, jar, cfg, KOSIT_JAR_SHA256="f" * 64)
    # empty CI variable: the lock value (wrong here) applies
    assert _run(lock, tmp_path / "a", KOSIT_JAR_SHA256="").returncode == 4
    # non-empty variable wins over the lock
    ok = _run(lock, tmp_path / "b", KOSIT_JAR_SHA256=_sha(jar))
    assert ok.returncode == 0, ok.stderr
    # a changed pin triggers a new download into an existing directory
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as z:
        z.writestr("validationtool-9.9.10-standalone.jar", b"newer")
    upd = _run(
        lock,
        tmp_path / "b",
        KOSIT_JAR_URL=other.as_uri(),
        KOSIT_JAR_SHA256=_sha(other),
    )
    assert upd.returncode == 0, upd.stderr
    assert (tmp_path / "b" / "validationtool-9.9.10-standalone.jar").is_file()
    assert not (tmp_path / "b" / "validationtool-9.9.9-standalone.jar").exists()
