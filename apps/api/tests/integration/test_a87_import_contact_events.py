"""A87: Immoware24 list imports emit the same contact events as the manual API (contact.created,
contact.updated with field names only), so the rule engine and the webhook outbox see them.
A test run leaves no event behind; the events stay inside the tenant."""

import asyncio
import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select

from mhvp.contacts.models import Contact, ContactRoleCode
from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import AuditLog, DomainEvent
from mhvp.core.webhooks import WebhookDelivery, WebhookSubscription, enqueue_deliveries
from mhvp.imports import kontakte, objektdaten, zuordnung
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration

KHEAD = (
    "id;Name;Briefanrede;Benutzername;Adresse;Stadt;PLZ;Staat;Land;Landesvorwahl;Vorwahl;"
    "Telefonnummer;E-Mail"
)
EIGENTUEMER = "\n".join([KHEAD, '10;"Steiger, Rolf";;;;;;;;;;;'])
MIETER = "\n".join([KHEAD, '11;"Bunte, Eva";;;;;;;;;;;'])
SONSTIGE = "\n".join([KHEAD, '10;"Steiger, Rolf";;;;;;;;;;;'])
OHEAD = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    '"aktueller Eigentümer";"vereinbarter Zahlbetrag";"aktueller Mieter";"vereinbarter Zahlbetrag"'
)
OBJEKTE = "\n".join(
    [
        OHEAD,
        '336;"Gladbacher Straße 95";WEG-Verwaltung;Haus;10001;01;EG;"Steiger, Rolf";269,12;;',
        '336;"Gladbacher Straße 95";WEG-Verwaltung;Haus;10002;02;OG;"Bunte, Eva";300,00;;',
    ]
)
START = date(2026, 1, 1)


async def _events(factory: Any, tenant_id: uuid.UUID) -> list[DomainEvent]:
    async with tenant_transaction(factory, tenant_id) as session:
        rows = await session.scalars(
            select(DomainEvent)
            .where(DomainEvent.entity_type == "contact")
            .order_by(DomainEvent.occurred_at, DomainEvent.id)
        )
        return list(rows.all())


async def _kontakte(
    factory: Any, tenant_id: uuid.UUID, text: str, role: ContactRoleCode, *, apply: bool
) -> dict[str, Any]:
    prepared = kontakte.prepare(kontakte.parse_kontakte(text, role, f"{role.value}.csv"))
    return await kontakte.import_prepared(factory, tenant_id, None, prepared, apply=apply)


async def _zuordnung(factory: Any, tenant_id: uuid.UUID, *, apply: bool) -> dict[str, Any]:
    return await zuordnung.import_rows(
        factory,
        tenant_id,
        None,
        objektdaten.parse_objektdaten(OBJEKTE).rows,
        apply=apply,
        start=START,
        start_assumed=False,
    )


