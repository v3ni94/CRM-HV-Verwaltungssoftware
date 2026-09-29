"""Configs per legal entity, connection test, outbound queue and worker loop of the Lexware
Office extension (rule INT-LEXO-01).

Every user action only writes rows (config, outbox); the worker (``tasks.process``) talks to
Lexware under the shared rate limiter and the retry plan of ``core.webhooks``. Gates are
re-checked per row inside the worker: config enabled, AVV recorded, feature switch of the
row's kind on, key not invalid. A failing check leaves the row pending (fail closed).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.config import Settings
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.webhooks import RETRY_SCHEDULE_SECONDS, UnsafeWebhookTargetError, check_target
from mhvp.integrations.lexoffice_async import (
    AsyncCredentials,
    LexofficeAsyncClient,
    LexofficeAuthError,
    LexofficeError,
    LexofficeOrganizationMismatchError,
    LexofficeRateLimitedError,
    LexofficeUnavailableError,
)
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeInvoiceKind,
    LexofficeInvoiceKindMapping,
    LexofficeOutbox,
    LexofficeOutboxKind,
    LexofficeOutboxStatus,
    LexofficeRunKind,
    LexofficeRunStatus,
    LexofficeSyncRun,
    LexofficeTenantConfig,
)
from mhvp.properties.models import LegalEntity, LegalEntityKind

log = logging.getLogger(__name__)

OUTBOX_BATCH = 50
INVOICING_FEATURES = ("INVOICING", "INVOICING_PRO")
FEATURE_BY_KIND = {
    LexofficeOutboxKind.CONTACT_CREATE.value: "sync_contacts",
    LexofficeOutboxKind.CONTACT_UPDATE.value: "sync_contacts",
    LexofficeOutboxKind.REFRESH_LINK.value: "sync_contacts",
    LexofficeOutboxKind.LOOKUP_INVOICE.value: "invoice_copies",
    LexofficeOutboxKind.FETCH_INVOICE_FILE.value: "invoice_copies",
    LexofficeOutboxKind.CREATE_INVOICE_DRAFT.value: "invoice_drafts",
}
RUN_KIND_BY_OUTBOX = {
    LexofficeOutboxKind.CONTACT_CREATE.value: LexofficeRunKind.CONTACT_SYNC,
    LexofficeOutboxKind.CONTACT_UPDATE.value: LexofficeRunKind.CONTACT_SYNC,
    LexofficeOutboxKind.REFRESH_LINK.value: LexofficeRunKind.CONTACT_SYNC,
    LexofficeOutboxKind.LOOKUP_INVOICE.value: LexofficeRunKind.INVOICE_LOOKUP,
    LexofficeOutboxKind.FETCH_INVOICE_FILE.value: LexofficeRunKind.INVOICE_FILE,
    LexofficeOutboxKind.CREATE_INVOICE_DRAFT.value: LexofficeRunKind.INVOICE_DRAFT,
}


class WorkerContext:
    """Per config state handed to the kind handlers."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        config: LexofficeTenantConfig,
        client: LexofficeAsyncClient,
        settings: Settings,
        blobs: Any,
        now: datetime,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.config = config
        self.client = client
        self.settings = settings
        self.blobs = blobs
        self.now = now


Handler = Callable[[WorkerContext, LexofficeOutbox], Awaitable[None]]
HANDLERS: dict[str, Handler] = {}


def handler(kind: LexofficeOutboxKind) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind.value] = fn
        return fn

    return register


# Configs -----------------------------------------------------------------------------------


async def get_config(session: AsyncSession, config_id: uuid.UUID) -> LexofficeTenantConfig | None:
    return await session.get(LexofficeTenantConfig, config_id)


async def require_config(session: AsyncSession, config_id: uuid.UUID) -> LexofficeTenantConfig:
    config = await get_config(session, config_id)
    if config is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return config


async def list_configs(session: AsyncSession, tenant_id: uuid.UUID) -> list[LexofficeTenantConfig]:
    rows = await session.scalars(
        select(LexofficeTenantConfig)
        .where(LexofficeTenantConfig.tenant_id == tenant_id)
        .order_by(
            LexofficeTenantConfig.legal_entity_id.nulls_first(), LexofficeTenantConfig.created_at
        )
    )
    return list(rows)


