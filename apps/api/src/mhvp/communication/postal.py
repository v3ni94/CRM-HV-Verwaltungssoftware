"""Brief- und Postversand mit Statusrückmeldung (M23-01, docs/rules/M23-01.md).

Ein Postauftrag (``postal_job``) gehört zu genau einer Zustellung (``dispatch``, Kanal
``post``). Der Anbieter (``manual`` oder ein registrierter Adapter, heute LetterXpress) ist
Mandanteneinstellung; ohne ``enabled`` reicht kein Weg (API, Job, Mahnwesen) einen Brief bei
einem externen Anbieter ein. Jede Statusänderung wird als ``postal_job_event`` protokolliert
und auf die Zustellung gespiegelt (``sent_at``, ``delivered_at``, Nachweis). Ein Mahnfall
erhält den Zugangsnachweis über ``dunning_case.delivered_at``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.dispatch import EVIDENCE
from mhvp.communication.models import Dispatch, PostalJob, PostalJobEvent, PostalSettings
from mhvp.communication.postal_providers import (
    FINAL_STATUSES,
    OPEN_STATUSES,
    STATUSES,
    LetterXpressProvider,
    PostalOptions,
    PostalProvider,
    PostalProviderError,
    PostalStatus,
    build_provider,
    provider_names,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open

router = APIRouter(prefix="/postal", tags=["Kommunikation"])
READ = require_permission("communication:read")
CREATE = require_permission("communication:create")
UPDATE = require_permission("communication:update")
APPROVE = require_permission("communication:approve")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

# Job status -> dispatch status (M23 evidence rule stays: delivered only with evidence).
DISPATCH_STATUS = {
    "submitted": "prepared",
    "printed": "prepared",
    "sent": "sent",
    "delivered": "delivered",
    "failed": "failed",
    "cancelled": "prepared",
}
POLL_MIN_INTERVAL_SECONDS = 600


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PostalSettingsIn(_In):
    provider: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None
    username: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    mode: str | None = Field(default=None, pattern="^(test|live)$")
    default_color: bool | None = None
    default_duplex: bool | None = None
    default_registered: str | None = Field(default=None, pattern="^(r1|r2)$")
    clear_api_key: bool = False


class PostalSubmitIn(_In):
    dispatch_id: uuid.UUID | None = None
    dunning_case_id: uuid.UUID | None = None
    registered: str | None = Field(default=None, pattern="^(r1|r2)$")
    color: bool | None = None
    duplex: bool | None = None
    notice: str | None = Field(default=None, max_length=255)


class PostalManualIn(_In):
    status: str = Field(pattern="^(printed|sent|delivered|failed)$")
    occurred_at: datetime | None = None
    evidence_kind: str | None = Field(default=None, pattern="^(" + "|".join(EVIDENCE) + ")$")
    evidence_ref: str | None = Field(default=None, max_length=200)
    evidence_document_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=1000)


# Settings -------------------------------------------------------------------------------


async def settings_row(session: AsyncSession, tenant_id: uuid.UUID) -> PostalSettings:
    row = await session.scalar(select(PostalSettings))
    if row is None:
        row = PostalSettings(tenant_id=tenant_id)
        session.add(row)
        await session.flush()
    return row


def settings_out(row: PostalSettings) -> dict[str, Any]:
    return {
        "provider": row.provider,
        "enabled": row.enabled,
        "username": row.username,
        "has_api_key": bool(row.api_key),
        "mode": row.mode,
        "default_color": row.default_color,
        "default_duplex": row.default_duplex,
        "default_registered": row.default_registered,
        "last_balance": row.last_balance,
        "last_checked_at": row.last_checked_at,
        "last_error": row.last_error,
        "providers": provider_names(),
    }


def provider_for(row: PostalSettings) -> PostalProvider:
    return build_provider(
        row.provider,
        {"username": row.username, "api_key": row.api_key, "mode": row.mode},
    )


def ensure_external_allowed(row: PostalSettings, provider: PostalProvider) -> None:
    """Kein Versand ohne Freigabe: externer Anbieter nur mit ``enabled`` (Standard aus)."""
    if provider.name != "manual" and not row.enabled:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Postdienst ist für diesen Mandanten nicht freigegeben "
            "(Einstellungen, Postversand).",
        )


# Jobs ------------------------------------------------------------------------------------


def job_out(job: PostalJob, events: list[PostalJobEvent] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        k: getattr(job, k)
        for k in (
            "id",
            "dispatch_id",
            "document_id",
            "contact_id",
            "dunning_case_id",
            "provider",
            "provider_job_id",
            "status",
            "options",
            "recipient_address",
            "filename",
            "pages",
            "price",
            "tracking_code",
            "tracking_status",
            "error",
            "submitted_at",
            "last_polled_at",
            "completed_at",
            "created_at",
        )
    }
    if events is not None:
        out["events"] = [
            {
                "id": e.id,
                "status": e.status,
                "source": e.source,
                "detail": e.detail,
                "occurred_at": e.occurred_at,
            }
            for e in events
        ]
    return out


async def recipient_address(session: AsyncSession, contact_id: uuid.UUID) -> str:
    """Anschriftblock wie in den Briefen (``mhvp.documents.services.recipient``): nur mit
    vollständiger Anschrift, sonst Validierungsfehler."""
    from mhvp.documents import services as docs

    _, lines, _ = await docs.recipient(session, contact_id)
    return "\n".join(lines)


async def _record(
    session: AsyncSession,
    job: PostalJob,
    status: str,
    *,
    source: str,
    detail: str | None,
    raw: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> PostalJobEvent:
    event = PostalJobEvent(
        tenant_id=job.tenant_id,
        job_id=job.id,
        dispatch_id=job.dispatch_id,
        status=status,
        source=source,
        detail=detail[:1000] if detail else None,
        raw=raw or {},
        occurred_at=occurred_at or datetime.now(UTC),
    )
    session.add(event)
    return event


async def apply_status(
    session: AsyncSession,
    job: PostalJob,
    status: str,
    *,
    source: str,
    detail: str | None = None,
    raw: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
    evidence_kind: str | None = None,
    evidence_ref: str | None = None,
    evidence_document_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    force_event: bool = False,
) -> bool:
    """Sets the job state, mirrors it on the dispatch and the dunning case, writes the
    history. Returns True when the state changed. A final state is never left again except
    by a manual correction (``source == "manual"``)."""
    if status not in STATUSES:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannter Status {status}.")
    at = occurred_at or datetime.now(UTC)
    changed = status != job.status
    if not changed and not force_event:
        return False
    if job.status in FINAL_STATUSES and source != "manual" and changed:
        await _record(
            session,
            job,
            status,
            source=source,
            detail=f"ignoriert, Auftrag ist {job.status}: {detail or ''}",
            raw=raw,
            occurred_at=at,
        )
        return False
    job.status = status
    if status in FINAL_STATUSES:
        job.completed_at = at
    if status == "failed":
        job.error = detail
    await _record(session, job, status, source=source, detail=detail, raw=raw, occurred_at=at)

    dispatch = await session.get(Dispatch, job.dispatch_id, with_for_update=True)
    if dispatch is not None:
        if status == "delivered" and not (
            evidence_kind or dispatch.evidence_kind or job.tracking_code
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zugang nur mit Nachweis (Art und Referenz oder Beleg).",
            )
        dispatch.status = DISPATCH_STATUS[status]
        if status in ("sent", "delivered") and dispatch.sent_at is None:
            dispatch.sent_at = at
        if status == "delivered":
            dispatch.delivered_at = at
            dispatch.evidence_kind = (
                evidence_kind
                or dispatch.evidence_kind
                or ("registered_mail" if job.options.get("registered") else "other")
            )
            dispatch.evidence_ref = (
                evidence_ref
                or job.tracking_code
                or dispatch.evidence_ref
                or (f"{job.provider}:{job.provider_job_id}" if job.provider_job_id else None)
            )
            if evidence_document_id is not None:
                dispatch.evidence_document_id = evidence_document_id
        elif evidence_kind or evidence_ref or evidence_document_id:
            dispatch.evidence_kind = evidence_kind or dispatch.evidence_kind
            dispatch.evidence_ref = evidence_ref or dispatch.evidence_ref
            if evidence_document_id is not None:
                dispatch.evidence_document_id = evidence_document_id
        if status == "cancelled":
            dispatch.sent_at, dispatch.delivered_at = None, None
        await emit(
            session,
            tenant_id=job.tenant_id,
            type=f"dispatch.postal_{status}",
            entity_type="dispatch",
            entity_id=dispatch.id,
            actor_user_id=actor_user_id,
            payload={"provider": job.provider, "job_id": str(job.id), "source": source},
        )
    if job.dunning_case_id is not None and status == "delivered":
        from mhvp.accounting.models import DunningCase

        case = await session.get(DunningCase, job.dunning_case_id, with_for_update=True)
        if case is not None:
            case.delivered_at = at
            case.delivery_channel = "post"
            await emit(
                session,
                tenant_id=job.tenant_id,
                type="dunning_case.delivered",
                entity_type="dunning_case",
                entity_id=case.id,
                actor_user_id=actor_user_id,
                payload={
                    "postal_job_id": str(job.id),
                    "evidence_ref": dispatch.evidence_ref if dispatch else None,
                },
            )
    await session.flush()
    return True


async def _document_pdf(
    request: Request, session: AsyncSession, document_id: uuid.UUID
) -> tuple[bytes, str]:
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document, StorageKind

    document = await session.get(Document, document_id)
    if document is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
    if document.mime_type != "application/pdf":
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Nur PDF-Dokumente können als Brief eingereicht werden."
        )
    if document.storage is StorageKind.GOOGLE_DRIVE:
        from mhvp.documents import services as docs

        return await docs.download_from_drive(session, request, document), document.filename
    return BlobStore(request.app.state.settings).get(document.storage_ref), document.filename


async def _dispatch_for_dunning_case(
    session: AsyncSession, principal: TenantPrincipal, case_id: uuid.UUID
) -> tuple[Dispatch, Any]:
    """Zustellung (Kanal post) für das Mahnschreiben des Falls; der Mahnlauf muss freigegeben
    sein, der Fall wird wie bei der manuellen Erfassung als versendet geführt (M16-09)."""
    from mhvp.accounting import dunning
    from mhvp.accounting.models import DunningCase
    from mhvp.contacts import recipients
    from mhvp.contracts.models import Contract

    case = await session.get(DunningCase, case_id, with_for_update=True)
    if case is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Mahnfall nicht gefunden.")
    if case.letter_document_id is None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Mahnfall hat noch kein Mahnschreiben (PDF)."
        )
    contract = await session.get(Contract, case.contract_id) if case.contract_id else None
    contact_id = (
        await recipients.debtor_contact_id(session, contract.party_id) if contract else None
    )
    if contact_id is None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Kein Empfänger (Schuldner) am Mahnfall ermittelbar."
        )
    if case.status == "proposed":
        await dunning.mark_sent(session, case, "post", principal.user_id)
    elif case.status != "sent":
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Nur vorgeschlagene oder versendete Mahnfälle können eingereicht werden.",
        )
    dispatch = await session.scalar(
        select(Dispatch)
        .where(
            Dispatch.document_id == case.letter_document_id,
            Dispatch.contact_id == contact_id,
            Dispatch.channel == "post",
        )
        .order_by(Dispatch.created_at.desc())
        .limit(1)
    )
    if dispatch is None or dispatch.status == "delivered":
        dispatch = Dispatch(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            document_id=case.letter_document_id,
            contact_id=contact_id,
            channel="post",
        )
        session.add(dispatch)
        await session.flush()
    return dispatch, case


async def submit(
    session: AsyncSession,
    request: Request,
    principal: TenantPrincipal,
    body: PostalSubmitIn,
) -> PostalJob:
    if (body.dispatch_id is None) == (body.dunning_case_id is None):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Genau eines von dispatch_id oder dunning_case_id angeben.",
        )
    row = await settings_row(session, principal.tenant_id)
    provider = provider_for(row)
    ensure_external_allowed(row, provider)
    if provider.name != "manual" and not principal.has("communication:approve"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            detail="Einreichen beim Postdienst erfordert das Recht communication:approve.",
        )
    case = None
    if body.dunning_case_id is not None:
        if provider.name != "manual":
            # Mahnschreiben über einen externen Dienst: gleiche Sperre wie der Versandpfad
            # des Mahnwesens (M16-02, G1 je Mandant); die Postausgangsliste bleibt offen.
            await ensure_release_gate_open(
                ReleaseGate.G1, principal.tenant_id, request.app.state.release_gate_resolver
            )
        dispatch, case = await _dispatch_for_dunning_case(session, principal, body.dunning_case_id)
    else:
        dispatch_ = await session.get(Dispatch, body.dispatch_id, with_for_update=True)
        if dispatch_ is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Zustellung nicht gefunden.")
        dispatch = dispatch_
    if dispatch.channel != "post":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Nur Zustellungen mit Kanal post.")
    if dispatch.status == "delivered":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Zugang ist bereits nachgewiesen.")
    open_job = await session.scalar(
        select(PostalJob).where(
            PostalJob.dispatch_id == dispatch.id, PostalJob.status.in_(OPEN_STATUSES)
        )
    )
    if open_job is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für diese Zustellung läuft bereits ein Postauftrag."
        )
    options = PostalOptions(
        registered=body.registered if body.registered is not None else row.default_registered,
        color=body.color if body.color is not None else row.default_color,
        duplex=body.duplex if body.duplex is not None else row.default_duplex,
        notice=body.notice or f"dispatch:{dispatch.id}",
    )
    address = await recipient_address(session, dispatch.contact_id)
    pdf, filename = await _document_pdf(request, session, dispatch.document_id)
    job = PostalJob(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        dispatch_id=dispatch.id,
        document_id=dispatch.document_id,
        contact_id=dispatch.contact_id,
        dunning_case_id=case.id if case is not None else None,
        provider=provider.name,
        status="submitted",
        options=options.as_dict(),
        recipient_address=address,
        filename=filename,
    )
    session.add(job)
    await session.flush()
    try:
        result = await provider.submit(pdf, address, options, filename)
    except PostalProviderError as exc:
        if case is not None:
            # Mahnfall: nichts bleibt stehen (kein "sent" ohne Einreichung), Fehler als 409.
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
        # Einzelbrief: der fehlgeschlagene Auftrag bleibt mit Fehlertext in der
        # Postausgangsliste sichtbar (Status ``failed``); die Zustellung wird ``failed``.
        job.provider_job_id = None
        await apply_status(
            session,
            job,
            "failed",
            source="system",
            detail=str(exc),
            actor_user_id=principal.user_id,
            force_event=True,
        )
        return job
    finally:
        await provider.aclose()
    job.provider_job_id, job.pages, job.price = result.job_id, result.pages, result.price
    job.submitted_at = datetime.now(UTC)
    job.last_polled_at = job.submitted_at
    detail = (
        "In die Postausgangsliste aufgenommen (Druck und Versand manuell)."
        if provider.name == "manual"
        else f"Bei {provider.name} eingereicht (Modus {row.mode}), Auftrag {result.job_id}."
    )
    await apply_status(
        session,
        job,
        result.status,
        source="system",
        detail=detail,
        raw=result.raw,
        actor_user_id=principal.user_id,
        force_event=True,
    )
    return job


async def refresh(session: AsyncSession, row: PostalSettings, job: PostalJob) -> bool:
    """Ruft den Anbieterstatus ab und übernimmt ihn (Beat-Job und Schaltfläche)."""
    if job.provider == "manual" or not job.provider_job_id:
        return False
    provider = build_provider(
        job.provider, {"username": row.username, "api_key": row.api_key, "mode": row.mode}
    )
    try:
        result = await provider.status(job.provider_job_id)
    except PostalProviderError as exc:
        job.error = str(exc)[:1000]
        job.last_polled_at = datetime.now(UTC)
        await _record(
            session, job, job.status, source="provider", detail=f"Statusabruf fehlgeschlagen: {exc}"
        )
        return False
    finally:
        await provider.aclose()
    job.last_polled_at = datetime.now(UTC)
    if result is None:
        return False
    return await _apply_provider_status(session, job, result)


async def _apply_provider_status(
    session: AsyncSession, job: PostalJob, result: PostalStatus
) -> bool:
    if result.tracking_code:
        job.tracking_code = result.tracking_code
    if result.tracking_status:
        job.tracking_status = result.tracking_status
    if result.pages is not None:
        job.pages = result.pages
    if result.price is not None:
        job.price = Decimal(result.price)
    return await apply_status(
        session, job, result.status, source="provider", detail=result.detail, raw=result.raw
    )


async def poll_open_jobs(
    session: AsyncSession, tenant_id: uuid.UUID, *, limit: int = 100
) -> dict[str, int]:
    """Alle offenen Aufträge eines Mandanten beim externen Anbieter abfragen (Beat-Job)."""
    row = await settings_row(session, tenant_id)
    counts = {"polled": 0, "changed": 0, "skipped": 0}
    if row.provider == "manual" or not row.enabled:
        return counts
    cutoff = datetime.now(UTC).timestamp() - POLL_MIN_INTERVAL_SECONDS
    jobs = list(
        await session.scalars(
            select(PostalJob)
            .where(
                PostalJob.provider == row.provider,
                PostalJob.status.in_(OPEN_STATUSES),
                PostalJob.provider_job_id.is_not(None),
            )
            .order_by(PostalJob.last_polled_at.nulls_first())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        if job.last_polled_at is not None and job.last_polled_at.timestamp() > cutoff:
            counts["skipped"] += 1
            continue
        # "sent" without registered mail never advances (no tracking): stop polling those.
        if job.status == "sent" and not job.options.get("registered"):
            counts["skipped"] += 1
            continue
        counts["polled"] += 1
        if await refresh(session, row, job):
            counts["changed"] += 1
    return counts


# Router ------------------------------------------------------------------------------------


@router.get("/settings", summary="Postversand: Anbieter und Freigabe des Mandanten")
async def get_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return settings_out(await settings_row(session, principal.tenant_id))


@router.put("/settings", summary="Postversand: Anbieter, Zugangsdaten und Freigabe ändern")
async def put_settings(
    body: PostalSettingsIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await settings_row(session, principal.tenant_id)
        before = {"provider": row.provider, "enabled": row.enabled, "mode": row.mode}
        if body.provider is not None:
            if body.provider not in provider_names():
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail=f"Unbekannter Postdienst {body.provider}."
                )
            row.provider = body.provider
        for name in ("username", "mode", "default_color", "default_duplex"):
            value = getattr(body, name)
            if value is not None:
                setattr(row, name, value)
        if body.default_registered is not None or (body.model_fields_set & {"default_registered"}):
            row.default_registered = body.default_registered
        if body.clear_api_key:
            row.api_key = None
        elif body.api_key:
            row.api_key = body.api_key
        if body.enabled is not None:
            if body.enabled and row.provider != "manual" and not (row.username and row.api_key):
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Freigabe nur mit hinterlegten Zugangsdaten."
                )
            row.enabled = body.enabled
        row.updated_by = principal.user_id
        after = {"provider": row.provider, "enabled": row.enabled, "mode": row.mode}
        if before != after:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="postal_settings.updated",
                entity_type="postal_settings",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload=after,
                changes={k: [before[k], after[k]] for k in after if before[k] != after[k]},
            )
        await session.flush()
        return settings_out(row)


@router.post("/settings/test", summary="Postversand: Verbindung prüfen (Guthaben abfragen)")
async def check_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await settings_row(session, principal.tenant_id)
        provider = provider_for(row)
        row.last_checked_at = datetime.now(UTC)
        try:
            if isinstance(provider, LetterXpressProvider):
                row.last_balance = await provider.balance()
            row.last_error = None
        except PostalProviderError as exc:
            row.last_error = str(exc)[:1000]
        finally:
            await provider.aclose()
        await session.flush()
        return settings_out(row)


@router.get(
    "/jobs",
    summary="Postausgang: Aufträge mit Anbieterstatus",
    dependencies=[Depends(strict_query)],
)
async def list_jobs(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    status: str | None = None,
    provider: str | None = None,
    contact_id: uuid.UUID | None = None,
    dunning_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(PostalJob)
        if status == "open":
            query = query.where(PostalJob.status.in_(OPEN_STATUSES))
        elif status:
            query = query.where(PostalJob.status == status)
        if provider:
            query = query.where(PostalJob.provider == provider)
        if contact_id:
            query = query.where(PostalJob.contact_id == contact_id)
        if dunning_only:
            query = query.where(PostalJob.dunning_case_id.is_not(None))
        jobs = (
            await session.scalars(
                query.order_by(PostalJob.created_at.desc()).limit(max(1, min(limit, 500)))
            )
        ).all()
        return [job_out(j) for j in jobs]


@router.get("/jobs/summary", summary="Postausgang: Anzahl je Status")
async def summary(request: Request, principal: TenantPrincipal = Depends(READ)) -> dict[str, int]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(select(PostalJob.status, func.count()).group_by(PostalJob.status))
        ).all()
        return dict.fromkeys(STATUSES, 0) | {str(s): int(n) for s, n in rows}


@router.get("/jobs/{job_id}", summary="Postauftrag mit Statushistorie")
async def get_job(
    job_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        job = await session.get(PostalJob, job_id)
        if job is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        events = (
            await session.scalars(
                select(PostalJobEvent)
                .where(PostalJobEvent.job_id == job.id)
                .order_by(PostalJobEvent.created_at, PostalJobEvent.id)
            )
        ).all()
        return job_out(job, list(events))


@router.get(
    "/dispatches/{dispatch_id}/history",
    summary="Statushistorie der Zustellung (Postdienst)",
    dependencies=[Depends(strict_query)],
)
async def dispatch_history(
    dispatch_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        events = (
            await session.scalars(
                select(PostalJobEvent)
                .where(PostalJobEvent.dispatch_id == dispatch_id)
                .order_by(PostalJobEvent.created_at, PostalJobEvent.id)
            )
        ).all()
        return [
            {
                "id": e.id,
                "job_id": e.job_id,
                "status": e.status,
                "source": e.source,
                "detail": e.detail,
                "occurred_at": e.occurred_at,
            }
            for e in events
        ]


@router.post(
    "/jobs",
    status_code=201,
    summary="Brief beim Postdienst einreichen oder in die Postausgangsliste aufnehmen",
)
async def create_job(
    body: PostalSubmitIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Anbieter ``manual``: Eintrag in der Postausgangsliste, Druck und Versand erfolgen von
    Hand. Externer Anbieter: nur mit Mandantenfreigabe und Recht ``communication:approve``;
    ein Mahnschreiben zusätzlich nur bei offenem G1 (M16-02)."""
    async with tenant_tx(request, principal) as session:
        job = await submit(session, request, principal, body)
        return job_out(job)


