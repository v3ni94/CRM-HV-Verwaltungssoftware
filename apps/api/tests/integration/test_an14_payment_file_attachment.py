"""AN14-01 (GAJ-301): an outgoing mail never carries a payment file as attachment while
release gate G2 is closed; with G2 open, or for an ordinary document, the attachment is added."""

import asyncio
from email.message import EmailMessage
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from mhvp.core.release_gates import ReleaseGate
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration


class _Gates:
    def __init__(self, open_: bool) -> None:
        self.open_ = open_

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return self.open_ and gate is ReleaseGate.G2


class _Blobs:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, *args: Any, **kwargs: Any) -> None:
        self.data[key] = data

    def get(self, key: str) -> bytes:
        return self.data[key]


async def _run(settings: Any) -> None:
    from mhvp.communication import attachments
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.problems import ProblemError
    from mhvp.documents import payment_files
    from mhvp.documents import services as docs
    from mhvp.documents.models import DocumentSource

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    tenant, _ = await services.provision_tenant(
        factory, slug=f"an14-{RUN}", name=f"AN14 Anhang {RUN}"
    )
    blobs = _Blobs()

    def request(open_: bool) -> Any:
        state = SimpleNamespace(settings=settings, release_gate_resolver=_Gates(open_))
        return SimpleNamespace(app=SimpleNamespace(state=state))

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
            from mhvp.documents import blobs as blob_module

            original = blob_module.BlobStore
            blob_module.BlobStore = lambda _s: blobs  # type: ignore[assignment,misc,return-value]
            try:
                msg = EmailMessage()
                assert (
                    await attachments.attach_documents(session, request(False), msg, [plain.id])
                    == 1
                )
                with pytest.raises(ProblemError) as refused:
                    await attachments.attach_documents(
                        session, request(False), EmailMessage(), [pay.id]
                    )
                assert refused.value.error.code == "MHVP-GATE-0001"
                assert (
                    await attachments.attach_documents(
                        session, request(True), EmailMessage(), [pay.id]
                    )
                    == 1
                )
            finally:
                blob_module.BlobStore = original  # type: ignore[misc]
    finally:
        await engine.dispose()


def test_payment_file_attachment_needs_g2(database: Database, redis_url: str) -> None:
    asyncio.run(_run(_settings(database, redis_url)))
