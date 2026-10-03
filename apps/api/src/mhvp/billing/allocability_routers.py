"""BetrKV catalogue, account mapping and allocability preview (M17-01).

``/billing/operating-cost-types`` lists the system catalogue; the mapping of a cost account
to a catalogue position is a human decision per ledger account (``PUT .../accounts/{id}``).
``/statements/{id}/allocability-check`` previews the review hints of a statement draft without
calculating anything; the same hints are stored in the snapshot on calculation.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.audit_events import record_change
from mhvp.accounting.audit_events import snap as audit_snap
from mhvp.accounting.models import AccountCategory, ChartTemplate, LedgerAccount
from mhvp.billing import betrkv
from mhvp.billing.models import Statement, StatementCostItem
from mhvp.billing.raw_responses import (
    BillingAllocabilityListAccountsOutItem,
    BillingAllocabilityListCatalogueOut,
    BillingAllocabilityMapAccountOut,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/billing/operating-cost-types", tags=["Abrechnung"])
# M2-02/S16-02: statements outside the membership's property assignment answer 404.
STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
statement_router = APIRouter(
    prefix="/statements", tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)]
)
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")


class CostAccountMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operating_cost_type: str | None = None


def _account_out(account: LedgerAccount, suggestion: str | None) -> dict[str, Any]:
    cost_type = betrkv.get(account.operating_cost_type)
    return {
        "account_id": account.id,
        "ledger_id": account.ledger_id,
        "number": account.number,
        "name": account.name,
        "allocation_category": account.allocation_category.value,
        "operating_cost_type": account.operating_cost_type,
        "operating_cost_type_label": cost_type.label if cost_type else None,
        "allocability": cost_type.allocability.value if cost_type else None,
        "suggested_operating_cost_type": (
            suggestion if account.operating_cost_type is None else None
        ),
    }


async def _suggestions(session: AsyncSession) -> dict[str, str | None]:
    """Suggestions from the template rows' ``betrkv_reference`` (M10-02), by account number."""
    out: dict[str, str | None] = {}
    for template in (await session.scalars(select(ChartTemplate))).all():
        for row in template.accounts:
            number = str(row.get("number", ""))
            if number and number not in out:
                out[number] = betrkv.suggest_from_reference(row.get("betrkv_reference"))
    return out


@router.get(
    "",
    summary="Systemkatalog der Betriebskostenarten nach BetrKV (Entwurf)",
    response_model=BillingAllocabilityListCatalogueOut,
    dependencies=[Depends(strict_query)],
)
async def list_catalogue(principal: TenantPrincipal = Depends(READ)) -> dict[str, Any]:
    return {"source": betrkv.SOURCE, "items": betrkv.catalogue()}


@router.get(
    "/accounts",
    summary="Kostenkonten eines Buchungskreises mit Katalogzuordnung",
    dependencies=[Depends(strict_query)],
    response_model=list[BillingAllocabilityListAccountsOutItem],
)
async def list_accounts(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        accounts = (
            await session.scalars(
                select(LedgerAccount)
                .where(
                    LedgerAccount.ledger_id == ledger_id,
                    LedgerAccount.category == AccountCategory.COST,
                )
                .order_by(LedgerAccount.number)
            )
        ).all()
        suggestions = await _suggestions(session)
        return [_account_out(a, suggestions.get(a.number)) for a in accounts]


@router.put(
    "/accounts/{account_id}",
    summary="Kostenkonto einer Katalogposition zuordnen",
    response_model=BillingAllocabilityMapAccountOut,
)
async def map_account(
    account_id: uuid.UUID,
    body: CostAccountMappingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        account = await session.get(LedgerAccount, account_id, with_for_update=True)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if account.category is not AccountCategory.COST:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Nur Kostenkonten erhalten eine Betriebskostenart."
            )
        if body.operating_cost_type is not None and betrkv.get(body.operating_cost_type) is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Unbekannte Katalogposition {body.operating_cost_type}.",
            )
        before = audit_snap(account, ("operating_cost_type",))
        account.operating_cost_type = body.operating_cost_type
        account.updated_by = principal.user_id
        await session.flush()
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            type="ledger_account.operating_cost_type_changed",
            entity_type="ledger_account",
            entity_id=account.id,
            before=before,
            after=audit_snap(account, ("operating_cost_type",)),
        )
        return _account_out(account, None)


async def hints_for_statement(session: AsyncSession, statement: Statement) -> list[dict[str, str]]:
    items = (
        await session.scalars(
            select(StatementCostItem)
            .where(StatementCostItem.statement_id == statement.id)
            .order_by(StatementCostItem.created_at)
        )
    ).all()
    hints: list[dict[str, str]] = []
    for item in items:
        account = await session.get(LedgerAccount, item.account_id) if item.account_id else None
        hints.extend(
            betrkv.position_hints(
                label=item.label,
                type_code=account.operating_cost_type if account else None,
                allocation_category=account.allocation_category.value if account else None,
            )
        )
    return hints


@statement_router.get(
    "/{statement_id}/allocability-check",
    summary="Prüfhinweise zur Umlagefähigkeit der Kostenpositionen (Vorschau, keine Sperre)",
)
async def allocability_check(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        statement = await session.get(Statement, statement_id)
        if statement is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        hints = await hints_for_statement(session, statement)
        return {
            "statement_id": statement.id,
            "source": betrkv.SOURCE,
            "hints": hints,
            "warnings": sum(1 for h in hints if h["level"] == "warning"),
        }
