"""Payables from statement credits (P04-04, Q01-01, M15-07, AE22, rule AE22).

Sources (candidates, read only):

* ``rent_statement``: posted result entry of a rental operating cost statement (idempotency key
  ``rent-statement:<statement>:<contract>``, listed in ``statement.result_entry_ids``) that
  credits the debtor account of the contract (Guthaben). Offset entries of the open advance
  switch (``rent-statement-offset:``) are no credits to pay out.
* ``owner_statement``: owner statement from status ``issued`` with a positive payout amount
  (``owner_statement_pdf.settlement``); the amount may be reduced, never raised.
* ``deposit_settlement``: released deposit settlement (G3) with a positive payout amount.

Flow: proposal (``accounting:create``), release by a second person (``accounting:approve``,
four eyes switch, G3), then a payment order without invoice from the payable (G2 and G3, two
approvals on the order, file behind G2). The booking rule variant is the tenant switch of
``credit_payable_setting`` (default ``off``: nothing is created). Withdrawal (Storno path):
before release the proposal is withdrawn; a reclass draft is discarded; a posted reclass entry
is reversed on the regular reversal path (B03, G1); a payable of the subledger variant is closed
only by reversing the statement result entry (correction of the statement), which settles the
item automatically. Paid or ordered payables are never withdrawn here (0.1.7).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.credit_payable_models import (
    MODES,
    PAYOUT_REASON,
    CreditPayable,
    CreditPayableSetting,
)
from mhvp.accounting.models import (
    AccountCategory,
    EntryKind,
    EntrySource,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemKind,
    OpenItemSettlement,
    ReversalReason,
)
from mhvp.accounting.write_offs import not_written_off_as_of
from mhvp.core.clock import local_today
from mhvp.core.problems import ErrorCodes, ProblemError

ZERO = Decimal("0.00")
RENT_KEY = "rent-statement:"
SOURCE_LABELS = {
    "rent_statement": "Guthaben aus Betriebskostenabrechnung",
    "owner_statement": "Auszahlung aus Eigentümerabrechnung",
    "deposit_settlement": "Kautionsrückzahlung",
}
ACTIVE_ORDER = ("draft", "approved", "exported", "submitted", "accepted_by_bank")


@dataclass(frozen=True)
class Candidate:
    source_type: str
    source_id: uuid.UUID
    contract_id: uuid.UUID | None
    ledger_id: uuid.UUID
    amount: Decimal
    label: str
    reference_date: date | None
    source_entry_id: uuid.UUID | None = None
    debtor_account_id: uuid.UUID | None = None

    @property
    def key(self) -> str:
        return source_key(self.source_type, self.source_id, self.contract_id)

    def as_json(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": str(self.source_id),
            "contract_id": str(self.contract_id) if self.contract_id else None,
            "ledger_id": str(self.ledger_id),
            "amount": str(self.amount),
            "label": self.label,
            "reference_date": self.reference_date.isoformat() if self.reference_date else None,
            "source_entry_id": str(self.source_entry_id) if self.source_entry_id else None,
            "payout_reason": PAYOUT_REASON[self.source_type],
        }


def source_key(source_type: str, source_id: uuid.UUID, contract_id: uuid.UUID | None) -> str:
    return f"{source_type}:{source_id}:{contract_id or '-'}"


def _conflict(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.CONFLICT, detail=detail)


# Settings -----------------------------------------------------------------------------------


async def get_setting(session: AsyncSession) -> CreditPayableSetting | None:
    return await session.scalar(select(CreditPayableSetting))


def setting_out(row: CreditPayableSetting | None) -> dict[str, Any]:
    return {
        "mode": row.mode if row else "off",
        "four_eyes_required": row.four_eyes_required if row else True,
        "creditor_account_number": row.creditor_account_number if row else None,
        "owner_debit_account_number": row.owner_debit_account_number if row else None,
        "deposit_debit_account_number": row.deposit_debit_account_number if row else None,
        "modes": list(MODES),
        "decision_ref": "Q01-01",
        "note": (
            "Buchungsregel offen (OPEN_QUESTIONS Q01-01). Standard aus: es entsteht kein "
            "Verbindlichkeitsposten. Konten sind Eingaben des Betreibers."
        ),
    }


async def update_setting(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None, changes: dict[str, Any]
) -> CreditPayableSetting:
    row = await get_setting(session)
    if row is None:
        row = CreditPayableSetting(tenant_id=tenant_id, created_by=user_id)
        session.add(row)
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_by = user_id
    await session.flush()
    return row


# Candidates ---------------------------------------------------------------------------------


async def _rent_candidates(session: AsyncSession, ledger_id: uuid.UUID | None) -> list[Candidate]:
    from mhvp.billing.models import Statement
    from mhvp.billing.status import StatementStatus

    credit = func.sum(JournalLine.credit - JournalLine.debit)
    query = (
        select(
            JournalEntry.id,
            JournalEntry.ledger_id,
            JournalEntry.contract_id,
            JournalEntry.idempotency_key,
            JournalEntry.booking_date,
            JournalLine.account_id,
            credit,
        )
        .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
        .where(
            JournalEntry.kind == EntryKind.STATEMENT_RESULT,
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.reversed_by_id.is_(None),
            JournalEntry.idempotency_key.like(f"{RENT_KEY}%"),
            LedgerAccount.category == AccountCategory.DEBTOR,
        )
        .group_by(
            JournalEntry.id,
            JournalEntry.ledger_id,
            JournalEntry.contract_id,
            JournalEntry.idempotency_key,
            JournalEntry.booking_date,
            JournalLine.account_id,
        )
        .having(credit > 0)
    )
    if ledger_id is not None:
        query = query.where(JournalEntry.ledger_id == ledger_id)
    rows = (await session.execute(query)).all()
    parsed: list[tuple[Any, uuid.UUID, uuid.UUID]] = []
    for row in rows:
        parts = str(row[3]).split(":")
        try:
            statement_id, contract_id = uuid.UUID(parts[1]), uuid.UUID(parts[2])
        except (IndexError, ValueError):
            continue
        if row[2] != contract_id:
            continue
        parsed.append((row, statement_id, contract_id))
    if not parsed:
        return []
    statements = {
        st.id: st
        for st in await session.scalars(
            select(Statement).where(Statement.id.in_({p[1] for p in parsed}))
        )
    }
    out = []
    for row, statement_id, contract_id in parsed:
        st = statements.get(statement_id)
        if (
            st is None
            or st.status
            not in (StatementStatus.DUE, StatementStatus.POSTED, StatementStatus.LOCKED)
            or str(row[0]) not in [str(i) for i in st.result_entry_ids or []]
        ):
            continue
        out.append(
            Candidate(
                source_type="rent_statement",
                source_id=statement_id,
                contract_id=contract_id,
                ledger_id=row[1],
                amount=Decimal(row[6]),
                label=(
                    f"{SOURCE_LABELS['rent_statement']} {st.period_from.year}"
                    f"{' (Version ' + str(st.version) + ')' if st.version > 1 else ''}"
                ),
                reference_date=row[4],
                source_entry_id=row[0],
                debtor_account_id=row[5],
            )
        )
    return out


async def _owner_candidates(session: AsyncSession, ledger_id: uuid.UUID | None) -> list[Candidate]:
    from mhvp.billing.owner_statement import OwnerStatement, OwnerStatementStatus
    from mhvp.billing.owner_statement_pdf import settlement

    statuses = (
        OwnerStatementStatus.ISSUED,
        OwnerStatementStatus.DUE,
        OwnerStatementStatus.POSTED,
        OwnerStatementStatus.LOCKED,
    )
    query = select(OwnerStatement).where(OwnerStatement.status.in_(statuses))
    if ledger_id is not None:
        query = query.where(OwnerStatement.ledger_id == ledger_id)
    out = []
    for st in await session.scalars(query):
        results = (st.snapshot or {}).get("results")
        if not results:
            continue
        try:
            payout = Decimal(settlement(results)["payout_amount"])
        except (KeyError, TypeError, ArithmeticError):
            continue
        if payout <= 0:
            continue
        out.append(
            Candidate(
                source_type="owner_statement",
                source_id=st.id,
                contract_id=None,
                ledger_id=st.ledger_id,
                amount=payout,
                label=(
                    f"{SOURCE_LABELS['owner_statement']} {st.period_from.isoformat()} bis "
                    f"{st.period_to.isoformat()}"
                ),
                reference_date=st.period_to,
            )
        )
    return out


async def _deposit_candidates(
    session: AsyncSession, ledger_id: uuid.UUID | None
) -> list[Candidate]:
    from mhvp.contracts.deposit_settlement import DepositSettlement, DepositSettlementStatus
    from mhvp.contracts.models import Contract, DebtorAccountReservation, Deposit

    query = (
        select(DepositSettlement, Deposit.contract_id, Ledger.id)
        .join(Deposit, Deposit.id == DepositSettlement.deposit_id)
        .join(Contract, Contract.id == Deposit.contract_id)
        .join(DebtorAccountReservation, DebtorAccountReservation.id == Contract.debtor_account_id)
        .join(Ledger, Ledger.legal_entity_id == DebtorAccountReservation.legal_entity_id)
        .where(
            DepositSettlement.status == DepositSettlementStatus.RELEASED,
            DepositSettlement.payout_amount > 0,
        )
    )
    if ledger_id is not None:
        query = query.where(Ledger.id == ledger_id)
    return [
        Candidate(
            source_type="deposit_settlement",
            source_id=row.id,
            contract_id=contract_id,
            ledger_id=ledger,
            amount=Decimal(row.payout_amount),
            label=f"{SOURCE_LABELS['deposit_settlement']} {row.number or ''}".strip(),
            reference_date=row.settlement_date,
        )
        for row, contract_id, ledger in (await session.execute(query)).all()
    ]


async def candidates(
    session: AsyncSession,
    *,
    ledger_id: uuid.UUID | None = None,
    source_type: str | None = None,
    include_taken: bool = False,
) -> list[Candidate]:
    """Credits that may become a payable; without ``include_taken`` sources with an active
    (not withdrawn) proposal are left out. Read only."""
    found: list[Candidate] = []
    if source_type in (None, "rent_statement"):
        found += await _rent_candidates(session, ledger_id)
    if source_type in (None, "owner_statement"):
        found += await _owner_candidates(session, ledger_id)
    if source_type in (None, "deposit_settlement"):
        found += await _deposit_candidates(session, ledger_id)
    if include_taken or not found:
        return found
    taken = set(
        await session.scalars(
            select(CreditPayable.source_key).where(CreditPayable.status != "withdrawn")
        )
    )
    return [c for c in found if c.key not in taken]


async def find_candidate(
    session: AsyncSession, source_type: str, source_id: uuid.UUID, contract_id: uuid.UUID | None
) -> Candidate:
    key = source_key(source_type, source_id, contract_id)
    for cand in await candidates(session, source_type=source_type, include_taken=True):
        if cand.key == key:
            return cand
    raise ProblemError(
        ErrorCodes.RESOURCE_NOT_FOUND,
        detail="Kein auszahlbares Guthaben für diese Quelle (Status, Buchung oder Betrag).",
    )


# Proposal and release -----------------------------------------------------------------------


async def _contract_receivables(
    session: AsyncSession, ledger_id: uuid.UUID, contract_id: uuid.UUID
) -> Decimal:
    settled = (
        select(func.coalesce(func.sum(OpenItemSettlement.amount), 0))
        .where(OpenItemSettlement.open_item_id == OpenItem.id)
        .scalar_subquery()
    )
    total = await session.scalar(
        select(func.coalesce(func.sum(OpenItem.amount - settled), 0)).where(
            OpenItem.ledger_id == ledger_id,
            OpenItem.contract_id == contract_id,
            OpenItem.kind == OpenItemKind.RECEIVABLE,
            # AO01 (GAK-104): date aware, written off only from written_off_on (B07).
            not_written_off_as_of(local_today()),
        )
    )
    return Decimal(total or 0)


async def _warnings(
    session: AsyncSession, cand: Candidate, amount: Decimal
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if cand.contract_id is not None:
        open_total = await _contract_receivables(session, cand.ledger_id, cand.contract_id)
        if open_total > 0:
            out.append(
                {
                    "code": "OPEN_RECEIVABLES",
                    "message": (
                        f"Offene Forderungen des Vertrags {open_total} EUR: Verrechnung vor der "
                        "Auszahlung prüfen. Es wird nichts automatisch verrechnet."
                    ),
                }
            )
    if amount < cand.amount:
        out.append(
            {
                "code": "PARTIAL_AMOUNT",
                "message": f"Betrag {amount} EUR unter dem Ergebnis {cand.amount} EUR.",
            }
        )
    return out


async def propose(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    source_type: str,
    source_id: uuid.UUID,
    contract_id: uuid.UUID | None,
    amount: Decimal | None,
    note: str | None,
) -> CreditPayable:
    setting = await get_setting(session)
    mode = setting.mode if setting else "off"
    if mode == "off":
        raise _conflict(
            "Verbindlichkeitsposten aus Guthaben sind ausgeschaltet (Mandantenschalter, "
            "Buchungsregel offen, Q01-01)."
        )
    if mode == "subledger" and source_type != "rent_statement":
        raise _conflict(
            "Variante Nebenbuchposten setzt eine gebuchte Gutschrift voraus; Eigentümer- und "
            "Kautionsabrechnung nur mit Variante Umbuchung."
        )
    key = source_key(source_type, source_id, contract_id)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"credit_payable:{key}"}
    )
    if await session.scalar(
        select(CreditPayable.id).where(
            CreditPayable.source_key == key, CreditPayable.status != "withdrawn"
        )
    ):
        raise _conflict("Für diese Quelle besteht bereits ein Vorschlag.")
    cand = await find_candidate(session, source_type, source_id, contract_id)
    value = cand.amount if amount is None else amount
    if value <= 0:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Betrag muss positiv sein.")
    if value != cand.amount and source_type != "owner_statement":
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Betrag ist das Abrechnungsergebnis und nicht änderbar.",
        )
    if value > cand.amount:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Der Betrag übersteigt das Abrechnungsergebnis."
        )
    row = CreditPayable(
        tenant_id=tenant_id,
        created_by=user_id,
        ledger_id=cand.ledger_id,
        source_type=source_type,
        source_id=source_id,
        source_key=key,
        contract_id=contract_id,
        source_entry_id=cand.source_entry_id,
        amount=value,
        variant=mode,
        status="proposed",
        payout_reason=PAYOUT_REASON[source_type],
        note=note,
        warnings=await _warnings(session, cand, value),
    )
    session.add(row)
    await session.flush()
    return row


async def _account(
    session: AsyncSession, ledger_id: uuid.UUID, number: str | None, label: str
) -> LedgerAccount:
    if not number:
        raise _conflict(f"{label} ist in den Einstellungen nicht hinterlegt (Q01-01).")
    account = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger_id, LedgerAccount.number == number
        )
    )
    if account is None or not account.active:
        raise _conflict(f"{label} {number} fehlt im Buchungskreis oder ist deaktiviert.")
    return account


async def release(
    session: AsyncSession,
    row: CreditPayable,
    *,
    user_id: uuid.UUID | None,
    booking_date: date,
) -> CreditPayable:
    """Release by a person (four eyes switch): subledger adds the payable open item to the
    posted credit line, reclass writes a draft only. The caller checked G3."""
    if row.status != "proposed":
        raise _conflict("Nur Vorschläge können freigegeben werden.")
    setting = await get_setting(session)
    mode = setting.mode if setting else "off"
    if mode == "off":
        raise _conflict("Verbindlichkeitsposten aus Guthaben sind ausgeschaltet (Q01-01).")
    if mode != row.variant:
        raise _conflict(
            "Die Variante wurde seit dem Vorschlag geändert: Vorschlag zurücknehmen und neu "
            "anlegen."
        )
    if (setting is None or setting.four_eyes_required) and row.created_by == user_id:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die Freigabe braucht eine andere Person als den Vorschlag.",
        )
    cand = await find_candidate(session, row.source_type, row.source_id, row.contract_id)
    if row.amount > cand.amount:
        raise _conflict("Das Abrechnungsergebnis hat sich geändert; Vorschlag zurücknehmen.")
    ledger = await session.get(Ledger, row.ledger_id)
    if ledger is None:  # pragma: no cover - FK
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.variant == "subledger":
        entry = await session.get(JournalEntry, cand.source_entry_id)
        if entry is None or cand.debtor_account_id is None:  # pragma: no cover - candidate
            raise _conflict("Ergebnisbuchung nicht gefunden.")
        if await session.scalar(
            select(OpenItem.id).where(
                OpenItem.journal_entry_id == entry.id,
                OpenItem.account_id == cand.debtor_account_id,
            )
        ):
            raise _conflict("Zur Gutschrift besteht bereits ein offener Posten.")
        item = OpenItem(
            tenant_id=row.tenant_id,
            ledger_id=ledger.id,
            account_id=cand.debtor_account_id,
            journal_entry_id=entry.id,
            kind=OpenItemKind.PAYABLE,
            booking_date=entry.booking_date,
            due_date=entry.due_date or entry.booking_date,
            amount=row.amount,
            contract_id=row.contract_id,
            component="statement_credit",
        )
        session.add(item)
        await session.flush()
        row.open_item_id = item.id
    else:
        if setting is None:  # pragma: no cover - mode reclass implies a row
            raise _conflict("Einstellungen fehlen.")
        creditor = await _account(
            session, ledger.id, setting.creditor_account_number, "Das Kreditorenkonto"
        )
        if creditor.category is not AccountCategory.CREDITOR:
            raise _conflict(f"Konto {creditor.number} ist kein Kreditorenkonto.")
        if row.source_type == "rent_statement":
            if cand.debtor_account_id is None:  # pragma: no cover - candidate
                raise _conflict("Debitorenkonto nicht gefunden.")
            source_account_id = cand.debtor_account_id
        elif row.source_type == "owner_statement":
            source_account_id = (
                await _account(
                    session,
                    ledger.id,
                    setting.owner_debit_account_number,
                    "Das Sollkonto der Eigentümerauszahlung",
                )
            ).id
        else:
            source_account_id = (
                await _account(
                    session,
                    ledger.id,
                    setting.deposit_debit_account_number,
                    "Das Sollkonto der Kautionsrückzahlung",
                )
            ).id
        label = SOURCE_LABELS[row.source_type]
        entry = JournalEntry(
            tenant_id=row.tenant_id,
            created_by=user_id,
            ledger_id=ledger.id,
            booking_date=booking_date,
            due_date=booking_date,
            text=f"Umbuchung {label} in Verbindlichkeit"[:500],
            kind=EntryKind.CREDIT_RECLASS,
            contract_id=row.contract_id,
            source=EntrySource.MANUAL,
            idempotency_key=f"credit-payable:{row.id}",
        )
        await acc.write_draft(
            session,
            ledger,
            entry,
            [
                acc.LineIn(source_account_id, row.amount, ZERO, text=label),
                acc.LineIn(creditor.id, ZERO, row.amount, text=label),
            ],
            [],
        )
        row.reclass_entry_id = entry.id
    row.status = "released"
    row.released_by, row.released_at = user_id, datetime.now(UTC)
    row.updated_by = user_id
    row.warnings = await _warnings(session, cand, row.amount)
    await session.flush()
    return row


# State --------------------------------------------------------------------------------------


async def open_item_of(session: AsyncSession, row: CreditPayable) -> OpenItem | None:
    """The payable of the row; for the reclass variant the item created by posting the reclass
    entry (linked on first sight)."""
    if row.open_item_id is not None:
        return await session.get(OpenItem, row.open_item_id)
    if row.reclass_entry_id is None:
        return None
    item = await session.scalar(
        select(OpenItem).where(
            OpenItem.journal_entry_id == row.reclass_entry_id,
            OpenItem.kind == OpenItemKind.PAYABLE,
        )
    )
    if item is not None:
        row.open_item_id = item.id
    return item


async def state(session: AsyncSession, row: CreditPayable) -> dict[str, Any]:
    from mhvp.banking.models import PaymentOrder

    item = await open_item_of(session, row)
    out: dict[str, Any] = {
        "state": row.status,
        "open_item_id": str(item.id) if item else None,
        "remaining": None,
        "reclass_entry_status": None,
        "payment_order_id": None,
        "payment_order_status": None,
    }
    if row.reclass_entry_id is not None:
        entry = await session.get(JournalEntry, row.reclass_entry_id)
        out["reclass_entry_status"] = entry.status.value if entry else None
    if row.status != "released":
        return out
    if item is None:
        out["state"] = "reclass_draft" if out["reclass_entry_status"] == "draft" else "discarded"
        return out
    remaining = await acc.remaining(session, item.id)
    out["remaining"] = str(remaining)
    order = await session.scalar(
        select(PaymentOrder)
        .where(PaymentOrder.open_item_id == item.id)
        .order_by(PaymentOrder.created_at.desc())
    )
    if order is not None:
        out["payment_order_id"], out["payment_order_status"] = str(order.id), order.status.value
    origin = await session.get(JournalEntry, item.journal_entry_id)
    source = (
        await session.get(JournalEntry, row.source_entry_id)
        if row.source_entry_id is not None and row.source_entry_id != item.journal_entry_id
        else None
    )
    if origin is not None and origin.reversed_by_id is not None:
        out["state"] = "reversed"
    elif source is not None and source.reversed_by_id is not None and remaining > 0:
        # Reclass variant: the statement result was reversed (correction) after the
        # reclass; the payable must not be paid out, withdrawal reverses the reclass.
        out["state"] = "source_reversed"
    elif order is not None and order.status.value in ACTIVE_ORDER:
        out["state"] = "ordered"
    elif remaining <= 0:
        out["state"] = "paid"
    elif remaining < item.amount:
        out["state"] = "partially_paid"
    else:
        out["state"] = "open"
    return out


# Payment order and withdrawal ---------------------------------------------------------------


async def payout_order(
    session: AsyncSession,
    row: CreditPayable,
    *,
    contact_bank_account_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    execution_date: date,
    purpose: str | None,
    user_id: uuid.UUID | None,
) -> Any:
    """Payment order without invoice on the payable (``payment_run.order_for_payout``); an
    owner payout goes only to a member of the owner's party of the legal entity."""
    from mhvp.banking import payment_run
    from mhvp.contacts.models import ContactBankAccount, PartyMember
    from mhvp.properties.models import LegalEntity

    if row.status != "released":
        raise _conflict("Zahlungsaufträge nur aus freigegebenen Verbindlichkeitsposten.")
    current = await state(session, row)
    if current["state"] not in ("open", "partially_paid"):
        raise _conflict(
            "Kein offener Verbindlichkeitsposten: Umbuchung zuerst buchen, oder der Posten ist "
            "bezahlt, beauftragt oder storniert."
        )
    if row.source_type == "owner_statement":
        ledger = await session.get(Ledger, row.ledger_id)
        entity = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
        payee = await session.get(ContactBankAccount, contact_bank_account_id)
        if entity is None or entity.party_id is None:
            raise _conflict("Dem Rechtsträger ist keine Eigentümerpartei zugeordnet.")
        if payee is not None and not await session.scalar(
            select(PartyMember.id).where(
                PartyMember.party_id == entity.party_id,
                PartyMember.contact_id == payee.contact_id,
            )
        ):
            raise _conflict("Der Empfänger gehört nicht zur Eigentümerpartei.")
    return await payment_run.order_for_payout(
        session,
        open_item_id=uuid.UUID(current["open_item_id"]),
        contact_bank_account_id=contact_bank_account_id,
        bank_account_id=bank_account_id,
        execution_date=execution_date,
        reason=row.payout_reason,
        purpose=purpose or SOURCE_LABELS[row.source_type],
        user_id=user_id,
    )


