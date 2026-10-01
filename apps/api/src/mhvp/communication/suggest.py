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

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.ai import gateway
from mhvp.ai.models import AiExample, AiTask, AiTaskRun, RunStatus
from mhvp.communication import mail
from mhvp.communication.models import Message, Playbook
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.tickets.flows import PROCESS_CATALOGUE

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


CATEGORY_BONUS = 0.2


def rank_playbooks(
    text: str, playbooks: list[Any], category: str | None = None
) -> list[tuple[float, Any]]:
    """Pure: playbooks with their score for ``text``, best first. A playbook of the mail's
    (deterministic) ``category`` gets ``CATEGORY_BONUS`` on top of the keyword score, one of
    another category none, so among equal keyword hits the category decides (audit
    29.09.2026). Playbooks without any keyword hit stay out whatever their category."""
    wanted = (category or "").strip().lower()
    scored: list[tuple[float, Any]] = []
    for row in playbooks:
        score = score_playbook(text, row.keywords)
        if score <= 0.0:
            continue
        own = (row.category or "").strip().lower()
        if wanted and own == wanted:
            score = round(min(score + CATEGORY_BONUS, 1.0), 4)
        scored.append((score, row))
    scored.sort(key=lambda item: -item[0])
    return scored


async def best_playbook(
    session: AsyncSession,
    text: str,
    *,
    category: str | None = None,
    playbooks: list[Playbook] | None = None,
) -> tuple[Playbook | None, float]:
    rows = playbooks if playbooks is not None else await _active_playbooks(session)
    ranked = rank_playbooks(text, rows, category)
    if ranked and ranked[0][0] >= MIN_PLAYBOOK_SCORE:
        return ranked[0][1], ranked[0][0]
    return None, 0.0


def fallback_suggestion(
    subject: str | None, body: str | None, categories: list[str]
) -> dict[str, Any]:
    """Deterministic suggestion from ``mhvp.communication.mail`` (keywords only), used where
    the model answers null or the run fails."""
    process = mail.process_category(subject, body)
    return {
        "category": mail.category(subject, body, categories),
        "urgency": "high" if mail.urgency(subject, body) == "urgent" else "normal",
        "summary": (subject or "E-Mail ohne Betreff")[:300],
        "property_number": mail.property_number(subject, body),
        "contact_name": None,
        "reply_draft": None,
        "process_code": process["process_code"],
        "process_confidence": process["confidence"],
        "process_reason": process["reason"],
    }


def _fallback(message: Message, categories: list[str]) -> dict[str, Any]:
    return fallback_suggestion(message.subject, message.body, categories)


