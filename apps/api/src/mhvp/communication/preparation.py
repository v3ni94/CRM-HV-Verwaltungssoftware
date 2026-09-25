"""Mail preparation (Welle 3 item 14): for one inbound message, resolve the sender to a contact,
their role (owner/tenant) and unit/property, search that property's documents (local plus the
external DMS mirrors, strictly scoped to the property, never a whole-account listing, M20-05),
and draft a reply using the tenant's and the property's knowledge base entries as context.

Everything here is a proposal (rule 0.1.6): the draft is stored as the existing mail suggestion
(``Message.suggestion``/``suggestion_status``, M20 Übernahme) under the ``preparation`` key, and
is never sent or booked automatically. A correction recorded against a preparation creates an
``ai_knowledge_entry`` of kind ``correction`` and source ``learned`` (mhvp.ai.routers), so the
next preparation for that property benefits from it.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.ai import gateway
from mhvp.ai.models import (
    AiKnowledgeEntry,
    AiKnowledgeKind,
    AiKnowledgeSource,
    AiTask,
    AiTaskRun,
    RunStatus,
)
from mhvp.communication.models import Message
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.documents.dms import GoogleDriveStore, property_folder_name

log = logging.getLogger(__name__)

MAX_EXCERPT = 4000
MAX_DOCUMENTS = 10

# Fachbegriffe, nach denen in Betreff und Text gesucht wird (Welle 3 item 14). Reine
# Stichwortliste, keine KI-Extraktion, damit die Dokumentsuche nachvollziehbar bleibt.
KEYWORD_TERMS = (
    "Teilungserklärung",
    "Wirtschaftsplan",
    "Jahresabrechnung",
    "Hausordnung",
    "Mietvertrag",
    "Nebenkostenabrechnung",
    "Betriebskostenabrechnung",
    "Protokoll",
    "Beschluss",
    "Kündigung",
    "Mieterhöhung",
    "Übergabeprotokoll",
    "Grundbuch",
    "Versicherung",
)


def keywords_in(*texts: str | None) -> list[str]:
    haystack = "\n".join(t for t in texts if t)
    return [term for term in KEYWORD_TERMS if term.lower() in haystack.lower()]


@dataclass
class Resolution:
    contact_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    role: str | None = None  # owner, tenant
    reasons: list[str] = field(default_factory=list)


async def resolve_contact(session: AsyncSession, message: Message) -> Resolution:
    """Sender to contact, role and unit/property, from existing contract and party data (6.1,
    6.3). ``message.contact_id``/``message.property_id`` were already set on intake by keyword
    or sender match (mhvp.communication.services); this refines it to a unit and a role."""
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract

    result = Resolution(contact_id=message.contact_id, property_id=message.property_id)
    if result.contact_id is None:
        result.reasons.append("Absender keinem Kontakt zugeordnet.")
        return result
    result.reasons.append("Kontakt über die Absenderadresse gefunden.")

    party_ids = list(
        await session.scalars(
            select(PartyMember.party_id).where(PartyMember.contact_id == result.contact_id)
        )
    )
    if not party_ids:
        result.reasons.append("Kontakt ist keiner Vertragspartei zugeordnet.")
        return result

    query = select(Contract).where(Contract.party_id.in_(party_ids))
    if result.property_id is not None:
        query = query.where(Contract.property_id == result.property_id)
    contracts = list(await session.scalars(query.order_by(Contract.start_date.desc())))
    active = [c for c in contracts if c.end_date is None] or contracts
    if not active:
        result.reasons.append("Keine Vertragsdaten zur Partei gefunden.")
        return result
    contract = active[0]
    result.unit_id = contract.unit_id
    result.property_id = result.property_id or contract.property_id
    result.role = "owner" if contract.kind.value == "ownership" else "tenant"
    result.reasons.append(
        f"Vertrag {contract.number} ({'Eigentümer' if result.role == 'owner' else 'Mieter'}) "
        "gefunden."
    )
    return result


async def _local_documents(
    session: AsyncSession, property_id: uuid.UUID, terms: list[str]
) -> list[dict[str, Any]]:
    """Documents already in the platform index, linked to this property (6.9.5); optionally
    narrowed by the matched keywords. Restricted to this property's links only."""
    from mhvp.documents.models import Document, DocumentLink

    query = (
        select(Document, DocumentLink)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .where(DocumentLink.entity_type == "property", DocumentLink.entity_id == property_id)
        .order_by(Document.created_at.desc())
        .limit(MAX_DOCUMENTS)
    )
    rows = (await session.execute(query)).all()
    hits = []
    for document, _link in rows:
        matched = next((t for t in terms if t.lower() in document.title.lower()), None)
        if terms and matched is None:
            continue
        hits.append(
            {
                "document_id": str(document.id),
                "title": document.title,
                "source": "local",
                "matched_keyword": matched,
            }
        )
    return hits


