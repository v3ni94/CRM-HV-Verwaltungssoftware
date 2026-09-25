"""Normalisation of raw bank data into bank_transaction (8.1, 6.9.7) and reconciliation (B09)."""

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.camt import ParsedFile, RawTransaction
from mhvp.banking.models import BankStatement, BankSyncRun, BankTransaction, TransactionStatus
from mhvp.core import crypto
from mhvp.core.problems import ErrorCodes, ProblemError

TRANSFER_WINDOW_DAYS = 5


def content_hash(iban_fp: str, tx: RawTransaction) -> str:
    """Hash of IBAN, date, amount, purpose and E2E (6.4); only a duplicate hint (6.9.7)."""
    parts = [
        iban_fp,
        tx.booking_date.isoformat(),
        str(tx.amount),
        tx.purpose or "",
        tx.end_to_end_id or "",
        tx.counterpart_iban or "",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def import_file(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    parsed: ParsedFile,
    document_id: uuid.UUID | None,
) -> BankSyncRun:
    """Import all statements of a file; accounts are matched by IBAN to own bank accounts."""
    from mhvp.properties.models import PropertyBankAccount

    run = BankSyncRun(
        tenant_id=tenant_id,
        created_by=user_id,
        source=f"file:{parsed.version}",
        document_id=document_id,
        status="running",
    )
    session.add(run)
    await session.flush()
    counts = {"new": 0, "duplicates": 0, "possible_duplicates": 0, "transfers": 0, "statements": 0}
    for stmt in parsed.statements:
        account = await session.scalar(
            select(PropertyBankAccount).where(
                PropertyBankAccount.iban_fingerprint == crypto.fingerprint(stmt.iban)
            )
        )
        if account is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Konto mit IBAN endend auf {stmt.iban[-4:]} "
                    "ist keinem Rechtsträger zugeordnet."
                ),
            )
        run.property_bank_account_id = account.id
        statement = None
        if stmt.statement_ref:
            statement = await session.scalar(
                select(BankStatement).where(
                    BankStatement.property_bank_account_id == account.id,
                    BankStatement.statement_ref == stmt.statement_ref,
                )
            )
        if statement is None:
            statement = BankStatement(
                tenant_id=tenant_id,
                property_bank_account_id=account.id,
                sync_run_id=run.id,
                statement_ref=stmt.statement_ref or f"run-{run.id}",
                from_date=stmt.from_date,
                to_date=stmt.to_date,
                opening_balance=stmt.opening_balance,
                closing_balance=stmt.closing_balance,
                closing_date=stmt.closing_date or stmt.to_date,
            )
            session.add(statement)
            await session.flush()
            counts["statements"] += 1
        for tx in stmt.transactions:
            if tx.bank_reference:
                known = await session.scalar(
                    select(BankTransaction.id).where(
                        BankTransaction.property_bank_account_id == account.id,
                        BankTransaction.bank_reference == tx.bank_reference,
                    )
                )
                if known is not None:
                    counts["duplicates"] += 1  # re-import: no additional effect (B08)
                    continue
            digest = content_hash(account.iban_fingerprint, tx)
            same = await session.scalar(
                select(BankTransaction.id)
                .where(
                    BankTransaction.property_bank_account_id == account.id,
                    BankTransaction.hash == digest,
                )
                .limit(1)
            )
            # With a distinct bank reference two equal payments are two payments (D05);
            # without any reference a hash match goes to review, it is never dropped.
            review = same is not None and tx.bank_reference is None
            row = BankTransaction(
                tenant_id=tenant_id,
                property_bank_account_id=account.id,
                legal_entity_id=account.legal_entity_id,
                statement_id=statement.id,
                sync_run_id=run.id,
                bank_reference=tx.bank_reference,
                booking_date=tx.booking_date,
                value_date=tx.value_date,
                amount=tx.amount,
                currency=tx.currency,
                counterpart_name=tx.counterpart_name,
                counterpart_iban=tx.counterpart_iban,
                counterpart_iban_fingerprint=crypto.fingerprint(tx.counterpart_iban)
                if tx.counterpart_iban
                else None,
                counterpart_bic=tx.counterpart_bic,
                purpose=tx.purpose,
                end_to_end_id=tx.end_to_end_id,
                mandate_reference=tx.mandate_reference,
                creditor_id=tx.creditor_id,
                transaction_code=tx.transaction_code,
                hash=digest,
                possible_duplicate_of_id=same,
                raw=tx.raw,
                status=TransactionStatus.NEEDS_REVIEW if review else TransactionStatus.NEW,
            )
            session.add(row)
            await session.flush()
            counts["new"] += 1
            counts["possible_duplicates"] += int(same is not None)
            counts["transfers"] += int(await pair_transfer(session, row))
    run.status, run.counts = "done", counts
    await session.flush()
    return run


