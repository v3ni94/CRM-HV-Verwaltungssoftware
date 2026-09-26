"""Document inbox pipeline (A42, master prompt 11.4, 15.1): text, classification, assignment.

Job ``mhvp.documents.process_inbox`` (beat, daily 06:30) collects, per active tenant, the
documents that arrived since the tenant's watermark from three sources:

* Paperless-ngx: documents added after the watermark (``PaperlessSearch.list_added_since``),
  indexed once as a platform document (``source_system="paperless"``) exactly like the
  post-consume webhook does; documents the mirror job pushed there itself are skipped by
  their mirror reference.
* Google Drive inbox folder: only when ``DmsConnection.options["inbox_folder_id"]`` is set
  (``GoogleDriveStore.list_folder``), indexed once (``source_system="google_drive"``).
* Mailbox: inbound ``Message`` attachments that carry no document link yet.

Every document then runs through the same three steps and ends in a **proposal**
(``AiProposal`` with ``entity_type="document_intake"``, one per document, idempotent), never in
a link, a category or a contact (rule 0.1.6). Text comes from the existing index (``ocr_text``
from the upload path, or Paperless' OCR content); classification reuses the tenant's
objektakte rules and the category names; assignment looks for the three digit object number,
the object address and the sender or a contact name. Confidence and a German reasoning list are
stored with the proposal; ``intake_routers`` offers accept and reject.

Watermarks: Paperless and Drive keep theirs in ``DmsConnection.options`` (string keys
``intake_watermark``), the mailbox source in ``TenantSettings.sources``
(``document_intake_mailbox_watermark``). A rerun with the same watermark creates nothing twice
because a proposal already exists per document.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
from botocore.exceptions import ClientError
from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.ai.models import AiExample, AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.communication.models import Message
from mhvp.contacts.models import Contact, ContactEmail
from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ProblemError
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.dms import DmsError, GoogleDriveStore
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentMirror,
    DocumentSource,
    MirrorStatus,
    StorageKind,
    TextStatus,
)
from mhvp.documents.paperless_search import PaperlessSearch, PaperlessSearchError
from mhvp.documents.text import ALLOWED_MIME_TYPES
from mhvp.objektakte.classification import rule_candidates
from mhvp.platform.models import Tenant, TenantSettings, TenantStatus
from mhvp.properties.models import Property

log = logging.getLogger(__name__)

ENTITY_TYPE = "document_intake"
PROMPT_VERSION = "intake-rules-v1"
SOURCE_PAPERLESS = "paperless"
SOURCE_DRIVE = "google_drive"
SOURCE_MAILBOX = "mailbox"
WATERMARK_KEY = "intake_watermark"
INBOX_FOLDER_KEY = "inbox_folder_id"
MAILBOX_WATERMARK_KEY = "document_intake_mailbox_watermark"
PAGE_SIZE = 50
MAX_PER_SOURCE = 500
TIMEOUT_SECONDS = 60.0
TEXT_LIMIT = 200_000

# "Objekt 602", "Obj. 602", "Objektnummer 602", "602 Monheim" or a bare three digit number.
OBJECT_HINT_RE = re.compile(r"\bObj(?:ekt)?(?:nummer|\.|\s*Nr\.?)?\s*[:#]?\s*(\d{3})\b", re.I)
THREE_DIGITS_RE = re.compile(r"(?<![\d,.])(\d{3})(?![\d,.])")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass
class Candidate:
    id: str
    label: str
    confidence: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
        }


@dataclass
class IntakeResult:
    source: str
    text_status: str
    classification: dict[str, Any] | None = None
    category_candidates: list[Candidate] = field(default_factory=list)
    property_candidates: list[Candidate] = field(default_factory=list)
    contact_candidates: list[Candidate] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        parts = [
            c[0].confidence
            for c in (self.category_candidates, self.property_candidates, self.contact_candidates)
            if c
        ]
        return round(sum(parts) / len(parts), 2) if parts else 0.0

    def as_dict(self) -> dict[str, Any]:
        best_cat = self.category_candidates[0] if self.category_candidates else None
        best_prop = self.property_candidates[0] if self.property_candidates else None
        best_contact = self.contact_candidates[0] if self.contact_candidates else None
        return {
            "source": self.source,
            "text_status": self.text_status,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "classification": self.classification,
            "category_id": best_cat.id if best_cat else None,
            "category_name": best_cat.label if best_cat else None,
            "property_id": best_prop.id if best_prop else None,
            "property_number": best_prop.label if best_prop else None,
            "contact_id": best_contact.id if best_contact else None,
            "contact_name": best_contact.label if best_contact else None,
            "candidates": {
                "categories": [c.as_dict() for c in self.category_candidates],
                "properties": [c.as_dict() for c in self.property_candidates],
                "contacts": [c.as_dict() for c in self.contact_candidates],
            },
        }


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


# Pipeline steps ----------------------------------------------------------------------------


def document_text(document: Document, extra: str | None = None) -> tuple[str, str]:
    """Text basis and its status; the existing index is reused, no second OCR here."""
    parts = [document.title, document.filename, extra or "", document.ocr_text or ""]
    text = "\n".join(p for p in parts if p)[:TEXT_LIMIT]
    status = document.text_status.value if document.ocr_text else TextStatus.PENDING.value
    return text, status


async def classify(
    session: AsyncSession, tenant_id: uuid.UUID, document: Document, text: str
) -> tuple[dict[str, Any] | None, list[Candidate], list[str]]:
    """Objektakte rules first (with rejected examples lowering the score), then a plain
    category name match as a weaker fallback."""
    reasons: list[str] = []
    candidates: list[Candidate] = []
    classification: dict[str, Any] | None = None
    rules = await rule_candidates(session, tenant_id, document)
    if rules:
        rejected = await _rejected_rule_counts(session)
        best = None
        for rule in rules:
            score = rule.score
            count = rejected.get(rule.rule_id, 0)
            if count:
                score = round(score * (0.5**count), 2)
            if best is None or score > best[0]:
                best = (score, rule, count)
        assert best is not None  # noqa: S101 - rules is non-empty
        score, rule, count = best
        classification = {
            "stage": "rules",
            "rule_id": rule.rule_id,
            "rule_name": rule.rule_name,
            "pattern_type": rule.pattern_type,
            "matched": rule.matched,
            "category_id": rule.category_id,
            "document_type": rule.document_type,
            "confidence": score,
            "rejected_examples": count,
        }
        reason = f"Regel '{rule.rule_name}' ({rule.pattern_type}) trifft auf '{rule.matched}' zu."
        if count:
            reason += f" Vorschläge dieser Regel wurden bereits {count} mal abgelehnt."
        reasons.append(reason)
        if rule.category_id:
            category = await session.get(DocumentCategory, uuid.UUID(rule.category_id))
            if category is not None:
                candidates.append(Candidate(str(category.id), category.name, score, reason))
    if not candidates:
        lowered = text.lower()
        rows = (await session.scalars(select(DocumentCategory))).all()
        for category in rows:
            name = category.name.strip()
            if len(name) >= 4 and name.lower() in lowered:
                candidates.append(
                    Candidate(
                        str(category.id),
                        category.name,
                        0.5,
                        f"Kategoriename '{name}' kommt im Text vor.",
                    )
                )
        candidates.sort(key=lambda c: (-c.confidence, c.label))
        if candidates:
            reasons.append(f"Kategorie '{candidates[0].label}' nach Namensfund im Text.")
    if not candidates:
        reasons.append("Keine Klassifikationsregel und kein Kategoriename trifft zu.")
    return classification, candidates, reasons


async def _rejected_rule_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.scalars(
            select(AiExample.features).where(AiExample.task == AiTask.CLASSIFY_DOCUMENT)
        )
    ).all()
    counts: dict[str, int] = {}
    for features in rows:
        rule_id = (features or {}).get("rule_id")
        if rule_id and (features or {}).get("decision") == "rejected":
            counts[str(rule_id)] = counts.get(str(rule_id), 0) + 1
    return counts


async def match_properties(
    session: AsyncSession, text: str, head: str
) -> tuple[list[Candidate], list[str]]:
    """Object number (three digits) and address against the tenant's properties.

    ``head`` (title, filename, subject) counts more than the body: a number there is meant as
    a reference, a bare three digit number in the body may be anything."""
    props = (await session.scalars(select(Property))).all()
    by_number = {p.number: p for p in props}
    found: dict[uuid.UUID, Candidate] = {}
    reasons: list[str] = []
    lowered = text.lower()

    def add(prop: Property, confidence: float, reason: str) -> None:
        current = found.get(prop.id)
        if current is None or current.confidence < confidence:
            found[prop.id] = Candidate(str(prop.id), prop.number, confidence, reason)

    for m in OBJECT_HINT_RE.finditer(text):
        prop = by_number.get(m.group(1))
        if prop is not None:
            add(prop, 0.9, f"Objektnummer {prop.number} mit Hinweis 'Objekt' im Text.")
    for m in THREE_DIGITS_RE.finditer(head):
        prop = by_number.get(m.group(1))
        if prop is not None:
            add(prop, 0.75, f"Objektnummer {prop.number} in Titel oder Betreff.")
    for prop in props:
        if prop.street and prop.city:
            street = _norm(f"{prop.street} {prop.house_number or ''}")
            if street and street in lowered:
                confidence = 0.85 if _norm(prop.city) in lowered else 0.7
                add(prop, confidence, f"Anschrift '{prop.street} {prop.house_number or ''}'.")
    if not found:
        numbers = {m.group(1) for m in THREE_DIGITS_RE.finditer(text)}
        hits = [by_number[n] for n in sorted(numbers) if n in by_number]
        confidence = 0.55 if len(hits) == 1 else 0.35
        for prop in hits[:5]:
            add(prop, confidence, f"Dreistellige Zahl {prop.number} im Text (ohne Hinweis).")
    candidates = sorted(found.values(), key=lambda c: (-c.confidence, c.label))
    if candidates:
        reasons.append(f"Objekt {candidates[0].label}: {candidates[0].reason}")
    else:
        reasons.append("Keine Objektnummer und keine Objektanschrift gefunden.")
    return candidates, reasons


async def match_contacts(
    session: AsyncSession, text: str, sender: str | None, correspondent: str | None
) -> tuple[list[Candidate], list[str]]:
    """Sender address first, then the mirror's correspondent, then contact names in the text."""
    found: dict[uuid.UUID, Candidate] = {}
    reasons: list[str] = []

    def add(contact: Contact, confidence: float, reason: str) -> None:
        current = found.get(contact.id)
        if current is None or current.confidence < confidence:
            found[contact.id] = Candidate(str(contact.id), contact.display_name, confidence, reason)

    emails: list[str] = []
    if sender:
        emails.extend(m.group(0).lower() for m in EMAIL_RE.finditer(sender))
    for address in emails[:1]:
        contact_ids = (
            await session.scalars(
                select(ContactEmail.contact_id).where(func.lower(ContactEmail.email) == address)
            )
        ).all()
        for contact_id in contact_ids:
            contact = await session.get(Contact, contact_id)
            if contact is not None and contact.deleted_at is None:
                add(contact, 0.95, f"Absenderadresse {address} ist beim Kontakt hinterlegt.")
    if correspondent:
        contact = await session.scalar(
            select(Contact).where(
                func.lower(Contact.display_name) == correspondent.strip().lower(),
                Contact.deleted_at.is_(None),
            )
        )
        if contact is not None:
            add(contact, 0.8, f"Korrespondent '{correspondent}' entspricht dem Kontaktnamen.")
    if not found:
        lowered = text.lower()
        contacts = (
            await session.scalars(select(Contact).where(Contact.deleted_at.is_(None)))
        ).all()
        for contact in contacts:
            names = [contact.company_name or ""]
            if contact.last_name and contact.first_name:
                names.append(f"{contact.first_name} {contact.last_name}")
                names.append(f"{contact.last_name}, {contact.first_name}")
            for name in names:
                if len(name) >= 5 and name.lower() in lowered:
                    add(contact, 0.6, f"Name '{name}' kommt im Text vor.")
                    break
    candidates = sorted(found.values(), key=lambda c: (-c.confidence, c.label))[:5]
    if candidates:
        reasons.append(f"Kontakt {candidates[0].label}: {candidates[0].reason}")
    else:
        reasons.append("Kein Absender und kein Kontaktname erkannt.")
    return candidates, reasons


