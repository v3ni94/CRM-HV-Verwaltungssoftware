"""Inspection requests outside the portal (A61, M25-04, section 14 phase boundary, PÜ12, PÜ13).

An owner asks to inspect the administrative documents of the community (statement, receipts,
contracts, resolutions). Until the owner portal covers this, the request, its release by a
user, the delivery and the retrieval are recorded here. Every status change writes an event
row; questions and answers are notes. The delivery package is a deterministic ZIP with an
index (JSON and CSV: file name, document category, date, SHA-256) over the selected documents
of the community that are released for owners (visibility ``owner``). The ZIP is stored as a
document linked to the request; every download of it is logged.

Product protection, no legal claim: which documents an owner may inspect, within which period
and in which form is an operator decision (docs/OPEN_QUESTIONS.md M25-05). The software never
derives a right to inspect from a status.
"""

import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentSource,
    LinkRole,
    StorageKind,
)
from mhvp.documents.services import store_document
from mhvp.properties.models import LegalEntity, LegalEntityKind

router = APIRouter(prefix="/hoa", tags=["hoa"])
# "hoa:write" of the gap list A61 maps to the matrix action ``update`` (section 3.4).
READ = require_permission("hoa:read")
WRITE = require_permission("hoa:update")

STATUSES = ("requested", "released", "provided", "retrieved", "closed", "rejected")
SCOPE_KINDS = ("statement", "receipts", "contracts", "resolutions")
DELIVERY_KINDS = ("portal", "data_medium", "on_site")
TRANSITIONS: dict[str, frozenset[str]] = {
    "requested": frozenset({"released", "rejected"}),
    "released": frozenset({"provided", "rejected"}),
    "provided": frozenset({"retrieved", "closed"}),
    "retrieved": frozenset({"closed"}),
    "closed": frozenset(),
    "rejected": frozenset(),
}
ENTITY = "hoa_inspection_request"
RELEASED_VISIBILITY = "owner"
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class InspectionRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "hoa_inspection_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'released', 'provided', 'retrieved', 'closed', 'rejected')",
            name="status",
        ),
        CheckConstraint(
            "delivery_kind IS NULL OR delivery_kind IN ('portal', 'data_medium', 'on_site')",
            name="delivery_kind",
        ),
        Index("ix_hoa_inspection_request_entity", "tenant_id", "legal_entity_id"),
        Index("ix_hoa_inspection_request_property", "tenant_id", "property_id"),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False)
    applicant_contact_id: Mapped[uuid.UUID] = _fk("contact.id", nullable=False)
    requested_on: Mapped[date] = mapped_column(Date, nullable=False)
    scope_text: Mapped[str | None] = mapped_column(Text)
    scope_kinds: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="requested")
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_kind: Mapped[str | None] = mapped_column(String(16))
    package_document_id: Mapped[uuid.UUID | None] = _fk("document.id", ondelete="SET NULL")
    package_sha256: Mapped[str | None] = mapped_column(String(64))
    package_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InspectionEvent(IdMixin, TenantMixin, Base):
    """Append-only trail: status changes, notes (questions and answers), package, retrieval."""

    __tablename__ = "hoa_inspection_event"
    __table_args__ = (
        CheckConstraint("kind IN ('status', 'note', 'package', 'retrieval')", name="kind"),
        Index("ix_hoa_inspection_event_request", "tenant_id", "request_id"),
    )

    request_id: Mapped[uuid.UUID] = _fk(
        "hoa_inspection_request.id", nullable=False, ondelete="CASCADE"
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # status, note, package, retrieval
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestIn(_In):
    legal_entity_id: uuid.UUID
    applicant_contact_id: uuid.UUID
    requested_on: date
    scope_text: str | None = Field(default=None, max_length=4000)
    scope_kinds: list[str] = Field(default_factory=list, max_length=4)


class InspectionTransitionIn(_In):
    status: str = Field(pattern="^(released|provided|retrieved|closed|rejected)$")
    note: str | None = Field(default=None, max_length=4000)
    delivery_kind: str | None = Field(default=None, pattern="^(portal|data_medium|on_site)$")


class InspectionNoteIn(_In):
    text: str = Field(min_length=1, max_length=4000)


class PackageIn(_In):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class InspectionEventOut(BaseModel):
    id: uuid.UUID
    kind: str
    from_status: str | None
    to_status: str | None
    note: str | None
    actor_user_id: uuid.UUID | None
    occurred_at: datetime


class RequestOut(BaseModel):
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    property_id: uuid.UUID
    applicant_contact_id: uuid.UUID
    requested_on: date
    scope_text: str | None
    scope_kinds: list[str]
    status: str
    released_by_user_id: uuid.UUID | None
    released_at: datetime | None
    delivery_kind: str | None
    package_document_id: uuid.UUID | None
    package_sha256: str | None
    package_created_at: datetime | None
    created_at: datetime
    events: list[InspectionEventOut] = Field(default_factory=list)


class PackageEntry(BaseModel):
    file: str
    document_id: uuid.UUID
    category: str | None
    date: date
    sha256: str
    bytes: int


class CandidateOut(BaseModel):
    """Document of the community offered for the package; ``released`` means owner visibility."""

    id: uuid.UUID
    filename: str
    title: str
    category: str | None
    created_at: datetime
    released: bool


class PackageOut(BaseModel):
    request_id: uuid.UUID
    document_id: uuid.UUID
    sha256: str
    entries: list[PackageEntry]


def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _blobs(request: Request) -> BlobStore:
    return BlobStore(request.app.state.settings)


async def _load(session: AsyncSession, request_id: uuid.UUID) -> InspectionRequest:
    row = await session.get(InspectionRequest, request_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _out(session: AsyncSession, row: InspectionRequest) -> RequestOut:
    events = (
        await session.scalars(
            select(InspectionEvent)
            .where(InspectionEvent.request_id == row.id)
            .order_by(InspectionEvent.occurred_at, InspectionEvent.id)
        )
    ).all()
    out = RequestOut.model_validate(row, from_attributes=True)
    out.events = [InspectionEventOut.model_validate(e, from_attributes=True) for e in events]
    return out


async def _trail(
    session: AsyncSession,
    principal: TenantPrincipal,
    row: InspectionRequest,
    *,
    kind: str,
    note: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    **payload: Any,
) -> None:
    session.add(
        InspectionEvent(
            tenant_id=principal.tenant_id,
            request_id=row.id,
            kind=kind,
            from_status=from_status,
            to_status=to_status,
            note=note,
            actor_user_id=principal.user_id,
            occurred_at=_now(),
        )
    )
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"hoa_inspection.{kind}",
        entity_type=ENTITY,
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"status": row.status, **{k: str(v) for k, v in payload.items()}},
    )


