"""Run a queued AI task and turn a successful result into a proposal and a chat answer."""

import asyncio
import uuid

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.ai import gateway, imports
from mhvp.ai.models import AiMessage, AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore


def _uuid(value: object) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


def _answer_text(run: AiTaskRun) -> str:
    output = run.output or {}
    if run.task is AiTask.ANSWER_QUESTION:
        text = str(output.get("answer", ""))
        if not output.get("answerable", True):
            text += "\n\n(Die vorhandenen Unterlagen beantworten die Frage nicht sicher.)"
        return text
    if run.task is AiTask.SUMMARIZE:
        points = "\n".join(f"- {p}" for p in output.get("open_points", []))
        return (
            f"{output.get('summary', '')}\n\nOffene Punkte:\n{points}"
            if points
            else str(output.get("summary", ""))
        )
    return "Vorschlag erstellt. Bitte Vorschau prüfen und bestätigen."


async def run_and_propose(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    blobs: BlobStore,
    actor_user_id: uuid.UUID | None,
) -> AiTaskRun:
    try:
        run = await gateway.execute(factory, tenant_id, run_id, blobs, actor_user_id)
    except gateway.GatewayBlockedError as exc:
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(AiTaskRun, run_id)
            if row is not None and row.status in (RunStatus.QUEUED, RunStatus.RUNNING):
                row.status, row.error = RunStatus.BLOCKED, str(exc)
            return row  # type: ignore[return-value]
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)  # type: ignore[assignment]
        assert run is not None  # noqa: S101
        proposal_id = None
        if run.status is RunStatus.SUCCEEDED and run.task in (
            AiTask.EXTRACT_CONTACTS,
            AiTask.EXTRACT_PROPERTY,
            AiTask.EXTRACT_INVOICE,
        ):
            output = run.output or {}
            if run.task is AiTask.EXTRACT_CONTACTS:
                preview = await imports.contacts_preview(session, output)
                entity_type = "contacts"
            elif run.task is AiTask.EXTRACT_PROPERTY:
                preview = imports.property_preview(output)
                entity_type = "property"
            else:
                preview = await imports.invoice_preview(session, output, run)
                entity_type = "invoice"
            proposal = AiProposal(
                tenant_id=tenant_id,
                task_run_id=run.id,
                entity_type=entity_type,
                context_id=_uuid(run.input_ref.get("context", {}).get("context_id")),
                proposed=preview,
            )
            session.add(proposal)
            await session.flush()
            proposal_id = proposal.id
        if run.conversation_id is not None:
            content = (
                _answer_text(run)
                if run.status is RunStatus.SUCCEEDED
                else f"Nicht ausgeführt: {run.error}"
            )
            session.add(
                AiMessage(
                    tenant_id=tenant_id,
                    conversation_id=run.conversation_id,
                    role="assistant",
                    content=content,
                    document_ids=[],
                    task_run_id=run.id,
                    proposal_id=proposal_id,
                )
            )
    return run


async def run_once(
    settings: Settings, tenant_id: uuid.UUID, run_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> str:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        run = await run_and_propose(
            create_session_factory(engine), tenant_id, run_id, BlobStore(settings), actor_user_id
        )
        return run.status.value
    finally:
        await engine.dispose()


@shared_task(name="mhvp.ai.run", acks_late=True)
def run(tenant_id: str, run_id: str, actor_user_id: str | None) -> str:
    return asyncio.run(
        run_once(
            get_settings(),
            uuid.UUID(tenant_id),
            uuid.UUID(run_id),
            uuid.UUID(actor_user_id) if actor_user_id else None,
        )
    )