async def analyse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document: Document,
    *,
    source: str,
    extra_text: str | None = None,
    head: str | None = None,
    sender: str | None = None,
    correspondent: str | None = None,
) -> IntakeResult:
    text, status = document_text(document, extra_text)
    result = IntakeResult(source=source, text_status=status)
    if status == TextStatus.PENDING.value:
        result.reasons.append("Kein Text im Index, nur Titel und Dateiname wurden geprüft.")
    classification, categories, reasons = await classify(session, tenant_id, document, text)
    result.classification = classification
    result.category_candidates = categories
    result.reasons.extend(reasons)
    head_text = " ".join(p for p in (document.title, document.filename, head) if p)
    result.property_candidates, reasons = await match_properties(session, text, head_text)
    result.reasons.extend(reasons)
    result.contact_candidates, reasons = await match_contacts(session, text, sender, correspondent)
    result.reasons.extend(reasons)
    return result


async def existing_proposal(session: AsyncSession, document_id: uuid.UUID) -> AiProposal | None:
    row: AiProposal | None = await session.scalar(
        select(AiProposal).where(
            AiProposal.entity_type == ENTITY_TYPE, AiProposal.context_id == document_id
        )
    )
    return row


async def propose(
    session: AsyncSession, tenant_id: uuid.UUID, document: Document, result: IntakeResult
) -> AiProposal | None:
    """One proposal per document; a second run leaves the existing one untouched."""
    if await existing_proposal(session, document.id) is not None:
        return None
    proposed = result.as_dict()
    run = AiTaskRun(
        tenant_id=tenant_id,
        task=AiTask.CLASSIFY_DOCUMENT,
        prompt_version=PROMPT_VERSION,
        input_hash=hashlib.sha256(
            f"{document.sha256}:{result.source}".encode(), usedforsecurity=False
        ).hexdigest(),
        input_ref={"document_id": str(document.id), "source": result.source},
        output=proposed,
        confidence=Decimal(str(result.confidence)),
        status=RunStatus.SUCCEEDED,
    )
    session.add(run)
    await session.flush()
    proposal = AiProposal(
        tenant_id=tenant_id,
        task_run_id=run.id,
        entity_type=ENTITY_TYPE,
        context_id=document.id,
        proposed=proposed,
    )
    session.add(proposal)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="document.intake_proposed",
        entity_type="document",
        entity_id=document.id,
        actor_user_id=None,
        payload={
            "proposal_id": str(proposal.id),
            "source": result.source,
            "confidence": result.confidence,
        },
    )
    return proposal