@router.get("/inspection-requests", summary="Einsichtsanfragen (A61)")
async def list_requests(
    request: Request,
    legal_entity_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[RequestOut]:
    async with tenant_tx(request, principal) as session:
        query = select(InspectionRequest).order_by(InspectionRequest.requested_on.desc())
        if legal_entity_id is not None:
            query = query.where(InspectionRequest.legal_entity_id == legal_entity_id)
        if property_id is not None:
            query = query.where(InspectionRequest.property_id == property_id)
        rows = (await session.scalars(query)).all()
        return [RequestOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/inspection-requests", status_code=201, summary="Einsichtsanfrage erfassen")
async def create_request(
    body: RequestIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> RequestOut:
    unknown = [k for k in body.scope_kinds if k not in SCOPE_KINDS]
    if unknown:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Umfang unbekannt: {', '.join(unknown)}.")
    if not body.scope_kinds and not (body.scope_text or "").strip():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Umfang der Einsicht fehlt.")
    async with tenant_tx(request, principal) as session:
        entity = await session.get(LegalEntity, body.legal_entity_id)
        if entity is None or entity.kind is not LegalEntityKind.HOA or entity.property_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Gemeinschaft mit Objekt.")
        if await session.get(Contact, body.applicant_contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Antragsteller fehlt.")
        row = InspectionRequest(
            tenant_id=principal.tenant_id,
            legal_entity_id=entity.id,
            property_id=entity.property_id,
            applicant_contact_id=body.applicant_contact_id,
            requested_on=body.requested_on,
            scope_text=body.scope_text,
            scope_kinds=sorted(set(body.scope_kinds)),
            status="requested",
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await _trail(session, principal, row, kind="status", to_status="requested")
        return await _out(session, row)


@router.get("/inspection-requests/{request_id}", summary="Einsichtsanfrage lesen")
async def get_request(
    request_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> RequestOut:
    async with tenant_tx(request, principal) as session:
        return await _out(session, await _load(session, request_id))


@router.get(
    "/inspection-requests/{request_id}/candidates", summary="Dokumente des Objekts für das Paket"
)
async def list_candidates(
    request_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[CandidateOut]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, request_id)
        linked = select(DocumentLink.document_id).where(
            DocumentLink.entity_type.in_(["legal_entity", "property"]),
            DocumentLink.entity_id.in_([row.legal_entity_id, row.property_id]),
        )
        docs = (
            await session.scalars(
                select(Document)
                .where(Document.id.in_(linked), Document.mime_type != "application/zip")
                .order_by(Document.filename)
            )
        ).all()
        categories = {c.id: c.code for c in (await session.scalars(select(DocumentCategory))).all()}
        return [
            CandidateOut(
                id=d.id,
                filename=d.filename,
                title=d.title,
                category=categories.get(d.category_id) if d.category_id else None,
                created_at=d.created_at,
                released=RELEASED_VISIBILITY in (d.visibility or []),
            )
            for d in docs
        ]


@router.post("/inspection-requests/{request_id}/transition", summary="Statuswechsel")
async def transition(
    request_id: uuid.UUID,
    body: InspectionTransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(WRITE),
) -> RequestOut:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, request_id)
        if body.status not in TRANSITIONS[row.status]:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Wechsel von {row.status} nach {body.status} nicht vorgesehen.",
            )
        if body.status == "released":
            if principal.user_id is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Freigabe nur durch einen Benutzer."
                )
            row.released_by_user_id = principal.user_id
            row.released_at = _now()
        if body.status == "provided":
            kind = body.delivery_kind or row.delivery_kind
            if kind is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Bereitstellungsart fehlt.")
            if kind != "on_site" and row.package_document_id is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Bereitstellungspaket fehlt (Portal oder Datenträger).",
                )
            row.delivery_kind = kind
        elif body.delivery_kind is not None:
            row.delivery_kind = body.delivery_kind
        if body.status == "rejected" and not (body.note or "").strip():
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ablehnung braucht eine Begründung.")
        previous = row.status
        row.status = body.status
        row.updated_by = principal.user_id
        await session.flush()
        await _trail(
            session,
            principal,
            row,
            kind="status",
            from_status=previous,
            to_status=body.status,
            note=body.note,
        )
        return await _out(session, row)


@router.post("/inspection-requests/{request_id}/notes", status_code=201, summary="Rückfrage")
async def add_note(
    request_id: uuid.UUID,
    body: InspectionNoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(WRITE),
) -> RequestOut:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, request_id)
        await _trail(session, principal, row, kind="note", note=body.text.strip())
        await session.flush()
        return await _out(session, row)


def _safe_name(document: Document, taken: set[str]) -> str:
    base = "".join(c if c.isalnum() or c in "._-" else "_" for c in document.filename) or "datei"
    name = base
    n = 2
    while name in taken:
        stem, dot, ext = base.rpartition(".")
        name = f"{stem}_{n}.{ext}" if dot else f"{base}_{n}"
        n += 1
    taken.add(name)
    return name


def build_package(entries: list[tuple[PackageEntry, bytes]]) -> bytes:
    """Deterministic ZIP: fixed timestamps, entries sorted by file name, index.json and
    index.csv with file name, category, date and SHA-256 per document."""
    ordered = sorted(entries, key=lambda e: e[0].file)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        def add(path: str, data: bytes) -> None:
            info = zipfile.ZipInfo(path, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)

        for entry, data in ordered:
            add(f"dokumente/{entry.file}", data)
        index = [
            {
                "file": e.file,
                "document_id": str(e.document_id),
                "category": e.category,
                "date": e.date.isoformat(),
                "sha256": e.sha256,
                "bytes": e.bytes,
            }
            for e, _ in ordered
        ]
        add("index.json", json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
        text = io.StringIO()
        writer = csv.writer(text, delimiter=";", lineterminator="\r\n")
        writer.writerow(["Dateiname", "Dokumentkategorie", "Datum", "SHA-256", "Bytes"])
        for e, _ in ordered:
            writer.writerow(
                [e.file, e.category or "", e.date.strftime("%d.%m.%Y"), e.sha256, e.bytes]
            )
        add("index.csv", text.getvalue().encode("utf-8-sig"))
    return buffer.getvalue()


@router.post("/inspection-requests/{request_id}/package", summary="Bereitstellungspaket erzeugen")
async def create_package(
    request_id: uuid.UUID,
    body: PackageIn,
    request: Request,
    principal: TenantPrincipal = Depends(WRITE),
) -> PackageOut:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, request_id)
        if row.status not in ("released", "provided"):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Paket nur nach Freigabe der Anfrage möglich."
            )
        wanted = list(dict.fromkeys(body.document_ids))
        docs = {
            d.id: d
            for d in (await session.scalars(select(Document).where(Document.id.in_(wanted)))).all()
        }
        linked = set(
            (
                await session.scalars(
                    select(DocumentLink.document_id).where(
                        DocumentLink.document_id.in_(wanted),
                        DocumentLink.entity_type.in_(["legal_entity", "property"]),
                        DocumentLink.entity_id.in_([row.legal_entity_id, row.property_id]),
                    )
                )
            ).all()
        )
        problems: list[str] = []
        for doc_id in wanted:
            doc = docs.get(doc_id)
            if doc is None:
                problems.append(f"{doc_id}: nicht gefunden")
            elif doc.id not in linked:
                problems.append(f"{doc.filename}: nicht dem Objekt zugeordnet")
            elif RELEASED_VISIBILITY not in (doc.visibility or []):
                problems.append(f"{doc.filename}: nicht für Eigentümer freigegeben")
            elif doc.storage is not StorageKind.MINIO:
                problems.append(f"{doc.filename}: keine lokale Kopie")
        if problems:
            raise ProblemError(ErrorCodes.VALIDATION, detail="; ".join(problems))
        categories = {c.id: c.code for c in (await session.scalars(select(DocumentCategory))).all()}
        blobs = _blobs(request)
        entries: list[tuple[PackageEntry, bytes]] = []
        taken: set[str] = set()
        for doc_id in sorted(wanted, key=lambda i: docs[i].filename):
            doc = docs[doc_id]
            data = blobs.get(doc.storage_ref)
            if _sha256(data) != doc.sha256:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail=f"{doc.filename}: Prüfsumme weicht vom Index ab."
                )
            entries.append(
                (
                    PackageEntry(
                        file=_safe_name(doc, taken),
                        document_id=doc.id,
                        category=categories.get(doc.category_id) if doc.category_id else None,
                        date=doc.created_at.date(),
                        sha256=doc.sha256,
                        bytes=len(data),
                    ),
                    data,
                )
            )
        package = build_package(entries)
        document = await store_document(
            session,
            blobs,
            tenant_id=principal.tenant_id,
            data=package,
            title=f"Einsichtspaket {row.requested_on:%d.%m.%Y}",
            filename=f"einsicht-{row.id}.zip",
            mime_type="application/zip",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("legal_entity", row.legal_entity_id, LinkRole.GENERATED)],
            created_by=principal.user_id,
            visibility=["tenant"],
        )
        # Link to the request itself (the request is no generic link target of the documents
        # API, so the row is added here; the link table carries no foreign key on entity_id).
        session.add(
            DocumentLink(
                tenant_id=principal.tenant_id,
                document_id=document.id,
                entity_type=ENTITY,
                entity_id=row.id,
                role=LinkRole.GENERATED,
            )
        )
        row.package_document_id = document.id
        row.package_sha256 = document.sha256
        row.package_created_at = _now()
        row.updated_by = principal.user_id
        await session.flush()
        await _trail(
            session,
            principal,
            row,
            kind="package",
            note=f"{len(entries)} Dokumente, SHA-256 {document.sha256}",
            document_id=document.id,
            sha256=document.sha256,
        )
        return PackageOut(
            request_id=row.id,
            document_id=document.id,
            sha256=document.sha256,
            entries=[e for e, _ in entries],
        )


@router.get("/inspection-requests/{request_id}/package", summary="Bereitstellungspaket abrufen")
async def download_package(
    request_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, request_id)
        if row.package_document_id is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kein Paket vorhanden.")
        document = await session.get(Document, row.package_document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Paketdokument fehlt.")
        data = _blobs(request).get(document.storage_ref)
        if _sha256(data) != document.sha256:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Prüfsumme des Pakets weicht ab.")
        previous = row.status
        if row.status == "provided":
            row.status = "retrieved"
        await _trail(
            session,
            principal,
            row,
            kind="retrieval",
            from_status=previous,
            to_status=row.status if row.status != previous else None,
            note=f"Abruf durch Benutzer, SHA-256 {document.sha256}",
            document_id=document.id,
        )
        filename = document.filename
        mime = document.mime_type
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