async def import_finapi_transactions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    property_bank_account_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
    iban_fingerprint: str,
    run: BankSyncRun,
    transactions: list[RawTransaction],
) -> dict[str, int]:
    """Same dedup rule as the file import (bank_reference primary, hash secondary, D05): the
    finAPI transaction id is the ``bank_reference``. A changed reference on re-fetch never
    overwrites an already posted match (``journal_entry_id`` set), it is only recorded as a
    possible duplicate for review."""
    counts = {"new": 0, "duplicates": 0, "possible_duplicates": 0, "transfers": 0}
    for tx in transactions:
        if tx.bank_reference:
            known = await session.scalar(
                select(BankTransaction).where(
                    BankTransaction.property_bank_account_id == property_bank_account_id,
                    BankTransaction.bank_reference == tx.bank_reference,
                )
            )
            if known is not None:
                counts["duplicates"] += 1
                continue
        digest = content_hash(iban_fingerprint, tx)
        same = await session.scalar(
            select(BankTransaction.id)
            .where(
                BankTransaction.property_bank_account_id == property_bank_account_id,
                BankTransaction.hash == digest,
            )
            .limit(1)
        )
        review = same is not None and tx.bank_reference is None
        row = BankTransaction(
            tenant_id=tenant_id,
            property_bank_account_id=property_bank_account_id,
            legal_entity_id=legal_entity_id,
            sync_run_id=run.id,
            bank_reference=tx.bank_reference,
            booking_date=tx.booking_date,
            value_date=tx.value_date,
            amount=tx.amount,
            currency=tx.currency,
            counterpart_name=tx.counterpart_name,
            counterpart_iban=tx.counterpart_iban,
            counterpart_iban_fingerprint=(
                crypto.fingerprint(tx.counterpart_iban) if tx.counterpart_iban else None
            ),
            counterpart_bic=tx.counterpart_bic,
            purpose=tx.purpose,
            end_to_end_id=tx.end_to_end_id,
            mandate_reference=tx.mandate_reference,
            creditor_id=tx.creditor_id,
            transaction_code=tx.transaction_code,
            hash=digest,
            possible_duplicate_of_id=same,
            raw=tx.raw,
            status=TransactionStatus.NEEDS_REVIEW if review else TransactionStatus.NEW,
        )
        session.add(row)
        await session.flush()
        counts["new"] += 1
        counts["possible_duplicates"] += int(same is not None)
        counts["transfers"] += int(await pair_transfer(session, row))
    return counts


async def pair_transfer(session: AsyncSession, tx: BankTransaction) -> bool:
    """Link an internal transfer between own accounts of the same legal entity (D04)."""
    from mhvp.properties.models import PropertyBankAccount

    if tx.counterpart_iban_fingerprint is None:
        return False
    other_account = await session.scalar(
        select(PropertyBankAccount).where(
            PropertyBankAccount.iban_fingerprint == tx.counterpart_iban_fingerprint,
            PropertyBankAccount.legal_entity_id == tx.legal_entity_id,
            PropertyBankAccount.id != tx.property_bank_account_id,
        )
    )
    if other_account is None:
        return False
    own = await session.get(PropertyBankAccount, tx.property_bank_account_id)
    if own is None:  # pragma: no cover
        return False
    partner = await session.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.property_bank_account_id == other_account.id,
            BankTransaction.amount == -tx.amount,
            BankTransaction.transfer_pair_id.is_(None),
            BankTransaction.counterpart_iban_fingerprint == own.iban_fingerprint,
            BankTransaction.booking_date.between(
                tx.booking_date - timedelta(days=TRANSFER_WINDOW_DAYS),
                tx.booking_date + timedelta(days=TRANSFER_WINDOW_DAYS),
            ),
        )
        .order_by(BankTransaction.booking_date)
        .limit(1)
    )
    if partner is None:
        return False
    tx.transfer_pair_id, partner.transfer_pair_id = partner.id, tx.id
    await session.flush()
    return True


async def reconcile(session: AsyncSession, bank_account_id: uuid.UUID) -> list[dict[str, Any]]:
    """Per statement: opening + movements = closing (B09); ledger balance compared if linked."""
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine, LedgerAccount

    statements = (
        await session.scalars(
            select(BankStatement)
            .where(BankStatement.property_bank_account_id == bank_account_id)
            .order_by(BankStatement.closing_date.nulls_last(), BankStatement.created_at)
        )
    ).all()
    ledger_account = await session.scalar(
        select(LedgerAccount).where(LedgerAccount.property_bank_account_id == bank_account_id)
    )
    out = []
    for st in statements:
        moved = Decimal(
            await session.scalar(
                select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
                    BankTransaction.statement_id == st.id
                )
            )
            or 0
        )
        difference = None
        if st.opening_balance is not None and st.closing_balance is not None:
            difference = st.closing_balance - (st.opening_balance + moved)
        ledger_balance = ledger_difference = None
        if ledger_account is not None and st.closing_date and st.closing_balance is not None:
            d, c = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(JournalLine.debit), 0),
                        func.coalesce(func.sum(JournalLine.credit), 0),
                    )
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .where(
                        JournalLine.account_id == ledger_account.id,
                        JournalEntry.status == EntryStatus.POSTED,
                        JournalEntry.booking_date <= st.closing_date,
                    )
                )
            ).one()
            ledger_balance = Decimal(d) - Decimal(c)
            ledger_difference = st.closing_balance - ledger_balance
        out.append(
            {
                "statement_id": st.id,
                "statement_ref": st.statement_ref,
                "closing_date": st.closing_date,
                "opening_balance": st.opening_balance,
                "movements": moved,
                "closing_balance": st.closing_balance,
                "statement_difference": difference,
                "ledger_balance": ledger_balance,
                "ledger_difference": ledger_difference,
            }
        )
    return out
