"""AI endpoints (/api/v1/ai, /imports): provider setup, chat, runs, proposals, import runs."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai import connection_test, gateway, imports, jobs, tasks
from mhvp.ai import schemas as s
from mhvp.ai.models import (
    AiConversation,
    AiKnowledgeEntry,
    AiKnowledgeKind,
    AiMessage,
    AiProposal,
    AiProvider,
    AiProviderConfig,
    AiTask,
    AiTaskRun,
    Decision,
    ImportRun,
    ImportRunItem,
    ImportStatus,
    RunStatus,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document

router = APIRouter(tags=["KI-Assistent"])
READ = require_permission("ai:read")
CREATE = require_permission("ai:create")
UNDO = require_permission("ai:delete")
APPROVE = require_permission("ai:approve")
SETTINGS = require_permission("tenant_settings:update")
AUDIT_PERMISSION = "audit:read"  # sees the chats of all users of the tenant (audit trail)


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, entity_id: uuid.UUID, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type=type_.split(".")[0],
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={k: str(v) if v is not None else None for k, v in payload.items()},
    )


def _provider_out(row: AiProviderConfig) -> s.ProviderOut:
    data = {c.key: getattr(row, c.key) for c in AiProviderConfig.__table__.columns}
    return s.ProviderOut.model_validate({**data, "has_api_key": bool(row.api_key)})


# Provider configuration ------------------------------------------------------------------


@router.get("/ai/providers", summary="KI-Anbieter")
async def list_providers(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> list[s.ProviderOut]:
    async with tenant_tx(request, principal) as session:
        return [_provider_out(r) for r in (await session.scalars(select(AiProviderConfig))).all()]


@router.put("/ai/providers/{provider}", summary="KI-Anbieter einrichten")
async def put_provider(
    provider: AiProvider,
    body: s.ProviderIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.ProviderOut:
    """Every change withdraws the release: the second person must confirm again."""
    async with tenant_tx(request, principal) as session:
        if body.dpa_document_id is not None:
            await _get(session, Document, body.dpa_document_id)
        row = await session.scalar(
            select(AiProviderConfig).where(AiProviderConfig.provider == provider).with_for_update()
        )
        if row is None:
            row = AiProviderConfig(tenant_id=principal.tenant_id, provider=provider)
            session.add(row)
        data = body.model_dump(mode="json", exclude={"api_key"})
        data["monthly_budget_eur"] = body.monthly_budget_eur
        data["dpa_document_id"] = body.dpa_document_id
        for key, value in data.items():
            setattr(row, key, value)
        if body.api_key is not None:
            row.api_key = body.api_key
        row.updated_by = principal.user_id
        row.released_at = row.released_by = None
        await session.flush()
        await _event(
            session,
            principal,
            "ai_provider.updated",
            row.id,
            provider=provider.value,
            enabled=row.enabled,
        )
        await session.refresh(row)
        return _provider_out(row)


@router.post("/ai/providers/{provider}/release", summary="KI-Anbieter freigeben (Vier-Augen)")
async def release_provider(
    provider: AiProvider, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> s.ProviderOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(AiProviderConfig).where(AiProviderConfig.provider == provider).with_for_update()
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if principal.user_id is None or row.updated_by == principal.user_id:
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        missing = [
            label
            for label, ok in (
                ("Auftragsverarbeitungsvertrag", row.data_processing_agreement_signed),
                ("AVV-Dokument", row.dpa_document_id is not None),
                ("Bestätigung Trainings-Opt-out", row.training_opt_out_confirmed),
                ("API-Schlüssel", bool(row.api_key)),
                ("Monatsbudget", row.monthly_budget_eur > 0),
            )
            if not ok
        ]
        if missing:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Freigabe nicht möglich, es fehlt: {', '.join(missing)}.",
            )
        row.released_at, row.released_by = datetime.now(UTC), principal.user_id
        await _event(session, principal, "ai_provider.released", row.id, provider=provider.value)
        await session.flush()
        await session.refresh(row)
        return _provider_out(row)


@router.post("/ai/providers/{provider}/test", summary="KI-Anbieter: Verbindung testen")
async def provider_connection_test(
    provider: AiProvider, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.ProviderTestOut:
    """One minimal prompt per configured tier (small, large) with the stored key. Works without
    a release, changes no release state and records each call as a run so the budget is
    charged; the provider's own error text is returned per tier."""
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(AiProviderConfig).where(AiProviderConfig.provider == provider)
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if not row.api_key:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Kein API-Schlüssel hinterlegt, Test nicht möglich."
            )
        if not connection_test.configured_tiers(row.models or {}):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Keine Stufe mit Modellname eingerichtet, Test nicht möglich.",
            )
        api_key, models = row.api_key, dict(row.models or {})
        config_id = row.id
    # The provider calls run outside the transaction, like every gateway run.
    results = await connection_test.check_provider(provider, api_key, models)
    async with tenant_tx(request, principal) as session:
        for result in results:
            run = AiTaskRun(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                task=connection_test.TEST_TASK,
                provider=provider,
                model=result.model,
                prompt_version=tasks.prompt(connection_test.TEST_TASK).version,
                input_hash=gateway.input_hash(
                    connection_test.TEST_TASK,
                    "connection-test",
                    connection_test.TEST_INSTRUCTION,
                    {"tier": result.tier, "at": datetime.now(UTC).isoformat()},
                ),
                input_ref={"connection_test": True, "tier": result.tier, "instruction": ""},
                status=RunStatus.SUCCEEDED if result.ok else RunStatus.FAILED,
                error=result.error,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_eur=result.cost_eur,
                duration_ms=result.duration_ms,
            )
            session.add(run)
        await _event(
            session,
            principal,
            "ai_provider.tested",
            config_id,
            provider=provider.value,
            ok=all(r.ok for r in results),
        )
    return s.ProviderTestOut(
        provider=provider,
        tiers=[
            s.TierTestOut(
                tier=r.tier,
                model=r.model,
                ok=r.ok,
                duration_ms=r.duration_ms,
                error=r.error,
                tokens_in=r.tokens_in,
                tokens_out=r.tokens_out,
                cost_eur=r.cost_eur,
            )
            for r in results
        ],
    )


