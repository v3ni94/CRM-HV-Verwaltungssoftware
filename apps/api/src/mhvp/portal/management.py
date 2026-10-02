"""Portal management, package P13 (A.5 Verwalteransicht): feature switches and statistics per
tenant (M21-08, SA-01), representatives with power of attorney (M21-05) and the read only
support view with the user's consent (SA-02).

None of this touches money or a gate. A power of attorney is a declaration with legal effect:
creating or revoking one is reserved to the management (``tenant_settings:update``) and the
document proves the authority; the system does not assess its validity (Einschätzung der
Geschäftsführung). The support view is deliberately no login as the user: it returns a fixed,
read only extract (roles, contracts, tickets, documents by title) and only while a consent of
the portal user is active; every call is logged with the staff user and the reason."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import access, features
from mhvp.portal.models import (
    PortalAccount,
    PortalFeatureSetting,
    PortalReadReceipt,
    PortalRepresentation,
    PortalSupportAccess,
    PortalSupportConsent,
)
from mhvp.portal.property_scope import (
    contact_visible,
    ensure_contact_visible,
    portal_admin_guard,
)
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

admin = APIRouter(
    prefix="/portal-admin",
    tags=["Portal Verwaltung"],
    dependencies=[Depends(portal_admin_guard)],  # M2-02, R08-01
)
router = APIRouter(prefix="/portal", tags=["Portal"])
READ = require_permission("tickets:read")
MANAGE = require_permission("tenant_settings:update")
SUPPORT_NOTE = (
    "Lesende Sicht ohne Anmeldung als Nutzer, nur mit gültiger Einwilligung, jeder Aufruf wird "
    "protokolliert."
)
MAX_CONSENT_HOURS = 72
ACTIVE_DAYS = 30


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortalFeaturesPatch(_In):
    chat_enabled: bool | None = None
    chat_ai_prequalification_enabled: bool | None = None
    support_login_enabled: bool | None = None
    owner_rental_income_enabled: bool | None = None
    owner_rental_statements_enabled: bool | None = None
    chat_bot_enabled: bool | None = None
    privacy_feature_enabled: bool | None = None
    tenant_statement_enabled: bool | None = None
    owner_ticket_scope: Literal["none", "released", "property"] | None = None
    provider_rating_display: Literal["off", "staff"] | None = None


class PortalRepresentationIn(_In):
    account_id: uuid.UUID
    principal_contact_id: uuid.UUID
    document_id: uuid.UUID
    valid_from: date
    valid_to: date | None = None
    note: str | None = Field(default=None, max_length=500)


class PortalSupportConsentIn(_In):
    hours: int = Field(default=24, ge=1, le=MAX_CONSENT_HOURS)


# Features and statistics ------------------------------------------------------------------


@admin.get("/features", summary="Portal-Funktionsschalter des Mandanten")
async def get_features(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return features.admin_feature_dict(await features.get_or_default(session))


@admin.patch("/features", summary="Portal-Funktionsschalter ändern")
async def patch_features(
    body: PortalFeaturesPatch, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(PortalFeatureSetting))
        if row is None:
            row = PortalFeatureSetting(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        for key, value in body.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(row, key, value)
        if not row.chat_enabled:
            # The AI stage is part of the chat: without chat it cannot stay on.
            row.chat_ai_prequalification_enabled = False
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.features_changed",
            entity_type="portal_feature_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload=features.admin_feature_dict(row),
        )
        return features.admin_feature_dict(row)


@admin.get("/statistics", summary="Portalstatistik (Einladungen, Nutzung, Einreichungen)")
async def statistics(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Counts only, no personal data. "Aktiv" means a login within the last 30 days."""
    from mhvp.platform.models import User
    from mhvp.portal.forms import PortalFormSubmission
    from mhvp.tickets.models import Ticket, TicketSource

    since = datetime.now(UTC) - timedelta(days=ACTIVE_DAYS)
    async with tenant_tx(request, principal) as session:
        status_rows = (
            await session.execute(
                select(PortalAccount.status, func.count()).group_by(PortalAccount.status)
            )
        ).all()
        by_status = {status: int(n) for status, n in status_rows}
        active_users = await session.scalar(
            select(func.count())
            .select_from(PortalAccount)
            .join(User, User.id == PortalAccount.user_id)
            .where(PortalAccount.status == "active", User.last_login_at >= since)
        )
        receipts = (
            await session.execute(
                select(PortalReadReceipt.kind, func.count())
                .where(PortalReadReceipt.occurred_at >= since)
                .group_by(PortalReadReceipt.kind)
            )
        ).all()
        submissions = await session.scalar(
            select(func.count())
            .select_from(PortalFormSubmission)
            .where(PortalFormSubmission.created_at >= since)
        )
        tickets = await session.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.source == TicketSource.PORTAL, Ticket.created_at >= since)
        )
        return {
            "period_days": ACTIVE_DAYS,
            "accounts": {
                "total": sum(by_status.values()),
                "invited": by_status.get("invited", 0),
                "active": by_status.get("active", 0),
                "by_status": by_status,
            },
            "active_users": int(active_users or 0),
            "document_retrievals": {kind: int(n) for kind, n in receipts},
            "form_submissions": int(submissions or 0),
            "portal_tickets": int(tickets or 0),
        }


