"""Document services: store originals, index text, link, mirror, retention, letters (6.7, 11)."""

import hashlib
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, ContactAddress
from mhvp.contracts.models import Contract
from mhvp.core.ids import uuid7
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentLink,
    DocumentMirror,
    DocumentSource,
    LinkRole,
    MirrorStatus,
    RetentionProfile,
    StorageKind,
)
from mhvp.documents.text import ALLOWED_MIME_TYPES, extract, sniff_matches
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import Building, LegalEntity, Property, Unit

# Entities a document may be linked to, with the model used to verify existence (RLS applies).
LINKABLE: dict[str, Any] = {
    "contact": Contact,
    "property": Property,
    "building": Building,
    "unit": Unit,
    "contract": Contract,
    # GdWE and other legal entities: administrative documents of the community (§ 18 Abs. 4 WEG).
    "legal_entity": LegalEntity,
}
VISIBILITY = frozenset({"tenant", "owner", "provider", "board"})


def invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


def check_upload(mime_type: str, data: bytes, max_bytes: int) -> None:
    if not data:
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Die Datei ist leer.")
    if len(data) > max_bytes:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail=f"Die Datei ist größer als {max_bytes // (1024 * 1024)} MB.",
        )
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED, detail=f"Dateityp {mime_type} ist nicht zulässig."
        )
    if not sniff_matches(mime_type, data):
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED, detail="Der Dateiinhalt passt nicht zum Dateityp."
        )


async def check_link_target(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
    model = LINKABLE.get(entity_type)
    if model is None:
        raise invalid(f"Verknüpfung mit {entity_type!r} ist nicht vorgesehen.")
    if await session.get(model, entity_id) is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Verknüpfungsziel fehlt.")


async def store_document(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    tenant_id: uuid.UUID,
    data: bytes,
    title: str,
    filename: str,
    mime_type: str,
    source: DocumentSource,
    category_id: uuid.UUID | None,
    links: list[tuple[str, uuid.UUID, LinkRole]],
    created_by: uuid.UUID | None,
    visibility: list[str] | None = None,
) -> Document:
    """Index row, links and mirror jobs in this transaction; the original goes to S3 first.

    If the transaction rolls back after the upload, an unreferenced object remains under a fresh
    key. It carries no index entry and is never served; cleaning such objects is open (M6-02).
    """
    for entity_type, entity_id, _ in links:
        await check_link_target(session, entity_type, entity_id)
    text, status = extract(mime_type, data)
    document_id = uuid7()
    sha256 = hashlib.sha256(data).hexdigest()
    key = BlobStore.key(tenant_id, document_id)
    blobs.put(key, data, mime_type, sha256)
    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        title=title[:300],
        filename=filename[:255],
        mime_type=mime_type,
        size=len(data),
        sha256=sha256,
        storage=StorageKind.MINIO,
        storage_ref=key,
        category_id=category_id,
        ocr_text=text,
        text_status=status,
        source=source,
        visibility=visibility or ["tenant"],
        created_by=created_by,
    )
    session.add(document)
    await session.flush()
    for entity_type, entity_id, role in links:
        session.add(
            DocumentLink(
                tenant_id=tenant_id,
                document_id=document.id,
                entity_type=entity_type,
                entity_id=entity_id,
                role=role,
            )
        )
    await queue_mirrors(session, tenant_id, document.id)
    await session.flush()
    return document