def merge_suggestion(
    output: dict[str, Any],
    fallback: dict[str, Any],
    *,
    candidates: dict[str, set[str]] | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Model answer (``MailSuggestion``) over the deterministic fallback: every null or empty
    classification field falls back; ``contact_name`` and ``reply_draft`` stay as answered
    (null stays null, nothing is invented). Pure, so the offline evaluation (9.1,
    ``mhvp.ai.evaluate``) scores exactly this step."""
    merged = {
        "category": output.get("category") or fallback["category"],
        "urgency": output.get("urgency") or fallback["urgency"],
        "summary": output.get("summary") or fallback["summary"],
        "property_number": output.get("property_number") or fallback["property_number"],
        "contact_name": output.get("contact_name"),
        "reply_draft": output.get("reply_draft"),
    }
    # Vorgangsart (Regel M19-11): nur ein Code des festen Katalogs zählt; ein unbekannter oder
    # fehlender Code fällt auf die Schlüsselworterkennung zurück, samt Grund und Konfidenz.
    from mhvp.tickets.flows import PROCESS_CODES

    code = output.get("process_code")
    if code in PROCESS_CODES:
        confidence = output.get("process_confidence")
        merged["process_code"] = code
        merged["process_confidence"] = (
            float(confidence) if isinstance(confidence, int | float) else None
        )
        merged["process_reason"] = output.get("process_reason") or "KI-Vorschlag"
    else:
        merged["process_code"] = fallback.get("process_code")
        merged["process_confidence"] = fallback.get("process_confidence")
        merged["process_reason"] = fallback.get("process_reason")
    merged.update(merge_v3_fields(output, fallback, candidates=candidates, text=text))
    return merged


REPLY_TONES = ("formell", "sachlich", "freundlich")
REPLY_PLACEHOLDERS = ("{anrede}", "{ticket}", "{objekt}")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")
APPOINTMENT_KINDS = ("uebergabe", "besichtigung", "telefonat", "vor_ort", "sonstiges")


def merge_v3_fields(
    output: dict[str, Any],
    fallback: dict[str, Any],
    *,
    candidates: dict[str, set[str]] | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Fields of prompt v3 (M20-02, M20-03, S13-08), each checked deterministically; a value
    that fails its check is dropped, never repaired:

    * ``contact_id``/``property_id`` only when listed in ``candidates`` (the IDs given to the
      model); the suggestion never assigns, a person confirms.
    * ``appointment`` only with an ISO date whose German form (TT.MM.JJJJ) occurs in the text.
    * ``intent``/``invoice_number``: keyword rule first; the model's number only when it
      occurs verbatim in the text.
    * ``reply_tone`` from the fixed list, ``reply_placeholders`` only known placeholders."""
    cands = candidates or {}
    haystack = text or ""
    out: dict[str, Any] = {}
    for key, pool in (("contact_id", "contacts"), ("property_id", "properties")):
        value = output.get(key)
        out[key] = value if isinstance(value, str) and value in cands.get(pool, set()) else None
    appointment = output.get("appointment")
    out["appointment"] = None
    if isinstance(appointment, dict):
        day = str(appointment.get("date") or "")
        if _ISO_DATE_RE.match(day):
            y, m, d = day.split("-")
            german = {f"{d}.{m}.{y}", f"{int(d)}.{int(m)}.{y}"}
            if any(g in haystack for g in german):
                at = appointment.get("time")
                kind = appointment.get("kind")
                out["appointment"] = {
                    "date": day,
                    "time": at if isinstance(at, str) and _HHMM_RE.match(at) else None,
                    "kind": kind if kind in APPOINTMENT_KINDS else "sonstiges",
                    "source": "ki",
                }
    rule = mail.invoice_copy_request(None, haystack) or {}
    intent = rule.get("intent") or (
        output.get("intent") if output.get("intent") == "invoice_copy_requested" else None
    )
    number = rule.get("invoice_number")
    if number is None and intent:
        candidate = output.get("invoice_number")
        if isinstance(candidate, str) and candidate.strip() and candidate.strip() in haystack:
            number = candidate.strip()
    out["intent"], out["invoice_number"] = intent, number
    hint = output.get("attachment_hint")
    out["attachment_hint"] = str(hint)[:300] if isinstance(hint, str) and hint.strip() else None
    tone = output.get("reply_tone")
    out["reply_tone"] = tone if tone in REPLY_TONES else None
    placeholders = output.get("reply_placeholders") or []
    out["reply_placeholders"] = [
        p for p in placeholders if isinstance(p, str) and p in REPLY_PLACEHOLDERS
    ]
    return out


class MailDraftReply(BaseModel):
    """Own schema of the reply draft (M20-02, 9.2 draft_reply): text, tone, placeholders and the
    style of the mailbox it was written under. A proposal for the clerk, never sent on its own;
    ``unknown_placeholders`` lists braces in the text that no template fills."""

    model_config = ConfigDict(extra="forbid")

    body: str
    tone: str | None = None
    placeholders: list[str] = Field(default_factory=list)
    unknown_placeholders: list[str] = Field(default_factory=list)
    style_tone: str = "sachlich"
    style_rules: str | None = None


_BRACES_RE = re.compile(r"\{[^{}\s]{1,40}\}")


def draft_reply_payload(
    output: dict[str, Any], style: dict[str, Any] | None
) -> dict[str, Any] | None:
    """``MailDraftReply`` from a checked suggestion and the mailbox style; ``None`` without a
    draft text. Pure and deterministic."""
    body = output.get("reply_draft")
    if not isinstance(body, str) or not body.strip():
        return None
    style = style or {}
    rules = " ".join(str(style.get("rules") or "").split())[:2000] or None
    tone = style.get("tone") if style.get("tone") in REPLY_TONES else "sachlich"
    used = [p for p in REPLY_PLACEHOLDERS if p in body]
    unknown = sorted({m for m in _BRACES_RE.findall(body) if m not in REPLY_PLACEHOLDERS})
    return MailDraftReply(
        body=body,
        tone=output.get("reply_tone") if output.get("reply_tone") in REPLY_TONES else None,
        placeholders=used,
        unknown_placeholders=unknown,
        style_tone=str(tone),
        style_rules=rules,
    ).model_dump()


def reply_style_text(style: dict[str, Any] | None) -> str:
    """Prompt line from the mailbox style (M20-02); empty style gives the neutral default."""
    style = style or {}
    tone = style.get("tone") if style.get("tone") in REPLY_TONES else "sachlich"
    rules = " ".join(str(style.get("rules") or "").split())[:2000]
    return f"Stilvorgaben des Postfachs: Tonfall {tone}." + (f" Regeln: {rules}" if rules else "")


def reply_task_payload(
    output: dict[str, Any], style: dict[str, Any] | None, *, model: str | None
) -> dict[str, Any] | None:
    """Result of the own ``reply_draft`` task (T12) as stored under ``suggestion.reply_ai``:
    checked body, tone, used and unknown placeholders, mailbox style, open questions. Always
    ``approved: false``; the clerk approves it explicitly. ``None`` without a body."""
    body = output.get("body")
    if not isinstance(body, str) or not body.strip():
        return None
    base = draft_reply_payload(
        {"reply_draft": body.strip(), "reply_tone": output.get("tone")}, style
    )
    if base is None:  # pragma: no cover - body is non-empty
        return None
    questions = [str(q)[:300] for q in output.get("open_questions") or [] if str(q).strip()]
    return {
        **base,
        "open_questions": questions[:10],
        "model": model,
        "approved": False,
        "approved_at": None,
        "approved_by": None,
    }


async def reply_task_for_message(
    session: AsyncSession, settings: Settings, message: Message
) -> dict[str, Any]:
    """Own AI task ``reply_draft`` (T12, 9.2): tone, placeholders and style from the mailbox
    style as input, own provider schema. Goes through the gateway (release switches, DPA,
    provider approval, masking). Returns ``status`` ready, skipped or failed plus the payload;
    the caller stores it under ``suggestion.reply_ai``. Never sent and not usable before the
    explicit approval."""
    from mhvp.objektakte.masking import mask_ibans
    from mhvp.tickets.models import Ticket

    style = await _reply_style(session, message)
    ticket = await session.get(Ticket, message.ticket_id) if message.ticket_id else None
    prompt_text = (
        f"Betreff: {mask_ibans(message.subject)}\n"
        f"Text (Auszug):\n{mask_ibans((message.body or '')[:MAX_EXCERPT])}\n"
        f"Ticketnummer vorhanden: {'ja' if ticket is not None else 'nein'}\n"
        f"{reply_style_text(style)}"
    )
    context = {"context_type": "message", "context_id": str(message.id)}
    try:
        run = await _run_gateway_task(
            settings, message.tenant_id, AiTask.REPLY_DRAFT, prompt_text, context
        )
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)[:500]}
    if run.status is RunStatus.SUCCEEDED and run.output:
        payload = reply_task_payload(run.output, style, model=run.model)
        if payload is not None:
            return {"status": "ready", **payload}
        return {"status": "failed", "reason": "Der Antwortentwurf ist leer."}
    if run.status is RunStatus.BLOCKED:
        return {"status": "skipped", "reason": run.error or "Kein freigegebener KI-Anbieter."}
    return {"status": "failed", "reason": run.error or "KI-Lauf fehlgeschlagen."}