@router.get("/ai/routing", summary="Anbieterstrategie")
async def get_routing(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.RoutingOut:
    async with tenant_tx(request, principal) as session:
        return s.RoutingOut(strategy=await gateway.routing_strategy(session))


@router.put("/ai/routing", summary="Anbieterstrategie setzen")
async def put_routing(
    body: s.RoutingIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.RoutingOut:
    """Which released provider answers first and whether the other one takes over when the
    budget is exhausted or the provider fails (M7-02). "_only" strategies never switch."""
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.ai_routing = body.strategy
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ai_routing.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"strategy": body.strategy},
        )
        return s.RoutingOut(strategy=body.strategy)


@router.get("/ai/fast-table-import", summary="Schneller Tabellenimport (Einstellung)")
async def get_fast_table_import(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.FastTableImportOut:
    async with tenant_tx(request, principal) as session:
        return s.FastTableImportOut(enabled=await gateway.fast_table_import_enabled(session))


@router.put("/ai/fast-table-import", summary="Schnellen Tabellenimport setzen")
async def put_fast_table_import(
    body: s.FastTableImportIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.FastTableImportOut:
    """Deterministic CSV/XLSX contact import (M7-06, docs/rules/M7-06.md): on by default. Off
    falls every ``extract_contacts`` run back to sending every row through the LLM."""
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.ai_fast_table_import = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ai_fast_table_import.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return s.FastTableImportOut(enabled=body.enabled)


@router.get("/ai/invoice-intake-auto", summary="Automatischer Belegeingang (Einstellung)")
async def get_invoice_intake_auto(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.InvoiceIntakeAutoOut:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        value = await session.scalar(select(TenantSettings.invoice_intake_auto))
        return s.InvoiceIntakeAutoOut(enabled=bool(value))


@router.put("/ai/invoice-intake-auto", summary="Automatischen Belegeingang setzen")
async def put_invoice_intake_auto(
    body: s.InvoiceIntakeAutoIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.InvoiceIntakeAutoOut:
    """M14-05: when on, the Gmail sync starts one ``extract_invoice`` run per new PDF attachment
    that looks like an invoice (heuristic in ``mhvp.communication.invoice_intake``). Default off;
    every run is a proposal only and costs AI budget."""
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.invoice_intake_auto = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice_intake_auto.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return s.InvoiceIntakeAutoOut(enabled=body.enabled)


@router.get("/ai/posting-enabled", summary="KI-Kontierung (Einstellung)")
async def get_posting_enabled(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.PostingEnabledOut:
    """M7-09, M12-01: tenant switch plus the reason why ``propose_posting`` would be blocked
    (switch off, no released provider with DPA evidence)."""
    async with tenant_tx(request, principal) as session:
        return s.PostingEnabledOut(
            enabled=await gateway.posting_enabled(session),
            blocked_reason=await gateway.posting_block_reason(session),
        )


@router.put("/ai/posting-enabled", summary="KI-Kontierung ein- oder ausschalten")
async def put_posting_enabled(
    body: s.PostingEnabledIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.PostingEnabledOut:
    """Default off. Even when on, a run needs a released provider with DPA evidence; the
    result is a proposal of entity type ``posting`` and is never posted (rule 0.1.6)."""
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.ai_posting_enabled = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ai_posting_enabled.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        await session.flush()
        return s.PostingEnabledOut(
            enabled=body.enabled, blocked_reason=await gateway.posting_block_reason(session)
        )


@router.get("/ai/usage", summary="KI-Kosten im laufenden Monat")
async def usage(request: Request, principal: TenantPrincipal = Depends(READ)) -> s.UsageOut:
    now = datetime.now(UTC)
    async with tenant_tx(request, principal) as session:
        spent = await gateway.spent_this_month(session, now)
        budget = await session.scalar(
            select(func.coalesce(func.sum(AiProviderConfig.monthly_budget_eur), 0)).where(
                AiProviderConfig.enabled.is_(True)
            )
        ) or Decimal(0)
        rows = (
            await session.execute(
                select(AiTaskRun.task, func.sum(AiTaskRun.cost_eur))
                .where(AiTaskRun.created_at >= gateway.month_start(now))
                .group_by(AiTaskRun.task)
            )
        ).all()
        return s.UsageOut(
            month=now.strftime("%Y-%m"),
            spent_eur=spent.quantize(Decimal("0.01")),
            budget_eur=Decimal(budget),
            warning=budget > 0 and spent >= Decimal(budget) * gateway.WARN_SHARE,
            blocked=budget <= 0 or spent >= Decimal(budget),
            by_task={t.value: Decimal(v or 0).quantize(Decimal("0.0001")) for t, v in rows},
        )


# Conversations and runs ------------------------------------------------------------------


async def _user_names(session: Any, user_ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    from mhvp.platform.models import User

    ids = [u for u in user_ids if u is not None]
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {row[0]: row[1] for row in rows}


async def _conversation_out(session: Any, row: AiConversation) -> s.ConversationOut:
    messages = (
        await session.scalars(
            select(AiMessage)
            .where(AiMessage.conversation_id == row.id)
            .order_by(AiMessage.created_at)
        )
    ).all()
    out = s.ConversationOut.model_validate(row)
    names = await _user_names(session, {row.created_by})
    out.created_by_name = names.get(row.created_by) if row.created_by else None
    out.messages = [s.MessageOut.model_validate(m) for m in messages]
    out.message_count = len(messages)
    out.last_message_at = messages[-1].created_at if messages else None
    return out


@router.post("/ai/conversations", status_code=201, summary="Chat beginnen")
async def create_conversation(
    body: s.ConversationIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.ConversationOut:
    async with tenant_tx(request, principal) as session:
        row = AiConversation(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return await _conversation_out(session, row)


def _can_audit(principal: TenantPrincipal) -> bool:
    return AUDIT_PERMISSION in principal.permissions


@router.get("/ai/conversations", summary="Chats")
async def list_conversations(
    request: Request,
    context_type: str | None = None,
    context_id: uuid.UUID | None = None,
    scope: Literal["own", "all"] = Query(
        default="own",
        description="own: eigene Chats; all: Chats aller Benutzer des Mandanten (audit:read)",
    ),
    user_id: uuid.UUID | None = Query(default=None, description="Nur mit scope=all"),
    date_from: date | None = Query(default=None, description="Erstellt ab (einschließlich)"),
    date_to: date | None = Query(default=None, description="Erstellt bis (einschließlich)"),
    q: str | None = Query(default=None, max_length=200, description="Suche in Titel und Text"),
    limit: int = Query(default=50, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.ConversationOut]:
    """Chronological overview, newest first. ``scope=all`` is the audit view: it lists the chats
    of every user of the tenant without their messages; each chat is read via its own URL."""
    if scope == "all" and not _can_audit(principal):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="audit:read required")
    async with tenant_tx(request, principal) as session:
        query = select(AiConversation)
        if scope == "own":
            query = query.where(AiConversation.created_by == principal.user_id)
        elif user_id is not None:
            query = query.where(AiConversation.created_by == user_id)
        if context_type:
            query = query.where(AiConversation.context_type == context_type)
        if context_id:
            query = query.where(AiConversation.context_id == context_id)
        if date_from:
            query = query.where(func.date(AiConversation.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(AiConversation.created_at) <= date_to)
        if q:
            needle = f"%{q.strip()}%"
            in_text = select(AiMessage.conversation_id).where(AiMessage.content.ilike(needle))
            query = query.where(AiConversation.title.ilike(needle) | AiConversation.id.in_(in_text))
        rows = (
            await session.scalars(query.order_by(AiConversation.created_at.desc()).limit(limit))
        ).all()
        names = await _user_names(session, {r.created_by for r in rows})
        stats = {
            conv_id: (count, last)
            for conv_id, count, last in await session.execute(
                select(
                    AiMessage.conversation_id,
                    func.count(AiMessage.id),
                    func.max(AiMessage.created_at),
                )
                .where(AiMessage.conversation_id.in_([r.id for r in rows]))
                .group_by(AiMessage.conversation_id)
            )
        }
        out = []
        for r in rows:
            item = s.ConversationOut.model_validate(r)
            item.created_by_name = names.get(r.created_by) if r.created_by else None
            item.message_count, item.last_message_at = stats.get(r.id, (0, None))
            out.append(item)
        return out


async def _own_conversation(
    session: Any, principal: TenantPrincipal, conversation_id: uuid.UUID, *, audit: bool = False
) -> AiConversation:
    """Chats are personal. ``audit=True`` lets audit:read holders read (never write) any chat."""
    row: AiConversation = await _get(session, AiConversation, conversation_id)
    if row.created_by != principal.user_id and not (audit and _can_audit(principal)):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get("/ai/conversations/{conversation_id}", summary="Chat lesen")
async def get_conversation(
    conversation_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ConversationOut:
    async with tenant_tx(request, principal) as session:
        return await _conversation_out(
            session, await _own_conversation(session, principal, conversation_id, audit=True)
        )


async def create_extraction_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    task: AiTask,
    document_ids: list[uuid.UUID],
    content: str,
    context_type: str,
    context_id: uuid.UUID | None,
    trigger: str | None = None,
) -> uuid.UUID:
    """Creates conversation, queued run and user message of an extraction start inside the
    caller's tenant transaction and returns the run id. Shared by the intake actions and the
    automatic invoice intake (M14-05); execution goes through the unchanged gateway."""
    prompt = tasks.prompt(task)
    conversation = AiConversation(
        tenant_id=tenant_id,
        created_by=user_id,
        context_type=context_type,
        context_id=context_id,
        title=content[:200],
    )
    session.add(conversation)
    await session.flush()
    context = {
        "context_type": context_type,
        "context_id": str(context_id) if context_id else None,
    }
    ref: dict[str, Any] = {
        "instruction": content,
        "document_ids": [str(d) for d in document_ids],
        "context": context,
    }
    if trigger:
        ref["trigger"] = trigger
    run = AiTaskRun(
        tenant_id=tenant_id,
        created_by=user_id,
        task=task,
        conversation_id=conversation.id,
        prompt_version=prompt.version,
        input_hash=gateway.input_hash(
            task, prompt.version, content, {**context, "docs": ref["document_ids"]}
        ),
        input_ref=ref,
        status=RunStatus.QUEUED,
    )
    session.add(run)
    await session.flush()
    session.add(
        AiMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=content,
            document_ids=document_ids,
            task_run_id=run.id,
        )
    )
    await session.flush()
    return run.id


async def start_extraction_run(
    request: Request,
    principal: TenantPrincipal,
    task: AiTask,
    document_ids: list[uuid.UUID],
    content: str,
    context_type: str,
    context_id: uuid.UUID | None,
) -> s.RunOut:
    """Starts an extraction run in a fresh conversation of the acting user (intake actions: mail
    attachment, Paperless pull). Same path as a chat message (gateway tier escalation, budget and
    release checks unchanged); the caller enforces its own permission before calling this."""
    async with tenant_tx(request, principal) as session:
        for document_id in document_ids:
            await _get(session, Document, document_id)
        run_id = await create_extraction_run(
            session,
            principal.tenant_id,
            principal.user_id,
            task,
            document_ids,
            content,
            context_type,
            context_id,
        )
    settings = request.app.state.settings
    if settings.ai_inline:
        await jobs.run_and_propose(
            sessions(request), principal.tenant_id, run_id, BlobStore(settings), principal.user_id
        )
    else:
        from mhvp.worker import get_celery

        get_celery().send_task(
            "mhvp.ai.run",
            args=[
                str(principal.tenant_id),
                str(run_id),
                str(principal.user_id) if principal.user_id else None,
            ],
            queue="io",
        )
    return await get_run(run_id, request, principal)


@router.post(
    "/ai/conversations/{conversation_id}/messages", status_code=202, summary="Nachricht senden"
)
async def send_message(
    conversation_id: uuid.UUID,
    body: s.MessageIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.RunOut:
    """Queues the task; the answer arrives as a new chat message when the run is done."""
    task = AiTask(body.task)
    if task is AiTask.ANSWER_QUESTION and "documents:read" not in principal.permissions:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="documents:read required for RAG"
        )
    prompt = tasks.prompt(task)
    async with tenant_tx(request, principal) as session:
        conversation = await _own_conversation(session, principal, conversation_id)
        for document_id in body.document_ids:
            await _get(session, Document, document_id)
        context = {
            "context_type": conversation.context_type,
            "context_id": str(conversation.context_id) if conversation.context_id else None,
        }
        ref = {
            "instruction": body.content,
            "document_ids": [str(d) for d in body.document_ids],
            "context": context,
        }
        run = AiTaskRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            task=task,
            conversation_id=conversation.id,
            prompt_version=prompt.version,
            input_hash=gateway.input_hash(
                task, prompt.version, body.content, {**context, "docs": ref["document_ids"]}
            ),
            input_ref=ref,
            status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.flush()
        session.add(
            AiMessage(
                tenant_id=principal.tenant_id,
                conversation_id=conversation.id,
                role="user",
                content=body.content,
                document_ids=body.document_ids,
                task_run_id=run.id,
            )
        )
        run_id = run.id
    settings = request.app.state.settings
    if settings.ai_inline:
        await jobs.run_and_propose(
            sessions(request), principal.tenant_id, run_id, BlobStore(settings), principal.user_id
        )
    else:
        from mhvp.worker import get_celery

        get_celery().send_task(
            "mhvp.ai.run",
            args=[
                str(principal.tenant_id),
                str(run_id),
                str(principal.user_id) if principal.user_id else None,
            ],
            queue="io",
        )
    return await get_run(run_id, request, principal)


@router.get("/ai/runs/{run_id}", summary="KI-Lauf lesen")
async def get_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.RunOut:
    async with tenant_tx(request, principal) as session:
        run = await _get(session, AiTaskRun, run_id)
        out = s.RunOut.model_validate(run)
        ref = run.input_ref or {}
        out.fallback = list(ref.get("fallback") or [])
        out.input_stats = dict(ref.get("input_stats") or {})
        out.progress = ref.get("progress")
        out.model_tier_reason = ref.get("model_tier_reason")
        out.warnings = list(ref.get("warnings") or [])
        out.proposal_id = await session.scalar(
            select(AiProposal.id).where(AiProposal.task_run_id == run.id)
        )
        return out


# Proposals and import runs ----------------------------------------------------------------


def _masked_proposal(proposal: AiProposal) -> s.ProposalOut:
    out = s.ProposalOut.model_validate(proposal)
    if out.entity_type == "invoice":
        proposed = dict(out.proposed)
        invoice = dict(proposed.get("invoice") or {})
        iban = invoice.get("iban")
        if iban:
            invoice["iban"] = f"...{iban[-4:]}" if len(iban) > 4 else "..."
        proposed["invoice"] = invoice
        out.proposed = proposed
    return out


@router.get("/ai/proposals/{proposal_id}", summary="Vorschlag lesen")
async def get_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ProposalOut:
    async with tenant_tx(request, principal) as session:
        return _masked_proposal(await _get(session, AiProposal, proposal_id))


async def _pending(session: Any, proposal_id: uuid.UUID) -> AiProposal:
    proposal: AiProposal = await _get(session, AiProposal, proposal_id)
    if proposal.decision is not Decision.PENDING:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Über den Vorschlag wurde bereits entschieden."
        )
    return proposal


@router.post("/ai/proposals/{proposal_id}/reject", summary="Vorschlag verwerfen")
async def reject_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.ProposalOut:
    async with tenant_tx(request, principal) as session:
        proposal = await _pending(session, proposal_id)
        proposal.decision, proposal.decided_by = Decision.REJECTED, principal.user_id
        proposal.decided_at = datetime.now(UTC)
        await _event(session, principal, "ai_proposal.rejected", proposal.id)
        return s.ProposalOut.model_validate(proposal)


@router.post("/ai/proposals/{proposal_id}/apply", status_code=201, summary="Vorschlag übernehmen")
async def apply_proposal(
    proposal_id: uuid.UUID,
    body: s.ApplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ImportOut:
    """Creates everything in one transaction; nothing is created before this confirmation."""
    required = {
        "contacts": {"contacts:create"},
        "property": {"properties:create", "contracts:create", "contacts:create"},
        "invoice": {"accounting:create"},
    }
    async with tenant_tx(request, principal) as session:
        proposal = await _pending(session, proposal_id)
        missing = required[proposal.entity_type] - set(principal.permissions)
        if missing:
            raise ProblemError(ErrorCodes.FORBIDDEN, developer_message=f"missing {sorted(missing)}")
        run_row = await _get(session, AiTaskRun, proposal.task_run_id)
        import_run = ImportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            source=f"ai:{run_row.task.value}",
            status=ImportStatus.APPLIED,
            document_ids=[uuid.UUID(d) for d in run_row.input_ref.get("document_ids", [])],
        )
        session.add(import_run)
        await session.flush()
        if proposal.entity_type == "contacts":
            if body.contacts is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Auswahl der Kontakte fehlt.")
            summary = await imports.apply_contacts(
                session, import_run, principal, proposal.proposed, body.contacts
            )
            modified = any(c.contact is not None or c.action != "create" for c in body.contacts)
        elif proposal.entity_type == "property":
            if body.property is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Angaben zum Objekt fehlen.")
            summary = await imports.apply_property(
                session, import_run, principal, proposal.proposed, body.property
            )
            modified = True
        else:
            if body.invoice is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Angaben zur Rechnung fehlen.")
            summary = await imports.apply_invoice(session, import_run, principal, body.invoice)
            modified = True
        import_run.summary = summary
        proposal.decision = Decision.MODIFIED if modified else Decision.ACCEPTED
        proposal.decided_by, proposal.decided_at = principal.user_id, datetime.now(UTC)
        proposal.final = body.model_dump(mode="json")
        proposal.import_run_id = import_run.id
        await _event(
            session, principal, "import_run.applied", import_run.id, source=import_run.source
        )
        return await _import_out(session, import_run)


async def _import_out(session: Any, row: ImportRun) -> s.ImportOut:
    await session.flush()
    items = (
        await session.scalars(
            select(ImportRunItem)
            .where(ImportRunItem.import_run_id == row.id)
            .order_by(ImportRunItem.sequence)
        )
    ).all()
    out = s.ImportOut.model_validate(row)
    out.items = [s.ImportItemOut.model_validate(i) for i in items]
    return out


@router.get("/imports", summary="Importläufe")
async def list_imports(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ImportOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(ImportRun).order_by(ImportRun.created_at.desc()).limit(100)
            )
        ).all()
        return [s.ImportOut.model_validate(r) for r in rows]


@router.get("/imports/{import_id}", summary="Importlauf lesen")
async def get_import(
    import_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ImportOut:
    async with tenant_tx(request, principal) as session:
        return await _import_out(session, await _get(session, ImportRun, import_id))


@router.post("/imports/{import_id}/undo", summary="Import zurücknehmen")
async def undo_import(
    import_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UNDO)
) -> s.ImportOut:
    """Removes what is not bound by later data; kept items carry the reason (10.1 step 5)."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, ImportRun, import_id)
        await imports.undo(session, row, principal.user_id)
        out = await _import_out(session, row)
        kept = [i for i in out.items if not i.undone and i.kept_reason]
        # D46: a partial undo is logged with every kept entity and its reason.
        await _event(
            session,
            principal,
            "import_run.undone",
            row.id,
            status=row.status.value,
            kept=len(kept),
            kept_reasons="; ".join(f"{i.entity_type}: {i.kept_reason}" for i in kept) or None,
        )
        return out


@router.post(
    "/ai/import-runs/{import_id}/apply-role", summary="Importlauf: Rolle nachträglich setzen"
)
async def apply_import_role(
    import_id: uuid.UUID,
    body: s.ApplyRoleIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ApplyRoleOut:
    """Adds the role to every contact the import run created; existing roles are kept."""
    if "contacts:update" not in principal.permissions:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="contacts:update required")
    async with tenant_tx(request, principal) as session:
        row = await _get(session, ImportRun, import_id)
        changed = await imports.apply_role(session, row, body.role.value)
        row.summary = {**(row.summary or {}), "role_applied": body.role.value}
        await _event(
            session,
            principal,
            "import_run.role_applied",
            row.id,
            role=body.role.value,
            contacts_changed=changed,
        )
        return s.ApplyRoleOut(import_run_id=row.id, role=body.role, contacts_changed=changed)


# Knowledge base (Welle 3 item 14): manually curated per tenant and optionally per property,
# plus entries learned from mail preparation corrections (mhvp.communication.preparation). Read
# only context for AI runs; never written by AI on its own (rule 0.1.6).


async def _knowledge_entry(session: Any, entry_id: uuid.UUID) -> Any:
    row = await session.get(AiKnowledgeEntry, entry_id)
    if row is None or row.deleted_at is not None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get("/ai/knowledge", summary="Wissensbasis")
async def list_knowledge(
    request: Request,
    property_id: uuid.UUID | None = None,
    kind: AiKnowledgeKind | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.KnowledgeEntryOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AiKnowledgeEntry).where(AiKnowledgeEntry.deleted_at.is_(None))
        if property_id is not None:
            query = query.where(AiKnowledgeEntry.property_id == property_id)
        if kind is not None:
            query = query.where(AiKnowledgeEntry.kind == kind)
        rows = (await session.scalars(query.order_by(AiKnowledgeEntry.created_at.desc()))).all()
        return [s.KnowledgeEntryOut.model_validate(r) for r in rows]


@router.post("/ai/knowledge", status_code=201, summary="Wissenseintrag anlegen")
async def create_knowledge(
    body: s.KnowledgeEntryIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.KnowledgeEntryOut:
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        if body.property_id is not None:
            await _get(session, Property, body.property_id)
        row = AiKnowledgeEntry(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=body.property_id,
            kind=body.kind,
            title=body.title,
            content=body.content,
        )
        session.add(row)
        await session.flush()
        await _event(session, principal, "ai_knowledge.created", row.id, kind=body.kind.value)
        return s.KnowledgeEntryOut.model_validate(row)


@router.put("/ai/knowledge/{entry_id}", summary="Wissenseintrag ändern")
async def update_knowledge(
    entry_id: uuid.UUID,
    body: s.KnowledgeEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.KnowledgeEntryOut:
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        row = await _knowledge_entry(session, entry_id)
        if body.property_id is not None:
            await _get(session, Property, body.property_id)
        row.property_id = body.property_id
        row.kind = body.kind
        row.title = body.title
        row.content = body.content
        row.updated_by = principal.user_id
        await session.flush()
        await _event(session, principal, "ai_knowledge.updated", row.id, kind=body.kind.value)
        await session.refresh(row)
        return s.KnowledgeEntryOut.model_validate(row)


@router.delete("/ai/knowledge/{entry_id}", status_code=204, summary="Wissenseintrag löschen")
async def delete_knowledge(
    entry_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UNDO)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await _knowledge_entry(session, entry_id)
        row.deleted_at = datetime.now(UTC)
        row.updated_by = principal.user_id
        await _event(session, principal, "ai_knowledge.deleted", row.id)