async def default_config(
    session: AsyncSession, tenant_id: uuid.UUID, *, create: bool = False
) -> LexofficeTenantConfig | None:
    row: LexofficeTenantConfig | None = await session.scalar(
        select(LexofficeTenantConfig).where(
            LexofficeTenantConfig.tenant_id == tenant_id,
            LexofficeTenantConfig.legal_entity_id.is_(None),
        )
    )
    if row is None and create:
        row = LexofficeTenantConfig(tenant_id=tenant_id)
        session.add(row)
        await session.flush()
    return row


def feature_on(config: LexofficeTenantConfig, feature: str | None) -> bool:
    """Enabled, AVV recorded, key valid and the named switch on."""
    if not config.enabled or not config.api_key or config.token_invalid:
        return False
    if config.avv_confirmed_on is None:
        return False
    return feature is None or bool(getattr(config, feature, False))


def check_base_url(url: str, settings: Settings) -> str:
    value = url.strip().rstrip("/")
    try:
        check_target(value, allow_private=settings.webhook_allow_private_targets, resolve=False)
    except (UnsafeWebhookTargetError, ValueError) as exc:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Die Basisadresse ist nicht zulässig."
        ) from exc
    return value


def has_invoicing(config: LexofficeTenantConfig) -> bool:
    return any(f in INVOICING_FEATURES for f in (config.profile_business_features or []))


def client_for(
    config: LexofficeTenantConfig, settings: Settings, *, redis: Any | None = None
) -> LexofficeAsyncClient:
    if not config.api_key:
        raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
    return LexofficeAsyncClient(
        AsyncCredentials(
            api_key=config.api_key,
            base_url=config.base_url,
            organization_id=config.organization_id,
            rate_key=config.organization_id or str(config.id),
            redis=redis,
            allow_private=settings.webhook_allow_private_targets,
        )
    )


def deeplink(config: LexofficeTenantConfig, kind: str, remote_id: str) -> str:
    base = config.app_base_url.rstrip("/")
    if kind == "contact":
        return f"{base}/permalink/contacts/view/{remote_id}"
    if kind == "invoice_edit":
        return f"{base}/permalink/invoices/edit/{remote_id}"
    if kind == "invoice":
        return f"{base}/permalink/invoices/view/{remote_id}"
    return f"{base}/permalink/recurring-templates/view/{remote_id}"


async def audit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    type_: str,
    *,
    entity_type: str = "lexoffice_config",
    entity_id: uuid.UUID | None,
    actor: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await emit(
        session,
        tenant_id=tenant_id,
        type=f"lexoffice.{type_}",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor,
        payload=payload or {},
    )


async def start_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    kind: LexofficeRunKind,
    started_by: uuid.UUID | None = None,
) -> LexofficeSyncRun:
    run = LexofficeSyncRun(
        tenant_id=tenant_id,
        kind=kind.value,
        status=LexofficeRunStatus.RUNNING.value,
        started_by=started_by,
    )
    session.add(run)
    await session.flush()
    return run


async def finish_run(
    session: AsyncSession,
    run: LexofficeSyncRun,
    counts: dict[str, int],
    errors: list[str],
    *,
    status: str | None = None,
) -> None:
    run.counts = counts
    run.errors = [e[:500] for e in errors]
    if status is not None:
        run.status = status
    elif not errors:
        run.status = LexofficeRunStatus.OK.value
    elif any(v for k, v in counts.items() if k in ("ok", "sent")):
        run.status = LexofficeRunStatus.PARTIAL.value
    else:
        run.status = LexofficeRunStatus.FAILED.value
    run.finished_at = datetime.now(UTC)
    await session.flush()