def playbook_fields(output: dict[str, Any], ticket_title: str) -> dict[str, Any]:
    """Playbook draft fields from a ``PlaybookDraft`` answer: title cut to 200 characters (the
    ticket title when empty), at most ten keywords of 64 characters, steps as text, template
    as answered. Pure, shared with the offline evaluation."""
    return {
        "title": str(output.get("title") or ticket_title)[:200],
        "category": output.get("category"),
        "keywords": [str(k)[:64] for k in output.get("keywords", [])][:10],
        "summary": str(output.get("summary") or ""),
        "steps": [str(s) for s in output.get("steps", [])],
        "reply_template": output.get("reply_template"),
    }


RESOLUTION_HISTORY = 200
RESOLUTION_HINTS = 3
MAX_STEPS = 20


def resolution_features(ticket: Any) -> dict[str, Any]:
    """Eingabe eines Lernbeispiels aus einer Erledigung: Betreff, Anliegen (Auszug),
    Kategorie, Thema und die erkannten Entitäten (Objekt, Einheit, Kontakt)."""
    return {
        "betreff": str(ticket.title or "")[:300],
        "anliegen": str(ticket.public_description or "")[:1000],
        "kategorie": ticket.category,
        "thema": ticket.topic,
        "entitaeten": {
            key: str(value)
            for key in ("property_id", "unit_id", "contact_id")
            if (value := getattr(ticket, key, None)) is not None
        },
    }