# Sources ------------------------------------------------------------------------------------


def _paperless_client(connection: DmsConnection, client: httpx.AsyncClient) -> PaperlessSearch:
    options = connection.options or {}
    object_field_id = options.get("object_field_id")
    return PaperlessSearch(
        base_url=str(connection.base_url),
        token=str(connection.secret),
        client=client,
        object_field_id=int(object_field_id) if object_field_id else None,
    )


def _drive_store(connection: DmsConnection, client: httpx.AsyncClient) -> GoogleDriveStore:
    secret = json.loads(connection.secret or "{}")
    options = connection.options or {}
    return GoogleDriveStore(
        root_folder_id=str(options.get("root_folder_id", "")),
        client_id=str(options.get("client_id", "")),
        client_secret=str(secret.get("client_secret", "")),
        refresh_token=str(secret.get("refresh_token", "")),
        client=client,
    )


async def _connection(session: AsyncSession, kind: StorageKind) -> DmsConnection | None:
    row: DmsConnection | None = await session.scalar(
        select(DmsConnection).where(DmsConnection.kind == kind, DmsConnection.enabled.is_(True))
    )
    if row is None or not row.secret:
        return None
    return row


def _set_watermark(connection: DmsConnection, value: str | None) -> None:
    if value:
        connection.options = {**(connection.options or {}), WATERMARK_KEY: value}


