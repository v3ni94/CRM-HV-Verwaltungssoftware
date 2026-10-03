"""Document services: store originals, index text, link, mirror, retention, letters (6.7, 11)."""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.models import Statement
from mhvp.contacts.models import Contact, ContactAddress
from mhvp.contracts.models import Contract
from mhvp.core.config import Settings
from mhvp.core.escaping import sanitize_filename
from mhvp.core.events import emit
from mhvp.core.ids import uuid7
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters, retention, scan
from mhvp.documents.blobs import BlobStore
from mhvp.documents.dms import DmsError, GoogleDriveStore
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentLink,
    DocumentMirror,
    DocumentRedaction,
    DocumentSource,
    LinkRole,
    MirrorStatus,
    RetentionProfile,
    StorageKind,
)
from mhvp.documents.text import ALLOWED_MIME_TYPES, extract, sniff_matches
from mhvp.handover.models import (
    HandoverDefect,
    HandoverItem,
    HandoverMeter,
    HandoverProtocol,
    HandoverRoom,
)
from mhvp.hoa.models import (
    HoaAssetReport,
    HoaInsuranceClaim,
    HoaLoan,
    HoaMeasure,
    HoaStatement,
)
from mhvp.letting.models import Listing, RentIncreaseCase
from mhvp.objektakte.drive_quota import drive_http_client
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import Building, LegalEntity, Property, Unit
from mhvp.tickets.models import Ticket, WorkOrder

# Entities a document may be linked to, with the model used to verify existence (RLS applies).
LINKABLE: dict[str, Any] = {
    "contact": Contact,
    "property": Property,
    "building": Building,
    "unit": Unit,
    "contract": Contract,
    # GdWE and other legal entities: administrative documents of the community (§ 18 Abs. 4 WEG).
    "legal_entity": LegalEntity,
    # Handover protocols (M30): photos, attachments, signatures and the final PDF.
    "handover_protocol": HandoverProtocol,
    "handover_meter": HandoverMeter,
    "handover_room": HandoverRoom,
    "handover_defect": HandoverDefect,
    "handover_item": HandoverItem,
    # Listings (M26-02): images and attachments of an advertisement; the OpenImmo export reads
    # image documents linked with entity_type "listing".
    "listing": Listing,
    # Rent increase letters on the letterhead (M12 gaps, 29.09.2026).
    "rent_increase_case": RentIncreaseCase,
    # Tickets (A55): photos of a damage report from the portal and other attachments.
    "ticket": Ticket,
    # Work orders (A58): photos of the execution documented by the provider in the portal.
    "work_order": WorkOrder,
    # WEG loans, insurance claims and measures (W10, A59): contracts, claim files, offers.
    "hoa_loan": HoaLoan,
    "hoa_insurance_claim": HoaInsuranceClaim,
    "hoa_measure": HoaMeasure,
    # AC05: generated documents hang directly at the asset report (GA07-02) and the
    # operating cost statement run (GA06-02, GA06-03).
    "asset_report": HoaAssetReport,
    "statement": Statement,
    # GAB-06: filed hoa statement PDFs (individual and total) hang at the statement.
    "hoa_statement": HoaStatement,
    # Released version of another document (E06, D31): a redacted copy links to its original
    # with role "generated"; the portal shows the copy with a redaction note, never the original.
    "document": Document,
}
VISIBILITY = frozenset({"tenant", "owner", "provider", "board"})


_log = get_logger("mhvp.documents")


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
    scan_for_malware: bool = True,
    settings: Settings | None = None,
    event_payload: dict[str, Any] | None = None,
) -> Document:
    """Index row, links and mirror jobs in this transaction; the original goes to S3 first.
    ``settings`` (the app settings) decide the upload to objektakte; without them the
    environment is read (``mhvp.objektakte.upload.plan``).

    Every file is scanned with ClamAV before the blob is written (``mhvp.documents.scan``,
    operator decision 27.09.2026): uploads, portal files, mail attachments, metering and
    import documents alike. PDFs rendered by the platform itself (``DocumentSource.GENERATED``)
    are skipped; callers may also pass ``scan_for_malware=False`` for such content.

    If the transaction rolls back after the upload, an unreferenced object remains under a fresh
    key. It carries no index entry and is never served; cleaning such objects is open (M6-02).
    """
    for entity_type, entity_id, _ in links:
        await check_link_target(session, entity_type, entity_id)
    filename, filename_flagged = sanitize_filename(filename)
    if filename_flagged:
        # Doppelendung wie ".pdf.exe" (Sicherheitspruefung 27.09.2026, Befund 4 /
        # OE-M27-02-02): der Name wird trotzdem gespeichert (MIME-Allowlist und Magic-Byte-
        # Pruefung entscheiden ueber den tatsaechlichen Inhalt), aber fuer die Nachvollziehbarkeit
        # protokolliert.
        _log.warning(
            "document.filename_double_extension",
            tenant_id=str(tenant_id),
            filename=filename,
            source=str(source),
        )
    sha256 = hashlib.sha256(data).hexdigest()
    if scan_for_malware and source is not DocumentSource.GENERATED:
        await scan.scan_before_store(
            session,
            blobs.settings,
            tenant_id=tenant_id,
            data=data,
            filename=filename,
            sha256=sha256,
            source=str(source),
            actor_user_id=created_by,
        )
    text, status = extract(mime_type, data)
    document_id = uuid7()
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
    # Retention matrix (M6-04): the category's mapped profile and the computed period; a
    # profile of the document's legal entity kind wins, a GdWE declaration of division or
    # minutes is a permanent record (S711-06).
    kinds = await retention.legal_entity_kinds(session, [(t, i) for t, i, _ in links])
    await retention.assign_profile(
        session, document, await retention.profile_for_document(session, category_id, kinds)
    )
    if await retention.is_permanent_record(session, category_id, kinds):
        document.permanent_record = True
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
    from mhvp.objektakte import upload as objektakte_upload  # local: avoids an import cycle

    await objektakte_upload.plan(session, tenant_id, document.id, settings)
    await queue_mirrors(session, tenant_id, document.id)
    # Webhook event for every new document, whatever the source (section 12, GAB-07):
    # uploads, generated letters, intake, Paperless webhook, dunning and imports alike.
    # ``event_payload`` carries caller context (list kind, listing); values are stringified.
    payload: dict[str, Any] = {"size": document.size, "source": str(source)}
    for k, v in (event_payload or {}).items():
        payload[k] = v if isinstance(v, int | bool | None) else str(v)
    await emit(
        session,
        tenant_id=tenant_id,
        type="document.created",
        entity_type="document",
        entity_id=document.id,
        actor_user_id=created_by,
        payload=payload,
    )
    await session.flush()
    return document


