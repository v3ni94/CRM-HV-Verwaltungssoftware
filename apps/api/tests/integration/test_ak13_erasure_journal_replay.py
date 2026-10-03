"""AK13 (GAI-512 Rest, Welle 22): erasure journal export and replay against a real database.

Own world (prefix ``ak13-<run>``): two tenants, contacts written through the ORM. A
``contact.anonymized`` event stands for the original Art. 17 execution; the contact rows are
left with their personal data, which is the state after restoring an older backup.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.contacts.models import Contact, ContactEmail, ContactKind
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.platform import services
from mhvp.privacy import erasure_journal as ej
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import _settings as base_settings

RUN = f"ak13-{uuid.uuid4().hex[:8]}"


async def _contact(factory: Any, tenant: uuid.UUID, last: str) -> uuid.UUID:
    async with tenant_transaction(factory, tenant) as s:
        c = Contact(
            tenant_id=tenant,
            kind=ContactKind.PERSON,
            first_name="Erika",
            last_name=last,
            display_name=f"{last}, Erika",
            search_text=last.lower(),
        )
        s.add(c)
        await s.flush()
        s.add(ContactEmail(tenant_id=tenant, contact_id=c.id, email=f"{last}@example.org"))
        return c.id


async def _event(factory: Any, tenant: uuid.UUID, contact_id: uuid.UUID) -> None:
    async with tenant_transaction(factory, tenant) as s:
        await emit(
            s,
            tenant_id=tenant,
            type=ej.EVENT_TYPE,
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=None,
            payload={"request_id": str(uuid.uuid4())},
        )


async def _state(factory: Any, tenant: uuid.UUID, cid: uuid.UUID) -> tuple[Contact | None, int]:
    async with tenant_transaction(factory, tenant) as s:
        c = await s.get(Contact, cid)
        n = await s.scalar(
            select(func.count()).select_from(ContactEmail).where(ContactEmail.contact_id == cid)
        )
        if c is not None:
            s.expunge(c)
        return c, int(n or 0)


async def _scenario(cfg: Any) -> dict[str, Any]:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(cfg)
    factory = create_session_factory(engine)
    out: dict[str, Any] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"{RUN}-a", name=f"AK13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"{RUN}-b", name=f"AK13 B {RUN}")
        since = datetime.now(UTC) - timedelta(minutes=1)
        restored = await _contact(factory, a, f"Restored{RUN[5:]}")
        done = await _contact(factory, a, f"Done{RUN[5:]}")
        foreign = await _contact(factory, b, f"Foreign{RUN[5:]}")
        absent = uuid.uuid4()
        # 'done' is already anonymised in the restored backup.
        async with tenant_transaction(factory, a) as s:
            c = await s.get(Contact, done)
            assert c is not None
            await ej.anonymize_contact(s, c, None)
        for cid in (restored, done, absent):
            await _event(factory, a, cid)
        journal = await ej.export_journal(factory, since=since, tenant_ids=[a, b])
        out["exported"] = [e["contact_id"] for e in journal["entries"]]
        # Tenant separation: an entry naming tenant A with a contact of tenant B is absent.
        journal["entries"].append(
            {"tenant_id": str(a), "event_id": str(uuid.uuid4()), "contact_id": str(foreign)}
        )
        journal["entries"].append({"tenant_id": "x", "event_id": "y"})
        dry = await ej.replay_journal(factory, journal, apply=False)
        out["dry"] = [r.outcome for r in dry.results]
        out["after_dry"] = await _state(factory, a, restored)
        applied = await ej.replay_journal(factory, journal, apply=True)
        out["applied"] = [r.outcome for r in applied.results]
        out["after_apply"] = await _state(factory, a, restored)
        out["foreign"] = await _state(factory, b, foreign)
        again = await ej.replay_journal(factory, journal, apply=True)
        out["again"] = [r.outcome for r in again.results]
        async with tenant_transaction(factory, a) as s:
            out["replay_events"] = [
                (str(e.entity_id), (e.payload or {}).get("journal_event_id"))
                for e in await s.scalars(
                    select(DomainEvent).where(
                        DomainEvent.type == ej.EVENT_TYPE,
                        DomainEvent.payload["replay"].astext == "true",
                    )
                )
            ]
        reexport = await ej.export_journal(factory, since=since, tenant_ids=[a])
        out["reexported"] = [e["contact_id"] for e in reexport["entries"]]
        out["ids"] = {"restored": str(restored), "done": str(done), "absent": str(absent)}
        out["first_event"] = journal["entries"][0]["event_id"]
    finally:
        await engine.dispose()
    return out


@pytest.fixture(scope="module")
def result(database: Database, redis_url: str) -> dict[str, Any]:
    return asyncio.run(_scenario(base_settings(database, redis_url)))


def test_export_lists_original_executions_only(result: dict[str, Any]) -> None:
    ids = result["ids"]
    assert result["exported"] == [ids["restored"], ids["done"], ids["absent"]]
    # Replay events are no new statements and are not exported again.
    assert result["reexported"] == result["exported"]


def test_dry_run_changes_nothing(result: dict[str, Any]) -> None:
    assert result["dry"] == ["would_anonymize", "already_anonymized", "absent", "absent", "invalid"]
    contact, emails = result["after_dry"]
    assert contact is not None
    assert not contact.blocked
    assert contact.first_name == "Erika"
    assert emails == 1


def test_apply_anonymizes_and_records(result: dict[str, Any]) -> None:
    assert result["applied"] == [
        "anonymized",
        "already_anonymized",
        "absent",
        "absent",
        "invalid",
    ]
    contact, emails = result["after_apply"]
    assert contact is not None
    assert contact.blocked
    assert contact.first_name is None
    assert contact.display_name.startswith(ej.ANONYMIZED_PREFIX)
    assert contact.deleted_at is not None
    assert emails == 0
    assert result["replay_events"] == [(result["ids"]["restored"], result["first_event"])]


def test_foreign_tenant_untouched_and_idempotent(result: dict[str, Any]) -> None:
    contact, emails = result["foreign"]
    assert contact is not None
    assert not contact.blocked
    assert emails == 1
    assert result["again"] == [
        "already_anonymized",
        "already_anonymized",
        "absent",
        "absent",
        "invalid",
    ]