def resolution_step(kind: str | None, note: str | None) -> str | None:
    """Schritt "was wurde gemacht" für ein gelerntes Playbook."""
    from mhvp.tickets.status import resolution_text

    text = resolution_text(kind, note)
    return f"Erledigung: {text}" if text else None


def with_resolution_step(steps: list[str], kind: str | None, note: str | None) -> list[str]:
    step = resolution_step(kind, note)
    if step is None or step in steps or len(steps) >= MAX_STEPS:
        return list(steps)
    return [*steps, step]


def resolution_hint(text: str, examples: list[dict[str, Any]]) -> str | None:
    """Vorschlagstext aus der Erledigungshistorie ähnlicher Tickets: Schlagwortüberlappung
    zwischen ``text`` und Betreff plus Anliegen je Beispiel (``features``/``result`` eines
    ``AiExample``), die besten drei unterschiedlichen Erledigungen. Rein, ohne Datenbank."""
    from mhvp.tickets.status import resolution_text

    words = {w.lower() for w in WORD_RE.findall(text)}
    if not words:
        return None
    scored: list[tuple[float, str]] = []
    for example in examples:
        features = example.get("features") or {}
        result = example.get("result") or {}
        source = f"{features.get('betreff', '')} {features.get('anliegen', '')}"
        keys = {w.lower() for w in WORD_RE.findall(source)}
        if not keys:
            continue
        score = len(words & keys) / len(keys)
        entry = resolution_text(result.get("kind"), result.get("note"))
        if score >= MIN_PLAYBOOK_SCORE and entry:
            scored.append((score, entry))
    seen: list[str] = []
    for _, entry in sorted(scored, key=lambda item: -item[0]):
        if entry not in seen:
            seen.append(entry)
        if len(seen) == RESOLUTION_HINTS:
            break
    if not seen:
        return None
    return "Bei ähnlichen Vorgängen wurde: " + "; ".join(seen)


async def resolution_examples(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(AiExample)
            .where(AiExample.task == AiTask.TICKET_RESOLUTION)
            .order_by(AiExample.created_at.desc())
            .limit(RESOLUTION_HISTORY)
        )
    ).all()
    return [{"features": r.features, "result": r.result} for r in rows]


