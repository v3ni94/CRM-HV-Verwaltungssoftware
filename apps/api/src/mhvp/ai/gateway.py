"""AI gateway (9.1, 9.3, 9.4): checks, prompt, provider call, validation, cost, logging.

Order of checks before any data leaves the platform: a released provider configuration with DPA
evidence and confirmed training opt-out (rule 0.1.13), a model and prices for the tier, and the
monthly budget. Results are validated against the task schema; one retry with the error message.
"""

import asyncio
import hashlib
import io
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openpyxl import load_workbook
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai import instructions as chat_instructions
from mhvp.ai import lookup, providers, table_mapper, tasks
from mhvp.ai.models import AiExample, AiProvider, AiProviderConfig, AiTask, AiTaskRun, RunStatus
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.core.logging import get_logger
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, TextStatus
from mhvp.objektakte.masking import mask_identifiers

log = get_logger("mhvp.ai.gateway")

MAX_INPUT_CHARS = 1_500_000  # pre chunking guard; chunking (below) keeps single calls small
HARD_LIMIT_CHARS = 2_000_000  # a single attached document beyond this always blocks
MAX_TABLE_ROWS = 20_000  # rows with content; formatted empty rows do not count
MAX_DOCUMENT_CHARS = 250_000  # per file for non chunked tasks; longer files are cut visibly
CHUNK_CHARS = 150_000  # extraction tasks: table text is split into row chunks of this size
CHUNK_CONCURRENCY = 4  # concurrent provider calls per chunked run (latency bound, not CPU)
CHUNK_ROWS = 80  # rows per chunk for extract_contacts/extract_property (fits 16000 output tokens)
# Output limit per call when the tier carries no ``max_output_tokens`` (operator entered per tier
# from the provider's published model limits, schemas.TierModel).
DEFAULT_MAX_OUTPUT_TOKENS = 16000
RETRIEVE_LIMIT = 6  # normal retrieval; reduced (below) when the input would be too large
REDUCED_RETRIEVE_LIMIT = 3
# Hard input budget of a chat call (answer_question): the tier's ``context_tokens`` when the
# operator entered it, else this conservative default; chars / 3.5 estimate. The reserve
# keeps room for the system prompt, the context line, examples and the estimate's error.
DEFAULT_INPUT_BUDGET_TOKENS = 150_000
BUDGET_RESERVE = Decimal("0.85")
MIN_EXCERPT_CHARS = 2_000  # a retrieved document is never cut below this
HISTORY_KEEP = 6  # turns kept when the history has to give way
LOOKUP_LINKS_PER_TOOL = 10
FEW_SHOT = 8
WARN_SHARE = Decimal("0.8")
# Rate limits and overloads: wait and retry the same provider before falling back (seconds).
RETRY_DELAYS_S: tuple[float, ...] = (3.0, 8.0)
MTOK = Decimal(1_000_000)
CHARS_PER_TOKEN = Decimal("3.5")
CHUNKED_TASKS: frozenset[AiTask] = frozenset({AiTask.EXTRACT_CONTACTS, AiTask.EXTRACT_PROPERTY})

# M34 Nachtrag 27.09.2026 (9.1 Datenschutz): tasks whose output does not need a raw IBAN,
# e-mail address or phone number get ``mask_identifiers`` applied to the assembled document
# text before it reaches the provider (names stay, e.g. for a salutation, per 9.1 "Textentwürfe
# brauchen nur Anrede"). Extraction (`CHUNKED_TASKS`), `extract_invoice` (needs the creditor's
# bank data), `propose_posting` (needs the payer's IBAN to match it) and `map_columns` (needs
# the raw sample values to recognise a phone/IBAN/name column) are deliberately excluded (the
# task cannot do its job masked, 9.1's "wo die Aufgabe es zulässt").
MASKED_TASKS: frozenset[AiTask] = frozenset(
    {
        AiTask.ANSWER_QUESTION,
        AiTask.SUMMARIZE,
        AiTask.CHECK_STATEMENT,
        AiTask.CLASSIFY_EMAIL,
        AiTask.CLASSIFY_DOCUMENT,
        AiTask.DRAFT_REPLY,
        AiTask.CALL_SUMMARY,
    }
)
# Fast table import (M7-06): deterministic column mapping instead of sending every row to the
# LLM. extract_contacts uses the contact column model (``tasks.ColumnMappingResult``),
# extract_property (A47) the owner/tenant list column model of ``table_mapper`` (units,
# parties, payments); both share the ``map_columns`` task for the mapping call.
FAST_TABLE_TASKS: frozenset[AiTask] = frozenset({AiTask.EXTRACT_CONTACTS, AiTask.EXTRACT_PROPERTY})


class GatewayBlockedError(Exception):
    """The run must not start; the reason is shown to the user."""


@dataclass
class TaskInput:
    text: str
    document_ids: list[uuid.UUID]
    context: dict[str, Any]
    input_stats: dict[str, int]
    # Row chunks (extraction tasks only): one prompt text per chunk, each self contained
    # (instruction, header line(s) kept, wrapped like a normal document). Empty for other tasks.
    chunks: list[str]
    # The user's instruction as its own delimited part (``<frage>``) in front of the data
    # block, so nothing inside ``<daten>`` can imitate it (chat, rule AI-LOOKUP-01). ``None``:
    # the instruction is the first line of ``text`` (other tasks, unchanged).
    instruction: str | None = None


# Input preparation (deterministic, no AI) ------------------------------------------------


def decode_text(data: bytes) -> str:
    """Encoding chain for uploaded text (never silently replaces characters): UTF-8 (with an
    optional BOM), then Windows-1252 (common in German exports), then Latin-1 as a last resort
    which never fails but keeps every byte meaningful for Western European text."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _table_text(rows: list[list[Any]], *, max_rows: int | None = None) -> str:
    """Compact rendering: empty rows are skipped, trailing empty cells are dropped (Excel files
    often carry formatting far beyond the data, which used to blow up the text), and only rows
    with content count towards the row limit. Row numbers stay those of the sheet."""
    limit = MAX_TABLE_ROWS if max_rows is None else max_rows
    lines: list[str] = []
    kept = 0
    for number, row in enumerate(rows, start=1):
        cells = ["" if c is None else str(c).strip() for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if not any(cells):
            continue
        if kept >= limit:
            lines.append(f"[gekürzt: weitere Zeilen ab Zeile {number} nicht übernommen]")
            break
        kept += 1
        lines.append(f"Zeile {number}: " + " | ".join(cells))
    return "\n".join(lines)


def spreadsheet_text(data: bytes) -> str:
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for sheet in book.worksheets:
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        parts.append(f"Tabellenblatt {sheet.title}\n{_table_text(rows)}")
    return "\n\n".join(parts)


def csv_text(data: bytes) -> str:
    import csv

    text = decode_text(data)
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t") if text else csv.excel
    return _table_text([list(r) for r in csv.reader(io.StringIO(text), dialect)])


def _chunk_table_body(
    body: str, *, chunk_chars: int = CHUNK_CHARS, chunk_rows: int = CHUNK_ROWS
) -> list[str]:
    """Split a sheet's or CSV's rendered table text (one ``Zeile n: ...`` line per row, sheet
    titles as their own lines) into chunks of at most ``chunk_rows`` data rows and
    ``chunk_chars`` characters, repeating the header (the first data line of each sheet) at the
    top of every chunk so a chunk can be understood on its own."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    current_rows = 0
    header: str | None = None
    for line in body.splitlines():
        if line.startswith("Tabellenblatt "):
            header = None  # a new sheet starts; its first data line becomes the next header
            if current:
                chunks.append(current)
                current, current_chars, current_rows = [], 0, 0
            current.append(line)
            current_chars += len(line) + 1
            continue
        if header is None and line.startswith("Zeile "):
            header = line
        is_new_row = line.startswith("Zeile ")
        would_overflow = current_rows >= chunk_rows or current_chars + len(line) + 1 > chunk_chars
        if is_new_row and would_overflow and current:
            chunks.append(current)
            current = [header] if header else []
            current_chars = len(header) + 1 if header else 0
            current_rows = 0
        current.append(line)
        current_chars += len(line) + 1
        if is_new_row:
            current_rows += 1
    if current:
        chunks.append(current)
    return ["\n".join(c) for c in chunks] or [body]


