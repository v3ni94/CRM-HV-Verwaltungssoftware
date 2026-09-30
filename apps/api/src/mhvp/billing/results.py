"""Results per contract of a rental operating cost statement (M17-01 to M17-06).

* Access per tenant (6.5 ``statement_result``, A04): delivery method, day of access and
  evidence per contract. Creation or calculation is never the access (D23).
* Result entries (M17-01, A01): Forderung for an additional payment, Gutschrift for a credit,
  written as **draft** journal entries (kind ``statement_result``, source ``statement``) only
  from status ``due`` and only with G3 (router). Posting the drafts is the normal accounting
  path with its own gates (G1); ``posted`` needs every draft to be posted. Nothing here posts.
* Difference report between a version and the version it supersedes (A01, M17-05).
* Belegeinsicht (PÜ11, M17-06): request, provision, redaction note, objection. The objection
  deadline is shown as orientation only (twelve months after access, § 556 Abs. 3 BGB, R06);
  it is to be verified per case and is no automated legal consequence.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.models import Statement, StatementResult, StatementSnapshot
from mhvp.core.problems import ErrorCodes, ProblemError

ZERO = Decimal("0.00")
RESULT_PAYMENT_TYPE = "statement_result"


def snapshot_rows(snapshot: StatementSnapshot | None) -> list[dict[str, Any]]:
    return list((snapshot.results if snapshot else {}).get("results", []))


def add_months(day: date, months: int) -> date:
    """Same day ``months`` later; the last day of a shorter month when it does not exist."""
    import calendar

    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def objection_deadline_orientation(delivered_at: date | None) -> date | None:
    """Orientation only (R06): end of the twelfth month after access. To be verified."""
    return add_months(delivered_at, 12) if delivered_at else None


async def result_rows(session: AsyncSession, statement: Statement) -> dict[str, StatementResult]:
    rows = (
        await session.scalars(
            select(StatementResult).where(StatementResult.statement_id == statement.id)
        )
    ).all()
    return {str(r.contract_id): r for r in rows}


def diff(old: StatementSnapshot | None, new: StatementSnapshot | None) -> dict[str, Any]:
    """Difference per contract and per position between two snapshots (A01, M17-05)."""
    before = {str(r["contract_id"]): r for r in snapshot_rows(old)}
    after = {str(r["contract_id"]): r for r in snapshot_rows(new)}
    tenants = []
    for cid in sorted(set(before) | set(after)):
        a, b = before.get(cid), after.get(cid)
        entry: dict[str, Any] = {
            "contract_id": cid,
            "unit_number": (b or a or {}).get("unit_number"),
            "status": "added" if a is None else "removed" if b is None else "changed",
        }
        for field in ("costs", "advances_paid", "balance"):
            old_v = Decimal(a[field]) if a else ZERO
            new_v = Decimal(b[field]) if b else ZERO
            entry[field] = {"old": str(old_v), "new": str(new_v), "delta": str(new_v - old_v)}
        if (
            a is not None
            and b is not None
            and all(entry[f]["delta"] == "0.00" for f in ("costs", "advances_paid", "balance"))
        ):
            entry["status"] = "unchanged"
        tenants.append(entry)

    def _positions(snap: StatementSnapshot | None) -> dict[str, str]:
        out: dict[str, Decimal] = {}
        for p in (snap.inputs if snap else {}).get("positions", []):
            out[p["label"]] = out.get(p["label"], ZERO) + Decimal(p["amount"])
        return {k: str(v) for k, v in out.items()}

    pos_old, pos_new = _positions(old), _positions(new)
    positions = [
        {
            "label": label,
            "old": pos_old.get(label),
            "new": pos_new.get(label),
            "delta": str(Decimal(pos_new.get(label, "0")) - Decimal(pos_old.get(label, "0"))),
        }
        for label in sorted(set(pos_old) | set(pos_new))
    ]
    return {
        "old_hash": old.hash if old else None,
        "new_hash": new.hash if new else None,
        "tenants": tenants,
        "positions": [p for p in positions if p["delta"] != "0.00" or p["old"] != p["new"]],
    }


async def create_result_drafts(
    session: AsyncSession,
    statement: Statement,
    snapshot: StatementSnapshot,
    *,
    booking_date: date,
    due_date: date,
    user_id: uuid.UUID | None,
) -> list[str]:
    """Draft entries of the result per contract (M17-01). Idempotent per statement and
    contract (``idempotency_key``); a contract with balance zero gets no entry. Late claims
    stay refused (A04): ``check_issue`` already refused issuing, this check repeats it."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import (
        EntryKind,
        EntrySource,
        JournalEntry,
        Ledger,
        LedgerAccount,
        PaymentTypeAccount,
    )
    from mhvp.contracts.models import Contract, DebtorAccountReservation

    ledger = await session.get(Ledger, statement.ledger_id)
    mapping = await session.scalar(
        select(PaymentTypeAccount).where(
            PaymentTypeAccount.ledger_id == statement.ledger_id,
            PaymentTypeAccount.payment_type_code == RESULT_PAYMENT_TYPE,
        )
    )
    if ledger is None or mapping is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Konto für Abrechnungsergebnisse (Zahlungsart statement_result) fehlt.",
        )
    await acc.sync_debtor_accounts(session, ledger)
    ids: list[str] = list(statement.result_entry_ids)
    for row in snapshot_rows(snapshot):
        balance = Decimal(row["balance"])
        if balance == 0:
            continue
        if balance > 0 and row.get("late_claim_blocked") and not statement.deadline_exception:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Einheit {row['unit_number']}: Nachforderung nach Fristablauf gesperrt.",
            )
        key = f"rent-statement:{statement.id}:{row['contract_id']}"
        existing = await session.scalar(
            select(JournalEntry).where(
                JournalEntry.ledger_id == ledger.id, JournalEntry.idempotency_key == key
            )
        )
        if existing is not None:
            continue
        contract = await session.get(Contract, uuid.UUID(str(row["contract_id"])))
        reservation = (
            await session.get(DebtorAccountReservation, contract.debtor_account_id)
            if contract
            else None
        )
        debtor = (
            await session.scalar(
                select(LedgerAccount).where(
                    LedgerAccount.ledger_id == ledger.id,
                    LedgerAccount.number == reservation.number,
                )
            )
            if reservation
            else None
        )
        if contract is None or debtor is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail=f"Kein Debitor für Einheit {row['unit_number']}."
            )
        value = abs(balance)
        if balance > 0:  # Forderung: debtor debit, result account credit
            lines = [
                acc.LineIn(debtor.id, value, ZERO),
                acc.LineIn(mapping.account_id, ZERO, value),
            ]
            label = "Nachzahlung"
        else:  # Gutschrift: debtor credit, result account debit
            lines = [
                acc.LineIn(debtor.id, ZERO, value),
                acc.LineIn(mapping.account_id, value, ZERO),
            ]
            label = "Guthaben"
        entry = JournalEntry(
            tenant_id=statement.tenant_id,
            created_by=user_id,
            ledger_id=ledger.id,
            booking_date=booking_date,
            due_date=due_date,
            accrual_date=statement.period_to,
            text=(
                f"Betriebskostenabrechnung {statement.period_from.year} {label} "
                f"Einheit {row['unit_number']}"
            )[:500],
            kind=EntryKind.STATEMENT_RESULT,
            contract_id=contract.id,
            source=EntrySource.STATEMENT,
            idempotency_key=key,
        )
        await acc.write_draft(session, ledger, entry, lines, [])
        ids.append(str(entry.id))
    statement.result_entry_ids = ids
    await session.flush()
    return ids


async def check_result_entries_posted(session: AsyncSession, statement: Statement) -> None:
    """``posted`` only when the result entries exist and every one is posted (M17-01)."""
    from mhvp.accounting.models import EntryStatus, JournalEntry

    snapshot = (
        await session.get(StatementSnapshot, statement.snapshot_id)
        if statement.snapshot_id
        else None
    )
    needed = [r for r in snapshot_rows(snapshot) if Decimal(r["balance"]) != 0]
    if needed and not statement.result_entry_ids:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Ergebnisbuchungen fehlen: erst die Entwürfe erzeugen und buchen (M17-01).",
        )
    for entry_id in statement.result_entry_ids:
        entry = await session.get(JournalEntry, uuid.UUID(entry_id))
        if entry is None or entry.status is not EntryStatus.POSTED:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Nicht alle Ergebnisbuchungen sind gebucht (Entwurf offen, M17-01).",
            )