# Representatives --------------------------------------------------------------------------


def _rep_out(r: PortalRepresentation) -> dict[str, Any]:
    return {
        "id": r.id,
        "account_id": r.account_id,
        "principal_contact_id": r.principal_contact_id,
        "document_id": r.document_id,
        "valid_from": r.valid_from,
        "valid_to": r.valid_to,
        "status": r.status,
        "note": r.note,
        "revoked_at": r.revoked_at,
    }


@admin.get(
    "/representations", summary="Vertreter mit Vollmacht", dependencies=[Depends(strict_query)]
)
async def list_representations(
    request: Request,
    account_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    from mhvp.platform.models import User

    async with tenant_tx(request, principal) as session:
        query = select(PortalRepresentation).order_by(PortalRepresentation.valid_from.desc())
        if account_id is not None:
            query = query.where(PortalRepresentation.account_id == account_id)
        reps = (await session.scalars(query)).all()
        # Representative (portal account) of each row for the CRM (M21-05): contact and login
        # address of the account; nothing else of the account or the user is exposed.
        accounts = {
            account.id: (account.contact_id, email)
            for account, email in (
                await session.execute(
                    select(PortalAccount, User.email)
                    .join(User, User.id == PortalAccount.user_id)
                    .where(PortalAccount.id.in_({r.account_id for r in reps}))
                )
            ).all()
        }
        out = []
        visible: dict[uuid.UUID, bool] = {}
        for r in reps:
            contact_id, email = accounts.get(r.account_id, (None, None))
            # U15 (M2-02): with a property assignment only representations whose represented
            # contact lies inside it.
            if r.principal_contact_id not in visible:
                visible[r.principal_contact_id] = await contact_visible(
                    session, r.principal_contact_id
                )
            if not visible[r.principal_contact_id]:
                continue
            out.append(
                _rep_out(r)
                | {"representative_contact_id": contact_id, "representative_email": email}
            )
        return out


@admin.post("/representations", status_code=201, summary="Vertreter mit Vollmacht anlegen")
async def create_representation(
    body: PortalRepresentationIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    """The representative (portal account) gets the owner view of the represented contact,
    read only and only within the period. The power of attorney document is mandatory."""
    from mhvp.contacts.models import Contact
    from mhvp.documents.models import Document

    if body.valid_to is not None and body.valid_to < body.valid_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Ende liegt vor dem Beginn.")
    async with tenant_tx(request, principal) as session:
        account = await session.get(PortalAccount, body.account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Portalzugang nicht gefunden.")
        if account.contact_id == body.principal_contact_id:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Vertreter und Vertretener sind dieselbe Person."
            )
        if await session.get(Contact, body.principal_contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kontakt nicht gefunden.")
        await ensure_contact_visible(session, body.principal_contact_id)  # U15, M2-02
        # V11-08: existence and visibility in the member's legal entity and property scope.
        from mhvp.documents.routers import _get as get_visible_document

        await get_visible_document(session, Document, body.document_id)
        row = PortalRepresentation(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            account_id=account.id,
            principal_contact_id=body.principal_contact_id,
            document_id=body.document_id,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            note=(body.note or "").strip() or None,
        )
        session.add(row)
        await session.flush()
        granted = await access.sync_grants(session, account)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.representation_created",
            entity_type="portal_representation",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"account_id": str(account.id), "grants": granted},
        )
        return _rep_out(row)


@admin.post("/representations/{rep_id}/revoke", summary="Vollmacht widerrufen")
async def revoke_representation(
    rep_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(PortalRepresentation, rep_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await ensure_contact_visible(session, row.principal_contact_id)  # U15, M2-02
        if row.status == "revoked":
            return _rep_out(row)
        row.status = "revoked"
        row.revoked_at = datetime.now(UTC)
        row.revoked_by = principal.user_id
        await session.flush()
        account = await session.get(PortalAccount, row.account_id)
        if account is not None:
            await access.sync_grants(session, account)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.representation_revoked",
            entity_type="portal_representation",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"account_id": str(row.account_id)},
        )
        return _rep_out(row)


@router.get("/representations", summary="Eigene Vertretungen mit Ablauf")
async def own_representations(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """M21-05: the powers of attorney of the signed-in representative with period and state;
    expired or revoked ones are listed as such and carry no access."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        return {"items": await features.own_representations(session, account)}


# Support view -----------------------------------------------------------------------------


async def _active_consent(session: Any, account_id: uuid.UUID) -> PortalSupportConsent | None:
    row: PortalSupportConsent | None = await session.scalar(
        select(PortalSupportConsent)
        .where(
            PortalSupportConsent.account_id == account_id,
            PortalSupportConsent.revoked_at.is_(None),
            PortalSupportConsent.expires_at > datetime.now(UTC),
        )
        .order_by(PortalSupportConsent.expires_at.desc())
        .limit(1)
    )
    return row


def _consent_out(row: PortalSupportConsent | None) -> dict[str, Any]:
    return {
        "active": row is not None,
        "expires_at": row.expires_at if row is not None else None,
    }


@router.get("/support-consent", summary="Einwilligung in die Support-Sicht (Status)")
async def consent_status(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        out = _consent_out(await _active_consent(session, account.id))
        out["available"] = (await features.get_or_default(session)).support_login_enabled
        out["note"] = SUPPORT_NOTE
        return out


@router.post("/support-consent", status_code=201, summary="In die Support-Sicht einwilligen")
async def grant_consent(
    body: PortalSupportConsentIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        if not (await features.get_or_default(session)).support_login_enabled:
            raise ProblemError(
                ErrorCodes.FORBIDDEN, detail="Die Support-Sicht ist nicht freigeschaltet."
            )
        row = PortalSupportConsent(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            account_id=account.id,
            expires_at=datetime.now(UTC) + timedelta(hours=body.hours),
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.support_consent_granted",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"hours": body.hours},
        )
        return _consent_out(row)


@router.delete("/support-consent", status_code=204, summary="Einwilligung widerrufen")
async def revoke_consent(request: Request, ctx: Portal = Depends(portal_user)) -> None:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(PortalSupportConsent).where(
                    PortalSupportConsent.account_id == account.id,
                    PortalSupportConsent.revoked_at.is_(None),
                )
            )
        ).all()
        for row in rows:
            row.revoked_at = datetime.now(UTC)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.support_consent_revoked",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"consents": len(rows)},
        )


@admin.get("/accounts/{account_id}/support-view", summary="Support-Sicht (lesend, protokolliert)")
async def support_view(
    account_id: uuid.UUID,
    request: Request,
    reason: str = Query(min_length=5, max_length=500),
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    """What the user sees in the portal, as a read only extract. Needs the tenant switch and an
    active consent; without either the answer is 403. Each call writes a log row."""
    from mhvp.contracts.models import Contract
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        if not (await features.get_or_default(session)).support_login_enabled:
            raise ProblemError(
                ErrorCodes.FORBIDDEN, detail="Die Support-Sicht ist nicht freigeschaltet."
            )
        account = await session.get(PortalAccount, account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        consent = await _active_consent(session, account.id)
        if consent is None:
            raise ProblemError(
                ErrorCodes.FORBIDDEN, detail="Es liegt keine gültige Einwilligung des Nutzers vor."
            )
        today = local_today()
        active = await access.grants(session, account, today)
        contract_ids = [g.scope_id for g in active if g.scope_type == "contract"]
        contracts = (
            (await session.scalars(select(Contract).where(Contract.id.in_(contract_ids)))).all()
            if contract_ids
            else []
        )
        tickets = (
            await session.scalars(
                select(Ticket)
                .where(Ticket.initiator_contact_id == account.contact_id)
                .order_by(Ticket.number.desc())
                .limit(50)
            )
        ).all()
        docs = await access.visible_documents(session, account, today)
        session.add(
            PortalSupportAccess(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                account_id=account.id,
                consent_id=consent.id,
                staff_user_id=principal.user_id,
                reason=reason.strip(),
                areas="roles,contracts,tickets,documents",
            )
        )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal.support_view",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"consent_id": str(consent.id)},
        )
        return {
            "read_only": True,
            "note": SUPPORT_NOTE,
            "consent_expires_at": consent.expires_at,
            "roles": sorted({g.role for g in active}),
            "contracts": [
                {"id": c.id, "kind": c.kind.value, "number": c.number} for c in contracts
            ],
            "tickets": [
                {"id": t.id, "number": t.number, "title": t.title, "status": t.status.value}
                for t in tickets
            ],
            "documents": [{"id": d.id, "title": d.title} for d in docs[:100]],
        }


@admin.get(
    "/accounts/{account_id}/support-log",
    summary="Protokoll der Support-Sicht",
    dependencies=[Depends(strict_query)],
)
async def support_log(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if await session.get(PortalAccount, account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = (
            await session.scalars(
                select(PortalSupportAccess)
                .where(PortalSupportAccess.account_id == account_id)
                .order_by(PortalSupportAccess.created_at.desc())
                .limit(200)
            )
        ).all()
        return [
            {
                "id": r.id,
                "staff_user_id": r.staff_user_id,
                "reason": r.reason,
                "areas": r.areas,
                "consent_id": r.consent_id,
                "created_at": r.created_at,
            }
            for r in rows
        ]
