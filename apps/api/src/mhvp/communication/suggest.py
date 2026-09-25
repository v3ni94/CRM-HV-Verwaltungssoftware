"""KI-Vorschläge je eingehender Mail und Playbooks aus geschlossenen Tickets (M20 Übernahme
aus dem Immoware Hub, docs/integrations/mail-optimierung.md).

Alles hier ist ein Vorschlag; nichts wird automatisch geschrieben oder versendet, das
Vier-Augen-Prinzip beim Versand (routers.py) bleibt unberührt. Der KI-Aufruf läuft über
``mhvp.ai.gateway``, also mit derselben Freigabe-, Budget- und Auditlogik wie der Assistent
(9.1, 9.3, 9.4, Regel 0.1.13). Ohne freigegebenen Anbieter oder bei ausgeschöpftem Budget wird
kein Fehler geworfen; der Vorschlag wird mit Status ``skipped`` und Grund gespeichert."""

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.ai import gateway
from mhvp.ai.models import AiTask, AiTaskRun, RunStatus
from mhvp.communication import mail
from mhvp.communication.models import Message, Playbook
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore

MAX_EXCERPT = 4000
MIN_PLAYBOOK_SCORE = 0.3
WORD_RE = re.compile(r"[\wäöüÄÖÜß]{4,}")


def score_playbook(text: str, keywords: list[str]) -> float:
    """Keyword-Überlappung zwischen Mailtext und den Schlagwörtern eines Playbooks, 0 bis 1."""
    if not keywords:
        return 0.0
    haystack = text.lower()
    words = {w.lower() for w in WORD_RE.findall(text)}
    hits = sum(1 for k in keywords if k.lower() in words or k.lower() in haystack)
    return round(min(hits / len(keywords), 1.0), 4)


async def _active_playbooks(session: AsyncSession) -> list[Playbook]:
    return list(
        await session.scalars(
            select(Playbook).where(Playbook.status == "active").order_by(Playbook.title)
        )
    )


async def best_playbook(session: AsyncSession, text: str) -> tuple[Playbook | None, float]:
    best: Playbook | None = None
    best_score = 0.0
    for row in await _active_playbooks(session):
        current = score_playbook(text, row.keywords)
        if current > best_score:
            best, best_score = row, current
    if best is not None and best_score >= MIN_PLAYBOOK_SCORE:
        return best, best_score
    return None, 0.0


def _fallback(message: Message, categories: list[str]) -> dict[str, Any]:
    return {
        "category": mail.category(message.subject, message.body, categories),
        "urgency": "high" if mail.urgency(message.subject, message.body) == "urgent" else "normal",
        "summary": (message.subject or "E-Mail ohne Betreff")[:300],
        "property_number": mail.property_number(message.subject, message.body),
        "contact_name": None,
        "reply_draft": None,
    }


async def _run_gateway_task(
    settings: Settings,
    tenant_id: uuid.UUID,
    task: AiTask,
    prompt_text: str,
    context: dict[str, Any],
) -> AiTaskRun:
    """Queues and executes one gateway run in its own connection (mirrors ``mhvp.ai.jobs``),
    independent from the caller's own transaction."""
    from mhvp.ai import tasks as ai_tasks

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        prompt = ai_tasks.prompt(task)
        run_id: uuid.UUID
        async with tenant_transaction(factory, tenant_id) as session:
            run = AiTaskRun(
                tenant_id=tenant_id,
                task=task,
                prompt_version=prompt.version,
                input_hash=gateway.input_hash(task, prompt.version, prompt_text, context),
                input_ref={
                    "instruction": prompt_text,
                    "document_ids": [],
                    "context": context,
                },
                status=RunStatus.QUEUED,
            )
            session.add(run)
            await session.flush()
            run_id = run.id
        return await gateway.execute(factory, tenant_id, run_id, BlobStore(settings), None)
    finally:
        await engine.dispose()