async def check_connection(
    session: AsyncSession,
    config: LexofficeTenantConfig,
    settings: Settings,
    *,
    actor: uuid.UUID | None,
    redis: Any | None = None,
) -> None:
    """``GET /v1/profile``: stores organisation and profile fields. A different organisation
    than the one already bound to existing links fails with MHVP-LEXO-0013."""
    if not config.api_key:
        raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
    run = await start_run(session, config.tenant_id, LexofficeRunKind.TEST, actor)
    probe = LexofficeAsyncClient(
        AsyncCredentials(
            api_key=config.api_key,
            base_url=config.base_url,
            organization_id=None,
            rate_key=config.organization_id or str(config.id),
            redis=redis,
            allow_private=settings.webhook_allow_private_targets,
        )
    )
    config.last_tested_at = datetime.now(UTC)
    try:
        profile = await probe.get_profile()
    except LexofficeError as exc:
        config.last_test_ok = False
        config.last_test_message = exc.redacted()
        if isinstance(exc, LexofficeAuthError):
            config.token_invalid = True
            config.enabled = False
        await finish_run(session, run, {"ok": 0, "failed": 1}, [exc.redacted()])
        await audit(session, config.tenant_id, "test_failed", entity_id=config.id, actor=actor)
        return
    organization_id = str(profile.get("organizationId") or "")
    if config.organization_id and organization_id != config.organization_id:
        links = await session.scalar(
            select(LexofficeContactLink.id)
            .where(LexofficeContactLink.config_id == config.id)
            .limit(1)
        )
        if links is not None:
            config.last_test_ok = False
            config.last_test_message = "API Schlüssel gehört zu einer anderen Lexware Organisation."
            config.enabled = False
            await finish_run(session, run, {"ok": 0, "failed": 1}, [config.last_test_message])
            await audit(
                session, config.tenant_id, "organization_mismatch", entity_id=config.id, actor=actor
            )
            raise ProblemError(ErrorCodes.LEXOFFICE_ORGANIZATION_MISMATCH)
    config.organization_id = organization_id or None
    config.organization_name = str(profile.get("companyName") or "")[:200] or None
    config.profile_tax_type = str(profile.get("taxType") or "")[:32] or None
    small = profile.get("smallBusiness")
    config.profile_small_business = bool(small) if small is not None else None
    features = profile.get("businessFeatures")
    config.profile_business_features = (
        [str(f)[:40] for f in features] if isinstance(features, list) else []
    )
    config.token_invalid = False
    config.last_test_ok = True
    config.last_test_message = "Verbindung erfolgreich."
    await finish_run(session, run, {"ok": 1, "failed": 0}, [])
    await audit(session, config.tenant_id, "test_ok", entity_id=config.id, actor=actor)


# Invoice kind to legal entity ----------------------------------------------------------------


