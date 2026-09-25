"""Invoice to bank transaction matching (M11-finapi Stage 3, operator rebuild prompt section 4).

Matches a posted, released payable invoice against imported, not yet booked outgoing bank
transactions by amount and by invoice number or IBAN in the purpose text. A match is only
recorded as evidence (`InvoiceBankTransactionLink`); booking still requires the existing,
unchanged `mhvp.banking.matching.book_payment`/`mhvp.banking.payments.record_execution` path
(four-eyes, gates). When nothing matches, the caller may ask for a payment PROPOSAL instead
(`propose_payment`), which only ever creates a draft `PaymentOrder` via the existing
`mhvp.banking.payments.order_from_invoice` -- gate G2 stays closed, so this never submits or
initiates a payment; the provider is never asked to pay.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Invoice, PostingStatus
from mhvp.banking import payments as pay
from mhvp.banking.models import (
    BankTransaction,
    InvoiceBankTransactionLink,
    InvoiceMatchBasis,
    PaymentOrder,
    TransactionStatus,
)
from mhvp.core.problems import ErrorCodes, ProblemError


@dataclass(frozen=True)
class MatchCandidate:
    transaction: BankTransaction
    basis: InvoiceMatchBasis
    reason: str


def _invoice_number_in_purpose(number: str, purpose: str | None) -> bool:
    if not number or not purpose:
        return False
    return re.search(rf"\b{re.escape(number.lower())}\b", purpose.lower()) is not None


async def find_candidates(session: AsyncSession, invoice: Invoice) -> list[MatchCandidate]:
    """Candidate outgoing bank transactions for this payable invoice: same legal entity's
    ledger, not yet booked or ignored, amount equal to the invoice's gross, and either the
    invoice number in the purpose text or the payee IBAN as the counterpart IBAN. Nothing
    beyond what was actually imported is considered (rule 0.1.3): a transaction the provider
    or file import never delivered is never invented as a match."""
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import PropertyBankAccount

    ledger = await session.get(Ledger, invoice.ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    account_ids = list(
        await session.scalars(
            select(PropertyBankAccount.id).where(
                PropertyBankAccount.legal_entity_id == ledger.legal_entity_id
            )
        )
    )
    if not account_ids:
        return []
    rows = (
        await session.scalars(
            select(BankTransaction).where(
                BankTransaction.property_bank_account_id.in_(account_ids),
                BankTransaction.amount == -invoice.gross,
                BankTransaction.status.not_in(
                    (TransactionStatus.BOOKED, TransactionStatus.IGNORED)
                ),
            )
        )
    ).all()
    out: list[MatchCandidate] = []
    for tx in rows:
        if _invoice_number_in_purpose(invoice.number, tx.purpose):
            out.append(
                MatchCandidate(
                    tx,
                    InvoiceMatchBasis.AMOUNT_AND_NUMBER,
                    "Betrag und Rechnungsnummer im Verwendungszweck",
                )
            )
        elif invoice.payee_iban_fingerprint and tx.counterpart_iban_fingerprint == (
            invoice.payee_iban_fingerprint
        ):
            out.append(
                MatchCandidate(
                    tx,
                    InvoiceMatchBasis.AMOUNT_AND_IBAN,
                    "Betrag und Empfänger-IBAN stimmen überein",
                )
            )
    return out


async def existing_links(
    session: AsyncSession, invoice_id: uuid.UUID
) -> list[InvoiceBankTransactionLink]:
    return list(
        await session.scalars(
            select(InvoiceBankTransactionLink).where(
                InvoiceBankTransactionLink.invoice_id == invoice_id
            )
        )
    )


async def link(
    session: AsyncSession,
    *,
    invoice: Invoice,
    candidate: MatchCandidate,
    user_id: uuid.UUID | None,
) -> InvoiceBankTransactionLink:
    """Records the match as evidence only; never books anything by itself (rule 0.1.6)."""
    row = InvoiceBankTransactionLink(
        tenant_id=invoice.tenant_id,
        created_by=user_id,
        invoice_id=invoice.id,
        bank_transaction_id=candidate.transaction.id,
        match_basis=candidate.basis,
        amount=candidate.transaction.amount,
    )
    session.add(row)
    await session.flush()
    return row


async def match_invoice(
    session: AsyncSession, *, invoice: Invoice, user_id: uuid.UUID | None
) -> list[InvoiceBankTransactionLink]:
    """Finds candidates and links every one not already linked. Ambiguous matches (more than
    one candidate) are all recorded for a person to pick from; this never guesses one."""
    if invoice.posting_status is not PostingStatus.POSTED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nur gebuchte Rechnungen werden abgeglichen."
        )
    candidates = await find_candidates(session, invoice)
    already = {row.bank_transaction_id for row in await existing_links(session, invoice.id)}
    created = []
    for candidate in candidates:
        if candidate.transaction.id in already:
            continue
        created.append(await link(session, invoice=invoice, candidate=candidate, user_id=user_id))
    return created


async def propose_payment(
    session: AsyncSession,
    *,
    invoice: Invoice,
    bank_account_id: uuid.UUID,
    execution_date: date,
    user_id: uuid.UUID | None,
) -> PaymentOrder:
    """Creates a draft payment PROPOSAL via the existing, unchanged
    `mhvp.banking.payments.order_from_invoice` when no matching transaction exists yet. The
    result is "vorbereitet, nicht ausgeführt": `PaymentOrder.status` starts at `DRAFT` and
    only the existing, gated approve/export/submit flow (G2) can move it further; nothing here
    calls a provider or initiates a payment."""
    return await pay.order_from_invoice(
        session,
        invoice=invoice,
        bank_account_id=bank_account_id,
        execution_date=execution_date,
        user_id=user_id,
    )
