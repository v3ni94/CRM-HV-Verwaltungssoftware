"""AN14-04 and AN14-12: payment files are refused when saved as attachment and dropped by the
forwarding job while G2 is closed; a WhatsApp contact recipient only gets its own number."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_an14_payment_file_attachment import _Blobs
from tests.integration.test_m2_platform import RUN
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration


async def _run(settings: Any) -> None:
    from mhvp.communication import forwarding_dispatch
    from mhvp.contacts.models import Contact, ContactKind, ContactPhone, PhoneLabel
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.problems import ProblemError
    from mhvp.documents import blobs as blob_module
    from mhvp.documents import payment_files
    from mhvp.documents import services as docs
    from mhvp.documents.models import DocumentSource
    from mhvp.sla import whatsapp

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    tenant, _ = await services.provision_tenant(
        factory, slug=f"ao06-{RUN}", name=f"AO06 Anhangswege {RUN}"
    )
    blobs = _Blobs()
    try:
        async with tenant_transaction(factory, tenant) as session:
            common: dict[str, Any] = {
                "tenant_id": tenant,
                "mime_type": "application/xml",
                "source": DocumentSource.GENERATED,
                "links": [],
                "created_by": None,
                "scan_for_malware": False,
                "settings": settings,
            }
            pay = await docs.store_document(
                session,
                blobs,
                data=b"<pain/>",
                title="Zahlungsdatei",
                filename="p.xml",
                category_id=await payment_files.category_id(session, tenant),
                **common,
            )
            plain = await docs.store_document(
                session,
                blobs,
                data=b"<x/>",
                title="Notiz",
                filename="n.xml",
                category_id=None,
                **common,
            )
            # Saving: refused with 422, ordinary documents pass.
            await payment_files.ensure_no_payment_attachment(session, [plain.id])
            with pytest.raises(ProblemError) as refused:
                await payment_files.ensure_no_payment_attachment(session, [plain.id, pay.id])
            assert refused.value.error.status == 422
            # Jobs: G2 closed by default (job resolver), the payment file is dropped.
            assert await payment_files.releasable_ids(session, tenant, [pay.id, plain.id]) == [
                plain.id
            ]
            original = blob_module.BlobStore
            blob_module.BlobStore = lambda _s: blobs  # type: ignore[assignment,misc,return-value]
            try:
                message = SimpleNamespace(
                    tenant_id=tenant, attachment_document_ids=[pay.id, plain.id]
                )
                out, expected = await forwarding_dispatch.load_attachments(
                    session,
                    settings,
                    message,  # type: ignore[arg-type]
                )
            finally:
                blob_module.BlobStore = original  # type: ignore[misc]
            assert expected == 2
            assert [name for name, _, _ in out] == ["n.xml"]

            contact = Contact(
                tenant_id=tenant,
                kind=ContactKind.PERSON,
                first_name="Erika",
                last_name="Ao",
                display_name="Erika Ao",
            )
            session.add(contact)
            await session.flush()
            session.add(
                ContactPhone(
                    tenant_id=tenant,
                    contact_id=contact.id,
                    label=PhoneLabel.MOBILE,
                    number="+4917012345",
                )
            )
            await session.flush()
            assert await whatsapp.contact_number(session, contact.id, "") == "+4917012345"
            assert (
                await whatsapp.contact_number(session, contact.id, "+49 170 12345") == "+4917012345"
            )
            with pytest.raises(ProblemError) as foreign:
                await whatsapp.contact_number(session, contact.id, "+4915199999")
            assert foreign.value.error.status == 422
    finally:
        await engine.dispose()


def test_ao06_attachment_paths_and_whatsapp_number(database: Database, redis_url: str) -> None:
    asyncio.run(_run(_settings(database, redis_url)))
