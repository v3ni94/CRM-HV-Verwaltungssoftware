"""Property assignment of the membership in the WEG routers (M2-02/S16-02, Q13-01).

Path ids of WEG records resolve to the property through the legal entity (GdWE) or the
ledger; outside ``Membership.property_ids`` the endpoint answers 404 before it runs.
Produktschutz, not a legal duty; next to tenant RLS and the legal entity scope (A37).
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from sqlalchemy import select

from mhvp.accounting.models import Ledger
from mhvp.core.auth.principal import get_principal
from mhvp.core.auth.scope import (
    allowed_legal_entity_ids,
    ensure_legal_entity_allowed,
    property_column_guard,
)
from mhvp.hoa.models import (
    AuditEngagement,
    EconomicPlan,
    HoaAssetReport,
    HoaInsuranceClaim,
    HoaLoan,
    HoaMeasure,
    HoaStatement,
    Meeting,
    Resolution,
    SpecialLevy,
)
from mhvp.properties.models import LegalEntity

HOA_COLUMNS: dict[str, Any] = {
    # query parameters of the lists "einer GdWE" / "eines Buchungskreises"
    "legal_entity_id": LegalEntity.property_id,
    "ledger_id": Ledger.property_id,
    "statement_id": HoaStatement.ledger_id,
    "plan_id": EconomicPlan.ledger_id,
    "meeting_id": Meeting.legal_entity_id,
    "levy_id": SpecialLevy.legal_entity_id,
    "loan_id": HoaLoan.legal_entity_id,
    "measure_id": HoaMeasure.legal_entity_id,
    "claim_id": HoaInsuranceClaim.legal_entity_id,
    "resolution_id": Resolution.legal_entity_id,
    "engagement_id": AuditEngagement.legal_entity_id,
    "audit_id": AuditEngagement.legal_entity_id,
}

# ``report_id`` names an asset report in assets.py and an audit report in board.py; the audit
# report carries no legal entity, board.py therefore guards only the other ids.


def legal_entity_column_guard(columns: dict[str, Any]) -> Callable[[Request], Awaitable[None]]:
    """Router dependency (A37, docs/rules/M18-05-steuerberaterzugang.md, review W79): for a
    scoped membership (tax advisor) a ``legal_entity_id`` path or query parameter, or the id of
    a WEG record carrying a ``legal_entity_id`` column, outside ``Membership.legal_entity_ids``
    answers 404 before the endpoint runs. The tax advisor holds ``accounting:read`` and so
    reaches the WEG lists (resolutions, meetings, levies, loans); before this guard those lists
    answered for every community of the tenant. Unknown ids and unparsable values pass through
    (the endpoint keeps its own 404 or 422); unrestricted members cost no query."""

    async def dependency(request: Request) -> None:
        params = {**request.query_params, **request.path_params}
        names = [name for name in columns if name in params]
        if not names:
            return
        principal = await get_principal(request)
        if principal.tenant_id is None or allowed_legal_entity_ids(principal) is None:
            return
        from mhvp.core.auth.principal import tenant_tx

        async with tenant_tx(request, principal) as session:
            for name in names:
                try:
                    value = uuid.UUID(str(params[name]))
                except ValueError:
                    continue
                column = columns[name]
                if column is LegalEntity.property_id:
                    ensure_legal_entity_allowed(principal, value)
                    continue
                found = (
                    await session.execute(select(column).where(column.class_.id == value))
                ).first()
                if found is not None and found[0] is not None:
                    ensure_legal_entity_allowed(principal, found[0])

    return dependency


_LE_COLUMNS: dict[str, Any] = {
    "legal_entity_id": LegalEntity.property_id,  # marker: the value is the legal entity itself
    "ledger_id": Ledger.legal_entity_id,
    **{
        name: column
        for name, column in HOA_COLUMNS.items()
        if name not in ("legal_entity_id", "ledger_id", "statement_id", "plan_id")
    },
}

_property_guard = property_column_guard(
    {**HOA_COLUMNS, "report_id": HoaAssetReport.legal_entity_id}
)
_board_property_guard = property_column_guard(HOA_COLUMNS)
_entity_guard = legal_entity_column_guard(
    {**_LE_COLUMNS, "report_id": HoaAssetReport.legal_entity_id}
)
_board_entity_guard = legal_entity_column_guard(_LE_COLUMNS)


async def HOA_GUARD(request: Request) -> None:  # noqa: N802 - kept name of the router guard
    await _property_guard(request)
    await _entity_guard(request)


async def HOA_BOARD_GUARD(request: Request) -> None:  # noqa: N802
    await _board_property_guard(request)
    await _board_entity_guard(request)