async def _known_external(session: AsyncSession, kind: StorageKind, ref: str) -> Document | None:
    """Document already indexed for this external id (own mirror upload or earlier intake)."""
    doc: Document | None = await session.scalar(
        select(Document).where(Document.source_system == kind.value, Document.source_id == ref[:64])
    )
    if doc is not None:
        return doc
    mirror = await session.scalar(
        select(DocumentMirror).where(
            DocumentMirror.kind == kind, DocumentMirror.external_ref == ref
        )
    )
    return await session.get(Document, mirror.document_id) if mirror is not None else None


async def _index_external(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    kind: StorageKind,
    ref: str,
    data: bytes,
    title: str,
    filename: str,
    mime_type: str,
) -> Document | None:
    """Store an external file once; the mirror row is marked done because the copy already
    lives in that DMS (same convention as the Paperless webhook)."""
    if mime_type not in ALLOWED_MIME_TYPES or not data or len(data) > settings.document_max_bytes:
        log.info("document_intake_skipped", extra={"kind": kind.value, "mime": mime_type})
        return None
    try:
        svc.check_upload(mime_type, data, settings.document_max_bytes)
        document = await svc.store_document(
            session,
            blobs,
            tenant_id=tenant_id,
            data=data,
            title=title,
            filename=filename,
            mime_type=mime_type,
            source=DocumentSource.IMPORT,
            category_id=None,
            links=[],
            created_by=None,
        )
    except ProblemError as exc:
        log.info("document_intake_rejected", extra={"kind": kind.value, "detail": exc.detail})
        return None
    document.source_system = kind.value
    document.source_id = ref[:64]
    mirror = await session.scalar(
        select(DocumentMirror).where(
            DocumentMirror.document_id == document.id, DocumentMirror.kind == kind
        )
    )
    if mirror is None:
        mirror = DocumentMirror(tenant_id=tenant_id, document_id=document.id, kind=kind)
        session.add(mirror)
    mirror.status = MirrorStatus.DONE
    mirror.external_ref = ref
    await session.flush()
    return document