async def queue_mirrors(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> int:
    """Mirror jobs for every enabled DMS connection. A document handed to objektakte
    (``mhvp.objektakte.upload``) gets no Paperless or Drive mirror: objektakte files it there."""
    from mhvp.objektakte import upload as objektakte_upload  # local: avoids an import cycle

    kinds = (
        await session.scalars(select(DmsConnection.kind).where(DmsConnection.enabled.is_(True)))
    ).all()
    if await objektakte_upload.is_routed(session, document_id):
        kinds = [k for k in kinds if k not in (StorageKind.PAPERLESS, StorageKind.GOOGLE_DRIVE)]
    from mhvp.documents import payment_files  # local: avoids an import cycle

    if await payment_files.payment_file_ids(session, [document_id]):
        return 0  # GAJ-301: payment files never leave the platform through a DMS mirror
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
    ticket_hold = await retention.ticket_hold(session, document.id)
    if ticket_hold:
        return f"Löschungssperre am Vorgang: {ticket_hold}"
    procedure = await retention.procedure_hold(session, document.id)
    if procedure:
        return f"Automatische Löschungssperre: offenes Verfahren ({procedure})."
    related = await retention.related_hold(session, document.id)
    if related:
        return f"Löschungssperre am verbundenen Dokument: {related}"
    if document.permanent_record:
        return "WEG-Dauerunterlage: bleibt unabhängig vom Standardprofil erhalten (S05)."
    if await session.scalar(
        select(DocumentRedaction.id)
        .where(DocumentRedaction.original_document_id == document.id)
        .limit(1)
    ):
        return "Zu diesem Original bestehen geschwärzte Kopien; diese zuerst löschen."
    if document.retention_profile_id is None:
        return "Kein Aufbewahrungsprofil zugeordnet (Aufbewahrungsmatrix V17 offen)."
    profile = await session.get(RetentionProfile, document.retention_profile_id)
    if profile is None or profile.released_at is None:
        return "Das Aufbewahrungsprofil ist nicht freigegeben (Entwurf, M6-04)."
    if profile.permanent:
        return "Dauerhaft aufzubewahren (WEG-Dauerunterlage, S05)."
    if document.retention_until is None:
        if retention.needs_base_date(profile) and document.retention_base_on is None:
            return "Der Fristbeginn fehlt (Vertragsende, letzte Eintragung oder Zweckende)."
        return "Die Aufbewahrungsfrist ist nicht berechnet."
    if document.retention_until >= today:
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


async def recipient_name(session: AsyncSession, contact_id: uuid.UUID) -> str:
    """Display name of a represented contact for the address block of a representative."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Empfänger nicht gefunden.")
    return str(contact.display_name)


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


async def download_from_drive(session: AsyncSession, request: Request, document: Document) -> bytes:
    """Original content of a `storage=google_drive` document (M35 Stufe 2 takeover): no local
    copy exists, `storage_ref` is the Drive file id itself, the same convention
    `mhvp.documents.dms.GoogleDriveStore.put`/`resolve` use for a mirrored document's
    `external_ref`, so the existing Drive connection and client both work unchanged.
    """
    connection = await session.scalar(
        select(DmsConnection).where(DmsConnection.kind == StorageKind.GOOGLE_DRIVE)
    )
    if connection is None or not connection.enabled or not connection.secret:
        raise ProblemError(
            ErrorCodes.RESOURCE_NOT_FOUND,
            detail="Keine Google-Drive-Anbindung eingerichtet, das Original ist nicht abrufbar.",
        )
    secret = json.loads(connection.secret or "{}")
    options = connection.options or {}
    timeout = getattr(request.app.state, "http_timeout", 60.0)
    # M35-06: rate limiting and backoff against the Drive quota (mhvp.objektakte.drive_quota).
    async with drive_http_client(timeout=timeout) as client:
        store = GoogleDriveStore(
            root_folder_id=str(options.get("root_folder_id", "")),
            client_id=str(options.get("client_id", "")),
            client_secret=str(secret.get("client_secret", "")),
            refresh_token=str(secret.get("refresh_token", "")),
            client=client,
        )
        try:
            return await store.download(document.storage_ref)
        except (DmsError, httpx.HTTPError) as exc:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Original in Google Drive nicht abrufbar."
            ) from exc


async def mark_mirrors_dirty(session: AsyncSession, document_id: uuid.UUID) -> None:
    """M6-06: flags the finished mirrors of a document so the mirror job pushes the changed
    metadata (title, category, links) via ``DocumentStore.update_meta``."""
    await session.execute(
        update(DocumentMirror)
        .where(
            DocumentMirror.document_id == document_id,
            DocumentMirror.status == MirrorStatus.DONE,
        )
        .values(meta_dirty=True)
    )
