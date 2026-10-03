"""AP13: Prüfpfad ohne Klartext nach Kontaktlöschung (GAM-401), Sperrbezüge (GAM-405),
neue Datenarten der Löschprofile (GAM-404), Widerspruch gegen KI und SMS (GAM-406)."""

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from mhvp.contacts.models import Consent, ConsentKind, Contact, ContactKind
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import AuditLog, DomainEvent, emit
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import _ok, _settings
from tests.integration.test_m6_documents import client as _m6_client
from tests.integration.test_m6_documents import s3 as _m6_s3

s3 = _m6_s3
client = _m6_client
pytestmark = pytest.mark.integration

SECRET_NAME = f"Geheimname{RUN[-6:]}"


async def _set_sources(factory: Any, tenant: uuid.UUID, **values: Any) -> None:
    from mhvp.platform.models import TenantSettings

    async with tenant_transaction(factory, tenant) as s:
        row = await s.scalar(select(TenantSettings))
        assert row is not None
        row.sources = {**(row.sources or {}), **values}


async def _contact_with_audit(factory: Any, tenant: uuid.UUID, last: str) -> uuid.UUID:
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
        await emit(
            s,
            tenant_id=tenant,
            type="contact.updated",
            entity_type="contact",
            entity_id=c.id,
            actor_user_id=None,
            payload={"probe": RUN},
            changes={"last_name": {"old": SECRET_NAME, "new": last}},
        )
        return c.id


async def _audit(factory: Any, tenant: uuid.UUID, cid: uuid.UUID) -> list[dict[str, Any]]:
    async with tenant_transaction(factory, tenant) as s:
        rows = await s.scalars(
            select(AuditLog.changes).where(
                AuditLog.entity_type == "contact", AuditLog.entity_id == cid
            )
        )
        return list(rows)


async def _anonymize(factory: Any, tenant: uuid.UUID, cid: uuid.UUID) -> dict[str, int]:
    from mhvp.privacy.erasure import anonymize_contact

    async with tenant_transaction(factory, tenant) as s:
        c = await s.get(Contact, cid)
        assert c is not None
        return await anonymize_contact(s, c, None)


async def _call(factory: Any, tenant: uuid.UUID, cid: uuid.UUID) -> None:
    from mhvp.communication.telephony import CallLog

    async with tenant_transaction(factory, tenant) as s:
        s.add(
            CallLog(
                tenant_id=tenant,
                event="ended",
                direction="inbound",
                number="+49301234567",
                started_at=datetime.now(UTC),
                contact_id=cid,
                match_status="matched",
            )
        )


async def _blockers(factory: Any, tenant: uuid.UUID, cid: uuid.UUID) -> list[dict[str, Any]]:
    from mhvp.privacy.erasure import blockers

    async with tenant_transaction(factory, tenant) as s:
        c = await s.get(Contact, cid)
        assert c is not None
        return await blockers(s, c, date(2099, 1, 1))


