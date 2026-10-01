"""Advance proposals from a statement snapshot and the tenant's surcharge setting (M17-03).

Proposals are drafts with a confirmation step by a second person (``accounting:approve``);
nothing here changes contract payments (§ 560 BGB, separate step, G3).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import advance_rule as rule
from mhvp.billing.models import Statement, StatementSnapshot
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/billing/advance-rule", tags=["Abrechnung"])
# M2-02/S16-02: statements outside the membership's property assignment answer 404.
STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
statement_router = APIRouter(
    prefix="/statements", tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)]
)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")


class AdvanceRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surcharge_percent: Decimal = Field(ge=0, le=100, decimal_places=2)


class ProposalsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Overrides the tenant setting for this run only; None uses the setting (default 0).
    surcharge_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)


class AdvanceDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


def _rule_out(row: rule.AdvanceRuleSetting) -> dict[str, Any]:
    return {
        "surcharge_percent": str(Decimal(row.surcharge_percent).quantize(rule.CENT)),
        "months": rule.MONTHS,
        "rule_version": rule.RULE_VERSION,
        "formula": "Kostenanteil des Abrechnungszeitraums geteilt durch zwölf, zuzüglich "
        "Sicherheitsaufschlag in Prozent, kaufmännisch auf den Cent gerundet (Entwurf, M17-03).",
    }


@router.get("", summary="Vorschussregel des Mandanten (Sicherheitsaufschlag, Standard 0)")
async def get_rule(request: Request, principal: TenantPrincipal = Depends(READ)) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _rule_out(await rule.setting(session, principal.tenant_id))


@router.put("", summary="Sicherheitsaufschlag der Vorschussregel setzen")
async def put_rule(
    body: AdvanceRuleIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await rule.setting(session, principal.tenant_id)
        row.surcharge_percent = body.surcharge_percent
        row.updated_by = principal.user_id
        await session.flush()
        return _rule_out(row)


async def _statement(session: AsyncSession, statement_id: uuid.UUID) -> Statement:
    st = await session.get(Statement, statement_id)
    if st is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return st


@statement_router.get(
    "/{statement_id}/advance-proposals",
    summary="Vorschläge neuer Vorauszahlungen (Entwurf)",
    dependencies=[Depends(strict_query)],
)
async def list_proposals(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        rows = (
            await session.scalars(
                select(rule.AdvanceProposal)
                .where(rule.AdvanceProposal.statement_id == st.id)
                .order_by(rule.AdvanceProposal.unit_number, rule.AdvanceProposal.created_at)
            )
        ).all()
        return [rule.out(r) for r in rows]


@statement_router.post(
    "/{statement_id}/advance-proposals",
    status_code=201,
    summary="Vorschläge neuer Vorauszahlungen aus dem Abrechnungsergebnis ermitteln",
)
async def create_proposals(
    statement_id: uuid.UUID,
    request: Request,
    body: ProposalsIn | None = None,
    principal: TenantPrincipal = Depends(CREATE),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
        if snap is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Kein Ergebnis-Snapshot: die Abrechnung ist noch nicht berechnet.",
            )
        rows = await rule.create_proposals(
            session,
            st,
            snap,
            surcharge_percent=body.surcharge_percent if body else None,
            user_id=principal.user_id,
        )
        return [rule.out(r) for r in rows]


async def _decide(
    request: Request,
    principal: TenantPrincipal,
    statement_id: uuid.UUID,
    proposal_id: uuid.UUID,
    status: rule.ProposalStatus,
    note: str | None,
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(rule.AdvanceProposal, proposal_id, with_for_update=True)
        if row is None or row.statement_id != statement_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != rule.ProposalStatus.PROPOSED.value:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Vorschlag ist bereits entschieden.")
        if row.created_by is not None and row.created_by == principal.user_id:
            raise ProblemError(
                ErrorCodes.FORBIDDEN,
                detail="Bestätigung durch eine zweite Person, nicht durch den Ersteller.",
            )
        st = await _statement(session, statement_id)
        snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
        if snap is None or snap.hash != row.snapshot_hash:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Der Vorschlag gehört zu einem älteren Ergebnis; Vorschläge neu ermitteln.",
            )
        row.status = status.value
        row.note = note or row.note
        row.decided_by = principal.user_id
        row.decided_at = datetime.now(UTC)
        row.updated_by = principal.user_id
        await session.flush()
        return rule.out(row)


@statement_router.post(
    "/{statement_id}/advance-proposals/{proposal_id}/confirm",
    summary="Vorschlag bestätigen (zweite Person; keine Änderung der Vertragszahlungen)",
)
async def confirm(
    statement_id: uuid.UUID,
    proposal_id: uuid.UUID,
    request: Request,
    body: AdvanceDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    return await _decide(
        request,
        principal,
        statement_id,
        proposal_id,
        rule.ProposalStatus.CONFIRMED,
        body.note if body else None,
    )


@statement_router.post(
    "/{statement_id}/advance-proposals/{proposal_id}/reject", summary="Vorschlag verwerfen"
)
async def reject(
    statement_id: uuid.UUID,
    proposal_id: uuid.UUID,
    request: Request,
    body: AdvanceDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    return await _decide(
        request,
        principal,
        statement_id,
        proposal_id,
        rule.ProposalStatus.REJECTED,
        body.note if body else None,
    )
