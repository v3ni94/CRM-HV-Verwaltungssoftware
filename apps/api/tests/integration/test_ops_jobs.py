"""A67: job ``ops.backup_verify`` writes its protocol (status, duration, checked file, error)
to the operating metrics ``GET /api/v1/platform/ops/metrics``. The script is replaced by a
fake so that no real backup is needed; the not configured, success and failure paths are
covered, plus the platform admin restriction."""

import asyncio
import stat
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace import backup_verify, ops
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
METRICS = "/api/v1/platform/ops/metrics"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ops-{RUN}", name=f"Ops {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, is_admin, role in [("opspadmin", True, ""), ("opstenant", False, "tenant_admin")]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            if role:
                await services.add_member(
                    factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_result(redis_url: str) -> Iterator[None]:
    async def clear() -> None:
        redis = Redis.from_url(redis_url)
        try:
            await redis.delete(backup_verify.RESULT_KEY)
        finally:
            await redis.aclose()

    asyncio.run(clear())
    yield
    asyncio.run(clear())


def _script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "backup-verify.sh"
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _metrics(client: TestClient, world: World) -> dict[str, Any]:
    response = client.get(METRICS, headers=bearer(login(client, world, "opspadmin")))
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_not_configured_is_recorded_not_failed(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    before = _metrics(client, world)
    assert before["jobs"]["backup_verify"]["status"] == "missing"
    assert before["metrics"]["backup_verify_stale"] == 1
    assert "backup_verify_stale" in before["alerts"]

    record = asyncio.run(backup_verify.backup_verify_once(_settings(database, redis_url)))
    assert record["status"] == "not_configured"
    assert "MHVP_BACKUP_VERIFY_ENABLED" in record["error"]

    body = _metrics(client, world)
    job = body["jobs"]["backup_verify"]
    assert job["status"] == "not_configured"
    assert job["stale"] is False
    assert job["age_seconds"] >= 0
    assert body["metrics"]["backup_verify_not_configured"] == 1
    assert body["metrics"]["backup_verify_failed"] == 0
    assert "backup_verify_failed" not in body["alerts"]
    assert "backup_verify_stale" not in body["alerts"]


def test_missing_script_is_not_configured(
    database: Database, redis_url: str, tmp_path: Path
) -> None:
    settings = _settings(
        database,
        redis_url,
        backup_verify_enabled=True,
        backup_verify_script=str(tmp_path / "does-not-exist.sh"),
    )
    record = asyncio.run(backup_verify.backup_verify_once(settings))
    assert record["status"] == "not_configured"
    assert "not found" in record["error"]


def test_successful_run_records_file_and_duration(
    client: TestClient, world: World, database: Database, redis_url: str, tmp_path: Path
) -> None:
    script = _script(
        tmp_path,
        'echo "backup-verify: file /backups/mhvp-20260926-020000.dump"\n'
        'echo "ok   alembic revision: 0119"\nexit 0\n',
    )
    settings = _settings(
        database, redis_url, backup_verify_enabled=True, backup_verify_script=str(script)
    )
    record = asyncio.run(backup_verify.backup_verify_once(settings))
    assert record["status"] == "ok"
    assert record["checked_file"] == "/backups/mhvp-20260926-020000.dump"
    assert record["exit_code"] == 0
    assert record["error"] is None
    assert record["duration_seconds"] >= 0

    body = _metrics(client, world)
    assert body["jobs"]["backup_verify"]["status"] == "ok"
    assert body["jobs"]["backup_verify"]["checked_file"].endswith(".dump")
    assert body["metrics"]["backup_verify_ok"] == 1
    assert body["alerts"] == [a for a in body["alerts"] if not a.startswith("backup_verify")]
    text = client.get(
        f"{METRICS}?format=prometheus", headers=bearer(login(client, world, "opspadmin"))
    ).text
    assert "mhvp_backup_verify_ok 1" in text
    assert "mhvp_backup_verify_duration_seconds " in text


def test_failed_run_records_error_and_alert(
    client: TestClient, world: World, database: Database, redis_url: str, tmp_path: Path
) -> None:
    script = _script(
        tmp_path,
        'echo "backup-verify: file /backups/mhvp-20260925-020000.dump"\n'
        'echo "FAIL alembic revision: source=0119 restore=0118" \n'
        'echo "backup-verify: checksum mismatch" >&2\nexit 1\n',
    )
    settings = _settings(
        database, redis_url, backup_verify_enabled=True, backup_verify_script=str(script)
    )
    record = asyncio.run(backup_verify.backup_verify_once(settings))
    assert record["status"] == "failed"
    assert record["exit_code"] == 1
    assert record["checked_file"] == "/backups/mhvp-20260925-020000.dump"
    assert "checksum mismatch" in record["error"]

    body = _metrics(client, world)
    assert body["jobs"]["backup_verify"]["status"] == "failed"
    assert body["metrics"]["backup_verify_failed"] == 1
    assert "backup_verify_failed" in body["alerts"]


def test_timeout_is_a_failure_with_exit_code_124(
    database: Database, redis_url: str, tmp_path: Path
) -> None:
    script = _script(tmp_path, "sleep 5\n")
    settings = _settings(
        database,
        redis_url,
        backup_verify_enabled=True,
        backup_verify_script=str(script),
        backup_verify_timeout_seconds=30,
    )

    async def slow_runner(command: list[str], timeout_seconds: int) -> tuple[int, str, str]:
        assert command[-1] == str(script)
        assert timeout_seconds == 30
        return await backup_verify.run_script(command, 1)

    record = asyncio.run(backup_verify.backup_verify_once(settings, runner=slow_runner))
    assert record["status"] == "failed"
    assert record["exit_code"] == 124
    assert "timeout" in record["error"]


def test_metrics_require_platform_admin(client: TestClient, world: World) -> None:
    tenant_admin = bearer(login(client, world, "opstenant"))
    assert client.get(METRICS, headers=tenant_admin).status_code == 403
    assert client.get(METRICS).status_code == 401


# Off-site copy (M9-02): the status line of scripts/backup-offsite.sh is read from a file and
# reported under jobs.backup_offsite with age, stale flag and alerts.

OFFSITE_LINE = (
    "backup-offsite: status={status} stamp=20260926T020000Z at={at} uploaded=3 bytes=1024 "
    "objects_new=2 objects_total=10 wal=4 pruned=1 seconds=12 dry_run=False{detail}\n"
)


def _offsite_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str | None) -> Path:
    path = tmp_path / "offsite-status"
    if text is not None:
        path.write_text(text)
    monkeypatch.setenv(ops.OFFSITE_STATUS_ENV, str(path))
    return path


def _stamp(now: datetime, *, hours_ago: float) -> str:
    return (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_offsite_status_ok_is_reported_with_age(
    client: TestClient, world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    path = _offsite_file(
        tmp_path,
        monkeypatch,
        OFFSITE_LINE.format(status="ok", at=_stamp(now, hours_ago=2), detail=""),
    )
    body = _metrics(client, world)
    job = body["jobs"]["backup_offsite"]
    assert job["status"] == "ok"
    assert job["stamp"] == "20260926T020000Z"
    assert job["file"] == str(path)
    assert job["wal"] == 4
    assert job["uploaded"] == 3
    assert job["dry_run"] is False
    assert job["error"] is None
    assert 7000 < job["age_seconds"] < 7400
    assert job["stale"] is False
    assert body["metrics"]["backup_offsite_ok"] == 1
    assert body["metrics"]["backup_offsite_failed"] == 0
    assert body["metrics"]["backup_offsite_stale"] == 0
    assert body["metrics"]["backup_offsite_wal_segments"] == 4
    assert "backup_offsite_failed" not in body["alerts"]
    assert "backup_offsite_stale" not in body["alerts"]

    prom = client.get(
        METRICS, params={"format": "prometheus"}, headers=bearer(login(client, world, "opspadmin"))
    )
    assert prom.status_code == 200
    assert "mhvp_backup_offsite_ok 1" in prom.text
    assert "mhvp_backup_offsite_age_seconds" in prom.text


def test_offsite_status_failed_and_stale_alert(
    client: TestClient, world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    _offsite_file(
        tmp_path,
        monkeypatch,
        OFFSITE_LINE.format(
            status="failed", at=_stamp(now, hours_ago=40), detail=" detail=upload_of_dump_failed"
        ),
    )
    body = _metrics(client, world)
    job = body["jobs"]["backup_offsite"]
    assert job["status"] == "failed"
    assert job["error"] == "upload of dump failed"
    assert job["stale"] is True
    assert body["metrics"]["backup_offsite_failed"] == 1
    assert body["metrics"]["backup_offsite_stale"] == 1
    assert "backup_offsite_failed" in body["alerts"]
    assert "backup_offsite_stale" in body["alerts"]


def test_offsite_status_missing_file_is_stale_alert(
    client: TestClient, world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offsite_file(tmp_path, monkeypatch, None)
    body = _metrics(client, world)
    job = body["jobs"]["backup_offsite"]
    assert job["status"] == "missing"
    assert "not readable" in job["error"]
    assert job["stale"] is True
    assert body["metrics"]["backup_offsite_failed"] == 0
    assert "backup_offsite_stale" in body["alerts"]


def test_offsite_status_malformed_line_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offsite_file(tmp_path, monkeypatch, "garbage without fields\n")
    result = ops.offsite_result()
    assert result["status"] == "missing"
    assert result["stale"] is True
    # Age falls back to the file mtime when "at" is unparsable.
    _offsite_file(tmp_path, monkeypatch, "backup-offsite: status=ok stamp=x at=nonsense wal=0\n")
    result = ops.offsite_result()
    assert result["status"] == "ok"
    assert result["age_seconds"] is not None
    assert result["age_seconds"] < 60
    assert result["stale"] is False


def test_offsite_not_configured_without_backup_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ops.OFFSITE_STATUS_ENV, raising=False)
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    result = ops.offsite_result()
    assert result["status"] == "not_configured"
    assert result["stale"] is False
    gauges = ops.job_gauges(
        {"backup_verify": backup_verify.summarize(None), "backup_offsite": result}
    )
    assert gauges["backup_offsite_not_configured"] == 1
    assert gauges["backup_offsite_stale"] == 0

    monkeypatch.setenv("BACKUP_DIR", "/srv/mhvp-backup")
    assert ops.offsite_status_path() == Path("/srv/mhvp-backup/offsite-status")
