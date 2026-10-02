"""Run a queued AI task and turn a successful result into a proposal and a chat answer."""

import asyncio
import uuid
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.ai import chat_actions, embeddings, examples, gateway, imports, lookup
from mhvp.ai.models import AiMessage, AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.logging import get_logger
from mhvp.documents.blobs import BlobStore

log = get_logger("mhvp.ai.jobs")
ERROR_MAX = 500


def failure_text(exc: BaseException) -> str:
    """Short error text for ``AiTaskRun.error``: class name plus message, at most ``ERROR_MAX``
    characters, so an unexpected exception never leaves the run in RUNNING without a reason."""
    text = f"{type(exc).__name__}: {exc}".strip().rstrip(":")
    return text if len(text) <= ERROR_MAX else text[: ERROR_MAX - 1] + "…"


def _uuid(value: object) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


def _role_text(preview: dict[str, Any]) -> str:
    """Confirms the role taken from the chat instruction, or asks for one (26.09.2026)."""
    role, count = preview.get("default_role"), int(preview.get("role_count") or 0)
    lines = []
    if role:
        lines.append(f"Rolle {role} für {count} Kontakte gesetzt.")
    elif preview.get("without_role"):
        lines.append(
            f"{preview['without_role']} Kontakte haben keine Rolle. {imports.ROLE_QUESTION} "
            'Antworten Sie zum Beispiel mit "Rolle bank" oder wählen Sie die Rolle in der '
            "Vorschau."
        )
    if preview.get("tags"):
        lines.append(f"Tags {', '.join(preview['tags'])} für alle Kontakte vorgesehen.")
    return "\n".join(lines)


