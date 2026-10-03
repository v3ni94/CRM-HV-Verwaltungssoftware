"""Stored tenant switches of the bank reconciliation (AO02, GAK-107, GAK-108).

Two keys in ``tenant_settings.sources`` (no migration, same pattern as
``contacts.address_history``), each with the previous behaviour as default:

* ``banking.clearing_account_number``: tenant standard of the clearing account, an account
  number of the tenant's chart of accounts with category ``transit`` or ``technical``. Default
  none: an overpayment remainder spread over several personal accounts still needs an explicit
  counter account (previous behaviour). When set, such a remainder goes to the account with
  this number in the ledger of the transaction; if the ledger has no such account the previous
  rule applies. A remainder on one personal account stays credit of that debtor (D07).
* ``banking.reconciliation_basis``: ``booking_date`` (default) or ``bank_date``, the stored
  default of ``GET /banking/accounts/{id}/reconciliation``; the query parameter ``basis``
  stays as an explicit override.

Nothing is booked by switching; the switches only change drafts and the cut-off of a read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import AccountCategory
from mhvp.core.problems import ErrorCodes, ProblemError

CLEARING_KEY = "banking.clearing_account_number"
BASIS_KEY = "banking.reconciliation_basis"
BASES = ("booking_date", "bank_date")
DEFAULT_BASIS = "booking_date"
CLEARING_CATEGORIES = (AccountCategory.TRANSIT.value, AccountCategory.TECHNICAL.value)


@dataclass(frozen=True)
class ReconciliationSettings:
    clearing_account_number: str | None = None
    reconciliation_basis: str = DEFAULT_BASIS


def from_sources(sources: dict[str, Any] | None) -> ReconciliationSettings:
    src = sources or {}
    number = src.get(CLEARING_KEY)
    basis = src.get(BASIS_KEY)
    return ReconciliationSettings(
        clearing_account_number=number if isinstance(number, str) and number else None,
        reconciliation_basis=basis if basis in BASES else DEFAULT_BASIS,
    )


async def load(session: AsyncSession) -> ReconciliationSettings:
    """Switches of the tenant of the session (RLS scoped); defaults without a row."""
    from mhvp.platform.models import TenantSettings

    return from_sources(await session.scalar(select(TenantSettings.sources)))


async def chart_accounts(session: AsyncSession) -> list[dict[str, Any]]:
    """Clearing account candidates of the tenant's charts of accounts (transit, technical),
    released charts first, unique by number."""
    from mhvp.accounting.models import ChartTemplate

    templates = (
        await session.scalars(
            select(ChartTemplate).order_by(
                ChartTemplate.released.desc(), ChartTemplate.version.desc()
            )
        )
    ).all()
    seen: dict[str, dict[str, Any]] = {}
    for template in templates:
        for row in template.accounts or []:
            number = str(row.get("number") or "")
            if not number or number in seen or row.get("category") not in CLEARING_CATEGORIES:
                continue
            seen[number] = {
                "number": number,
                "name": str(row.get("name") or ""),
                "category": str(row.get("category")),
            }
    return sorted(seen.values(), key=lambda r: r["number"])


async def validate_clearing_number(session: AsyncSession, number: str) -> None:
    """422 unless the number is a transit or technical account of the tenant's charts."""
    if number not in {row["number"] for row in await chart_accounts(session)}:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Konto {number} ist im Kontenrahmen nicht als Klärungs- oder Transitkonto "
                "(Kategorie transit oder technical) vorhanden."
            ),
        )