async def _dms_documents(
    session: AsyncSession, property_id: uuid.UUID, terms: list[str]
) -> list[dict[str, Any]]:
    """Documents from the connected external DMS, strictly scoped to this one property: the
    Paperless custom field object number (``PaperlessSearch.list_by_object_number``, M31) or the
    Google Drive object folder (``GoogleDriveStore.search``); never a whole-account listing
    (11.2, M20-05). ``terms`` (keywords found in the mail) narrow the Drive result further and
    the already object-scoped Paperless result client side, on title."""
    from mhvp.documents.models import DmsConnection, StorageKind
    from mhvp.documents.paperless_search import PaperlessSearch, PaperlessSearchError
    from mhvp.properties.models import Property

    prop = await session.get(Property, property_id)
    if prop is None:
        return []
    connections = list(
        await session.scalars(select(DmsConnection).where(DmsConnection.enabled.is_(True)))
    )
    hits: list[dict[str, Any]] = []
    for connection in connections:
        if connection.kind is StorageKind.PAPERLESS:
            if not connection.base_url or not connection.secret:
                continue
            options = connection.options or {}
            object_field_id = options.get("object_field_id")
            client = PaperlessSearch(
                base_url=connection.base_url,
                token=connection.secret,
                object_field_id=int(object_field_id) if object_field_id else None,
            )
            try:
                found = await client.list_by_object_number(prop.number, page_size=MAX_DOCUMENTS)
            except PaperlessSearchError as exc:
                log.warning("paperless search failed", extra={"error": str(exc)})
                continue
            finally:
                await client.aclose()
            for doc in found.items:
                if terms and not any(t.lower() in doc.title.lower() for t in terms):
                    continue
                hits.append(
                    {
                        "document_id": None,
                        "title": doc.title,
                        "source": "dms",
                        "matched_keyword": next(
                            (t for t in terms if t.lower() in doc.title.lower()), None
                        ),
                        "ref": str(doc.id),
                    }
                )
        elif connection.kind is StorageKind.GOOGLE_DRIVE:
            secret = json.loads(connection.secret or "{}")
            options = connection.options or {}
            async with httpx.AsyncClient(timeout=30.0) as client_http:
                drive = GoogleDriveStore(
                    root_folder_id=str(options.get("root_folder_id", "")),
                    client_id=str(options.get("client_id", "")),
                    client_secret=str(secret.get("client_secret", "")),
                    refresh_token=str(secret.get("refresh_token", "")),
                    client=client_http,
                )
                folder = property_folder_name(
                    prop.number, prop.city, prop.street, prop.house_number
                )
                try:
                    found_drive = await drive.search(folder, terms)
                except Exception as exc:  # DMS unreachable: preparation continues without it
                    log.warning("drive search failed", extra={"error": str(exc)})
                    continue
            for hit in found_drive[:MAX_DOCUMENTS]:
                hits.append(
                    {
                        "document_id": None,
                        "title": hit.title,
                        "source": "dms",
                        "matched_keyword": next(
                            (t for t in terms if t.lower() in hit.title.lower()), None
                        ),
                        "ref": hit.ref,
                        "url": hit.url,
                    }
                )
    return hits


async def _knowledge_context(
    session: AsyncSession, tenant_id: uuid.UUID, property_id: uuid.UUID | None
) -> str:
    query = select(AiKnowledgeEntry).where(AiKnowledgeEntry.deleted_at.is_(None))
    if property_id is not None:
        query = query.where(
            (AiKnowledgeEntry.property_id.is_(None)) | (AiKnowledgeEntry.property_id == property_id)
        )
    else:
        query = query.where(AiKnowledgeEntry.property_id.is_(None))
    rows = list(await session.scalars(query.order_by(AiKnowledgeEntry.created_at.desc())))
    if not rows:
        return "-"
    return "\n".join(f"- ({r.kind.value}) {r.title}: {r.content}" for r in rows[:30])


async def _run_gateway_task(
    settings: Settings, tenant_id: uuid.UUID, prompt_text: str, context: dict[str, Any]
) -> AiTaskRun:
    """Mirrors ``mhvp.communication.suggest._run_gateway_task``: its own connection, independent
    from the caller's transaction."""
    from mhvp.ai import tasks as ai_tasks

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        prompt = ai_tasks.prompt(AiTask.CLASSIFY_EMAIL)
        run_id: uuid.UUID
        async with tenant_transaction(factory, tenant_id) as session:
            run = AiTaskRun(
                tenant_id=tenant_id,
                task=AiTask.CLASSIFY_EMAIL,
                prompt_version=prompt.version,
                input_hash=gateway.input_hash(
                    AiTask.CLASSIFY_EMAIL, prompt.version, prompt_text, context
                ),
                input_ref={"instruction": prompt_text, "document_ids": [], "context": context},
                status=RunStatus.QUEUED,
            )
            session.add(run)
            await session.flush()
            run_id = run.id
        return await gateway.execute(factory, tenant_id, run_id, BlobStore(settings), None)
    finally:
        await engine.dispose()


