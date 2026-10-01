"""AI answer of the portal assistant (AE28, M7-06, 9.1 RAG, 9.2 ``answer_question``, 14).

A question of a tenant or owner runs as task ``answer_question`` through the regular gateway
path (released provider with data processing agreement and training opt out, budget, masking)
under these restrictions, all enforced here or in ``gateway.build_input``:

* the audience marker ``portal`` makes the gateway take the readable documents from the access
  grants of the account (``mhvp.portal.assistant_scope``) and never from CRM permissions; the
  focus list of the run can only narrow that scope;
* no platform lookup, no tool use, no chat action, no internal knowledge base, no few shot
  examples: only released documents of the person reach the prompt (prompt ``portal_v1``);
* the question is masked (IBAN, e-mail, phone, addresses) before it is stored and before the
  provider sees it (rule 0.1.13);
* the input hash contains the account and a fingerprint of the scope, so the deduplication of
  the gateway can never hand the answer of one person to another;
* the answer is a proposal for information. Sources are checked against the scope after the run:
  a source outside the scope is dropped, an answer without any valid source is not shown as an
  answer (grounded answers only); a chat action of the model is discarded.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai import gateway, tasks
from mhvp.ai.masking import mask_personal_data
from mhvp.ai.models import AiTask, AiTaskRun, RunStatus
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.models import Document

PROMPT_VARIANT = "portal_v1"
CONTEXT_TYPE = "portal_assistant"
MAX_ANSWER_CHARS = 4000
MAX_EXCERPT_CHARS = 300
NO_BASIS_TEXT = (
    "Zu Ihrer Frage habe ich in den für Sie freigegebenen Unterlagen keine ausreichende "
    "Grundlage gefunden. Bitte schreiben Sie der Verwaltung eine Meldung."
)


@dataclass
class PortalAnswer:
    """Result of one AI stage: ``status`` is answered, not_answerable or failed."""

    status: str
    answer: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    run_id: uuid.UUID | None = None
    reason_code: str | None = None
    technical_reason: str | None = None


def scope_fingerprint(scope_ids: set[uuid.UUID] | frozenset[uuid.UUID]) -> str:
    return hashlib.sha256(",".join(sorted(str(i) for i in scope_ids)).encode()).hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


async def verified_sources(
    session: AsyncSession, raw_sources: object, scope_ids: set[uuid.UUID] | frozenset[uuid.UUID]
) -> list[dict[str, Any]]:
    """Sources named by the model that lie inside the scope, one entry per document. The excerpt
    is kept only when it occurs in the stored text of the document (best effort check)."""
    if not isinstance(raw_sources, list):
        return []
    wanted: dict[uuid.UUID, str | None] = {}
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        try:
            document_id = uuid.UUID(str(item.get("document_id")))
        except ValueError:
            continue
        if document_id in scope_ids and document_id not in wanted:
            excerpt = item.get("excerpt")
            wanted[document_id] = excerpt if isinstance(excerpt, str) else None
    if not wanted:
        return []
    rows = (await session.scalars(select(Document).where(Document.id.in_(list(wanted))))).all()
    by_id = {d.id: d for d in rows}
    out: list[dict[str, Any]] = []
    for document_id, excerpt in wanted.items():
        document = by_id.get(document_id)
        if document is None:
            continue
        shown: str | None = None
        if excerpt and document.ocr_text and _norm(excerpt) in _norm(document.ocr_text):
            shown = excerpt.strip()[:MAX_EXCERPT_CHARS]
        out.append(
            {
                "document_id": document_id,
                "title": document.title or document.filename,
                "excerpt": shown,
            }
        )
    return out


async def answer(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    *,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    question: str,
    scope_ids: set[uuid.UUID] | frozenset[uuid.UUID],
    focus_ids: list[uuid.UUID] | None,
    attach_document_id: uuid.UUID | None,
    blobs: Any,
) -> PortalAnswer:
    """Queues and executes the run inline and returns the checked result. The caller has checked
    the tenant switches, the privacy acknowledgement and that the scope is not empty."""
    from mhvp.ai import jobs

    masked = mask_personal_data(question)
    prompt = tasks.prompt(AiTask.ANSWER_QUESTION, PROMPT_VARIANT)
    context = {"context_type": CONTEXT_TYPE, "context_id": str(account_id)}
    ref: dict[str, Any] = {
        "instruction": masked,
        "document_ids": [str(attach_document_id)] if attach_document_id else [],
        "context": context,
        "audience": gateway.PORTAL_AUDIENCE,
        "portal_account_id": str(account_id),
        "portal_focus_ids": [str(i) for i in sorted(focus_ids)] if focus_ids is not None else None,
        "rag": True,
    }
    hash_context = {
        **context,
        "account": str(account_id),
        "scope": scope_fingerprint(scope_ids),
        "docs": ref["document_ids"],
    }
    async with tenant_transaction(factory, tenant_id) as session:
        run = AiTaskRun(
            tenant_id=tenant_id,
            created_by=user_id,
            task=AiTask.ANSWER_QUESTION,
            conversation_id=None,
            prompt_version=prompt.version,
            input_hash=gateway.input_hash(
                AiTask.ANSWER_QUESTION, prompt.version, masked, hash_context
            ),
            input_ref=ref,
            status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.flush()
        run_id = run.id
    done = await jobs.run_and_propose(factory, tenant_id, run_id, blobs, user_id)
    if done is None or done.status is not RunStatus.SUCCEEDED:
        reason = (done.error if done is not None else None) or "Lauf nicht ausgeführt."
        return PortalAnswer(
            status="failed",
            run_id=run_id,
            reason_code="ai_run_failed",
            technical_reason=str(reason)[:500],
        )
    output = done.output or {}
    async with tenant_transaction(factory, tenant_id) as session:
        sources = await verified_sources(session, output.get("sources"), scope_ids)
    text = str(output.get("answer") or "").strip()
    if not output.get("answerable", True) or not sources or not text:
        # Grounded answers only: no valid source inside the scope, no answer shown.
        return PortalAnswer(
            status="not_answerable", answer=NO_BASIS_TEXT, sources=sources, run_id=run_id
        )
    return PortalAnswer(
        status="answered", answer=text[:MAX_ANSWER_CHARS], sources=sources, run_id=run_id
    )