def _answer_text(run: AiTaskRun, contacts_preview: dict[str, Any] | None = None) -> str:
    output = run.output or {}
    if contacts_preview is not None:
        extra = _role_text(contacts_preview)
        base = "Vorschlag erstellt. Bitte Vorschau prüfen und bestätigen."
        return f"{base}\n{extra}" if extra else base
    if run.task is AiTask.ANSWER_QUESTION:
        text = str(output.get("answer", ""))
        found = run.input_ref.get("lookup")
        links = lookup.links_of(found)
        if not links and not output.get("answerable", True):
            text += "\n\n(Die vorhandenen Unterlagen beantworten die Frage nicht sicher.)"
        if found is not None and (links or found.get("terms")):
            # The hit list (with the links below the message) comes from the platform, not
            # from the model (rule AI-LOOKUP-01); "nothing found" is said just as plainly.
            text += "\n\n" + lookup.answer_text(found)
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
    except Exception as exc:
        # Anything unexpected (blob store, parsing, database) must not leave the run RUNNING
        # forever: mark it FAILED with a short reason, log the traceback, and hand the result
        # back to the chat like any other failed run. No re-raise; Celery would only retry.
        log.exception(
            "ai_run_unhandled_error",
            tenant_id=str(tenant_id),
            run_id=str(run_id),
            error_type=type(exc).__name__,
        )
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(AiTaskRun, run_id)
            if row is not None and row.status in (RunStatus.QUEUED, RunStatus.RUNNING):
                row.status, row.error = RunStatus.FAILED, failure_text(exc)
                if row.conversation_id is not None:
                    session.add(
                        AiMessage(
                            tenant_id=tenant_id,
                            conversation_id=row.conversation_id,
                            role="assistant",
                            content=f"Nicht ausgeführt: {row.error}",
                            document_ids=[],
                            task_run_id=row.id,
                            proposal_id=None,
                        )
                    )
            return row  # type: ignore[return-value]
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)  # type: ignore[assignment]
        contacts_preview: dict[str, Any] | None = None
        assert run is not None  # noqa: S101
        proposal_id = None
        # The answering provider is part of every proposal (M7-02): after a fallback the
        # reviewer sees which provider produced it. Proposal only, never a decision.
        provider_used = run.provider.value if run.provider is not None else None
        if run.status is RunStatus.SUCCEEDED and run.task is AiTask.CHECK_STATEMENT:
            # A35 KI-Plausibilität: findings only, stored as a proposal at the statement;
            # nothing is written to the statement or its snapshot (rule 0.1.6).
            from mhvp.billing import ai_check

            check = AiProposal(
                tenant_id=tenant_id,
                task_run_id=run.id,
                entity_type=ai_check.ENTITY_TYPE,
                context_id=_uuid(run.input_ref.get("context", {}).get("context_id")),
                proposed={**ai_check.proposal_payload(run), "provider_used": provider_used},
            )
            session.add(check)
            await session.flush()
            proposal_id = check.id
        if run.status is RunStatus.SUCCEEDED and run.task is AiTask.RENT_INCREASE_CHECK:
            # M26-01: hints only, linked as ai_check_id of the case; never a release.
            from mhvp.ai import rent_increase_check

            hint = await rent_increase_check.store_result(session, run, provider_used)
            proposal_id = hint.id
        if run.status is RunStatus.SUCCEEDED and run.task is AiTask.PROPOSE_POSTING:
            # M7-09 KI-Kontierung: proposal only (entity_type posting); nothing is posted and
            # the bank transaction stays untouched (rule 0.1.6, 7.4).
            from mhvp.banking import ai_posting

            posting = AiProposal(
                tenant_id=tenant_id,
                task_run_id=run.id,
                entity_type=ai_posting.ENTITY_TYPE,
                context_id=_uuid(run.input_ref.get("context", {}).get("context_id")),
                proposed={**ai_posting.proposal_payload(run), "provider_used": provider_used},
            )
            session.add(posting)
            await session.flush()
            proposal_id = posting.id
        if run.status is RunStatus.SUCCEEDED and run.task in (
            AiTask.EXTRACT_CONTACTS,
            AiTask.EXTRACT_PROPERTY,
            AiTask.EXTRACT_INVOICE,
        ):
            output = run.output or {}
            if run.task is AiTask.EXTRACT_CONTACTS:
                preview = await imports.contacts_preview(
                    session, output, str(run.input_ref.get("instruction", ""))
                )
                contacts_preview = preview
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
                proposed={**preview, "provider_used": provider_used},
            )
            session.add(proposal)
            await session.flush()
            proposal_id = proposal.id
        action_note: str | None = None
        if (
            run.status is RunStatus.SUCCEEDED
            and run.task is AiTask.ANSWER_QUESTION
            and run.input_ref.get("lookup") is not None
        ):
            # Chat action (rule AI-LOOKUP-01): only for chat runs with a platform lookup (never
            # for the automation or intake callers of the task), checked by the platform,
            # proposal only; nothing is written before a human confirms it (0.1.6).
            payload, action_note = chat_actions.build(run)
            if payload is not None:
                payload, action_note = await chat_actions.enrich(session, payload)
            if payload is not None:
                action = chat_actions.proposal(run, payload, provider_used)
                session.add(action)
                await session.flush()
                proposal_id = action.id
        if run.conversation_id is not None:
            found = run.input_ref.get("lookup") if run.task is AiTask.ANSWER_QUESTION else None
            if run.status is RunStatus.SUCCEEDED:
                content = _answer_text(run, contacts_preview)
                if action_note:
                    content += f"\n\n{action_note}"
                elif proposal_id is not None and run.task is AiTask.ANSWER_QUESTION:
                    content += "\n\nVorschlag erstellt. Bitte prüfen und bestätigen."
            elif found is not None:
                # Deterministic fallback (rule AI-LOOKUP-01): no released provider, budget
                # exhausted or provider error; the platform hits are still answered.
                content = (
                    f"Die KI ist derzeit nicht verfügbar ({run.error}), daher zeige ich nur die "
                    "Treffer der Plattformsuche.\n" + lookup.answer_text(found)
                )
            else:
                content = f"Nicht ausgeführt: {run.error}"
            session.add(
                AiMessage(
                    tenant_id=tenant_id,
                    conversation_id=run.conversation_id,
                    role="assistant",
                    content=content,
                    document_ids=[],
                    task_run_id=run.id,
                    proposal_id=proposal_id,
                    links=lookup.links_of(found),
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


async def index_embeddings_once(
    settings: Settings, tenant_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> dict[str, Any]:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        report = await embeddings.index_tenant(
            create_session_factory(engine), tenant_id, actor_user_id
        )
        return report.as_dict()
    finally:
        await engine.dispose()


@shared_task(name="mhvp.ai.embed_index", acks_late=True)
def embed_index(tenant_id: str, actor_user_id: str | None) -> dict[str, Any]:
    """Embedding index job per tenant (M7-03): batches with budget accounting, see
    ``mhvp.ai.embeddings.index_tenant``."""
    return asyncio.run(
        index_embeddings_once(
            get_settings(),
            uuid.UUID(tenant_id),
            uuid.UUID(actor_user_id) if actor_user_id else None,
        )
    )


async def examples_retention_once(settings: Settings) -> dict[str, Any]:
    """Daily retention run over all active tenants (ADR 0010 addendum 27.09.2026): deletes
    learning examples older than the tenant's retention months, one transaction and one
    journal event per tenant. A failing tenant is recorded and the others still run."""
    from mhvp.platform.models import Tenant, TenantStatus

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"tenants": 0, "deleted": 0, "errors": []}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    summary = await examples.purge_expired_examples(session, tenant_id)
            except Exception as exc:  # the other tenants must still run
                log.exception("ai examples retention failed", tenant_id=str(tenant_id))
                report["errors"].append(f"{tenant_id}: {failure_text(exc)}")
                continue
            report["tenants"] += 1
            report["deleted"] += int(summary["deleted"])
    finally:
        await engine.dispose()
    return report


@shared_task(name="mhvp.ai.examples_retention", acks_late=True)
def examples_retention() -> dict[str, Any]:
    return asyncio.run(examples_retention_once(get_settings()))


async def batch_nightly_once(settings: Settings) -> dict[str, Any]:
    """Nightly collective run of deferred runs over all active tenants (9.3, M7-07)."""
    from mhvp.ai import batch
    from mhvp.platform.models import Tenant, TenantStatus

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"tenants": 0, "runs": 0, "succeeded": 0, "errors": []}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                summary = await batch.submit_deferred(factory, tenant_id, BlobStore(settings))
                callers = await batch.run_callers(factory, tenant_id, settings)
                report.setdefault("callers", {})[str(tenant_id)] = callers
            except Exception as exc:  # the other tenants must still run
                log.exception("ai batch nightly failed", tenant_id=str(tenant_id))
                report["errors"].append(f"{tenant_id}: {failure_text(exc)}")
                continue
            report["tenants"] += 1
            report["runs"] += summary["runs"]
            report["succeeded"] += summary["succeeded"]
    finally:
        await engine.dispose()
    return report


@shared_task(name="mhvp.ai.batch_nightly", acks_late=True)
def batch_nightly() -> dict[str, Any]:
    return asyncio.run(batch_nightly_once(get_settings()))


async def batch_poll_once(settings: Settings) -> dict[str, Any]:
    """Polls the open provider batches of all active tenants (9.3, GAB-09)."""
    from mhvp.ai import batch
    from mhvp.platform.models import Tenant, TenantStatus

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"tenants": 0, "batches": 0, "runs": 0, "errors": []}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                summary = await batch.poll_submitted(factory, tenant_id, BlobStore(settings))
            except Exception as exc:  # the other tenants must still run
                log.exception("ai batch poll failed", tenant_id=str(tenant_id))
                report["errors"].append(f"{tenant_id}: {failure_text(exc)}")
                continue
            report["tenants"] += 1
            report["batches"] += summary["batches"]
            report["runs"] += summary["runs"]
    finally:
        await engine.dispose()
    return report


@shared_task(name="mhvp.ai.batch_poll", acks_late=True)
def batch_poll() -> dict[str, Any]:
    return asyncio.run(batch_poll_once(get_settings()))
