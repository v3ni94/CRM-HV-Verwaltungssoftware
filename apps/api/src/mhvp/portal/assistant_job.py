"""Asynchronous AI stage of the portal assistant (GAE-29, AE28).

The request only checks scope, switches and rate limit, writes a log row with status ``pending``
(question already masked) and queues the job. The worker claims the row atomically
(``job_started_at``), so a redelivered job never calls the provider twice, re-derives the scope
from the access grants of the account (the permission filter is unchanged and never taken from
the queue message), runs the AI stage and finishes the row. The portal polls the row. A row that
stays ``pending`` longer than ``JOB_TIMEOUT`` is closed as ``timeout`` with the search hits as
fallback; a late result of the job is then discarded (the finish only touches ``pending``)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction

JOB_TIMEOUT = timedelta(seconds=120)
TIMEOUT_MESSAGE = (
    "Die KI-Antwort hat zu lange gedauert. Sie sehen Treffer aus Ihren Unterlagen, "
    "bitte stellen Sie die Frage bei Bedarf erneut."
)
FAILED_MESSAGE = (
    "Die KI-Antwort ist derzeit nicht verfügbar. Sie sehen Treffer aus Ihren Unterlagen."
)


def is_expired(created_at: datetime, now: datetime | None = None) -> bool:
    return (now or datetime.now(UTC)) - created_at > JOB_TIMEOUT


def enqueue(tenant_id: uuid.UUID, log_id: uuid.UUID) -> None:
    """Queues the job; tests replace this function (no broker, no network)."""
    answer_job.apply_async(args=(str(tenant_id), str(log_id)), time_limit=int(JOB_TIMEOUT.seconds))


async def run_job(settings: Settings, tenant_id: uuid.UUID, log_id: uuid.UUID) -> str:
    """Runs one queued question; returns claimed, skipped or the final status."""
    from mhvp.ai import portal_answer
    from mhvp.documents.blobs import BlobStore
    from mhvp.portal import assistant_scope
    from mhvp.portal.models import PortalAccount, PortalChatLog
    from mhvp.workspace.services import local_today

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            claimed = await session.scalar(
                update(PortalChatLog)
                .where(
                    PortalChatLog.id == log_id,
                    PortalChatLog.status == "pending",
                    PortalChatLog.job_started_at.is_(None),
                )
                .values(job_started_at=datetime.now(UTC))
                .returning(PortalChatLog.id)
            )
            if claimed is None:
                return "skipped"
            log = await session.get(PortalChatLog, log_id)
            if log is None:  # pragma: no cover - claimed in this transaction
                return "skipped"
            account = await session.get(PortalAccount, log.account_id)
            user_id = log.created_by
            question, unit_id, document_id = log.question, log.unit_id, log.document_id
            if account is None or user_id is None:
                return await _finish(session, log_id, "failed", FAILED_MESSAGE, "account_missing")
            scope = await assistant_scope.build_scope(
                session, account, local_today(), unit_id=unit_id, document_id=document_id
            )
            account_id = account.id
        if scope.empty:  # grants withdrawn meanwhile: no provider call
            async with tenant_transaction(factory, tenant_id) as session:
                return await _finish(session, log_id, "no_sources", FAILED_MESSAGE, "no_documents")
        try:
            result = await portal_answer.answer(
                factory,
                tenant_id,
                account_id=account_id,
                user_id=user_id,
                question=question,
                scope_ids=set(scope.document_ids),
                focus_ids=(
                    sorted(scope.document_ids)
                    if scope.focus_unit_id is not None or scope.focus_document_id is not None
                    else None
                ),
                attach_document_id=scope.focus_document_id,
                blobs=BlobStore(settings),
            )
        except Exception as exc:
            async with tenant_transaction(factory, tenant_id) as session:
                return await _finish(
                    session, log_id, "failed", FAILED_MESSAGE, "ai_run_failed", str(exc)[:500]
                )
        failed = result.status == "failed"
        async with tenant_transaction(factory, tenant_id) as session:
            return await _finish(
                session,
                log_id,
                "failed" if failed else result.status,
                FAILED_MESSAGE if failed else result.answer,
                result.reason_code,
                result.technical_reason,
                sources=[]
                if failed
                else [
                    {"document_id": str(s["document_id"]), "title": s["title"]}
                    for s in result.sources
                ],
                run_id=result.run_id,
            )
    finally:
        await engine.dispose()


async def _finish(
    session: Any,
    log_id: uuid.UUID,
    status: str,
    answer: str | None,
    reason_code: str | None,
    technical_reason: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    run_id: uuid.UUID | None = None,
) -> str:
    """Only a still pending row is finished (a timeout wins over a late result)."""
    from mhvp.core.events import emit
    from mhvp.portal.models import PortalChatLog

    row = await session.scalar(
        update(PortalChatLog)
        .where(PortalChatLog.id == log_id, PortalChatLog.status == "pending")
        .values(
            status=status,
            answer=answer,
            reason_code=reason_code,
            technical_reason=technical_reason,
            sources=sources or [],
            run_id=run_id,
        )
        .returning(PortalChatLog.tenant_id)
    )
    if row is None:
        return "discarded"
    await emit(
        session,
        tenant_id=row,
        type="portal_assistant.question_finished",
        entity_type="portal_chat_log",
        entity_id=log_id,
        actor_user_id=None,
        payload={"status": status, "reason_code": reason_code},
    )
    return status


async def expire(session: Any, log: Any) -> None:
    """Closes an overdue pending row as timeout (called by the status poll)."""
    if log.status == "pending" and is_expired(log.created_at):
        await _finish(session, log.id, "timeout", TIMEOUT_MESSAGE, "timeout", "job_timeout")
        await session.refresh(log)


@shared_task(name="mhvp.portal.assistant_answer", acks_late=True, queue="default")
def answer_job(tenant_id: str, log_id: str) -> str:
    return asyncio.run(run_job(get_settings(), uuid.UUID(tenant_id), uuid.UUID(log_id)))


__all__ = ["JOB_TIMEOUT", "answer_job", "enqueue", "expire", "run_job"]
