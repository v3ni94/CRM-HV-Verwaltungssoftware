"""Number range checks of the chart of accounts (7.2, GAH-105)."""

import uuid
from typing import Any

BANK_RANGE = ("001200", "001999")
BANK_RANGE_CATEGORIES = frozenset({"bank", "cash", "technical", "transit"})


def account_range_problem(
    number: str, category: Any, property_bank_account_id: uuid.UUID | None
) -> str | None:
    """GAH-105 (7.2): the bank and cash range 001200 to 001999 holds only bank or cash
    accounts, and only bank or cash accounts may link a property bank account (B09,
    liquidity). The default chart (Immoware24 convention, annex A.1) also keeps technical
    and transit accounts there (001400, Geldtransit), so these stay allowed in the range;
    cost, revenue, debtor, creditor, reserve, loan, tax and opening balance are refused.
    Other ranges of 7.2 are a migration convention and stay unchecked."""
    cat = getattr(category, "value", category)
    bank_like = cat in ("bank", "cash")
    in_range = BANK_RANGE[0] <= number <= BANK_RANGE[1]
    if in_range and cat not in BANK_RANGE_CATEGORIES:
        return (
            f"Kontonummer {number} liegt im Bereich Bank und Kasse (001200 bis 001999), "
            f"die Kategorie {cat} ist dort nicht zulässig "
            "(erlaubt: bank, cash, technical, transit)."
        )
    if property_bank_account_id is not None and not bank_like:
        return (
            f"Eine Bankkontoverknüpfung ist nur an Konten der Kategorie bank oder cash "
            f"zulässig, nicht an {cat}."
        )
    return None
