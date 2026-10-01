"""T03 (M11-07, M11-08): raw bank data key and retention profile, consent expiry from the
provider answer, renewal task. Fake S3 and fake finAPI only, no network."""

# ruff: noqa: F811

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.banking import raw_archive
from mhvp.banking import tasks as banking_tasks
from mhvp.banking.finapi import parse_consent_valid_until
from mhvp.core.problems import ProblemError
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m8_import import _settings
from tests.integration.test_m11_finapi import (
    _configure,
    _connect_and_check,
    _consent_notifications,
    _fake_finapi,  # noqa: F401
    _run_reminders,
    _set_consent,
    client,  # noqa: F401
    world,  # noqa: F401
)

pytestmark = pytest.mark.integration


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_: Any) -> None:  # noqa: N803
        self.objects[Key] = Body


def test_raw_key_scheme_and_extension_allowlist() -> None:
    tenant, account = uuid.uuid4(), uuid.uuid4()
    assert raw_archive.raw_object_key(tenant, account, date(2026, 9, 30), "XML") == (
        f"bank/{tenant}/{account}/2026-09-30.xml"
    )
    assert raw_archive.raw_object_key(tenant, account, date(2026, 9, 30), ".json", 2).endswith(
        "/2026-09-30-2.json"
    )
    with pytest.raises(ProblemError):
        raw_archive.raw_object_key(tenant, account, date(2026, 9, 30), "exe")


def test_parse_consent_valid_until() -> None:
    assert parse_consent_valid_until({"status": "UPDATED"}) is None
    assert parse_consent_valid_until({"consentExpiresAt": "2026-12-24T10:00:00.000Z"}) == date(
        2026, 12, 24
    )
    # earliest over connection and interfaces; garbage is ignored, nothing is estimated
    details = {
        "consentValidUntil": "2027-01-10",
        "interfaces": [{"consentExpiresAt": "2026-11-05"}, {"consentExpiresAt": "kaputt"}, 7],
    }
    assert parse_consent_valid_until(details) == date(2026, 11, 5)


def test_archive_raw_key_retention_and_no_overwrite(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document, RetentionProfile

    settings = _settings(database, redis_url)
    s3 = _FakeS3()
    account = uuid.uuid4()
    day = date(2026, 9, 30)

    async def _go() -> tuple[list[str], str, date | None, uuid.UUID | None, uuid.UUID | None]:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                blobs = BlobStore(settings, client=s3)  # type: ignore[arg-type]
                docs = [
                    await raw_archive.archive_raw(
                        s,
                        blobs,
                        tenant_id=world.tenant_a,
                        account_id=account,
                        data=data,
                        ext="xml",
                        day=day,
                        created_by=None,
                    )
                    for data in (b"<a/>", b"<b/>")
                ]
                profile = await s.scalar(
                    select(RetentionProfile).where(
                        RetentionProfile.document_class == "accounting_records"
                    )
                )
                first = await s.get(Document, docs[0].id)
                assert first is not None
                assert profile is not None
                assert profile.retention_years == 10
                assert not profile.permanent
                return (
                    [d.storage_ref for d in docs],
                    str(first.source_system),
                    first.retention_until,
                    first.retention_profile_id,
                    profile.id,
                )
        finally:
            await engine.dispose()

    keys, source_system, until, profile_id, expected_profile = asyncio.run(_go())
    base = f"bank/{world.tenant_a}/{account}/2026-09-30"
    assert keys == [f"{base}.xml", f"{base}-2.xml"]
    assert s3.objects[keys[0]] == b"<a/>"  # no overwrite
    assert s3.objects[keys[1]] == b"<b/>"
    assert source_system == "bank_raw"
    assert profile_id == expected_profile
    # 10 years from the end of the creation year (profile start rule END_OF_YEAR_CREATED)
    assert until is not None
    assert until.year >= datetime.now(UTC).year + 10


def test_consent_from_check_and_renewal_task(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.tickets.models import Ticket

    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    checked = _connect_and_check(client, h)
    today = date(2026, 9, 26)
    expiry = today + timedelta(days=10)
    _set_consent(database, redis_url, world.tenant_a, checked["id"], expiry)
    _run_reminders(database, redis_url, world.tenant_a, today)
    _run_reminders(database, redis_url, world.tenant_a, today)  # idempotent
    assert len(_consent_notifications(client, h, checked["bank_connection_id"])) == 1

    async def _tasks() -> list[str]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                rows = await s.scalars(select(Ticket).where(Ticket.category == "task"))
                return [t.title for t in rows.all() if "Bankzustimmung" in t.title]
        finally:
            await engine.dispose()

    titles = asyncio.run(_tasks())
    assert len(titles) == 1
    assert "06.10.2026" in titles[0]
    assert banking_tasks.CONSENT_WARN_DAYS == 10