async def prepare_for_message(
    session: AsyncSession, settings: Settings, message: Message
) -> dict[str, Any]:
    """Computes the preparation result for one inbound message. Returns a dict with ``status``
    (ready, skipped, failed) and the preparation fields; the caller stores it under
    ``message.suggestion["preparation"]`` and ``message.suggestion_status``."""
    resolution = await resolve_contact(session, message)
    terms = keywords_in(message.subject, message.body)
    documents: list[dict[str, Any]] = []
    if resolution.property_id is not None:
        documents = await _local_documents(session, resolution.property_id, terms)
        documents += await _dms_documents(session, resolution.property_id, terms)

    body_excerpt = (message.body or "")[:MAX_EXCERPT]
    knowledge = await _knowledge_context(session, message.tenant_id, resolution.property_id)
    prompt_text = (
        f"Betreff: {message.subject or ''}\n"
        f"Absender: {message.from_address or ''}\n"
        f"Text (Auszug):\n{body_excerpt}\n\n"
        f"Rolle des Absenders: {resolution.role or 'unbekannt'}\n"
        f"Gefundene Dokumente: {', '.join(d['title'] for d in documents) or '-'}\n\n"
        f"Wissensbasis (Mandant und Objekt):\n{knowledge}\n\n"
        "Formuliere einen sachlichen Antwortentwurf auf Deutsch. Nenne offene Punkte, die eine "
        "Person prüfen muss, statt sie zu erfinden."
    )
    context = {"context_type": "message", "context_id": str(message.id)}

    try:
        run = await _run_gateway_task(settings, message.tenant_id, prompt_text, context)
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)[:500]}

    result: dict[str, Any] = {
        "contact_id": str(resolution.contact_id) if resolution.contact_id else None,
        "unit_id": str(resolution.unit_id) if resolution.unit_id else None,
        "property_id": str(resolution.property_id) if resolution.property_id else None,
        "role": resolution.role,
        "documents": documents,
        "reasons": resolution.reasons,
        "computed_at": datetime.now(UTC).isoformat(),
    }
    if run.status is RunStatus.SUCCEEDED and run.output:
        result["draft"] = run.output.get("reply_draft") or run.output.get("draft")
        confidence = run.confidence if run.confidence is not None else None
        result["confidence"] = str(confidence) if confidence is not None else None
        result["status"] = "ready"
    elif run.status is RunStatus.BLOCKED:
        result["draft"] = None
        result["confidence"] = None
        result["status"] = "skipped"
        result["reasons"].append(run.error or "Kein freigegebener KI-Anbieter.")
    else:
        result["draft"] = None
        result["confidence"] = None
        result["status"] = "failed"
        result["reasons"].append(run.error or "KI-Lauf fehlgeschlagen.")
    return result


async def record_correction(
    session: AsyncSession,
    message: Message,
    *,
    contact_id: uuid.UUID | None,
    unit_id: uuid.UUID | None,
    property_id: uuid.UUID | None,
    note: str,
    user_id: uuid.UUID | None,
) -> AiKnowledgeEntry:
    """A human correction of a preparation becomes a learned knowledge entry (rule 0.1.6: AI
    never approves this alone, a person recorded it) and updates the stored preparation."""
    entry = AiKnowledgeEntry(
        tenant_id=message.tenant_id,
        created_by=user_id,
        property_id=property_id,
        kind=AiKnowledgeKind.CORRECTION,
        title=f"Korrektur zu Mail {message.subject or message.id}"[:200],
        content=note,
        source=AiKnowledgeSource.LEARNED,
    )
    session.add(entry)
    suggestion = dict(message.suggestion or {})
    preparation = dict(suggestion.get("preparation") or {})
    preparation["correction"] = {
        "contact_id": str(contact_id) if contact_id else None,
        "unit_id": str(unit_id) if unit_id else None,
        "property_id": str(property_id) if property_id else None,
        "note": note,
        "corrected_by": str(user_id) if user_id else None,
        "corrected_at": datetime.now(UTC).isoformat(),
    }
    if contact_id is not None:
        preparation["contact_id"] = str(contact_id)
    if unit_id is not None:
        preparation["unit_id"] = str(unit_id)
    if property_id is not None:
        preparation["property_id"] = str(property_id)
    suggestion["preparation"] = preparation
    message.suggestion = suggestion
    await session.flush()
    return entry
