"""M35: WhatsApp consent for contacts (tenants, owners) reuses the contacts consent model
(``ConsentKind.WHATSAPP``); staff members are an internal channel and need no contact consent
(documented assumption, docs/ASSUMPTIONS.md)."""

import asyncio
from typing import Any

import pytest

from mhvp.contacts.models import Consent, ConsentKind, Contact, ContactKind
from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.platform import services
from mhvp.sla.models import WhatsAppConfig, WhatsAppDelivery
from mhvp.sla.whatsapp import NO_CONSENT_ERROR, has_whatsapp_consent, send_whatsapp
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


async def _run(settings: Any) -> None:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant_id, _ = await services.provision_tenant(
            factory, slug=f"wac-{RUN}", name=f"WA Consent {RUN}"
        )
        async with tenant_transaction(factory, tenant_id) as session:
            contact = Contact(
                tenant_id=tenant_id,
                kind=ContactKind.PERSON,
                first_name="Erika",
                last_name="Musterfrau",
                display_name="Erika Musterfrau",
            )
            session.add(contact)
            await session.flush()
            contact_id = contact.id

        async with tenant_transaction(factory, tenant_id) as session:
            assert await has_whatsapp_consent(session, contact_id) is False
            # GAJ-405: the send path refuses a contact without consent before any API call.
            config = WhatsAppConfig(
                tenant_id=tenant_id,
                enabled=True,
                phone_number_id="1",
                access_token="t",
                template_names={"test": "test_de"},
            )
            error = await send_whatsapp(
                session,
                settings,
                config,
                alert_id=None,
                to="+49170",
                alert_type="test",
                params=[],
                recipient="contact",
                contact_id=contact_id,
            )
            assert error == NO_CONSENT_ERROR
            assert not [o for o in session.new if isinstance(o, WhatsAppDelivery)]

        from datetime import UTC, datetime

        async with tenant_transaction(factory, tenant_id) as session:
            session.add(
                Consent(
                    tenant_id=tenant_id,
                    contact_id=contact_id,
                    kind=ConsentKind.WHATSAPP,
                    granted_at=datetime.now(UTC),
                    source="Test",
                )
            )

        async with tenant_transaction(factory, tenant_id) as session:
            assert await has_whatsapp_consent(session, contact_id) is True

        from sqlalchemy import select

        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.scalar(select(Consent).where(Consent.contact_id == contact_id))
            assert row is not None
            row.revoked_at = datetime.now(UTC)

        async with tenant_transaction(factory, tenant_id) as session:
            assert await has_whatsapp_consent(session, contact_id) is False
    finally:
        await engine.dispose()


def test_has_whatsapp_consent_reflects_grant_and_revoke(database: Database, redis_url: str) -> None:
    asyncio.run(_run(_settings(database, redis_url)))