NO_DOCUMENT_HINT = (
    "Hinweis: Es wurde keine Datei angehängt. Die Daten stehen im Text der Anweisung des Nutzers."
)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TABLE_MIME_TYPES = {XLSX, "text/csv"}


async def _document_body(
    session: AsyncSession, blobs: BlobStore, document_id: uuid.UUID
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise GatewayBlockedError("Dokument nicht gefunden.")
    return document


def _table_body(document: Document, blobs: BlobStore) -> str:
    if document.mime_type == XLSX:
        return spreadsheet_text(blobs.get(document.storage_ref))
    return csv_text(blobs.get(document.storage_ref))


async def document_body(
    session: AsyncSession, blobs: BlobStore, document_id: uuid.UUID
) -> tuple[Document, str]:
    """The document and its raw text (table text or OCR text)."""
    document = await _document_body(session, blobs, document_id)
    if document.mime_type in TABLE_MIME_TYPES:
        body = _table_body(document, blobs)
    elif document.text_status is TextStatus.EXTRACTED and document.ocr_text:
        body = document.ocr_text
    else:
        raise GatewayBlockedError(
            f"Für {document.filename} liegt noch kein Text vor (Texterkennung ausstehend)."
        )
    return document, body


def wrap_document(name: str, document_id: uuid.UUID | str, body: str, max_chars: int) -> str:
    """The ``<datei>`` block of one document, cut visibly at ``max_chars``."""
    if len(body) > max_chars:
        body = body[:max_chars] + "\n[gekürzt: Datei länger als das Limit für eine Datei]"
    return f'<datei name="{name}" id="{document_id}">\n{body}\n</datei>'


async def document_text(
    session: AsyncSession,
    blobs: BlobStore,
    document_id: uuid.UUID,
    *,
    max_chars: int = MAX_DOCUMENT_CHARS,
) -> tuple[str, int]:
    """Returns the wrapped text and the raw character count before any cut (for input_stats)."""
    document, body = await document_body(session, blobs, document_id)
    return wrap_document(document.filename, document.id, body, max_chars), len(body)


async def document_chunks(
    session: AsyncSession, blobs: BlobStore, document_id: uuid.UUID
) -> tuple[list[str], int]:
    """For extraction tasks: table documents are split into row chunks; other documents stay a
    single chunk (cut at ``MAX_DOCUMENT_CHARS`` like before, since they are never row data)."""
    document = await _document_body(session, blobs, document_id)
    if document.mime_type in TABLE_MIME_TYPES:
        body = _table_body(document, blobs)
        raw_chars = len(body)
        pieces = _chunk_table_body(body)
        return [
            f'<datei name="{document.filename}" id="{document.id}" teil="{i}/{len(pieces)}">\n'
            f"{piece}\n</datei>"
            for i, piece in enumerate(pieces, start=1)
        ], raw_chars
    text, raw_chars = await document_text(session, blobs, document_id)
    return [text], raw_chars


async def retrieve(
    session: AsyncSession,
    question: str,
    limit: int = RETRIEVE_LIMIT,
    *,
    tenant_id: uuid.UUID | None = None,
    actor: uuid.UUID | None = None,
    only_ids: list[uuid.UUID] | None = None,
) -> list[Document]:
    """Documents of the tenant (RLS) for a question: similarity search over the embeddings
    (M7-03) when the tenant has any and the route is usable, otherwise the keyword search.
    ``only_ids`` (portal scope) filters before the ranking; the keyword path is filtered by the
    caller as before."""
    if tenant_id is not None:
        from mhvp.ai import embeddings

        found = await embeddings.retrieve_documents(
            session, question, tenant_id=tenant_id, actor=actor, limit=limit, only_ids=only_ids
        )
        if found is not None:
            return found
    return await retrieve_keyword(session, question, limit)


async def retrieve_keyword(
    session: AsyncSession, question: str, limit: int = RETRIEVE_LIMIT
) -> list[Document]:
    """Full text retrieval over documents the tenant holds (RLS); the fallback of ``retrieve``."""
    words = set(re.findall(r"[\wÄÖÜäöüß]{3,}", question))
    if not words:
        return []
    # Any word may match (OR); ranking puts documents with more matches first.
    ts = func.to_tsquery("german", " | ".join(sorted(words)))
    rows = (
        await session.scalars(
            select(Document)
            .where(Document.search_vector.op("@@")(ts), Document.ocr_text.is_not(None))
            .order_by(func.ts_rank(Document.search_vector, ts).desc())
            .limit(limit)
        )
    ).all()
    return list(rows)


async def knowledge_context(session: AsyncSession, run: AiTaskRun, question: str) -> str:
    """Knowledge base block of a chat run ("" when nothing applies): tenant wide entries plus
    those of the property in focus (``context.entity_type == "property"``). Records the used
    ids in ``run.input_ref["knowledge_ids"]``."""
    from mhvp.ai import knowledge

    context = run.input_ref.get("context") or {}
    property_id: uuid.UUID | None = None
    if context.get("entity_type") == "property" and context.get("entity_id"):
        try:
            property_id = uuid.UUID(str(context["entity_id"]))
        except ValueError:
            property_id = None
    text, used = await knowledge.context(
        session,
        tenant_id=run.tenant_id,
        property_id=property_id,
        question=question,
        actor=run.created_by,
    )
    if not used:
        return ""
    run.input_ref = {**run.input_ref, "knowledge_ids": [str(u.id) for u in used]}
    return "Freigegebene Wissensbasis des Mandanten (Vorrang vor Dokumenttext):\n" + text


async def _document_name(session: AsyncSession, document_id: uuid.UUID) -> str:
    document = await session.get(Document, document_id)
    return document.filename if document is not None else str(document_id)


HISTORY_MESSAGES = 10  # earlier messages of the conversation handed to the model
HISTORY_CHARS = 1500  # per message


async def conversation_history(session: AsyncSession, run: AiTaskRun) -> str:
    """Earlier messages of the run's conversation (oldest first, without the current question),
    so remarks and follow up questions keep their context."""
    return history_text(await conversation_history_lines(session, run))


def history_text(lines: list[str], keep: int | None = None) -> str:
    """The history block; ``keep`` limits it to the last messages (input budget)."""
    if not lines:
        return ""
    if keep is not None and len(lines) > keep:
        lines = lines[-keep:]
    return "\n".join(["Bisheriger Gesprächsverlauf (älteste zuerst, nur als Kontext):", *lines])


async def conversation_history_lines(session: AsyncSession, run: AiTaskRun) -> list[str]:
    """One line per earlier message of the conversation, oldest first."""
    from mhvp.ai.models import AiMessage

    if run.conversation_id is None:
        return []
    rows = (
        await session.scalars(
            select(AiMessage)
            .where(
                AiMessage.conversation_id == run.conversation_id,
                (AiMessage.task_run_id != run.id) | AiMessage.task_run_id.is_(None),
            )
            .order_by(AiMessage.created_at.desc())
            .limit(HISTORY_MESSAGES)
        )
    ).all()
    lines = []
    for message in reversed(rows):
        who = "Nutzer" if message.role == "user" else "Assistent"
        # One line per message: a line break inside a message can never start a line that
        # looks like another turn or the instruction (9.1).
        text = lookup.flat(message.content).replace("<", "\u2039").replace(">", "\u203a")
        lines.append(f"{who}: {text[:HISTORY_CHARS]}")
    return lines


# Input budget of a chat call ----------------------------------------------------------------


@dataclass
class DocPart:
    name: str
    document_id: uuid.UUID
    body: str
    attached: bool  # attached by the user (kept), else retrieved (dropped first)


@dataclass
class AnswerParts:
    """Everything that goes into the data block of an ``answer_question`` call, before the
    budget is applied. The user's question and the page context are not part of it: they are
    never trimmed."""

    history: list[str]
    lookup: dict[str, Any] | None
    documents: list[DocPart]  # attached first, then retrieved in rank order
    instruction: str | None = None  # first line of the block (non chat callers only)
    knowledge: str = ""  # approved knowledge entries (M34-01), capped upstream, never trimmed


def budget_chars(budget_tokens: int) -> int:
    return int(Decimal(budget_tokens) * CHARS_PER_TOKEN * BUDGET_RESERVE)


def fit_answer_input(
    parts: AnswerParts, budget_tokens: int
) -> tuple[str, list[uuid.UUID], dict[str, int]]:
    """Assembles the data block within the input budget. Trim order until it fits: retrieved
    documents (least relevant first), then each document to a smaller excerpt, then lookup
    hits beyond 10 per tool, then history beyond the last ``HISTORY_KEEP`` turns. Returns the
    text, the document ids kept and the sizes for ``input_stats``."""
    limit = budget_chars(budget_tokens)
    retrieved = [d for d in parts.documents if not d.attached]
    attached = [d for d in parts.documents if d.attached]
    excerpt = MAX_DOCUMENT_CHARS
    links_max: int | None = None
    history_keep: int | None = None
    tools = max(1, len((parts.lookup or {}).get("tools") or []))
    all_links = len((parts.lookup or {}).get("links") or [])
    trimmed = 0

    def assemble() -> str:
        blocks = [] if parts.instruction is None else [parts.instruction]
        records = "\n\n".join(
            p
            for p in (
                history_text(parts.history, history_keep),
                parts.knowledge,
                lookup.prompt_text(parts.lookup, links_max),
            )
            if p
        )
        if records:
            blocks.append(records)
        blocks += [
            wrap_document(d.name, d.document_id, d.body, excerpt) for d in [*attached, *retrieved]
        ]
        return "\n\n".join(blocks)

    text = assemble()
    while len(text) > limit:
        if retrieved:
            retrieved.pop()
        elif excerpt > MIN_EXCERPT_CHARS and any(len(d.body) > MIN_EXCERPT_CHARS for d in attached):
            excerpt = max(MIN_EXCERPT_CHARS, excerpt // 2)
        elif links_max is None and all_links > LOOKUP_LINKS_PER_TOOL * tools:
            links_max = LOOKUP_LINKS_PER_TOOL * tools
        elif history_keep is None and len(parts.history) > HISTORY_KEEP:
            history_keep = HISTORY_KEEP
        else:
            break  # the question and the page context are never trimmed
        trimmed += 1
        text = assemble()
    kept = [*attached, *retrieved]
    stats = {
        "budget_tokens": budget_tokens,
        "budget_chars": limit,
        "input_chars": len(text),
        "estimated_tokens": estimate_tokens(len(text)),
        "documents_attached": len(attached),
        "documents_retrieved": len(retrieved),
        "documents_dropped": len(parts.documents) - len(kept),
        "document_excerpt_chars": excerpt,
        "history_messages": min(len(parts.history), history_keep or len(parts.history)),
        "knowledge_chars": len(parts.knowledge),
        "lookup_links": min(all_links, links_max) if links_max is not None else all_links,
        "trim_steps": trimmed,
    }
    for d in kept:
        stats[d.name] = len(d.body)
    return text, [d.document_id for d in kept], stats


async def input_budget_tokens(session: AsyncSession, task: AiTask) -> int:
    """The tier's ``context_tokens`` of the preferred usable provider, else the default."""
    try:
        usable, _reasons = await routes(session, task)
    except GatewayBlockedError:
        return DEFAULT_INPUT_BUDGET_TOKENS
    if usable and usable[0].context_tokens:
        return int(usable[0].context_tokens)
    return DEFAULT_INPUT_BUDGET_TOKENS


async def build_input(
    session: AsyncSession,
    blobs: BlobStore,
    run: AiTaskRun,
    *,
    budget_tokens: int | None = None,
) -> TaskInput:
    """``budget_tokens`` (chat): hard input budget of the call, see ``fit_answer_input``."""
    ref = run.input_ref
    document_ids = [uuid.UUID(d) for d in ref.get("document_ids", [])]
    question = str(ref.get("instruction", ""))
    instruction = f"Anweisung des Nutzers: {question}"
    # Chat (rule AI-LOOKUP-01): the instruction becomes its own delimited part in front of the
    # data block instead of its first line, so record fields, mails and history inside
    # ``<daten>`` can never pass as the instruction (9.1).
    separate = run.task is AiTask.ANSWER_QUESTION
    context = dict(ref.get("context", {}))
    input_stats: dict[str, int] = {}

    # Access matrix on the AI path (6.9.6, D30): a run started by an external portal user may
    # only carry documents that user sees through the portal; attached foreign documents block
    # the run, retrieved ones are dropped before any text is assembled (M20-05: nothing foreign
    # enters the prompt context). CRM users are governed by permissions and RLS (scope None).
    from mhvp.portal.access import document_scope_for_user
    from mhvp.workspace.services import local_today

    scope = await document_scope_for_user(session, run.created_by, local_today())
    if scope is not None and any(d not in scope for d in document_ids):
        raise GatewayBlockedError("Mindestens ein angehängtes Dokument ist nicht freigegeben.")

    if run.task in CHUNKED_TASKS:
        # extract_contacts / extract_property: retrieved documents never enter here (rule 1),
        # and every document is chunked by rows instead of being cut off (rule 2).
        chunk_texts: list[str] = []
        for document_id in document_ids:
            name = await _document_name(session, document_id)
            pieces, raw_chars = await document_chunks(session, blobs, document_id)
            input_stats[name] = raw_chars
            chunk_texts.extend(pieces)
        # No document attached (contact data pasted into the chat): the message text itself is
        # the material; the hint keeps the model from waiting for a file.
        chunks = [f"{instruction}\n\n{piece}" for piece in chunk_texts] or [
            f"{instruction}\n\n{NO_DOCUMENT_HINT}"
        ]
        return TaskInput(
            text=chunks[0],
            document_ids=document_ids,
            context=context,
            input_stats=input_stats,
            chunks=chunks,
        )

    if run.task is AiTask.ANSWER_QUESTION and ref.get("rag", True):
        found = await retrieve(
            session,
            str(ref.get("instruction", "")),
            tenant_id=run.tenant_id,
            actor=run.created_by,
            only_ids=sorted(scope) if scope is not None else None,
        )
        if scope is not None:
            found = [d for d in found if d.id in scope]
        document_ids = [*document_ids, *[d.id for d in found if d.id not in document_ids]]

    if run.task is AiTask.ANSWER_QUESTION:
        # Multi turn (rule AI-LOOKUP-01): the stored conversation is the history; platform hits
        # of this question follow as data. Both are masked with the rest of the input. The
        # whole block is fitted into the input budget (``fit_answer_input``): the question and
        # the page context are never trimmed.
        attached_ids = [uuid.UUID(d) for d in ref.get("document_ids", [])]
        docs: list[DocPart] = []
        for document_id in document_ids:
            document, body = await document_body(session, blobs, document_id)
            if len(body) > HARD_LIMIT_CHARS and document_id in attached_ids:
                raise GatewayBlockedError(
                    f"Die Datei {document.filename} ist mit {len(body)} Zeichen zu umfangreich "
                    f"(höchstens {HARD_LIMIT_CHARS}). Bitte in kleinere Teile aufteilen."
                )
            docs.append(DocPart(document.filename, document.id, body, document_id in attached_ids))
        # Approved knowledge entries (M34-01) in front of the documents, so a released rule of
        # the tenant outranks raw document text (audit 29.09.2026, mhvp.ai.knowledge); capped
        # by count and characters, the used ids stay on the run for proof and feedback.
        parts = AnswerParts(
            history=await conversation_history_lines(session, run),
            knowledge=await knowledge_context(session, run, question),
            lookup=ref.get("lookup"),
            documents=docs,
            instruction=None if separate else instruction,
        )
        text, document_ids, input_stats = fit_answer_input(
            parts, budget_tokens or DEFAULT_INPUT_BUDGET_TOKENS
        )
        text = mask_identifiers(text)
        return TaskInput(
            text=text,
            document_ids=document_ids,
            context=context,
            input_stats=input_stats,
            chunks=[],
            instruction=mask_identifiers(question) if separate else None,
        )

    records = ""

    async def _assemble(ids: list[uuid.UUID], max_chars: int) -> tuple[str, dict[str, int]]:
        parts = [] if separate else [instruction]
        if records:
            parts.append(records)
        stats: dict[str, int] = {}
        for document_id in ids:
            text, raw_chars = await document_text(session, blobs, document_id, max_chars=max_chars)
            document = await session.get(Document, document_id)
            stats[document.filename if document else str(document_id)] = raw_chars
            parts.append(text)
        return "\n\n".join(parts), stats

    text, input_stats = await _assemble(document_ids, MAX_DOCUMENT_CHARS)
    if len(text) > MAX_INPUT_CHARS:
        attached = [uuid.UUID(d) for d in ref.get("document_ids", [])]
        for document_id in attached:
            name = await _document_name(session, document_id)
            if input_stats.get(name, 0) > HARD_LIMIT_CHARS:
                raise GatewayBlockedError(
                    f"Die Datei {name} ist mit {input_stats[name]} Zeichen zu umfangreich "
                    f"(höchstens {HARD_LIMIT_CHARS}). Bitte in kleinere Teile aufteilen."
                )
        # Reduce: fewer retrieved documents, each cut harder, before giving up.
        reduced_ids = [
            *attached,
            *[d for d in document_ids if d not in attached][: max(0, REDUCED_RETRIEVE_LIMIT)],
        ]
        text, input_stats = await _assemble(reduced_ids, MAX_DOCUMENT_CHARS // 2)
        document_ids = reduced_ids
        if len(text) > MAX_INPUT_CHARS:
            raise GatewayBlockedError(
                f"Die Unterlagen sind zu umfangreich ({len(text)} Zeichen, höchstens "
                f"{MAX_INPUT_CHARS}). Bitte in kleinere Teile aufteilen."
            )
    if run.task in MASKED_TASKS:
        text = mask_identifiers(text)
        question = mask_identifiers(question)
    return TaskInput(
        text=text,
        document_ids=document_ids,
        context=context,
        input_stats=input_stats,
        chunks=[],
        instruction=question if separate else None,
    )


# Checks and cost --------------------------------------------------------------------------


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _complete_with_retry(
    client: providers.ProviderClient,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> providers.Completion:
    for delay in (*RETRY_DELAYS_S, None):
        try:
            return await client.complete(
                model=model, system=system, messages=messages, schema=schema, max_tokens=max_tokens
            )
        except providers.ProviderError as exc:
            if not exc.retryable or delay is None:
                raise
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def spent_this_month(
    session: AsyncSession, now: datetime, provider: AiProvider | None = None
) -> Decimal:
    query = select(func.coalesce(func.sum(AiTaskRun.cost_eur), 0)).where(
        AiTaskRun.created_at >= month_start(now)
    )
    if provider is not None:
        query = query.where(AiTaskRun.provider == provider)
    value = await session.scalar(query)
    return Decimal(value or 0)


ONLY = {"anthropic_only": AiProvider.ANTHROPIC, "openai_only": AiProvider.OPENAI}
FIRST = {"anthropic_first": AiProvider.ANTHROPIC, "openai_first": AiProvider.OPENAI}


async def routing_strategy(session: AsyncSession) -> str:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(select(TenantSettings.ai_routing))
    return value or "anthropic_first"


async def fast_table_import_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(select(TenantSettings.ai_fast_table_import))
    return True if value is None else bool(value)


POSTING_NOT_RELEASED = "KI-Kontierung ist nicht freigegeben"


async def posting_enabled(session: AsyncSession) -> bool:
    """Tenant switch ``ai_posting_enabled`` (M7-09, M12-01); default off."""
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(select(TenantSettings.ai_posting_enabled))
    return bool(value)


async def posting_block_reason(session: AsyncSession) -> str | None:
    """Why ``propose_posting`` must not run, or ``None``. Both conditions are required: the
    tenant switch and at least one released provider with DPA evidence and training opt-out
    (rule 0.1.13, M7-01 mechanics in ``routes``). Bank transactions carry personal data."""
    if not await posting_enabled(session):
        return f"{POSTING_NOT_RELEASED}: Mandantenschalter ai_posting_enabled ist aus."
    try:
        usable, reasons = await routes(session, AiTask.PROPOSE_POSTING)
    except GatewayBlockedError as exc:
        return f"{POSTING_NOT_RELEASED}: {exc}"
    if not usable:
        return f"{POSTING_NOT_RELEASED}: " + ("; ".join(reasons) or "kein Anbieter freigegeben")
    return None


async def _provider_order(session: AsyncSession, strategy: str) -> list[AiProvider]:
    """Preferred provider first; "alternate" starts with the provider not used last."""
    if strategy in ONLY:
        return [ONLY[strategy]]
    first = FIRST.get(strategy)
    if strategy == "alternate":
        last = await session.scalar(
            select(AiTaskRun.provider)
            .where(AiTaskRun.provider.is_not(None))
            .order_by(AiTaskRun.created_at.desc())
            .limit(1)
        )
        first = AiProvider.OPENAI if last is AiProvider.ANTHROPIC else AiProvider.ANTHROPIC
    others = [p for p in AiProvider if p is not first]
    return [first, *others] if first else others


@dataclass
class Route:
    config: AiProviderConfig
    model: str
    price_in: Decimal
    price_out: Decimal
    tier: str = ""
    context_tokens: int | None = None
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS


def max_output_tokens_of(entry: dict[str, Any]) -> int:
    """Output limit of a tier entry; the platform default when unset or unusable."""
    value = entry.get("max_output_tokens")
    try:
        parsed = int(value) if value is not None else DEFAULT_MAX_OUTPUT_TOKENS
    except (TypeError, ValueError):
        return DEFAULT_MAX_OUTPUT_TOKENS
    return parsed if parsed > 0 else DEFAULT_MAX_OUTPUT_TOKENS


def estimate_tokens(chars: int) -> int:
    return int(Decimal(chars) / CHARS_PER_TOKEN)


async def routes(
    session: AsyncSession, task: AiTask, *, estimated_tokens: int | None = None
) -> tuple[list[Route], list[str]]:
    """Usable providers in strategy order plus the reasons for the unusable ones.

    ``estimated_tokens`` (chars / 3.5 of the run's input): when the configured tier's
    ``context_tokens`` (operator entered, never invented here) is set and the estimate exceeds
    it, the provider's "large" tier is used instead (9.1, model tier escalation)."""
    strategy = await routing_strategy(session)
    order = await _provider_order(session, strategy)
    configs = {
        c.provider: c
        for c in (
            await session.scalars(
                select(AiProviderConfig).where(AiProviderConfig.enabled.is_(True))
            )
        ).all()
    }
    if not configs:
        raise GatewayBlockedError("Kein freigegebener KI-Anbieter eingerichtet.")
    usable: list[Route] = []
    reasons: list[str] = []
    for provider in order:
        config = configs.get(provider)
        if config is None:
            if strategy in ONLY:
                reasons.append(f"{provider.value}: nicht eingerichtet oder nicht aktiv")
            continue
        if config.released_at is None:
            reasons.append(f"{config.provider.value}: Freigabe (Vier-Augen) fehlt")
            continue
        if not (
            config.data_processing_agreement_signed
            and config.dpa_document_id
            and config.training_opt_out_confirmed
        ):
            reasons.append(f"{config.provider.value}: AVV-Nachweis oder Opt-out fehlt")
            continue
        if not config.api_key:
            reasons.append(f"{config.provider.value}: API-Schlüssel fehlt")
            continue
        tier = config.task_tiers.get(task.value) or tasks.DEFAULT_TIERS.get(task, "large")
        entry = (config.models or {}).get(tier) or {}
        context_tokens = entry.get("context_tokens")
        if (
            estimated_tokens is not None
            and tier != "large"
            and context_tokens is not None
            and estimated_tokens > int(context_tokens)
        ):
            tier = "large"
            entry = (config.models or {}).get(tier) or {}
            context_tokens = entry.get("context_tokens")
        try:
            price_in = Decimal(str(entry["input_eur_per_mtok"]))
            price_out = Decimal(str(entry["output_eur_per_mtok"]))
            model = str(entry["model"])
        except (KeyError, ArithmeticError):
            reasons.append(f"{config.provider.value}: Modell oder Preise für Stufe {tier} fehlen")
            continue
        usable.append(
            Route(
                config,
                model,
                price_in,
                price_out,
                tier=tier,
                context_tokens=int(context_tokens) if context_tokens is not None else None,
                max_output_tokens=max_output_tokens_of(entry),
            )
        )
    return usable, reasons


async def route(session: AsyncSession, task: AiTask) -> Route:
    usable, reasons = await routes(session, task)
    if not usable:
        raise GatewayBlockedError("; ".join(reasons))
    return usable[0]


def cost(route_: Route, tokens_in: int, tokens_out: int) -> Decimal:
    # Cache reads are priced like normal input here: an upper bound for the budget check.
    return (Decimal(tokens_in) * route_.price_in + Decimal(tokens_out) * route_.price_out) / MTOK


def input_hash(task: AiTask, version: str, text: str, context: dict[str, Any]) -> str:
    payload = json.dumps({"t": task.value, "v": version, "x": text, "c": context}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def examples(session: AsyncSession, task: AiTask) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(AiExample)
            .where(AiExample.task == task)
            .order_by(AiExample.created_at.desc())
            .limit(FEW_SHOT)
        )
    ).all()
    return [{"merkmale": r.features, "bestaetigt": r.result} for r in rows]


def confidence_of(task: AiTask, data: dict[str, Any]) -> Decimal | None:
    items: list[Any] = []
    if task is AiTask.EXTRACT_CONTACTS:
        items = data.get("contacts", [])
    elif task is AiTask.EXTRACT_PROPERTY:
        items = [*data.get("units", []), *data.get("parties", [])]
    elif task is AiTask.PROPOSE_POSTING:
        items = data.get("proposals", [])
    values = [min(max(float(i.get("confidence", 0)), 0.0), 1.0) for i in items]
    if not values:
        return None
    return Decimal(str(round(sum(values) / len(values), 8)))


# Execution --------------------------------------------------------------------------------


def _messages(
    text: str,
    context: dict[str, Any],
    shots: list[dict[str, Any]],
    instruction: str | None = None,
    *,
    masked: bool = False,
) -> list[dict[str, str]]:
    """The user message: examples, context, the instruction in ``<frage>`` (when handed
    separately) and the data block. ``masked``: the examples are masked like the text of a
    ``MASKED_TASKS`` run, so a stored example (a rejected proposal, ``examples.record_rejection``)
    never carries a phone number, e-mail address or IBAN to the provider (0.1.13)."""
    context_json = json.dumps(context, ensure_ascii=False, sort_keys=True)
    parts = []
    if shots:
        shots_json = json.dumps(shots, ensure_ascii=False)
        if masked:
            shots_json = mask_identifiers(shots_json)
        parts.append(
            "Bestätigte Beispiele dieses Mandanten (nur als Orientierung für Format und "
            f"Zuordnung):\n{shots_json}"
        )
    parts.append(f"Kontext: {context_json}")
    if instruction is not None:
        neutral = lookup.flat(instruction).replace("<", "\u2039").replace(">", "\u203a")
        parts.append(f"<frage>\n{neutral}\n</frage>")
    parts.append(f"<daten>\n{text}\n</daten>")
    return [{"role": "user", "content": "\n\n".join(parts)}]


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def merge_extraction(task: AiTask, outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Concatenates the per chunk results of a row chunked extraction (rule 2): contacts/rows
    are concatenated and deduped by exact identical entries, questions are merged, and one
    property record (the first chunk's) is kept for ``extract_property``."""
    if not outputs:
        outputs = [{}]
    if task is AiTask.EXTRACT_CONTACTS:
        return {
            "contacts": _dedupe_dicts([c for o in outputs for c in o.get("contacts", [])]),
            "questions": _dedupe_strings([q for o in outputs for q in o.get("questions", [])]),
        }
    if task is AiTask.EXTRACT_PROPERTY:
        return {
            "property": outputs[0].get("property", {}),
            "buildings": _dedupe_strings([b for o in outputs for b in o.get("buildings", [])]),
            "units": _dedupe_dicts([u for o in outputs for u in o.get("units", [])]),
            "parties": _dedupe_dicts([p for o in outputs for p in o.get("parties", [])]),
            "questions": _dedupe_strings([q for o in outputs for q in o.get("questions", [])]),
        }
    raise AssertionError(task)  # pragma: no cover - CHUNKED_TASKS covers only these two


def _split_chunk_in_half(chunk_text: str) -> list[str] | None:
    """The provider stopped at ``max_tokens`` for this chunk (too many rows for one answer):
    split it into two, keeping the header (the chunk's first data row) in both halves. Returns
    ``None`` when the chunk holds one row or less and cannot be split further."""
    lines = chunk_text.splitlines()
    row_positions = [i for i, line in enumerate(lines) if line.strip().startswith("Zeile ")]
    if len(row_positions) <= 1:
        return None
    preamble = lines[: row_positions[0]]
    rows = [lines[i] for i in row_positions]
    header, rest = rows[0], rows[1:]
    mid = max(1, len(rest) // 2)

    def build(part: list[str]) -> str:
        return "\n".join([*preamble, header, *part])

    return [build(rest[:mid]), build(rest[mid:])]


@dataclass
class _ChunkResult:
    outputs: list[dict[str, Any]]
    tokens_in: int
    tokens_out: int
    warnings: list[str]
    skips: list[str]
    chosen: "Route"


async def _process_chunks(
    chunks: list[str],
    plan: list[tuple["Route", Decimal, Decimal]],
    keys: dict[AiProvider, str],
    system: str,
    schema: dict[str, Any],
    task: AiTask,
    context: dict[str, Any],
    shots: list[dict[str, Any]],
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    chosen: "Route",
) -> _ChunkResult:
    """Row chunked extraction (rule 2): one provider call per chunk, run concurrently (bounded
    by ``CHUNK_CONCURRENCY``); progress is reported after every finished chunk. Shared by the
    chunked extraction path and the residual rows of the fast table import (M7-06)."""
    tokens_in = tokens_out = 0
    outputs: list[dict[str, Any]] = []
    warnings: list[str] = []
    skips: list[str] = []
    queue: asyncio.Queue[str] = asyncio.Queue()
    for chunk_text in chunks:
        queue.put_nowait(chunk_text)
    done = 0
    pending = len(chunks)
    chosen_ref: list[Any] = [chosen]
    lock = asyncio.Lock()

    async def _work() -> None:
        nonlocal tokens_in, tokens_out, done, pending
        while True:
            try:
                chunk_text = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            messages = _messages(chunk_text, context, shots)
            result = await _call_plan(
                plan, keys, system, messages, schema, task, tenant_id=tenant_id, run_id=run_id
            )
            async with lock:
                tokens_in += result.tokens_in
                tokens_out += result.tokens_out
                skips.extend(result.skips)
                chosen_ref[0] = result.chosen
                if result.output is None and result.error and "max_tokens" in result.error:
                    halves = _split_chunk_in_half(chunk_text)
                    if halves is not None:
                        for half in halves:
                            queue.put_nowait(half)
                        pending += 1
                        continue
                if result.output is not None:
                    outputs.append(result.output)
                else:
                    warnings.append(f"Ein Teil konnte nicht verarbeitet werden: {result.error}")
                done += 1
                total_now = pending
                stage = (
                    f"Verarbeitung Teil {done} von {total_now}" if done < total_now else "Fertig"
                )
            await _update_progress(
                factory, tenant_id, run_id, {"stage": stage, "current": done, "total": total_now}
            )

    await asyncio.gather(*(_work() for _ in range(max(1, CHUNK_CONCURRENCY))))
    return _ChunkResult(outputs, tokens_in, tokens_out, warnings, skips, chosen_ref[0])


async def _run_fast_contacts(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    table: table_mapper.TableData,
    map_plan: list[tuple["Route", Decimal, Decimal]],
    plan: list[tuple["Route", Decimal, Decimal]],
    keys: dict[AiProvider, str],
    instruction: str,
    context: dict[str, Any],
    shots: list[dict[str, Any]],
    chosen: "Route",
) -> tuple[dict[str, Any], int, int, list[str], list[str], "Route"] | None:
    """Fast path for ``extract_contacts`` on a CSV/XLSX table (M7-06): one small ``map_columns``
    call, then deterministic row processing in Python, then only the residual rows (ambiguous or
    invalid ones) through the normal chunked LLM extraction. Returns ``None`` to tell the caller
    to fall back to the full chunked path (no header, or the mapping's confidence is below
    ``table_mapper.MIN_CONFIDENCE``, rule 2 of the plan)."""
    map_prompt = tasks.prompt(AiTask.MAP_COLUMNS)
    map_schema = tasks.json_schema(AiTask.MAP_COLUMNS)
    map_messages = _messages(table_mapper.column_samples(table), {}, [])
    # Operator instruction ("Rolle bank hinterlegen") goes to the mapping call too; before
    # 26.09.2026 only the column samples were sent, so a role from the chat never arrived.
    instructed_role = chat_instructions.role_from_instruction(instruction)
    hint = instruction
    if instructed_role:
        hint += f"\nStandardrolle (roles) aus der Anweisung: {instructed_role}"
    map_messages[0]["content"] = f"{hint}\n\n{map_messages[0]['content']}"
    map_result = await _call_plan(
        map_plan,
        keys,
        map_prompt.system,
        map_messages,
        map_schema,
        AiTask.MAP_COLUMNS,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    tokens_in, tokens_out = map_result.tokens_in, map_result.tokens_out
    mapping_output = map_result.output
    if (
        mapping_output is None
        or not mapping_output.get("has_header", True)
        or float(mapping_output.get("confidence") or 0) < table_mapper.MIN_CONFIDENCE
    ):
        return None
    await _update_progress(
        factory, tenant_id, run_id, {"stage": "Spalten erkannt", "current": 0, "total": 1}
    )
    mapping: dict[str, Any] = {
        m["source_column"]: m["target_field"] for m in mapping_output["mappings"]
    }
    mapped = table_mapper.apply_mapping(
        table, mapping, default_role=mapping_output.get("default_role")
    )
    await _update_progress(
        factory,
        tenant_id,
        run_id,
        {"stage": f"{mapped.processed_rows} Zeilen verarbeitet", "current": 0, "total": 1},
    )
    warnings: list[str] = []
    skipped: list[str] = list(map_result.skips)
    contacts = list(mapped.contacts)
    questions: list[str] = []
    chosen_final = map_result.chosen
    if mapped.residual:
        await _update_progress(
            factory,
            tenant_id,
            run_id,
            {
                "stage": f"{len(mapped.residual)} Zeilen an KI",
                "current": 0,
                "total": len(mapped.residual),
            },
        )
        body = table_mapper.residual_table_text(table, mapped.residual)
        pieces = _chunk_table_body(body)
        residual_chunks = [
            f'{instruction}\n\n<datei name="{table.filename}" teil="{i}/{len(pieces)}">\n'
            f"{piece}\n</datei>"
            for i, piece in enumerate(pieces, start=1)
        ]
        chunk_result = await _process_chunks(
            residual_chunks,
            plan,
            keys,
            tasks.prompt(AiTask.EXTRACT_CONTACTS).system,
            tasks.json_schema(AiTask.EXTRACT_CONTACTS),
            AiTask.EXTRACT_CONTACTS,
            context,
            shots,
            factory,
            tenant_id,
            run_id,
            chosen,
        )
        tokens_in += chunk_result.tokens_in
        tokens_out += chunk_result.tokens_out
        warnings.extend(chunk_result.warnings)
        skipped.extend(chunk_result.skips)
        chosen_final = chunk_result.chosen
        if chunk_result.outputs:
            llm_merged = merge_extraction(AiTask.EXTRACT_CONTACTS, chunk_result.outputs)
            contacts = _dedupe_dicts([*contacts, *llm_merged["contacts"]])
            questions = llm_merged["questions"]
        else:
            warnings.append(
                f"{len(mapped.residual)} Zeile(n) konnten nicht per KI ergänzt werden: "
                f"{chunk_result.warnings[-1] if chunk_result.warnings else 'unbekannter Fehler'}"
            )
    await _update_progress(
        factory, tenant_id, run_id, {"stage": "Fertig", "current": 1, "total": 1}
    )
    output = {"contacts": contacts, "questions": questions}
    return output, tokens_in, tokens_out, warnings, skipped, chosen_final


async def _run_fast_property(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    table: table_mapper.TableData,
    map_plan: list[tuple["Route", Decimal, Decimal]],
    plan: list[tuple["Route", Decimal, Decimal]],
    keys: dict[AiProvider, str],
    instruction: str,
    context: dict[str, Any],
    shots: list[dict[str, Any]],
    chosen: "Route",
) -> tuple[dict[str, Any], int, int, list[str], list[str], "Route"] | None:
    """Fast path for ``extract_property`` on an owner/tenant list (A47): one small
    ``map_columns`` call with the property column model, then deterministic unit/party/payment
    rows in Python (German numbers and dates via ``mhvp.imports.fields``), then only the
    residual rows through the normal chunked ``extract_property`` extraction. The result keeps
    the ``PropertyResult`` shape, so preview and apply (with confirmation) are unchanged; an
    IBAN only appears masked in ``questions`` and is never part of the proposal. Returns
    ``None`` to fall back to the full chunked path (no header or low mapping confidence)."""
    map_messages = _messages(table_mapper.column_samples(table), {}, [])
    map_result = await _call_plan(
        map_plan,
        keys,
        table_mapper.property_map_system_prompt(),
        map_messages,
        table_mapper.property_map_schema(),
        AiTask.MAP_COLUMNS,
        tenant_id=tenant_id,
        run_id=run_id,
        model=table_mapper.PropertyColumnMappingResult,
    )
    tokens_in, tokens_out = map_result.tokens_in, map_result.tokens_out
    mapping_output = map_result.output
    if not table_mapper.mapping_usable(mapping_output):
        return None
    assert mapping_output is not None  # noqa: S101 - mapping_usable checked it
    await _update_progress(
        factory, tenant_id, run_id, {"stage": "Spalten erkannt", "current": 0, "total": 1}
    )
    mapping: dict[str, str] = {
        m["source_column"]: m["target_field"] for m in mapping_output["mappings"]
    }
    mapped = table_mapper.apply_property_mapping(
        table, mapping, default_role=mapping_output.get("default_role")
    )
    await _update_progress(
        factory,
        tenant_id,
        run_id,
        {"stage": f"{mapped.processed_rows} Zeilen verarbeitet", "current": 0, "total": 1},
    )
    warnings: list[str] = []
    skipped: list[str] = list(map_result.skips)
    output: dict[str, Any] = {
        "property": mapped.property,
        "buildings": mapped.buildings,
        "units": mapped.units,
        "parties": mapped.parties,
        "questions": mapped.questions,
    }
    chosen_final = map_result.chosen
    if mapped.residual:
        await _update_progress(
            factory,
            tenant_id,
            run_id,
            {
                "stage": f"{len(mapped.residual)} Zeilen an KI",
                "current": 0,
                "total": len(mapped.residual),
            },
        )
        body = table_mapper.residual_table_text(table, mapped.residual)
        pieces = _chunk_table_body(body)
        residual_chunks = [
            f'{instruction}\n\n<datei name="{table.filename}" teil="{i}/{len(pieces)}">\n'
            f"{piece}\n</datei>"
            for i, piece in enumerate(pieces, start=1)
        ]
        chunk_result = await _process_chunks(
            residual_chunks,
            plan,
            keys,
            tasks.prompt(AiTask.EXTRACT_PROPERTY).system,
            tasks.json_schema(AiTask.EXTRACT_PROPERTY),
            AiTask.EXTRACT_PROPERTY,
            context,
            shots,
            factory,
            tenant_id,
            run_id,
            chosen,
        )
        tokens_in += chunk_result.tokens_in
        tokens_out += chunk_result.tokens_out
        warnings.extend(chunk_result.warnings)
        skipped.extend(chunk_result.skips)
        chosen_final = chunk_result.chosen
        if chunk_result.outputs:
            # Deterministic result first: its property record wins when it names anything,
            # units and parties are concatenated and deduped like the chunked path does.
            llm = merge_extraction(AiTask.EXTRACT_PROPERTY, chunk_result.outputs)
            has_property = any(v for v in mapped.property.values())
            output = merge_extraction(
                AiTask.EXTRACT_PROPERTY, [output, llm] if has_property else [llm, output]
            )
        else:
            warnings.append(
                f"{len(mapped.residual)} Zeile(n) konnten nicht per KI ergänzt werden: "
                f"{chunk_result.warnings[-1] if chunk_result.warnings else 'unbekannter Fehler'}"
            )
    await _update_progress(
        factory, tenant_id, run_id, {"stage": "Fertig", "current": 1, "total": 1}
    )
    return output, tokens_in, tokens_out, warnings, skipped, chosen_final


@dataclass
class _PlanResult:
    output: dict[str, Any] | None
    tokens_in: int
    tokens_out: int
    error: str | None
    skips: list[str]
    chosen: Route
    # The provider refused the input as too large (HTTP 400 naming tokens or the context):
    # the chat retries once with the budget halved (``_call_within_budget``).
    token_limit: bool = False


def _status_of(exc: providers.ProviderError) -> int | None:
    """HTTP status from the chained SDK exception, if any (for the structured log)."""
    cause = exc.__cause__
    status = getattr(cause, "status_code", None)
    return status if isinstance(status, int) else None


_TOKEN_LIMIT = re.compile(r"token|context|kontext", re.I)
CONTEXT_WINDOW_NOTICE = (
    "Die Eingabe überschreitet das Kontextfenster des KI-Anbieters, auch nach Kürzung der "
    "Dokumente und des Verlaufs."
)


def is_token_limit_error(exc: providers.ProviderError) -> bool:
    """A 400 whose message names tokens or the context window ("Input tokens exceed the
    configured limit ...")."""
    text = str(exc)
    status = _status_of(exc)
    return (status == 400 or "400" in text) and bool(_TOKEN_LIMIT.search(text))


async def _call_within_budget(
    call: Callable[[TaskInput], Awaitable[_PlanResult]],
    rebuild: Callable[[int], Awaitable[TaskInput]],
    item: TaskInput,
    budget_tokens: int,
) -> tuple[_PlanResult, TaskInput]:
    """Chat call with the input budget: on a provider 400 naming the token or context limit
    the input is rebuilt with the budget halved and sent once more; a second refusal ends
    the run with ``CONTEXT_WINDOW_NOTICE`` (the job then answers with the hit list)."""
    result = await call(item)
    if not result.token_limit:
        return result, item
    log.warning("ai_input_over_limit_retry", budget_tokens=budget_tokens)
    item = await rebuild(max(1, budget_tokens // 2))
    result = await call(item)
    if result.token_limit:
        result.error = CONTEXT_WINDOW_NOTICE
    return result, item


async def _call_plan(
    plan: list[tuple[Route, Decimal, Decimal]],
    keys: dict[AiProvider, str],
    system: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    task: AiTask,
    *,
    tenant_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    model: type[BaseModel] | None = None,
) -> _PlanResult:
    """One prompt against the routing plan: retries per provider (schema errors), falls back to
    the next provider of the plan on a provider error (budget exhausted providers are already
    filtered out of ``plan``). ``model`` overrides the task's output schema for validation
    (the property variant of ``map_columns``, A47); by default ``tasks.SCHEMAS[task]``."""
    output_model: type[BaseModel] = model or tasks.SCHEMAS[task]
    tokens_in = tokens_out = 0
    output: dict[str, Any] | None = None
    error: str | None = None
    skips: list[str] = []
    chosen = plan[0][0]
    token_limit = False
    for step in plan:
        chosen, _spent, _budget = step
        provider = chosen.config.provider
        client = providers.client_for(provider, keys[provider], chosen.config.endpoint_region)
        current_messages = messages
        provider_failed = False
        try:
            for attempt in range(2):
                try:
                    completion = await _complete_with_retry(
                        client,
                        chosen.model,
                        system,
                        current_messages,
                        schema,
                        max_tokens=chosen.max_output_tokens,
                    )
                except providers.ProviderError as exc:
                    error = f"Anbieterfehler: {exc}"
                    provider_failed = True
                    token_limit = is_token_limit_error(exc)
                    log.warning(
                        "ai_provider_error",
                        tenant_id=str(tenant_id) if tenant_id else None,
                        run_id=str(run_id) if run_id else None,
                        provider=provider.value,
                        model=chosen.model,
                        status=_status_of(exc),
                        reason=str(exc),
                        retryable=exc.retryable,
                    )
                    break
                tokens_in += completion.tokens_in
                tokens_out += completion.tokens_out
                try:
                    output = output_model.model_validate(completion.data).model_dump(mode="json")
                    error = None
                    break
                except ValidationError as exc:
                    error = f"Schemafehler: {exc.errors()[0]['msg']} bei {exc.errors()[0]['loc']}"
                    if attempt == 0:
                        current_messages = [
                            *current_messages,
                            {"role": "assistant", "content": completion.raw_text or "{}"},
                            {
                                "role": "user",
                                "content": f"Die Antwort verletzt das Schema: {error}. "
                                "Bitte vollständig und schemakonform neu antworten.",
                            },
                        ]
        finally:
            await providers.close_client(client)
        if not provider_failed:
            break
        skips.append(f"{provider.value}: {error}")
        if token_limit:
            break  # the caller retries with a smaller input instead of the next provider
    return _PlanResult(output, tokens_in, tokens_out, error, skips, chosen, token_limit)


async def _update_progress(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    progress: dict[str, Any],
) -> None:
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)
        if run is not None:
            run.input_ref = {**run.input_ref, "progress": progress}


async def execute(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    blobs: BlobStore,
    actor_user_id: uuid.UUID | None,
) -> AiTaskRun:
    """Run a queued task. Three short transactions; the provider call happens outside them."""
    now = datetime.now(UTC)
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)
        if run is None or run.status is not RunStatus.QUEUED:
            raise GatewayBlockedError("Lauf nicht gefunden oder bereits bearbeitet.")
        task = run.task
        prompt = tasks.prompt(task, run.prompt_version)
        try:
            if task is AiTask.PROPOSE_POSTING:
                blocked = await posting_block_reason(session)
                if blocked is not None:
                    raise GatewayBlockedError(blocked)
            budget_tokens = (
                await input_budget_tokens(session, task) if task is AiTask.ANSWER_QUESTION else None
            )
            item = await build_input(session, blobs, run, budget_tokens=budget_tokens)
            estimated_chars = (
                len(item.text) if not item.chunks else max(len(c) for c in item.chunks)
            )
            estimated_tokens = estimate_tokens(estimated_chars)
            usable, reasons = await routes(session, task, estimated_tokens=estimated_tokens)
            model_tier_reason = (
                "Großes Modell wegen Umfang gewählt"
                if usable
                and usable[0].tier == "large"
                and estimated_tokens > 0
                and tasks.DEFAULT_TIERS.get(task, "large") != "large"
                and any(r.context_tokens is not None for r in usable)
                else None
            )
            run.input_ref = {**run.input_ref, "input_stats": item.input_stats}
            if model_tier_reason:
                run.input_ref = {**run.input_ref, "model_tier_reason": model_tier_reason}
            # Budget per provider; exhausted providers are skipped (fallback, M7-02) unless
            # the strategy names a single provider, then the run is blocked.
            plan: list[tuple[Route, Decimal, Decimal]] = []
            for candidate in usable:
                budget = candidate.config.monthly_budget_eur
                spent = await spent_this_month(session, now, candidate.config.provider)
                if budget <= 0 or spent >= budget:
                    reasons.append(
                        f"{candidate.config.provider.value}: Monatsbudget erreicht "
                        f"({spent:.2f} von {budget:.2f} EUR); harte Sperre"
                    )
                    continue
                plan.append((candidate, spent, budget))
            if not plan:
                raise GatewayBlockedError("; ".join(reasons))
            skipped = list(reasons)
            preferred = usable[0].config.provider
            # Fast table import (M7-06): a table document eligible for the deterministic path
            # also needs its own (small) route for the map_columns call; without one, or with
            # the flag off, the run falls back to the normal chunked extraction below unchanged.
            fast_table: table_mapper.TableData | None = None
            map_plan: list[tuple[Route, Decimal, Decimal]] = []
            if task in FAST_TABLE_TASKS and await fast_table_import_enabled(session):
                doc_ids = [uuid.UUID(d) for d in run.input_ref.get("document_ids", [])]
                if len(doc_ids) == 1:
                    document = await session.get(Document, doc_ids[0])
                    if document is not None and document.mime_type in TABLE_MIME_TYPES:
                        candidate_table = table_mapper.load_table(
                            document.mime_type,
                            blobs.get(document.storage_ref),
                            document.filename,
                        )
                        if candidate_table.header and candidate_table.rows:
                            fast_table = candidate_table
            if fast_table is not None:
                try:
                    map_usable, _map_reasons = await routes(session, AiTask.MAP_COLUMNS)
                except GatewayBlockedError:
                    map_usable = []
                for candidate in map_usable:
                    m_spent = await spent_this_month(session, now, candidate.config.provider)
                    m_budget = candidate.config.monthly_budget_eur
                    if m_budget > 0 and m_spent < m_budget:
                        map_plan.append((candidate, m_spent, m_budget))
                if not map_plan:
                    fast_table = None  # no usable route for the mapping call: silent fallback
        except GatewayBlockedError as exc:
            run.status, run.error = RunStatus.BLOCKED, str(exc)
            await emit(
                session,
                tenant_id=tenant_id,
                type="ai.run_blocked",
                entity_type="ai_task_run",
                entity_id=run.id,
                actor_user_id=actor_user_id,
                payload={"reason": str(exc)},
            )
            return run
        previous = await session.scalar(
            select(AiTaskRun)
            .where(
                AiTaskRun.input_hash == run.input_hash,
                AiTaskRun.status == RunStatus.SUCCEEDED,
                AiTaskRun.id != run.id,
            )
            .order_by(AiTaskRun.created_at.desc())
            .limit(1)
        )
        if previous is not None:  # deduplication by input hash (9.3)
            run.status, run.output, run.confidence = (
                RunStatus.SUCCEEDED,
                previous.output,
                previous.confidence,
            )
            run.provider, run.model = previous.provider, previous.model
            run.input_ref = {**run.input_ref, "deduplicated_from": str(previous.id)}
            return run
        shots = await examples(session, task)
        keys = {c.config.provider: c.config.api_key or "" for c, _, _ in [*plan, *map_plan]}
        chosen, spent, budget = plan[0]
        total_parts = len(item.chunks) if item.chunks else 1
        instruction = f"Anweisung des Nutzers: {run.input_ref.get('instruction', '')}"
        run.status, run.provider, run.model = (
            RunStatus.RUNNING,
            chosen.config.provider,
            chosen.model,
        )
        run.input_ref = {
            **run.input_ref,
            "progress": {
                "stage": f"Verarbeitung Teil 1 von {total_parts}",
                "current": 0,
                "total": total_parts,
            },
        }
    started = time.monotonic()
    schema = tasks.json_schema(task)
    tokens_in = tokens_out = 0
    output: dict[str, Any] | None = None
    error: str | None = None
    skipped_extra: list[str] = []
    warnings: list[str] = []

    outputs: list[dict[str, Any]] = []
    fast_used = False
    if fast_table is not None:
        # Fast table import (M7-06): map_columns plus deterministic rows, only residual rows
        # (if any) go through the chunked LLM extraction below.
        fast_runner = _run_fast_property if task is AiTask.EXTRACT_PROPERTY else _run_fast_contacts
        fast_out = await fast_runner(
            factory,
            tenant_id,
            run_id,
            fast_table,
            map_plan,
            plan,
            keys,
            instruction,
            item.context,
            shots,
            chosen,
        )
        if fast_out is not None:
            fast_used = True
            output, tokens_in, tokens_out, warnings, skipped_extra, chosen = fast_out
            error = None
            total_parts = 1
    if not fast_used:
        if item.chunks and task in CHUNKED_TASKS:
            # Row chunked extraction (rule 2): one provider call per chunk, merged afterwards.
            # Chunks run concurrently (bounded by CHUNK_CONCURRENCY): the wall clock is dominated
            # by provider latency, not CPU, so sequential calls made an 11 part import take
            # minutes.
            chunk_result = await _process_chunks(
                item.chunks,
                plan,
                keys,
                prompt.system,
                schema,
                task,
                item.context,
                shots,
                factory,
                tenant_id,
                run_id,
                chosen,
            )
            outputs = chunk_result.outputs
            tokens_in, tokens_out = chunk_result.tokens_in, chunk_result.tokens_out
            warnings, skipped_extra, chosen = (
                chunk_result.warnings,
                chunk_result.skips,
                chunk_result.chosen,
            )
            if outputs:
                output = merge_extraction(task, outputs)
                error = None
            else:
                error = warnings[-1] if warnings else "Alle Teile fehlgeschlagen."
        else:

            async def _call(current: TaskInput) -> _PlanResult:
                messages = _messages(
                    current.text,
                    current.context,
                    shots,
                    current.instruction,
                    masked=task in MASKED_TASKS,
                )
                return await _call_plan(
                    plan,
                    keys,
                    prompt.system,
                    messages,
                    schema,
                    task,
                    tenant_id=tenant_id,
                    run_id=run_id,
                )

            async def _rebuild(smaller: int) -> TaskInput:
                async with tenant_transaction(factory, tenant_id) as session:
                    current = await session.get(AiTaskRun, run_id)
                    assert current is not None  # noqa: S101 - locked above
                    rebuilt = await build_input(session, blobs, current, budget_tokens=smaller)
                    current.input_ref = {**current.input_ref, "input_stats": rebuilt.input_stats}
                    return rebuilt

            if task is AiTask.ANSWER_QUESTION and budget_tokens is not None:
                result, item = await _call_within_budget(_call, _rebuild, item, budget_tokens)
            else:
                result = await _call(item)
            tokens_in, tokens_out = result.tokens_in, result.tokens_out
            output, error, skipped_extra, chosen = (
                result.output,
                result.error,
                result.skips,
                result.chosen,
            )

    skipped.extend(skipped_extra)
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)
        assert run is not None  # noqa: S101 - locked above
        run.provider, run.model = chosen.config.provider, chosen.model
        # The answering provider (M7-02): differs from the preferred one after a fallback.
        run.input_ref = {**run.input_ref, "provider_used": chosen.config.provider.value}
        if skipped:
            run.input_ref = {**run.input_ref, "fallback": skipped}
        if skipped and chosen.config.provider is not preferred:
            # The switch itself is an event (M7-02): preferred provider, answering provider and
            # the reasons; ``skipped`` carries no key material (providers.status_detail).
            log.info(
                "ai_provider_fallback",
                tenant_id=str(tenant_id),
                run_id=str(run_id),
                preferred=preferred.value,
                provider_used=chosen.config.provider.value,
            )
            await emit(
                session,
                tenant_id=tenant_id,
                type="ai.provider_fallback",
                entity_type="ai_task_run",
                entity_id=run.id,
                actor_user_id=actor_user_id,
                payload={
                    "task": task.value,
                    "preferred": preferred.value,
                    "provider_used": chosen.config.provider.value,
                    "reasons": skipped,
                },
            )
        if not fast_used and item.chunks and task in CHUNKED_TASKS:
            row_count = sum(text.count("Zeile ") for text in item.chunks)
            extracted = len(output.get("contacts") or output.get("units") or []) if output else 0
            skipped_rows = len(item.chunks) - len(outputs)
            if row_count and extracted + skipped_rows < row_count:
                warnings = [
                    *warnings,
                    f"Zeilen gelesen: {row_count}, Datensätze erzeugt: {extracted} "
                    f"(nicht verarbeitete Teile: {skipped_rows}). Bitte Ergebnis prüfen.",
                ]
        if warnings:
            run.input_ref = {**run.input_ref, "warnings": warnings}
        run.input_ref = {
            **run.input_ref,
            "progress": {"stage": "Fertig", "current": total_parts, "total": total_parts},
        }
        run.tokens_in, run.tokens_out = tokens_in, tokens_out
        run.cost_eur = cost(chosen, tokens_in, tokens_out)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        if output is not None:
            run.status, run.output = RunStatus.SUCCEEDED, output
            run.confidence = confidence_of(task, output)
        else:
            run.status, run.error = RunStatus.FAILED, error
        threshold = budget * WARN_SHARE
        if spent < threshold <= spent + run.cost_eur:
            await emit(
                session,
                tenant_id=tenant_id,
                type="ai.budget_warning",
                entity_type="ai_task_run",
                entity_id=run.id,
                actor_user_id=actor_user_id,
                payload={"threshold": "80%"},
            )
        await emit(
            session,
            tenant_id=tenant_id,
            type=f"ai.run_{run.status.value}",
            entity_type="ai_task_run",
            entity_id=run.id,
            actor_user_id=actor_user_id,
            payload={"task": task.value, "cost_eur": str(run.cost_eur)},
        )
    return run
