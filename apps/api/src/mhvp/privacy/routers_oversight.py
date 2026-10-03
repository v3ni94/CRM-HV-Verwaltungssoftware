"""Privacy oversight (Welle 21, AJ13): consent overview (GAI-508), request deadline monitoring
(GAI-507) and the pre G1 readiness evaluation of the processing register (GAI-510).

Nothing here decides a legal question: the response deadlines have no default value (the
operator enters them after legal review), the readiness evaluation only lists open points and
never opens a gate, the consent overview counts records without judging their validity.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.contacts.models import Consent, ConsentKind
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.config import Settings
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Tenant, TenantSettings
from mhvp.privacy import config_sources
from mhvp.privacy.models import (
    ACCESS_REQUEST_OPEN,
    PrivacyAccessRequest,
    PrivacyErasureRequest,
    PrivacyRegisterEntry,
)

router = APIRouter(tags=["Datenschutz"])
READ = require_permission("privacy:read")
APPROVE = require_permission("privacy:approve")

DEADLINES_KEY = "privacy_request_deadlines"
OPEN_ERASURE = ("requested", "approved")


# --- GAI-508 consent overview ------------------------------------------------------------


class PrivacyConsentPurposeOut(BaseModel):
    kind: str
    active: int
    revoked: int
    objections: int
    without_proof: int
    contacts_active: int


class PrivacyConsentOverviewOut(BaseModel):
    as_of: datetime
    items: list[PrivacyConsentPurposeOut]


@router.get(
    "/privacy/consent-overview",
    summary="Einwilligungen mandantenweit je Zweck (aktiv, widerrufen, ohne Nachweis)",
    dependencies=[Depends(strict_query)],
)
async def consent_overview(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyConsentOverviewOut:
    """Counts per purpose. ``without_proof``: active consent without linked document (the
    source text alone is recorded); whether that suffices as proof is not judged here."""
    now = datetime.now(UTC)
    active_cond = (Consent.granted_at <= now) & (
        Consent.revoked_at.is_(None) | (Consent.revoked_at > now)
    )
    is_consent = Consent.record_type == "consent"
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(
                    Consent.kind,
                    func.count().filter(is_consent & active_cond),
                    func.count().filter(
                        is_consent & Consent.revoked_at.is_not(None) & (Consent.revoked_at <= now)
                    ),
                    func.count().filter(Consent.record_type == "objection"),
                    func.count().filter(is_consent & active_cond & Consent.document_id.is_(None)),
                    func.count(func.distinct(Consent.contact_id)).filter(is_consent & active_cond),
                ).group_by(Consent.kind)
            )
        ).all()
    found = {r[0]: r for r in rows}
    items = []
    for kind in ConsentKind:
        r = found.get(kind)
        items.append(
            PrivacyConsentPurposeOut(
                kind=kind.value,
                active=int(r[1]) if r else 0,
                revoked=int(r[2]) if r else 0,
                objections=int(r[3]) if r else 0,
                without_proof=int(r[4]) if r else 0,
                contacts_active=int(r[5]) if r else 0,
            )
        )
    return PrivacyConsentOverviewOut(as_of=now, items=items)


# --- GAI-507 deadline monitoring -----------------------------------------------------------


class PrivacyDeadlinesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No default value: the response periods are a legal question (OPEN_QUESTIONS AJ13-01).
    access_days: int | None = Field(default=None, ge=1, le=365)
    erasure_days: int | None = Field(default=None, ge=1, le=365)
    warn_days: int | None = Field(default=None, ge=0, le=180)
    note: str | None = Field(default=None, max_length=500)


class PrivacyDeadlinesOut(PrivacyDeadlinesIn):
    configured: bool


class PrivacyDeadlineItemOut(BaseModel):
    kind: Literal["erasure", "access"]
    request_id: str
    contact_id: str
    status: str
    received_on: date
    warn_on: date | None
    due_on: date | None
    state: Literal["unconfigured", "ok", "warn", "overdue"]


class PrivacyDeadlineListOut(BaseModel):
    settings: PrivacyDeadlinesOut
    today: date
    items: list[PrivacyDeadlineItemOut]
    access_requests_tracked: bool


def _deadlines(sources: dict[str, object] | None) -> PrivacyDeadlinesOut:
    raw = (sources or {}).get(DEADLINES_KEY)
    raw = raw if isinstance(raw, dict) else {}
    try:
        val = PrivacyDeadlinesIn.model_validate(
            {k: raw.get(k) for k in ("access_days", "erasure_days", "warn_days", "note")}
        )
    except ValueError:
        val = PrivacyDeadlinesIn()
    return PrivacyDeadlinesOut(
        **val.model_dump(), configured=val.access_days is not None or val.erasure_days is not None
    )


@router.get(
    "/privacy/request-deadlines",
    summary="Fristen für Auskunfts- und Löschanträge (Einstellung ohne Standardwert)",
    dependencies=[Depends(strict_query)],
)
async def get_deadlines(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyDeadlinesOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        return _deadlines(row.sources if row else None)


@router.put("/privacy/request-deadlines", summary="Fristen für Datenschutzanträge setzen")
async def put_deadlines(
    body: PrivacyDeadlinesIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> PrivacyDeadlinesOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        before = (row.sources or {}).get(DEADLINES_KEY)
        value = body.model_dump()
        row.sources = {**(row.sources or {}), DEADLINES_KEY: value}
        row.version += 1
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="privacy_deadlines.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": value},
        )
        return _deadlines(row.sources)


def deadline_state(
    received: date, days: int | None, warn_days: int | None, today: date
) -> tuple[date | None, date | None, str]:
    if days is None:
        return None, None, "unconfigured"
    due = received + timedelta(days=days)
    warn = due - timedelta(days=warn_days or 0)
    if today > due:
        return warn, due, "overdue"
    if today >= warn:
        return warn, due, "warn"
    return warn, due, "ok"


@router.get(
    "/privacy/request-deadlines/monitor",
    summary="Fristenüberwachung offener Datenschutzanträge (Eingang, Vorfrist, Frist)",
    dependencies=[Depends(strict_query)],
)
async def monitor_deadlines(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyDeadlineListOut:
    """Open erasure and access requests with warn and due date computed from the tenant
    setting (access requests since migration 0448, AK06). Dates are an orientation to be
    verified, never a legal calculation."""
    today = local_today()
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        cfg = _deadlines(row.sources if row else None)
        reqs = await session.scalars(
            select(PrivacyErasureRequest)
            .where(PrivacyErasureRequest.status.in_(OPEN_ERASURE))
            .order_by(PrivacyErasureRequest.received_on, PrivacyErasureRequest.id)
        )
        items = []
        for r in reqs:
            warn, due, state = deadline_state(r.received_on, cfg.erasure_days, cfg.warn_days, today)
            items.append(
                PrivacyDeadlineItemOut(
                    kind="erasure",
                    request_id=str(r.id),
                    contact_id=str(r.contact_id),
                    status=r.status,
                    received_on=r.received_on,
                    warn_on=warn,
                    due_on=due,
                    state=state,
                )
            )
        # AK06 (GAI-507): access requests have an intake record since migration 0448.
        access = await session.scalars(
            select(PrivacyAccessRequest)
            .where(PrivacyAccessRequest.status.in_(ACCESS_REQUEST_OPEN))
            .order_by(PrivacyAccessRequest.received_on, PrivacyAccessRequest.id)
        )
        for a in access:
            warn, due, state = deadline_state(a.received_on, cfg.access_days, cfg.warn_days, today)
            items.append(
                PrivacyDeadlineItemOut(
                    kind="access",
                    request_id=str(a.id),
                    contact_id=str(a.contact_id),
                    status=a.status,
                    received_on=a.received_on,
                    warn_on=warn,
                    due_on=due,
                    state=state,
                )
            )
    return PrivacyDeadlineListOut(
        settings=cfg, today=today, items=items, access_requests_tracked=True
    )


# --- GAI-510 readiness of the register before G1 ---------------------------------------------


class PrivacyReadinessItemOut(BaseModel):
    key: str | None
    name: str
    entry_id: str | None
    issues: list[str]


class PrivacyReadinessOut(BaseModel):
    complete: bool
    active_services: int
    items: list[PrivacyReadinessItemOut]
    note: str


_ISSUES = {
    "missing_entry": "Kein Registereintrag für einen aktiv genutzten Dienst",
    "avv_open": "AVV ohne Nachweis oder angefragt",
    "third_country_open": "Drittlandübermittlung nicht geklärt",
    "legal_review_open": "Rechtliche Prüfung offen",
}


def entry_issues(entry: PrivacyRegisterEntry | None) -> list[str]:
    if entry is None:
        return ["missing_entry"]
    out = []
    if entry.avv_status not in ("confirmed", "not_required"):
        out.append("avv_open")
    if entry.third_country_status == "open":
        out.append("third_country_open")
    if entry.legal_review_status == "open":
        out.append("legal_review_open")
    return out


@router.get(
    "/privacy/register/readiness",
    summary="Vor-G1-Auswertung: aktiv genutzte Dienste mit geklärtem Registereintrag",
    dependencies=[Depends(strict_query)],
)
async def register_readiness(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyReadinessOut:
    """Lists every actively used service (detected from configuration) and every active
    register entry whose AVV, third country or legal review is still open. Information only:
    it neither opens nor closes a gate (AE32-01, AJ13-02)."""
    settings: Settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        tenant = await session.get(Tenant, principal.tenant_id)
        detected = await config_sources.detect(session, settings, tenant.slug if tenant else "")
        entries = list(
            await session.scalars(select(PrivacyRegisterEntry).order_by(PrivacyRegisterEntry.name))
        )
    by_key = {e.source_key: e for e in entries if e.source_key and e.active}
    items: list[PrivacyReadinessItemOut] = []
    seen: set[str] = set()
    active = [d for d in detected if d.active]
    for d in active:
        entry = by_key.get(d.key)
        if entry is not None:
            seen.add(str(entry.id))
        issues = entry_issues(entry)
        if issues:
            items.append(
                PrivacyReadinessItemOut(
                    key=d.key,
                    name=d.name,
                    entry_id=str(entry.id) if entry else None,
                    issues=[_ISSUES[i] for i in issues],
                )
            )
    for e in entries:
        if not e.active or str(e.id) in seen:
            continue
        issues = entry_issues(e)
        if issues:
            items.append(
                PrivacyReadinessItemOut(
                    key=e.source_key,
                    name=e.name,
                    entry_id=str(e.id),
                    issues=[_ISSUES[i] for i in issues],
                )
            )
    return PrivacyReadinessOut(
        complete=not items,
        active_services=len(active),
        items=items,
        note="Auswertung zur Vorbereitung von Gate G1; ersetzt keine rechtliche Prüfung und "
        "öffnet kein Gate.",
    )