async def process_paperless(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    tenant_id: uuid.UUID,
    client: httpx.AsyncClient,
) -> int:
    connection = await _connection(session, StorageKind.PAPERLESS)
    if connection is None or not connection.base_url:
        return 0
    search = _paperless_client(connection, client)
    watermark = (connection.options or {}).get(WATERMARK_KEY)
    created = 0
    seen = 0
    page = 1
    try:
        while seen < MAX_PER_SOURCE:
            found = await search.list_added_since(watermark, page=page, page_size=PAGE_SIZE)
            if not found.items:
                break
            for item in found.items:
                seen += 1
                ref = str(item.id)
                document = await _known_external(session, StorageKind.PAPERLESS, ref)
                if document is None:
                    file = await search.fetch_file(item.id, "download")
                    filename = item.original_file_name or file.filename or f"paperless-{ref}.pdf"
                    document = await _index_external(
                        session,
                        blobs,
                        settings,
                        tenant_id=tenant_id,
                        kind=StorageKind.PAPERLESS,
                        ref=ref,
                        data=file.content,
                        title=item.title or filename,
                        filename=filename,
                        mime_type=file.content_type.split(";")[0].strip(),
                    )
                if document is None:
                    continue
                if item.content and not document.ocr_text:
                    document.ocr_text = item.content[:TEXT_LIMIT]
                    document.text_status = TextStatus.EXTRACTED
                result = await analyse(
                    session,
                    tenant_id,
                    document,
                    source=SOURCE_PAPERLESS,
                    extra_text=item.content,
                    correspondent=item.correspondent,
                )
                if await propose(session, tenant_id, document, result) is not None:
                    created += 1
                if item.added and (watermark is None or item.added > watermark):
                    watermark = item.added
            if len(found.items) < PAGE_SIZE:
                break
            page += 1
    except (PaperlessSearchError, DmsError, httpx.HTTPError, ClientError) as exc:
        log.warning("document_intake_paperless_failed: %s", str(exc)[:200])
    _set_watermark(connection, watermark)
    return created


async def process_drive(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    tenant_id: uuid.UUID,
    client: httpx.AsyncClient,
) -> int:
    connection = await _connection(session, StorageKind.GOOGLE_DRIVE)
    if connection is None:
        return 0
    folder_id = str((connection.options or {}).get(INBOX_FOLDER_KEY) or "")
    if not folder_id:
        return 0
    store = _drive_store(connection, client)
    watermark = (connection.options or {}).get(WATERMARK_KEY)
    created = 0
    try:
        files = await store.list_folder(folder_id, watermark)
        for item in files[:MAX_PER_SOURCE]:
            document = await _known_external(session, StorageKind.GOOGLE_DRIVE, item.ref)
            if document is None:
                data = await store.download(item.ref)
                document = await _index_external(
                    session,
                    blobs,
                    settings,
                    tenant_id=tenant_id,
                    kind=StorageKind.GOOGLE_DRIVE,
                    ref=item.ref,
                    data=data,
                    title=item.name,
                    filename=item.name,
                    mime_type=item.mime_type,
                )
            if document is not None:
                result = await analyse(session, tenant_id, document, source=SOURCE_DRIVE)
                if await propose(session, tenant_id, document, result) is not None:
                    created += 1
            if item.modified_at and (watermark is None or item.modified_at > watermark):
                watermark = item.modified_at
    except (DmsError, httpx.HTTPError, ClientError, ValueError, KeyError) as exc:
        log.warning("document_intake_drive_failed: %s", str(exc)[:200])
    _set_watermark(connection, watermark)
    return created