async def suggest_for_message(
    session: AsyncSession, settings: Settings, message: Message
) -> dict[str, Any]:
    """Berechnet den Vorschlag für eine Mail. Gibt ein Dict mit ``status`` (ready, skipped,
    failed) und den Vorschlagsfeldern zurück; der Aufrufer trägt es in ``Message.suggestion``
    und ``Message.suggestion_status`` ein."""
    from mhvp.tickets.models import TicketTemplate

    categories = list(await session.scalars(select(TicketTemplate.category)))
    playbooks = await _active_playbooks(session)
    body_excerpt = (message.body or "")[:MAX_EXCERPT]
    match_text = f"{message.subject or ''}\n{body_excerpt}"
    playbook, playbook_score = await best_playbook(session, match_text)

    prompt_text = (
        f"Betreff: {message.subject or ''}\n"
        f"Absender: {message.from_address or ''}\n"
        f"Text (Auszug):\n{body_excerpt}\n\n"
        f"Bekannte Ticketkategorien: {', '.join(categories) or '-'}\n"
        "Bekannte Playbooks (Titel, Schlagwörter): "
        + ("; ".join(f"{p.title} ({', '.join(p.keywords)})" for p in playbooks) or "-")
        + "\nObjektnummern stehen meist als dreistellige Zahl nach 'Objekt' oder 'Objekt Nr.'."
    )
    context = {"context_type": "message", "context_id": str(message.id)}

    try:
        run = await _run_gateway_task(
            settings, message.tenant_id, AiTask.CLASSIFY_EMAIL, prompt_text, context
        )
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)[:500]}

    result: dict[str, Any]
    if run.status is RunStatus.SUCCEEDED and run.output:
        output = run.output
        fallback = _fallback(message, categories)
        result = {
            "category": output.get("category") or fallback["category"],
            "urgency": output.get("urgency") or fallback["urgency"],
            "summary": output.get("summary") or fallback["summary"],
            "property_number": output.get("property_number") or fallback["property_number"],
            "contact_name": output.get("contact_name"),
            "reply_draft": output.get("reply_draft"),
            "model": run.model,
        }
        status = "ready"
    elif run.status is RunStatus.BLOCKED:
        result = {"reason": run.error or "Kein freigegebener KI-Anbieter."}
        status = "skipped"
    else:
        result = {"reason": run.error or "KI-Lauf fehlgeschlagen."}
        status = "failed"

    if playbook is not None:
        result["playbook_id"] = str(playbook.id)
        result["playbook_score"] = playbook_score
    return {"status": status, **result}


async def learn_playbook_from_ticket(
    session: AsyncSession, settings: Settings, ticket: Any
) -> Playbook | None:
    """Erzeugt aus einem geschlossenen Ticket einen Playbook-Entwurf (Status draft), sofern
    noch kein ähnlich betiteltes Playbook existiert und ein KI-Anbieter freigegeben ist."""
    from mhvp.tickets.models import TicketComment

    comments = list(
        await session.scalars(
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket.id)
            .order_by(TicketComment.created_at)
        )
    )
    sent_replies = list(
        await session.scalars(
            select(Message)
            .where(
                Message.ticket_id == ticket.id,
                Message.direction == "out",
                Message.status == "sent",
            )
            .order_by(Message.sent_at)
        )
    )
    if not comments and not sent_replies:
        return None

    existing = await session.scalar(
        select(Playbook).where(Playbook.title.ilike(f"%{ticket.title[:60]}%"))
    )
    if existing is not None:
        return None

    body = [f"Titel: {ticket.title}", f"Kategorie: {ticket.category or '-'}"]
    for comment in comments:
        body.append(f"Kommentar ({'intern' if comment.internal else 'extern'}): {comment.body}")
    for reply in sent_replies:
        body.append(f"Gesendete Antwort: {reply.body or ''}")
    prompt_text = "\n".join(body)[:MAX_EXCERPT]
    context = {"context_type": "ticket", "context_id": str(ticket.id)}

    try:
        run = await _run_gateway_task(
            settings, ticket.tenant_id, AiTask.DRAFT_REPLY, prompt_text, context
        )
    except Exception:
        return None
    if run.status is not RunStatus.SUCCEEDED or not run.output:
        return None

    output = run.output
    title = str(output.get("title") or ticket.title)[:200]
    duplicate = await session.scalar(select(Playbook).where(Playbook.title == title))
    if duplicate is not None:
        return None
    draft = Playbook(
        tenant_id=ticket.tenant_id,
        title=title,
        category=output.get("category"),
        keywords=[str(k)[:64] for k in output.get("keywords", [])][:10],
        summary=str(output.get("summary") or ""),
        steps=[str(s) for s in output.get("steps", [])],
        reply_template=output.get("reply_template"),
        source_ticket_id=ticket.id,
        status="draft",
    )
    session.add(draft)
    await session.flush()
    return draft