async def payout_options(session: AsyncSession, row: CreditPayable) -> dict[str, Any]:
    """Selectable accounts for the payout order: released bank accounts of the members of the
    contract party (owner payout: of the owner's party of the legal entity) and the ordering
    accounts of the legal entity (deposit refund only segregated, everything else never)."""
    from mhvp.contacts.models import BankAccountApproval, ContactBankAccount, PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import LegalEntity, PropertyBankAccount

    ledger = await session.get(Ledger, row.ledger_id)
    if ledger is None:  # pragma: no cover - FK
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    party_id = None
    if row.contract_id is not None:
        contract = await session.get(Contract, row.contract_id)
        party_id = contract.party_id if contract else None
    else:
        entity = await session.get(LegalEntity, ledger.legal_entity_id)
        party_id = entity.party_id if entity else None
    payees: list[dict[str, Any]] = []
    if party_id is not None:
        rows = await session.scalars(
            select(ContactBankAccount)
            .join(PartyMember, PartyMember.contact_id == ContactBankAccount.contact_id)
            .where(
                PartyMember.party_id == party_id,
                ContactBankAccount.approval_status == BankAccountApproval.APPROVED,
            )
        )
        payees = [{"id": str(a.id), "holder": a.holder, "iban_suffix": a.iban_suffix} for a in rows]
    deposit = row.payout_reason == "deposit_refund"
    accounts = await session.scalars(
        select(PropertyBankAccount).where(
            PropertyBankAccount.legal_entity_id == ledger.legal_entity_id,
            PropertyBankAccount.segregated.is_(deposit),
        )
    )
    return {
        "payees": payees,
        "bank_accounts": [
            {"id": str(a.id), "holder": a.holder, "iban_suffix": a.iban_suffix} for a in accounts
        ],
    }


