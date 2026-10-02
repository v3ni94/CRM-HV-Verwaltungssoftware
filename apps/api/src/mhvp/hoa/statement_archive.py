"""GAB-06 (11.3): hoa statement PDFs are filed once in the DMS and served from there.

The first output of a released statement (individual statement per unit, total statement)
renders the PDF from the stored snapshot and files it via ``documents.services.store_document``
with links to the statement, the property, the community, the unit and the owner contacts of
the statement year. Every later retrieval (CRM and owner portal) returns exactly the filed
bytes (snapshot fidelity: a later letter date or layout change never alters an issued
document). The filename carries the snapshot hash prefix, so a new version (new snapshot)
yields a new document while the old one stays unchanged. Filing changes no statement values
and needs the same gate G4 as the output itself (callers check it first).
"""

import hashlib
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole
from mhvp.hoa.models import HoaStatement

ENTITY = "hoa_statement"


def archive_filename(st: HoaStatement, unit_number: str | None) -> str:
    """Deterministic name per statement, kind and snapshot (the lookup key of the archive)."""
    tag = (st.snapshot_hash or "")[:12] or "ohnehash"
    if unit_number is None:
        return f"gesamtabrechnung-{st.year}-v{st.version}-{tag}.pdf"
    return f"hausgeldabrechnung-{st.year}-{unit_number}-v{st.version}-{tag}.pdf"


async def _owner_contacts(session: AsyncSession, unit_id: uuid.UUID, year: int) -> list[uuid.UUID]:
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract, ContractKind

    rows = await session.scalars(
        select(PartyMember.contact_id)
        .join(Contract, Contract.party_id == PartyMember.party_id)
        .where(
            Contract.kind == ContractKind.OWNERSHIP,
            Contract.unit_id == unit_id,
            Contract.start_date <= date(year, 12, 31),
            or_(Contract.end_date.is_(None), Contract.end_date >= date(year, 1, 1)),
        )
        .distinct()
    )
    return list(rows)


async def find_archived(session: AsyncSession, st: HoaStatement, filename: str) -> Document | None:
    return (
        await session.scalars(
            select(Document)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(
                DocumentLink.entity_type == ENTITY,
                DocumentLink.entity_id == st.id,
                DocumentLink.role == LinkRole.GENERATED,
                Document.filename == filename,
            )
            .order_by(Document.created_at)
            .limit(1)
        )
    ).first()


async def archived_pdf(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    st: HoaStatement,
    property_id: uuid.UUID | None,
    legal_entity_id: uuid.UUID | None,
    unit: dict[str, Any] | None,
    render: Callable[[], bytes],
    created_by: uuid.UUID | None,
) -> tuple[bytes, Document]:
    """Filed PDF of ``st`` (``unit`` None: total statement); files it on first call."""
    unit_number = None if unit is None else str(unit["unit_number"])
    filename = archive_filename(st, unit_number)
    # Serialise concurrent first outputs of the same document (idempotent filing).
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"{st.tenant_id}:{st.id}:{filename}"},
    )
    doc = await find_archived(session, st, filename)
    if doc is not None:
        data = blobs.get(doc.storage_ref)
        if hashlib.sha256(data).hexdigest() != doc.sha256:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Abgelegte Abrechnung weicht vom Prüfwert ab."
            )
        return data, doc
    data = render()
    links: list[tuple[str, uuid.UUID, LinkRole]] = [(ENTITY, st.id, LinkRole.GENERATED)]
    if property_id is not None:
        links.append(("property", property_id, LinkRole.GENERATED))
    if legal_entity_id is not None:
        links.append(("legal_entity", legal_entity_id, LinkRole.GENERATED))
    title = f"Gesamtabrechnung {st.year} (Version {st.version})"
    if unit is not None:
        unit_id = uuid.UUID(str(unit["unit_id"]))
        links.append(("unit", unit_id, LinkRole.GENERATED))
        for contact_id in await _owner_contacts(session, unit_id, st.year):
            links.append(("contact", contact_id, LinkRole.GENERATED))
        title = f"Hausgeldabrechnung {st.year} Einheit {unit_number} (Version {st.version})"
    from mhvp.documents.services import store_document

    doc = await store_document(
        session,
        blobs,
        tenant_id=st.tenant_id,
        data=data,
        title=title,
        filename=filename,
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=links,
        created_by=created_by,
        visibility=["tenant", "owner"] if unit is not None else ["tenant"],
        scan_for_malware=False,
        settings=blobs.settings,
    )
    return data, doc