async def queue_mirrors(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> int:
    kinds = (
        await session.scalars(select(DmsConnection.kind).where(DmsConnection.enabled.is_(True)))
    ).all()
    for kind in kinds:
        exists = await session.scalar(
            select(DocumentMirror.id).where(
                DocumentMirror.document_id == document_id, DocumentMirror.kind == kind
            )
        )
        if exists is None:
            session.add(
                DocumentMirror(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    kind=kind,
                    status=MirrorStatus.PENDING,
                    next_attempt_at=datetime.now(UTC),
                )
            )
    return len(kinds)


async def deletion_blocker(session: AsyncSession, document: Document, today: date) -> str | None:
    """Reason why the document must be kept, or None (6.9.5, D43, D46)."""
    if document.retention_hold_reason:
        return f"Löschungssperre: {document.retention_hold_reason}"
    if document.retention_profile_id is None:
        return "Kein Aufbewahrungsprofil zugeordnet (Aufbewahrungsmatrix V17 offen)."
    profile = await session.get(RetentionProfile, document.retention_profile_id)
    if profile is None or profile.released_at is None:
        return "Das Aufbewahrungsprofil ist nicht freigegeben."
    if document.retention_until is None or document.retention_until >= today:
        return "Die Aufbewahrungsfrist ist nicht abgelaufen."
    return None


# Letters ---------------------------------------------------------------------------------


def _fmt_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


async def letterhead(session: AsyncSession, blobs: BlobStore | None) -> letters.Letterhead:
    settings = await session.scalar(select(TenantSettings))
    company = dict(settings.company) if settings else {}
    branding = dict(settings.branding) if settings else {}
    head = letters.Letterhead(company=company, branding=branding)
    missing = head.missing_mandatory()
    if missing:
        raise ProblemError(
            ErrorCodes.LETTERHEAD_INCOMPLETE,
            detail=f"Fehlende Firmendaten des Mandanten: {', '.join(missing)}.",
        )
    logo_id = branding.get("logo_light_document_id")
    if logo_id and blobs is not None:
        logo = await session.get(Document, uuid.UUID(str(logo_id)))
        if logo is not None and logo.mime_type in ("image/png", "image/jpeg"):
            head.logo = blobs.get(logo.storage_ref)
    return head


async def recipient(
    session: AsyncSession, contact_id: uuid.UUID
) -> tuple[Contact, list[str], dict[str, Any]]:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Empfänger nicht gefunden.")
    address = await session.scalar(
        select(ContactAddress)
        .where(ContactAddress.contact_id == contact.id)
        .order_by(ContactAddress.is_primary.desc(), ContactAddress.created_at)
        .limit(1)
    )
    if address is None or not (address.street and address.postal_code and address.city):
        raise invalid(f"Für {contact.display_name} ist keine vollständige Anschrift erfasst.")
    lines = [contact.display_name]
    if address.addition:
        lines.append(address.addition)
    lines.append(" ".join(p for p in (address.street, address.house_number) if p))
    lines.append(f"{address.postal_code} {address.city}")
    if address.country and address.country != "DE":
        lines.append(address.country)
    # Salutation only from recorded data; otherwise the neutral form (no guessed gender).
    if contact.salutation and contact.last_name:
        name = " ".join(p for p in (contact.title, contact.last_name) if p)
        form = {"Herr": "Sehr geehrter Herr", "Frau": "Sehr geehrte Frau"}.get(contact.salutation)
        greeting = f"{form} {name}," if form else "Sehr geehrte Damen und Herren,"
    else:
        greeting = "Sehr geehrte Damen und Herren,"
    data = {
        "name": contact.display_name,
        "vorname": contact.first_name or "",
        "nachname": contact.last_name or "",
        "firma": contact.company_name or "",
        "anrede": greeting,
        "strasse": address.street,
        "hausnummer": address.house_number or "",
        "plz": address.postal_code,
        "ort": address.city,
    }
    return contact, lines, data


async def entity_context(
    session: AsyncSession,
    property_id: uuid.UUID | None,
    unit_id: uuid.UUID | None,
    contract_id: uuid.UUID | None,
) -> tuple[dict[str, Any], list[tuple[str, str]], list[tuple[str, uuid.UUID]]]:
    context: dict[str, Any] = {}
    info: list[tuple[str, str]] = []
    links: list[tuple[str, uuid.UUID]] = []
    contract = await session.get(Contract, contract_id) if contract_id else None
    if contract_id and contract is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht gefunden.")
    if contract is not None:
        unit_id = unit_id or contract.unit_id
        property_id = property_id or contract.property_id
        context["vertrag"] = {
            "nummer": contract.number,
            "beginn": _fmt_date(contract.start_date),
            "ende": _fmt_date(contract.end_date),
        }
        links.append(("contract", contract.id))
    unit = await session.get(Unit, unit_id) if unit_id else None
    if unit_id and unit is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Einheit nicht gefunden.")
    if unit is not None:
        property_id = property_id or unit.property_id
        context["einheit"] = {"nummer": unit.number, "bezeichnung": unit.label or unit.number}
        links.append(("unit", unit.id))
    prop = await session.get(Property, property_id) if property_id else None
    if property_id and prop is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Objekt nicht gefunden.")
    if prop is not None:
        context["objekt"] = {
            "nummer": prop.number,
            "name": prop.name,
            "strasse": prop.street or "",
            "hausnummer": prop.house_number or "",
            "plz": prop.postal_code or "",
            "ort": prop.city or "",
        }
        info.append(("Objekt", f"{prop.number} {prop.name}"))
        links.append(("property", prop.id))
    if unit is not None:
        info.append(("Einheit", unit.label or unit.number))
    return context, info, links