async def needs_reversal(session: AsyncSession, row: CreditPayable) -> bool:
    """A withdrawal reverses a posting only for a posted, unreversed reclass entry."""
    if row.status != "released" or row.reclass_entry_id is None:
        return False
    entry = await session.get(JournalEntry, row.reclass_entry_id)
    return bool(
        entry is not None and entry.status is EntryStatus.POSTED and entry.reversed_by_id is None
    )


async def withdraw(
    session: AsyncSession,
    row: CreditPayable,
    *,
    user_id: uuid.UUID | None,
    reason: str,
    booking_date: date,
    ensure_g1: Callable[[], Awaitable[None]],
) -> CreditPayable:
    if row.status == "withdrawn":
        raise _conflict("Der Vorschlag ist bereits zurückgenommen.")
    if row.status == "released":
        current = await state(session, row)
        if current["state"] == "ordered":
            raise _conflict(
                "Für den Posten besteht ein Zahlungsauftrag: zuerst den Auftrag ablehnen oder "
                "stornieren."
            )
        if current["state"] in ("paid", "partially_paid"):
            raise _conflict(
                "Der Posten ist (teilweise) bezahlt: Korrektur nur über die Rückbuchung der "
                "Zahlung (Storno, 0.1.7)."
            )
        if current["state"] == "reclass_draft":
            entry = await session.get(JournalEntry, row.reclass_entry_id)
            if entry is not None:
                row.reclass_entry_id = None
                await session.flush()
                await session.delete(entry)  # drafts are no postings (0.1.7)
        elif current["state"] in ("open", "source_reversed"):
            if row.variant == "subledger":
                raise _conflict(
                    "Ein Nebenbuchposten wird über den Storno der Ergebnisbuchung (Korrektur "
                    "der Abrechnung) geschlossen; der Storno gleicht den Posten aus."
                )
            if await needs_reversal(session, row):
                await ensure_g1()
                entry = await session.get(JournalEntry, row.reclass_entry_id)
                ledger = await session.get(Ledger, row.ledger_id)
                if entry is None or ledger is None:  # pragma: no cover - checked above
                    raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
                reversal = await acc.reverse(
                    session,
                    ledger,
                    entry,
                    user_id=user_id,
                    reason=reason,
                    booking_date=booking_date,
                    reason_code=ReversalReason.OTHER,
                )
                row.reversal_entry_id = reversal.id
    row.status = "withdrawn"
    row.withdrawn_by, row.withdrawn_at, row.withdraw_reason = user_id, datetime.now(UTC), reason
    row.updated_by = user_id
    await session.flush()
    return row