async def _scenario(cfg: Any) -> dict[str, Any]:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(cfg)
    factory = create_session_factory(engine)
    out: dict[str, Any] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap13s-{RUN}", name=f"AP13 {RUN}")
        # GAM-401 switch off: audit unchanged (behaviour before AP13)
        off = await _contact_with_audit(factory, a, f"Aus{RUN[-5:]}")
        out["off_removed"] = await _anonymize(factory, a, off)
        out["off_audit"] = await _audit(factory, a, off)
        # switch on: values gone, field names stay, events untouched
        await _set_sources(factory, a, **{"privacy.audit_redaction": True})
        on = await _contact_with_audit(factory, a, f"Ein{RUN[-5:]}")
        out["on_removed"] = await _anonymize(factory, a, on)
        out["on_audit"] = await _audit(factory, a, on)
        async with tenant_transaction(factory, a) as s:
            out["event_payloads"] = [
                e.payload
                for e in await s.scalars(
                    select(DomainEvent).where(
                        DomainEvent.entity_id == on, DomainEvent.type == "contact.updated"
                    )
                )
            ]
        # database guard: any other update or delete stays forbidden
        out["forged"] = []
        for stmt in (
            "UPDATE audit_log SET changes = '{}'::jsonb WHERE entity_id = :cid",
            "UPDATE audit_log SET actor_user_id = gen_random_uuid() WHERE entity_id = :cid",
            "DELETE FROM audit_log WHERE entity_id = :cid",
        ):
            try:
                async with tenant_transaction(factory, a) as s:
                    await s.execute(text(stmt), {"cid": off})
                out["forged"].append("passed")
            except DBAPIError as exc:
                out["forged"].append("append-only" in str(exc))
        async with tenant_transaction(factory, a) as s:
            await emit(
                s,
                tenant_id=a,
                type="probe.updated",
                entity_type="probe",
                entity_id=uuid.uuid4(),
                actor_user_id=None,
                changes={"x": {"old": 1, "new": 2}},
            )
        try:
            async with tenant_transaction(factory, a) as s:
                await s.execute(
                    update(AuditLog)
                    .where(AuditLog.entity_type != "contact")
                    .values(changes=text("audit_redact_changes(changes)"))
                )
            out["non_contact"] = "passed"
        except DBAPIError as exc:
            out["non_contact"] = "append-only" in str(exc)
        # GAM-405: a call blocks; with the coupling switch it becomes a non blocking note
        ref = await _contact_with_audit(factory, a, f"Ruf{RUN[-5:]}")
        await _call(factory, a, ref)
        out["coupling_off"] = await _blockers(factory, a, ref)
        await _set_sources(factory, a, **{"privacy.erasure_coupling": True})
        out["coupling_on"] = await _blockers(factory, a, ref)
        # GAM-406: AI objection blocks a contact related run; no entry, no objection: allowed
        from mhvp.ai.gateway import ai_processing_block_reason
        from mhvp.contacts import consent_rules

        async with tenant_transaction(factory, a) as s:
            out["ai_free"] = await ai_processing_block_reason(s, {"contact_id": str(ref)})
            out["sms_free"] = (await consent_rules.sms_decision(s, ref)).allowed
            s.add(
                Consent(
                    tenant_id=a,
                    contact_id=ref,
                    kind=ConsentKind.AI_PROCESSING,
                    record_type="objection",
                    source="ap13-test",
                    granted_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            s.add(
                Consent(
                    tenant_id=a,
                    contact_id=ref,
                    kind=ConsentKind.SMS,
                    record_type="objection",
                    source="ap13-test",
                    granted_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            await s.flush()
            out["ai_objected"] = await ai_processing_block_reason(s, {"contact_ids": [str(ref)]})
            out["ai_other"] = await ai_processing_block_reason(s, {"contact_id": str(off)})
            out["ai_none"] = await ai_processing_block_reason(s, {})
            out["sms_objected"] = (await consent_rules.sms_decision(s, ref)).reason
    finally:
        await engine.dispose()
    return out


@pytest.fixture(scope="module")
def result(database: Database, redis_url: str) -> dict[str, Any]:
    return asyncio.run(_scenario(_settings(database, redis_url)))


def test_audit_unchanged_with_switch_off(result: dict[str, Any]) -> None:
    assert "audit_log_redacted" not in result["off_removed"]
    assert SECRET_NAME in str(result["off_audit"])


def test_audit_redacted_with_switch_on(result: dict[str, Any]) -> None:
    assert result["on_removed"]["audit_log_redacted"] == 1
    assert result["on_audit"] == [{"last_name": {"redacted": True}}]
    assert SECRET_NAME not in str(result["on_audit"])
    assert result["event_payloads"] == [{"probe": RUN}]


def test_audit_log_stays_append_only(result: dict[str, Any]) -> None:
    assert result["forged"] == [True, True, True]
    assert result["non_contact"] is True


def test_communication_reference_coupling(result: dict[str, Any]) -> None:
    from mhvp.privacy.erasure_coupling import blocking

    off = [b for b in result["coupling_off"] if b.get("table") == "call_log"]
    assert off
    assert off[0]["code"] == "referenced"
    assert off[0]["class"] == "communication"
    on = [b for b in result["coupling_on"] if b.get("table") == "call_log"]
    assert on[0]["code"] == "coupled_communication"
    assert on[0]["blocking"] is False
    assert on[0] not in blocking(result["coupling_on"])


def test_ai_and_sms_objection(result: dict[str, Any]) -> None:
    assert result["ai_free"] is None
    assert result["sms_free"] is True
    assert result["ai_objected"]
    assert "ai_processing_objection_recorded" in result["ai_objected"]
    assert result["ai_other"] is None
    assert result["ai_none"] is None
    assert result["sms_objected"] == "sms_objection_recorded"


# API: switches, permissions, validation, tenant separation, new data types -------------------


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap13a-{RUN}", name=f"AP13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ap13b-{RUN}", name=f"AP13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ap13one", a, "tenant_admin"),
            ("ap13std", a, "standard"),
            ("ap13other", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def test_erasure_settings_api(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "ap13one"))
    std = bearer(login(client, world, "ap13std"))
    other = bearer(login(client, world, "ap13other"))
    url = "/api/v1/privacy/erasure-settings"
    assert _ok(client.get(url, headers=one), 200) == {
        "audit_redaction": False,
        "erasure_coupling": False,
    }
    assert client.put(url, json={"audit_redaction": True}, headers=std).status_code == 403
    assert client.put(url, json={"bogus": True}, headers=one).status_code == 422
    assert client.get(url, params={"x": 1}, headers=one).status_code == 422
    after = _ok(client.put(url, json={"audit_redaction": True}, headers=one), 200)
    assert after == {"audit_redaction": True, "erasure_coupling": False}
    # tenant separation: the other tenant keeps its default
    assert _ok(client.get(url, headers=other), 200)["audit_redaction"] is False


def test_new_data_types_counted_without_period(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "ap13one"))
    for data_type in ("ai_run", "call_log", "webhook_delivery", "postal_job"):
        _ok(
            client.put(
                "/api/v1/privacy/deletion-profiles",
                json={"data_type": data_type, "retention_months": 1200, "start_rule": "Test"},
                headers=one,
            ),
            200,
        )
    preview = _ok(client.get("/api/v1/privacy/deletion-proposals", headers=one), 200)
    rows = {p["data_type"]: p for p in preview}
    for data_type in ("ai_run", "call_log", "webhook_delivery", "postal_job"):
        assert rows[data_type]["candidates"] == 0
    assert (
        client.put(
            "/api/v1/privacy/deletion-profiles",
            json={"data_type": "bogus", "retention_months": 1, "start_rule": "Test"},
            headers=one,
        ).status_code
        == 422
    )


def test_consent_register_lists_new_purposes(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "ap13one"))
    items = {
        i["purpose"]: i
        for i in _ok(client.get("/api/v1/consent-legal-basis", headers=one), 200)["items"]
    }
    assert items["sms"]["origin"] == "default"
    assert items["sms"]["consent_required"] is False
    assert items["ai_processing"]["consent_required"] is False
    _ok(
        client.put(
            "/api/v1/consent-legal-basis/ai_processing",
            json={"basis": "consent"},
            headers=one,
        ),
        200,
    )
    items = {
        i["purpose"]: i
        for i in _ok(client.get("/api/v1/consent-legal-basis", headers=one), 200)["items"]
    }
    assert items["ai_processing"]["consent_required"] is True