async def resolution_example(session: AsyncSession, ticket: Any) -> AiExample:
    """Lernbeispiel je Abschluss: Ausgabe ist Erledigungsart, Notiz, Status und die zuletzt
    versendete Antwort (Auszug), sofern vorhanden."""
    reply = await session.scalar(
        select(Message.body)
        .where(
            Message.ticket_id == ticket.id,
            Message.direction == "out",
            Message.status == "sent",
        )
        .order_by(Message.sent_at.desc())
        .limit(1)
    )
    status = getattr(ticket.status, "value", ticket.status)
    return AiExample(
        tenant_id=ticket.tenant_id,
        created_by=ticket.resolved_by,
        task=AiTask.TICKET_RESOLUTION,
        features={**resolution_features(ticket), "ticket_id": str(ticket.id)},
        result={
            "kind": ticket.resolution_kind,
            "note": ticket.resolution_note,
            "status": status,
            "antwort": (reply or "")[:2000] or None,
        },
    )


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


async def _candidates(session: AsyncSession, message: Message) -> tuple[dict[str, set[str]], str]:
    """IDs the model may choose from (M20-03): the deterministic assignment of the mail and the
    property named by number in the text. No personal data of the contact."""
    from mhvp.contacts.models import Contact
    from mhvp.properties.models import Property

    contacts: dict[str, str] = {}
    properties: dict[str, str] = {}
    if message.contact_id:
        contact = await session.get(Contact, message.contact_id)
        if contact is not None:
            # Data minimisation: the model sees the ID and the role, never the name.
            contacts[str(contact.id)] = "zugeordneter Absender"
    if message.property_id:
        prop = await session.get(Property, message.property_id)
        if prop is not None:
            properties[str(prop.id)] = f"{prop.number} {prop.name}"
    number = mail.property_number(message.subject, message.body)
    if number:
        prop = await session.scalar(select(Property).where(Property.number == number))
        if prop is not None:
            properties[str(prop.id)] = f"{prop.number} {prop.name}"
    lines = "Kandidaten Kontakt (ID: Rolle): " + (
        "; ".join(f"{k}: {v}" for k, v in contacts.items()) or "-"
    )
    lines += "\nKandidaten Objekt (ID: Nummer Name): " + (
        "; ".join(f"{k}: {v}" for k, v in properties.items()) or "-"
    )
    return {"contacts": set(contacts), "properties": set(properties)}, lines


async def _attachment_line(session: AsyncSession, message: Message) -> str:
    """File name and type of the attachments (M20-03); the content is not sent."""
    from mhvp.documents.models import Document

    ids = list(message.attachment_document_ids or [])[:10]
    if not ids:
        return "Anhänge: -"
    rows = (await session.scalars(select(Document).where(Document.id.in_(ids)))).all()
    from mhvp.objektakte.masking import mask_ibans

    return "Anhänge: " + (
        "; ".join(f"{mask_ibans(d.filename or d.title)} ({d.mime_type})" for d in rows) or "-"
    )