@router.post("/jobs/{job_id}/manual", summary="Versand oder Zugang manuell erfassen")
async def manual(
    job_id: uuid.UUID,
    body: PostalManualIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        job = await session.get(PostalJob, job_id, with_for_update=True)
        if job is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if job.status == "delivered":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Zugang ist bereits nachgewiesen.")
        if body.status == "delivered" and not (
            body.evidence_kind and (body.evidence_ref or body.evidence_document_id)
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zugang nur mit Nachweis (Art und Referenz oder Beleg).",
            )
        await apply_status(
            session,
            job,
            body.status,
            source="manual",
            detail=body.note,
            occurred_at=body.occurred_at,
            evidence_kind=body.evidence_kind,
            evidence_ref=body.evidence_ref,
            evidence_document_id=body.evidence_document_id,
            actor_user_id=principal.user_id,
            force_event=True,
        )
        return job_out(job)


@router.post("/jobs/{job_id}/refresh", summary="Anbieterstatus jetzt abrufen")
async def refresh_job(
    job_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        job = await session.get(PostalJob, job_id, with_for_update=True)
        if job is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await settings_row(session, principal.tenant_id)
        await refresh(session, row, job)
        return job_out(job)


@router.post("/jobs/{job_id}/cancel", summary="Postauftrag stornieren")
async def cancel_job(
    job_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        job = await session.get(PostalJob, job_id, with_for_update=True)
        if job is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if job.status not in OPEN_STATUSES:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Auftrag ist {job.status} und kann nicht storniert werden.",
            )
        row = await settings_row(session, principal.tenant_id)
        ok = True
        if job.provider != "manual" and job.provider_job_id:
            provider = build_provider(
                job.provider, {"username": row.username, "api_key": row.api_key, "mode": row.mode}
            )
            try:
                ok = await provider.cancel(job.provider_job_id)
            except PostalProviderError as exc:
                raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
            finally:
                await provider.aclose()
        if not ok:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Anbieter hat die Stornierung abgelehnt."
            )
        await apply_status(
            session,
            job,
            "cancelled",
            source="manual",
            detail="Storniert.",
            actor_user_id=principal.user_id,
            force_event=True,
        )
        return job_out(job)
