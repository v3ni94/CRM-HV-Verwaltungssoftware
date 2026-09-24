"""AI endpoints (/api/v1/ai, /imports): provider setup, chat, runs, proposals, import runs."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from mhvp.ai import gateway, imports, jobs, tasks
from mhvp.ai import schemas as s
from mhvp.ai.models import (
    AiConversation,
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


@router.get("/ai/usage", summary="KI-Kosten im laufenden Monat")
async def usage(request: Request, principal: TenantPrincipal = Depends(READ)) -> s.UsageOut:
    now = datetime.now(UTC)
    async with tenant_tx(request, principal) as session:
        spent = await gateway.spent_this_month(session, now)
        budget = await session.scalar(
            select(func.coalesce(func.max(AiProviderConfig.monthly_budget_eur), 0)).where(
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


async def _conversation_out(session: Any, row: AiConversation) -> s.ConversationOut:
    messages = (
        await session.scalars(
            select(AiMessage)
            .where(AiMessage.conversation_id == row.id)
            .order_by(AiMessage.created_at)
        )
    ).all()
    out = s.ConversationOut.model_validate(row)
    out.messages = [s.MessageOut.model_validate(m) for m in messages]
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


@router.get("/ai/conversations", summary="Chats")
async def list_conversations(
    request: Request,
    context_type: str | None = None,
    context_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.ConversationOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AiConversation).where(AiConversation.created_by == principal.user_id)
        if context_type:
            query = query.where(AiConversation.context_type == context_type)
        if context_id:
            query = query.where(AiConversation.context_id == context_id)
        rows = (
            await session.scalars(query.order_by(AiConversation.created_at.desc()).limit(50))
        ).all()
        return [s.ConversationOut.model_validate(r) for r in rows]


async def _own_conversation(
    session: Any, principal: TenantPrincipal, conversation_id: uuid.UUID
) -> AiConversation:
    row: AiConversation = await _get(session, AiConversation, conversation_id)
    if row.created_by != principal.user_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # chats are personal
    return row


@router.get("/ai/conversations/{conversation_id}", summary="Chat lesen")
async def get_conversation(
    conversation_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ConversationOut:
    async with tenant_tx(request, principal) as session:
        return await _conversation_out(
            session, await _own_conversation(session, principal, conversation_id)
        )


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
        out.proposal_id = await session.scalar(
            select(AiProposal.id).where(AiProposal.task_run_id == run.id)
        )
        return out


# Proposals and import runs ----------------------------------------------------------------


@router.get("/ai/proposals/{proposal_id}", summary="Vorschlag lesen")
async def get_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ProposalOut:
    async with tenant_tx(request, principal) as session:
        return s.ProposalOut.model_validate(await _get(session, AiProposal, proposal_id))


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
        else:
            if body.property is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Angaben zum Objekt fehlen.")
            summary = await imports.apply_property(
                session, import_run, principal, proposal.proposed, body.property
            )
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
        await _event(session, principal, "import_run.undone", row.id, status=row.status.value)
        return await _import_out(session, row)