async def _scenario(settings: Any) -> None:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant, _ = await services.provision_tenant(
            factory, slug=f"a87-a-{RUN}", name=f"A87 A {RUN}"
        )
        other, _ = await services.provision_tenant(
            factory, slug=f"a87-b-{RUN}", name=f"A87 B {RUN}"
        )
        async with tenant_transaction(factory, tenant) as session:
            session.add(
                WebhookSubscription(
                    tenant_id=tenant,
                    url="https://hooks.example.test/a87",
                    event_types=["contact.created", "contact.updated"],
                    secret="s" * 32,
                )
            )

        # Test run: report as with apply, but no event and no outbox row.
        dry = await _kontakte(
            factory, tenant, EIGENTUEMER, ContactRoleCode.EIGENTUEMER, apply=False
        )
        assert dry["counts"] == {"created": 1}
        assert await _events(factory, tenant) == []

        applied = await _kontakte(
            factory, tenant, EIGENTUEMER, ContactRoleCode.EIGENTUEMER, apply=True
        )
        assert applied["counts"] == {"created": 1}
        applied = await _kontakte(factory, tenant, MIETER, ContactRoleCode.MIETER, apply=True)
        assert applied["counts"] == {"created": 1}
        created = await _events(factory, tenant)
        assert [e.type for e in created] == ["contact.created", "contact.created"]
        assert all(e.payload == {"kind": "person", "source": "import.kontakte"} for e in created)
        assert all(e.tenant_id == tenant for e in created)
        async with tenant_transaction(factory, tenant) as session:
            ids = set(
                (
                    await session.scalars(select(Contact.id).where(Contact.deleted_at.is_(None)))
                ).all()
            )
        assert {e.entity_id for e in created} == ids

        # Same id in a second list: role added, contact.updated with field names only.
        dry_role = await _kontakte(
            factory, tenant, SONSTIGE, ContactRoleCode.SONSTIGES, apply=False
        )
        assert dry_role["counts"] == {"role_added": 1}
        assert len(await _events(factory, tenant)) == 2
        role_added = await _kontakte(
            factory, tenant, SONSTIGE, ContactRoleCode.SONSTIGES, apply=True
        )
        assert role_added["counts"] == {"role_added": 1}
        events = await _events(factory, tenant)
        assert [e.type for e in events] == ["contact.created", "contact.created", "contact.updated"]
        updated = events[-1]
        assert updated.payload == {"fields": ["roles"], "source": "import.kontakte"}
        async with tenant_transaction(factory, tenant) as session:
            audit = await session.scalar(select(AuditLog).where(AuditLog.event_id == updated.id))
            assert audit is not None
            assert audit.changes == {
                "roles": {"old": ["eigentuemer"], "new": ["eigentuemer", "sonstiges"]}
            }
            steiger = await session.get(Contact, updated.entity_id)
            assert steiger is not None
            assert steiger.version == 2
        # Idempotent: a repeated apply changes nothing and emits nothing.
        again = await _kontakte(factory, tenant, SONSTIGE, ContactRoleCode.SONSTIGES, apply=True)
        assert again["counts"] == {"unchanged": 1}
        assert len(await _events(factory, tenant)) == 3

        # Zuordnung: Bunte (imported as Mieter) becomes owner, Steiger already is one.
        prepared = objektdaten.prepare(objektdaten.parse_objektdaten(OBJEKTE), {})
        await objektdaten.import_prepared(factory, tenant, None, prepared, apply=True)
        before = len(await _events(factory, tenant))
        dry_z = await _zuordnung(factory, tenant, apply=False)
        assert dry_z["counts"]["vertraege_angelegt"] == 2
        assert dry_z["counts"]["kontakte_aktualisiert"] == 1
        assert len(await _events(factory, tenant)) == before
        applied_z = await _zuordnung(factory, tenant, apply=True)
        assert applied_z["counts"]["vertraege_angelegt"] == 2
        assert applied_z["counts"]["kontakte_aktualisiert"] == 1
        events = await _events(factory, tenant)
        assert len(events) == before + 1
        async with tenant_transaction(factory, tenant) as session:
            bunte = await session.scalar(
                select(Contact).where(Contact.external_ids["immoware24"].astext == "11")
            )
            assert bunte is not None
            assert sorted(bunte.roles) == ["eigentuemer", "mieter"]
            audit = await session.scalar(select(AuditLog).where(AuditLog.event_id == events[-1].id))
            assert audit is not None
            assert audit.changes == {"roles": {"old": ["mieter"], "new": ["eigentuemer", "mieter"]}}
        assert events[-1].type == "contact.updated"
        assert events[-1].entity_id == bunte.id
        assert events[-1].payload == {"fields": ["roles"], "source": "import.zuordnung"}
        # Second apply finds the contracts and changes no role: no further event.
        again_z = await _zuordnung(factory, tenant, apply=True)
        assert again_z["counts"]["vertraege_vorhanden"] == 2
        assert again_z["counts"].get("kontakte_aktualisiert", 0) == 0
        assert len(await _events(factory, tenant)) == before + 1

        # Webhook outbox: the subscription receives every contact event of this tenant.
        async with tenant_transaction(factory, tenant) as session:
            assert await enqueue_deliveries(session, tenant) == len(events)
            deliveries = (await session.scalars(select(WebhookDelivery))).all()
            assert {d.event_id for d in deliveries} == {e.id for e in events}

        # Tenant separation: nothing of this is visible from the other tenant.
        assert await _events(factory, other) == []
        async with tenant_transaction(factory, other) as session:
            assert await enqueue_deliveries(session, other) == 0
            assert (await session.scalars(select(WebhookDelivery))).all() == []
    finally:
        await engine.dispose()


def test_import_contact_events(database: Database, redis_url: str) -> None:
    asyncio.run(_scenario(base_settings(database, redis_url)))