async def process_mailbox(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Inbound messages with attachments that are linked to nothing yet."""
    settings_row = await session.scalar(select(TenantSettings))
    sources = dict(settings_row.sources) if settings_row is not None else {}
    watermark = sources.get(MAILBOX_WATERMARK_KEY)
    stmt = (
        select(Message)
        .where(Message.direction == "in", func.cardinality(Message.attachment_document_ids) > 0)
        .order_by(Message.created_at)
        .limit(MAX_PER_SOURCE)
    )
    if watermark:
        stmt = stmt.where(Message.created_at > datetime.fromisoformat(watermark))
    messages = (await session.scalars(stmt)).all()
    created = 0
    latest: datetime | None = None
    for message in messages:
        latest = message.created_at
        for document_id in message.attachment_document_ids:
            document = await session.get(Document, document_id)
            if document is None:
                continue
            linked = await session.scalar(
                select(DocumentLink.id).where(DocumentLink.document_id == document.id).limit(1)
            )
            if linked is not None:
                continue
            result = await analyse(
                session,
                tenant_id,
                document,
                source=SOURCE_MAILBOX,
                extra_text="\n".join(p for p in (message.subject, message.body) if p),
                head=message.subject,
                sender=message.from_address,
            )
            if message.property_id and not any(
                c.id == str(message.property_id) for c in result.property_candidates
            ):
                prop = await session.get(Property, message.property_id)
                if prop is not None:
                    result.property_candidates.insert(
                        0, Candidate(str(prop.id), prop.number, 0.8, "Zuordnung der Nachricht.")
                    )
            if message.contact_id and not any(
                c.id == str(message.contact_id) for c in result.contact_candidates
            ):
                contact = await session.get(Contact, message.contact_id)
                if contact is not None:
                    result.contact_candidates.insert(
                        0,
                        Candidate(
                            str(contact.id), contact.display_name, 0.8, "Zuordnung der Nachricht."
                        ),
                    )
            if await propose(session, tenant_id, document, result) is not None:
                created += 1
    if latest is not None and settings_row is not None:
        settings_row.sources = {**sources, MAILBOX_WATERMARK_KEY: latest.isoformat()}
    return created


async def process_tenant_inbox(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    tenant_id: uuid.UUID,
    client: httpx.AsyncClient,
) -> dict[str, int]:
    return {
        SOURCE_PAPERLESS: await process_paperless(session, blobs, settings, tenant_id, client),
        SOURCE_DRIVE: await process_drive(session, blobs, settings, tenant_id, client),
        SOURCE_MAILBOX: await process_mailbox(session, tenant_id),
    }


async def process_inbox_once(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    blobs: BlobStore | None = None,
) -> dict[str, int]:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    http = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    store = blobs or BlobStore(settings)
    totals = {SOURCE_PAPERLESS: 0, SOURCE_DRIVE: 0, SOURCE_MAILBOX: 0, "tenants": 0}
    try:
        async with platform_transaction(factory) as session:
            tenant_ids = [
                t.id
                for t in await session.scalars(
                    select(Tenant).where(Tenant.status == TenantStatus.ACTIVE)
                )
            ]
        for tenant_id in tenant_ids:
            async with tenant_transaction(factory, tenant_id) as session:
                counts = await process_tenant_inbox(session, store, settings, tenant_id, http)
            for key, value in counts.items():
                totals[key] += value
            totals["tenants"] += 1
    finally:
        if client is None:
            await http.aclose()
        await engine.dispose()
    return totals


@shared_task(name="mhvp.documents.process_inbox")
def process_inbox() -> dict[str, int]:
    return asyncio.run(process_inbox_once(get_settings()))
