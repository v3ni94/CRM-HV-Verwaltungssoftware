"""Migrated journal as training base for posting proposals (M8-05, 13.1).

The Immoware24 journal taken over by the migration (``migrated_journal_entry`` and
``migrated_journal_line``) serves as read only few shot examples for ``propose_posting``: how
comparable entries were booked in the old system (account numbers, debit and credit). Nothing
is written and nothing is booked; the examples only steer the proposal, which a person still
confirms (rule 0.1.6). Selection is deterministic (keyword match on the entry text, reconciled
entries first, newest first), texts are masked like every provider input.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.masking import mask_personal_data
from mhvp.imports.migration_models import MigratedJournalEntry, MigratedJournalLine

MAX_KEYWORDS = 6
MIN_KEYWORD_CHARS = 4
MAX_LINES_PER_ENTRY = 6
SOURCE_LABEL = "migrationsjournal"
_WORD = re.compile(rf"[A-Za-zÄÖÜäöüß]{{{MIN_KEYWORD_CHARS},}}")


def keywords(text: str) -> list[str]:
    """Distinct lower case words of the input, longest first, at most ``MAX_KEYWORDS``."""
    seen: dict[str, None] = {}
    for word in _WORD.findall(text):
        seen.setdefault(word.lower(), None)
    return sorted(seen, key=lambda w: (-len(w), w))[:MAX_KEYWORDS]


async def journal_examples(
    session: AsyncSession, text: str, *, limit: int = 3
) -> list[dict[str, Any]]:
    """Up to ``limit`` few shot examples from the migrated journal, or an empty list."""
    words = keywords(mask_personal_data(text))
    if not words or limit <= 0:
        return []
    entries = (
        await session.scalars(
            select(MigratedJournalEntry)
            .where(or_(*[MigratedJournalEntry.text.ilike(f"%{w}%") for w in words]))
            .order_by(
                MigratedJournalEntry.reconciled.desc(),
                MigratedJournalEntry.booking_date.desc(),
                MigratedJournalEntry.id,
            )
            .limit(limit)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for entry in entries:
        lines = (
            await session.scalars(
                select(MigratedJournalLine)
                .where(MigratedJournalLine.entry_id == entry.id)
                .order_by(MigratedJournalLine.line_no)
                .limit(MAX_LINES_PER_ENTRY)
            )
        ).all()
        out.append(
            {
                "merkmale": {"text": mask_personal_data(entry.text), "quelle": SOURCE_LABEL},
                "bestaetigt": {
                    "buchungszeilen": [
                        {
                            "konto": ln.account_number,
                            "soll": str(ln.debit),
                            "haben": str(ln.credit),
                        }
                        for ln in lines
                    ]
                },
            }
        )
    return out


BANK_SOURCE_LABEL = "historische_bankzuordnung"


async def bank_examples(
    session: AsyncSession, text: str, *, limit: int = 3
) -> list[dict[str, Any]]:
    """Historical bank assignments as learning examples (M8-05, 13.1): a historical
    ``bank_transaction`` linked by the migration (``migrated_bank_link``) to the Immoware24
    journal entry it was booked in. Read only few shot examples for ``propose_posting``: the
    masked purpose, the direction and a coarse amount class (never the exact amount, a name,
    an IBAN or an id) with the account lines of the old booking. Nothing is written."""
    from mhvp.banking.ai_posting import amount_class
    from mhvp.banking.models import BankTransaction
    from mhvp.imports.history_models import MigratedBankLink

    words = keywords(mask_personal_data(text))
    if not words or limit <= 0:
        return []
    rows = (
        await session.execute(
            select(BankTransaction.purpose, BankTransaction.amount, MigratedJournalEntry.id)
            .join(MigratedBankLink, MigratedBankLink.bank_transaction_id == BankTransaction.id)
            .join(
                MigratedJournalEntry, MigratedJournalEntry.id == MigratedBankLink.journal_entry_id
            )
            .where(or_(*[BankTransaction.purpose.ilike(f"%{w}%") for w in words]))
            .order_by(BankTransaction.booking_date.desc(), BankTransaction.id)
            .limit(limit)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for purpose, amount, entry_id in rows:
        lines = (
            await session.scalars(
                select(MigratedJournalLine)
                .where(MigratedJournalLine.entry_id == entry_id)
                .order_by(MigratedJournalLine.line_no)
                .limit(MAX_LINES_PER_ENTRY)
            )
        ).all()
        out.append(
            {
                "merkmale": {
                    "verwendungszweck": mask_personal_data(purpose or "")[:300],
                    "richtung": "eingang" if amount > 0 else "ausgang",
                    "betragsklasse": amount_class(amount),
                    "quelle": BANK_SOURCE_LABEL,
                },
                "bestaetigt": {
                    "buchungszeilen": [
                        {"konto": ln.account_number, "soll": str(ln.debit), "haben": str(ln.credit)}
                        for ln in lines
                    ]
                },
            }
        )
    return out
