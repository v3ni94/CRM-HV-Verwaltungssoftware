"""CRM side of the board audit room (7.9.2 PÜ06 to PÜ08, A52): list of engagements, board
portal access per engagement (invitation like an owner, role ``board``) and the management
answer to a board question. The board itself acts only through ``mhvp.portal.board``."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import AuditEngagement
from mhvp.portal.board import (
    BOARD_LEGAL_BASIS,
    BOARD_ROLE,
    BoardAccess,
    BoardAuditNote,
    answer_note,
    engagement_notes,
    note_out,
)
from mhvp.portal.models import AccessGrant, PortalAccount
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/hoa", tags=["hoa"])
READ = require_permission("accounting:read")
ANSWER = require_permission("accounting:create")
# Creating a portal account is contact management (same right as the owner invitation).
GRANT = require_permission("contacts:update")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoardAccessIn(_In):
    contact_id: uuid.UUID
    # Needed only when the contact has no portal account yet (invitation like an owner).
    email: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)


class BoardAnswerIn(_In):
    answer: str = Field(min_length=1, max_length=4000)


async def _engagement(session: AsyncSession, engagement_id: uuid.UUID) -> AuditEngagement:
    eng = await session.get(AuditEngagement, engagement_id)
    if eng is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return eng


def _access_out(a: BoardAccess, account: PortalAccount | None) -> dict[str, Any]:
    return {
        "id": a.id,
        "account_id": a.account_id,
        "contact_id": a.contact_id,
        "account_status": account.status if account else None,
        "created_at": a.created_at,
        "revoked_at": a.revoked_at,
    }


@router.get("/audits", summary="Prüfaufträge einer GdWE")
async def list_audits(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(AuditEngagement)
            .where(AuditEngagement.legal_entity_id == legal_entity_id)
            .order_by(AuditEngagement.period_from.desc(), AuditEngagement.id)
        )
        return [
            {
                "id": e.id,
                "legal_entity_id": e.legal_entity_id,
                "statement_id": e.statement_id,
                "period_from": e.period_from,
                "period_to": e.period_to,
                "purpose": e.purpose,
                "sampling": e.sampling,
                "status": e.status,
            }
            for e in rows
        ]


@router.get("/audit-engagements/{engagement_id}/board", summary="Beiratszugänge und Rückfragen")
async def board_section(
    engagement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, engagement_id)
        accesses = (
            await session.scalars(
                select(BoardAccess)
                .where(BoardAccess.engagement_id == eng.id)
                .order_by(BoardAccess.created_at)
            )
        ).all()
        out = []
        for a in accesses:
            out.append(_access_out(a, await session.get(PortalAccount, a.account_id)))
        notes = await engagement_notes(session, eng.id)
        return {
            "engagement_id": eng.id,
            "auditor_contact_ids": eng.auditor_contact_ids,
            "access": out,
            "notes": [note_out(n) for n in notes],
        }


@router.post(
    "/audit-engagements/{engagement_id}/board-access",
    status_code=201,
    summary="Beiratszugang zum Prüfauftrag anlegen (Einladung wie bei Eigentümern)",
)
async def create_board_access(
    engagement_id: uuid.UUID,
    body: BoardAccessIn,
    request: Request,
    principal: TenantPrincipal = Depends(GRANT),
) -> dict[str, Any]:
    from mhvp.portal.routers import provision_account

    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, engagement_id)
        if str(body.contact_id) not in eng.auditor_contact_ids:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Kontakt ist nicht als Prüfer des Prüfauftrags eingetragen.",
            )
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == body.contact_id)
        )
        if account is not None and await _is_staff(session, account.id):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Ein interner Mitarbeiterzugang erhält keinen Beiratszugang.",
            )
        existing = (
            await session.scalar(
                select(BoardAccess.id).where(
                    BoardAccess.engagement_id == eng.id,
                    BoardAccess.account_id == account.id,
                    BoardAccess.revoked_at.is_(None),
                )
            )
            if account is not None
            else None
        )
        if existing is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beiratszugang besteht bereits.")
        existing_account_id = account.id if account is not None else None
    invitation_token: str | None = None
    if existing_account_id is None:
        if not body.email or not body.display_name:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Für einen neuen Portalzugang sind E-Mail und Anzeigename erforderlich.",
            )
        created = await provision_account(
            request,
            principal,
            contact_id=body.contact_id,
            email=body.email,
            display_name=body.display_name,
        )
        invitation_token = str(created["invitation_token"])
        account_id = uuid.UUID(str(created["id"]))
    else:
        account_id = existing_account_id
    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, engagement_id)
        row = BoardAccess(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            engagement_id=eng.id,
            account_id=account_id,
            contact_id=body.contact_id,
            legal_entity_id=eng.legal_entity_id,
        )
        session.add(row)
        # Role board in the access matrix (6.9.6): scope is the engagement only, right comment
        # (notes and questions); survives a resync (MANUAL_BASES in mhvp.portal.access).
        session.add(
            AccessGrant(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                account_id=account_id,
                scope_type="audit_engagement",
                scope_id=eng.id,
                right="comment",
                legal_basis=BOARD_LEGAL_BASIS,
                role=BOARD_ROLE,
                valid_from=local_today(),
                valid_to=None,
            )
        )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="board_access.created",
            entity_type="audit_engagement",
            entity_id=eng.id,
            actor_user_id=principal.user_id,
            payload={"account_id": str(account_id), "contact_id": str(body.contact_id)},
        )
        return {
            "id": row.id,
            "account_id": account_id,
            "contact_id": body.contact_id,
            "invitation_token": invitation_token,
        }


async def _is_staff(session: AsyncSession, account_id: uuid.UUID) -> bool:
    from mhvp.portal import access

    return await access.has_staff_grant(session, account_id)


@router.post(
    "/audit-engagements/{engagement_id}/board-access/{access_id}/revoke",
    summary="Beiratszugang beenden",
)
async def revoke_board_access(
    engagement_id: uuid.UUID,
    access_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(GRANT),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(BoardAccess, access_id)
        if row is None or row.engagement_id != engagement_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            row.revoked_by = principal.user_id
            grants = await session.scalars(
                select(AccessGrant).where(
                    AccessGrant.account_id == row.account_id,
                    AccessGrant.legal_basis == BOARD_LEGAL_BASIS,
                    AccessGrant.scope_id == engagement_id,
                    AccessGrant.valid_to.is_(None),
                )
            )
            for g in grants:
                g.valid_to = local_today()
            await session.flush()
        return _access_out(row, await session.get(PortalAccount, row.account_id))


@router.post(
    "/audit-engagements/{engagement_id}/notes/{note_id}/answer",
    summary="Rückfrage des Beirats beantworten (PÜ08)",
)
async def answer_board_note(
    engagement_id: uuid.UUID,
    note_id: uuid.UUID,
    body: BoardAnswerIn,
    request: Request,
    principal: TenantPrincipal = Depends(ANSWER),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        note = await session.get(BoardAuditNote, note_id)
        if note is None or note.engagement_id != engagement_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if note.kind == "answered":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Rückfrage ist bereits beantwortet.")
        await answer_note(
            session,
            note=note,
            answer=body.answer,
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
        )
        return note_out(note)