async def ensure_default_mappings(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Seed: the management kind maps to the manager legal entity when it exists. Broker and
    consulting kinds are set by the operator in the settings UI (no company name is hard
    coded here)."""
    existing = {
        row.kind
        for row in await session.scalars(
            select(LexofficeInvoiceKindMapping).where(
                LexofficeInvoiceKindMapping.tenant_id == tenant_id
            )
        )
    }
    if LexofficeInvoiceKind.MANAGEMENT.value in existing:
        return
    manager = await session.scalar(
        select(LegalEntity)
        .where(LegalEntity.tenant_id == tenant_id, LegalEntity.kind == LegalEntityKind.MANAGER)
        .order_by(LegalEntity.created_at)
        .limit(1)
    )
    if manager is None:
        return
    session.add(
        LexofficeInvoiceKindMapping(
            tenant_id=tenant_id,
            kind=LexofficeInvoiceKind.MANAGEMENT.value,
            legal_entity_id=manager.id,
        )
    )
    await session.flush()


async def config_for_invoice_kind(
    session: AsyncSession, tenant_id: uuid.UUID, kind: str
) -> LexofficeTenantConfig:
    """The config of the legal entity mapped to ``kind``; MHVP-LEXO-0017 when unmapped or the
    legal entity has no config."""
    mapping = await session.scalar(
        select(LexofficeInvoiceKindMapping).where(
            LexofficeInvoiceKindMapping.tenant_id == tenant_id,
            LexofficeInvoiceKindMapping.kind == kind,
        )
    )
    if mapping is None:
        raise ProblemError(ErrorCodes.LEXOFFICE_KIND_UNMAPPED)
    config = await session.scalar(
        select(LexofficeTenantConfig).where(
            LexofficeTenantConfig.tenant_id == tenant_id,
            LexofficeTenantConfig.legal_entity_id == mapping.legal_entity_id,
        )
    )
    if config is None:
        raise ProblemError(
            ErrorCodes.LEXOFFICE_KIND_UNMAPPED,
            detail="Für die zugeordnete Gesellschaft ist keine Lexware Organisation eingerichtet.",
        )
    return config


# Outbox --------------------------------------------------------------------------------------


async def enqueue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
    kind: LexofficeOutboxKind,
    idempotency_key: str,
    target_kind: str,
    target_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    requested_by: uuid.UUID | None = None,
    next_attempt_at: datetime | None = None,
) -> LexofficeOutbox:
    """Writes one queue row; the same idempotency key returns the existing row."""
    existing: LexofficeOutbox | None = await session.scalar(
        select(LexofficeOutbox).where(
            LexofficeOutbox.tenant_id == tenant_id,
            LexofficeOutbox.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing
    row = LexofficeOutbox(
        tenant_id=tenant_id,
        config_id=config_id,
        kind=kind.value,
        idempotency_key=idempotency_key[:120],
        target_kind=target_kind,
        target_id=target_id,
        payload=payload or {},
        status=LexofficeOutboxStatus.PENDING.value,
        next_attempt_at=next_attempt_at or datetime.now(UTC),
        requested_by=requested_by,
    )
    session.add(row)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        found: LexofficeOutbox | None = await session.scalar(
            select(LexofficeOutbox).where(
                LexofficeOutbox.tenant_id == tenant_id,
                LexofficeOutbox.idempotency_key == idempotency_key,
            )
        )
        if found is None:  # pragma: no cover - the unique row exists
            raise
        return found
    return row


def schedule_retry(row: LexofficeOutbox, exc: LexofficeError, now: datetime) -> None:
    """``max(plan[attempt], Retry-After)``; beyond the plan the row fails."""
    row.last_status_code = exc.status_code
    row.last_error = exc.redacted()
    retry_after = getattr(exc, "retry_after", None)
    if exc.retryable and row.attempts <= len(RETRY_SCHEDULE_SECONDS):
        delay = RETRY_SCHEDULE_SECONDS[row.attempts - 1]
        if retry_after is not None:
            delay = max(delay, int(retry_after))
        row.next_attempt_at = now + timedelta(seconds=delay)
    else:
        row.status = LexofficeOutboxStatus.FAILED.value


def fail(row: LexofficeOutbox, message: str, status_code: int | None = None) -> None:
    row.status = LexofficeOutboxStatus.FAILED.value
    row.last_error = message[:500]
    row.last_status_code = status_code


async def process_outbox(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    config: LexofficeTenantConfig,
    settings: Settings,
    *,
    blobs: Any = None,
    redis: Any | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Sends due rows of one config; gates re-checked per row (fail closed)."""
    # Handlers live in sibling modules; importing them registers the kinds.
    from mhvp.integrations.lexoffice_ext import invoice_copy, invoice_drafts, sync  # noqa: F401

    now = now or datetime.now(UTC)
    counts = {"sent": 0, "retry": 0, "failed": 0, "skipped": 0}
    if not feature_on(config, None):
        return counts
    ctx = WorkerContext(
        session=session,
        tenant_id=tenant_id,
        config=config,
        client=client_for(config, settings, redis=redis),
        settings=settings,
        blobs=blobs,
        now=now,
    )
    rows = (
        await session.scalars(
            select(LexofficeOutbox)
            .where(
                LexofficeOutbox.config_id == config.id,
                LexofficeOutbox.status == LexofficeOutboxStatus.PENDING.value,
                LexofficeOutbox.next_attempt_at <= now,
            )
            .order_by(LexofficeOutbox.created_at, LexofficeOutbox.id)
            .limit(OUTBOX_BATCH)
            .with_for_update(skip_locked=True)
        )
    ).all()
    if not rows:
        return counts
    seen_contacts: set[uuid.UUID] = set()
    run = await start_run(
        session, tenant_id, RUN_KIND_BY_OUTBOX.get(rows[0].kind, LexofficeRunKind.CONTACT_SYNC)
    )
    errors: list[str] = []
    for row in rows:
        feature = FEATURE_BY_KIND.get(row.kind)
        if feature is None or not feature_on(config, feature):
            counts["skipped"] += 1
            continue
        if row.kind == LexofficeOutboxKind.CONTACT_UPDATE.value:
            # One update per contact per run, oldest first; the rest wait.
            if row.target_id in seen_contacts:
                counts["skipped"] += 1
                continue
            seen_contacts.add(row.target_id)
        handle = HANDLERS.get(row.kind)
        if handle is None:
            fail(row, "Unbekannte Art.")
            counts["failed"] += 1
            continue
        row.attempts += 1
        try:
            await handle(ctx, row)
        except LexofficeAuthError as exc:
            config.token_invalid = True
            row.attempts -= 1
            row.last_error = exc.redacted()
            row.last_status_code = exc.status_code
            errors.append(exc.redacted())
            await audit(session, tenant_id, "token_invalid", entity_id=config.id)
            break
        except LexofficeOrganizationMismatchError as exc:
            fail(row, exc.redacted(), exc.status_code)
            config.enabled = False
            counts["failed"] += 1
            errors.append(exc.redacted())
            await audit(session, tenant_id, "organization_mismatch", entity_id=config.id)
            break
        except (LexofficeRateLimitedError, LexofficeUnavailableError) as exc:
            schedule_retry(row, exc, now)
            if row.status == LexofficeOutboxStatus.FAILED.value:
                counts["failed"] += 1
                errors.append(exc.redacted())
            else:
                counts["retry"] += 1
            continue
        except LexofficeError as exc:
            fail(row, exc.redacted(), exc.status_code)
            counts["failed"] += 1
            errors.append(exc.redacted())
            await audit(
                session,
                tenant_id,
                "push_failed",
                entity_type="lexoffice_outbox",
                entity_id=row.id,
                payload={"kind": row.kind, "status": exc.status_code},
            )
            continue
        if row.status == LexofficeOutboxStatus.PENDING.value:
            row.status = LexofficeOutboxStatus.SENT.value
            row.sent_at = now
            row.last_error = None
        if row.status == LexofficeOutboxStatus.SENT.value:
            counts["sent"] += 1
        else:
            counts["failed"] += 1
            if row.last_error:
                errors.append(row.last_error)
    await finish_run(session, run, counts, errors)
    await session.flush()
    return counts


async def retry_row(session: AsyncSession, row: LexofficeOutbox) -> None:
    if row.status != LexofficeOutboxStatus.FAILED.value:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Nur fehlgeschlagene Einträge.")
    row.status = LexofficeOutboxStatus.PENDING.value
    row.attempts = 0
    row.next_attempt_at = datetime.now(UTC)
    row.last_error = None


async def purge(session: AsyncSession, tenant_id: uuid.UUID, *, retention_days: int = 90) -> int:
    """Queue rows in a final state older than the retention are deleted; remote display of
    undecided remote rows is cleared."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    rows = (
        await session.scalars(
            select(LexofficeOutbox).where(
                LexofficeOutbox.tenant_id == tenant_id,
                LexofficeOutbox.status.in_(
                    [
                        LexofficeOutboxStatus.SENT.value,
                        LexofficeOutboxStatus.FAILED.value,
                        LexofficeOutboxStatus.SUPERSEDED.value,
                    ]
                ),
                LexofficeOutbox.updated_at < cutoff,
            )
        )
    ).all()
    for row in rows:
        await session.delete(row)
    links = (
        await session.scalars(
            select(LexofficeContactLink).where(
                LexofficeContactLink.tenant_id == tenant_id,
                LexofficeContactLink.sync_status.in_(["dismissed", "remote_only"]),
                LexofficeContactLink.updated_at < cutoff,
            )
        )
    ).all()
    for link in links:
        link.remote_display = {}
    await session.flush()
    return len(rows)