async def _reply_style(session: AsyncSession, message: Message) -> dict[str, Any]:
    """Style of the message's mailbox, otherwise of the tenant's default mailbox (M20-02)."""
    from mhvp.communication.models import Mailbox

    box = await session.get(Mailbox, message.mailbox_id) if message.mailbox_id else None
    if box is not None and box.reply_style:
        return dict(box.reply_style)
    default = await session.scalar(
        select(Mailbox).where(Mailbox.is_default.is_(True), Mailbox.deleted_at.is_(None)).limit(1)
    )
    return dict(default.reply_style) if default is not None and default.reply_style else {}


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
    # One load of the playbooks for the prompt and the match; the deterministic category of
    # the mail (mhvp.communication.mail) steers the match before any model answer exists.
    playbook, playbook_score = await best_playbook(
        session,
        match_text,
        category=mail.category(message.subject, message.body, categories),
        playbooks=playbooks,
    )
    hint = resolution_hint(match_text, await resolution_examples(session))

    # An IBAN never reaches the provider (rule 0.1.13); the classification does not need it.
    from mhvp.objektakte.masking import mask_ibans

    candidates, candidate_lines = await _candidates(session, message)
    attachment_line = await _attachment_line(session, message)
    style = await _reply_style(session, message)

    prompt_text = (
        f"Betreff: {mask_ibans(message.subject)}\n"
        f"Absender: {message.from_address or ''}\n"
        f"Text (Auszug):\n{mask_ibans(body_excerpt)}\n\n"
        f"Bekannte Ticketkategorien: {', '.join(categories) or '-'}\n"
        "Vorgangsarten (process_code): "
        + ", ".join(f"{p['code']} ({p['label']})" for p in PROCESS_CATALOGUE)
        + "\n"
        "Bekannte Playbooks (Titel, Schlagwörter): "
        + ("; ".join(f"{p.title} ({', '.join(p.keywords)})" for p in playbooks) or "-")
        + "\nObjektnummern stehen meist als dreistellige Zahl nach 'Objekt' oder 'Objekt Nr.'."
        + (f"\n{hint}" if hint else "")
        + "\n"
        + candidate_lines
        + "\n"
        + attachment_line
        + "\n"
        + reply_style_text(style)
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
        result = merge_suggestion(
            run.output,
            _fallback(message, categories),
            candidates=candidates,
            text=f"{message.subject or ''}\n{message.body or ''}",
        )
        result["model"] = run.model
        result["draft_reply"] = draft_reply_payload(result, style)
        status = "ready"
    elif run.status is RunStatus.BLOCKED:
        result = {"reason": run.error or "Kein freigegebener KI-Anbieter."}
        status = "skipped"
    else:
        result = {"reason": run.error or "KI-Lauf fehlgeschlagen."}
        status = "failed"

    if hint:
        result["resolution_hint"] = hint
    if playbook is not None:
        result["playbook_id"] = str(playbook.id)
        result["playbook_score"] = playbook_score
    return {"status": status, **result}


async def learn_playbook_from_ticket(
    session: AsyncSession, settings: Settings, ticket: Any
) -> Playbook | None:
    """Erzeugt aus einem geschlossenen Ticket einen Playbook-Entwurf (Status draft), sofern
    noch kein ähnlich betiteltes Playbook existiert und ein KI-Anbieter freigegeben ist. Die
    Erledigungsnotiz (``resolution_kind``, ``resolution_note``) geht in den Prompt und als
    Schritt "Erledigung: ..." in die Schritte ein; ein bestehendes ähnliches Playbook erhält
    den Schritt ergänzt, ohne neuen KI-Lauf."""
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
    step = resolution_step(ticket.resolution_kind, ticket.resolution_note)
    if not comments and not sent_replies and step is None:
        return None

    existing = await session.scalar(
        select(Playbook).where(Playbook.title.ilike(f"%{ticket.title[:60]}%"))
    )
    if existing is not None:
        steps = with_resolution_step(
            list(existing.steps or []), ticket.resolution_kind, ticket.resolution_note
        )
        if steps != list(existing.steps or []):
            existing.steps = steps
            await session.flush()
        return None

    body = [f"Titel: {ticket.title}", f"Kategorie: {ticket.category or '-'}"]
    if step is not None:
        body.append(f"Was wurde gemacht ({step})")
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

    fields = playbook_fields(run.output, ticket.title)
    fields["steps"] = with_resolution_step(
        fields["steps"], ticket.resolution_kind, ticket.resolution_note
    )
    duplicate = await session.scalar(select(Playbook).where(Playbook.title == fields["title"]))
    if duplicate is not None:
        return None
    draft = Playbook(
        tenant_id=ticket.tenant_id,
        **fields,
        source_ticket_id=ticket.id,
        status="draft",
    )
    session.add(draft)
    await session.flush()
    return draft
