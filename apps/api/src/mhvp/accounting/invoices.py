"""Incoming invoices (7.9.1 PÜ01 to PÜ05, 7.3 Eingangsrechnung, D12).

Automatic checks only produce findings (hints); a review status changes only through recorded
human review steps (PÜ05). Posting needs a closed review and a release by a second person that
is bound to a hash of the payment relevant fields (6.9.9). Payment is M15 and G2.
"""

import hashlib
import json
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    AccountType,
    EntryKind,
    EntrySource,
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceReview,
    JournalEntry,
    Ledger,
    LedgerAccount,
    PostingStatus,
    ReviewStatus,
    VatMode,
)
from mhvp.core import crypto
from mhvp.core.problems import ErrorCodes, ProblemError

CENT = Decimal("0.01")
STEPS = ("completeness", "factual", "arithmetic_tax")
CREDITOR_START = 70000


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def payment_hash(invoice: Invoice) -> str:
    """Hash over payment relevant fields; a change voids the release (6.9.9)."""
    fields = {
        "gross": str(invoice.gross),
        "payee": str(invoice.provider_contact_id),
        "iban": invoice.payee_iban_fingerprint or "",
        "due": invoice.due_date.isoformat() if invoice.due_date else "",
        "number": invoice.number,
        "ledger": str(invoice.ledger_id),
        "deductions": invoice.deductions,
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


def arithmetic_findings(invoice: Invoice, lines: list[InvoiceLine]) -> list[str]:
    out = []
    if invoice.net + invoice.vat != invoice.gross:
        out.append("Netto plus Steuer ergibt nicht den Bruttobetrag")
    if sum((ln.net for ln in lines), Decimal("0")) != invoice.net:
        out.append("Summe der Positionen weicht vom Nettobetrag ab")
    if sum((ln.vat for ln in lines), Decimal("0")) != invoice.vat:
        out.append("Summe der Steuer je Position weicht vom Steuerbetrag ab")
    for i, ln in enumerate(lines, start=1):
        expected = (ln.net * ln.vat_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if expected != ln.vat:
            out.append(f"Position {i}: Steuer {ln.vat} statt {expected} nachgerechnet")
        if ln.section_35a_amount is not None and ln.section_35a_amount > ln.net + ln.vat:
            out.append(f"Position {i}: §-35a-Anteil höher als die Position")
    return out


async def creditor_account(
    session: AsyncSession, ledger: Ledger, contact_id: uuid.UUID
) -> LedgerAccount:
    """Creditor account per provider in the ledger (7.2: 070000 to 079999, created on demand)."""
    from mhvp.contacts.models import Contact

    existing = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.category == AccountCategory.CREDITOR,
            LedgerAccount.contact_id == contact_id,
        )
    )
    if existing is not None:
        return existing
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechnungssteller nicht gefunden.")
    highest = await session.scalar(
        select(func.max(LedgerAccount.number)).where(
            LedgerAccount.ledger_id == ledger.id, LedgerAccount.number.between("070000", "079999")
        )
    )
    number = int(highest) + 1 if highest else CREDITOR_START
    if number > 79999:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kreditorennummernkreis erschöpft.")
    account = LedgerAccount(
        tenant_id=ledger.tenant_id,
        ledger_id=ledger.id,
        number=f"{number:06d}",
        name=contact.display_name[:200],
        category=AccountCategory.CREDITOR,
        type=AccountType.LIABILITY,
        contact_id=contact_id,
        is_system=True,
    )
    session.add(account)
    await session.flush()
    return account


async def evaluate(session: AsyncSession, invoice: Invoice) -> None:
    """Automatic findings: completeness, arithmetic, duplicates, unverified IBAN (hints only)."""
    from mhvp.contacts.models import BankAccountApproval, ContactBankAccount

    lines = list(
        (
            await session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
        ).all()
    )
    findings = arithmetic_findings(invoice, lines)
    if invoice.document_id is None:
        findings.append("Originalbeleg fehlt")
    if invoice.service_from is None:
        findings.append("Leistungszeitraum fehlt")
    duplicate = await session.scalar(
        select(Invoice.id).where(
            Invoice.provider_contact_id == invoice.provider_contact_id,
            Invoice.number == invoice.number,
            Invoice.id != invoice.id,
            Invoice.id != invoice.supersedes_id
            if invoice.supersedes_id
            else Invoice.id == Invoice.id,
        )
    )
    invoice.duplicate_of_id = None if invoice.supersedes_id else duplicate
    if invoice.duplicate_of_id:
        findings.append("Mögliche Doppelrechnung: gleiche Rechnungsnummer beim selben Aussteller")
    if invoice.payee_iban_fingerprint:
        known = await session.scalar(
            select(ContactBankAccount.id).where(
                ContactBankAccount.contact_id == invoice.provider_contact_id,
                ContactBankAccount.iban_fingerprint == invoice.payee_iban_fingerprint,
                ContactBankAccount.approval_status == BankAccountApproval.APPROVED,
            )
        )
        if known is None and invoice.iban_confirmed_by is None:
            findings.append(
                "IBAN weicht von den freigegebenen Stammdaten ab: gesonderte Bestätigung nötig"
            )
    if not invoice.order_reference:
        findings.append("Auftrags- oder Vertragsbezug nicht angegeben (sachliche Prüfung)")
    if invoice.recipient_name:
        from mhvp.properties.models import LegalEntity

        ledger = await session.get(Ledger, invoice.ledger_id)
        entity = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
        if entity is not None and _norm(entity.name) not in _norm(invoice.recipient_name):
            findings.append(
                f"Rechnungsempfänger weicht vom Rechtsträger des Buchungskreises ab: {entity.name}"
            )
    same_amount = await session.scalar(
        select(Invoice.id).where(
            Invoice.provider_contact_id == invoice.provider_contact_id,
            Invoice.gross == invoice.gross,
            Invoice.invoice_date == invoice.invoice_date,
            Invoice.number != invoice.number,
            Invoice.id != invoice.id,
        )
    )
    if same_amount and not invoice.supersedes_id:
        findings.append("Mögliche Doppelrechnung: gleicher Betrag und Tag bei anderer Nummer")
    if invoice.document_id:
        same_doc = await session.scalar(
            select(Invoice.id).where(
                Invoice.document_id == invoice.document_id,
                Invoice.id != invoice.id,
                Invoice.id != invoice.supersedes_id
                if invoice.supersedes_id
                else Invoice.id == Invoice.id,
            )
        )
        if same_doc:
            findings.append("Originalbeleg ist bereits einer anderen Rechnung zugeordnet")
    invoice.findings = findings


async def write(
    session: AsyncSession, invoice: Invoice, lines: list[dict[str, Any]], payee_iban: str | None
) -> Invoice:
    ledger = await session.get(Ledger, invoice.ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    accounts = {
        a.id: a
        for a in (
            await session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.id.in_([ln["account_id"] for ln in lines])
                )
            )
        ).all()
    }
    for ln in lines:
        account = accounts.get(ln["account_id"])
        if account is None or account.ledger_id != ledger.id:
            raise ProblemError(
                ErrorCodes.ACC_WRONG_ENTITY,
                detail="Konto gehört nicht zum Buchungskreis der Rechnung.",
            )
    invoice.payee_iban = payee_iban
    invoice.payee_iban_fingerprint = crypto.fingerprint(payee_iban) if payee_iban else None
    if invoice not in session:
        session.add(invoice)
    await session.flush()
    await session.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
    for ln in lines:
        session.add(InvoiceLine(tenant_id=invoice.tenant_id, invoice_id=invoice.id, **ln))
    await session.flush()
    await evaluate(session, invoice)
    await session.flush()
    return invoice


def aggregate(reviews: list[InvoiceReview], version: int) -> ReviewStatus:
    current = {r.step: r for r in reviews if r.invoice_version == version}
    if not current:
        return ReviewStatus.OPEN
    results = {r.result for r in current.values()}
    if "objected" in results:
        return ReviewStatus.OBJECTED
    if "query" in results:
        return ReviewStatus.QUERY
    if set(current) != set(STEPS):
        return ReviewStatus.PARTIALLY_REVIEWED
    return (
        ReviewStatus.CLOSED_WITH_RESERVATION if "reservation" in results else ReviewStatus.CLOSED_OK
    )


async def expense_amount(session: AsyncSession, invoice: Invoice) -> Decimal:
    """Final invoice: only the remaining effect is posted (D12: 5.950 - 2.380 = 3.570)."""
    if invoice.kind is not InvoiceKind.FINAL:
        return invoice.gross
    deducted = Decimal("0.00")
    for d in invoice.deductions:
        partial = await session.get(Invoice, uuid.UUID(str(d["invoice_id"])))
        if (
            partial is None
            or partial.kind is not InvoiceKind.PARTIAL
            or partial.provider_contact_id != invoice.provider_contact_id
            or partial.ledger_id != invoice.ledger_id
            or partial.posting_status is not PostingStatus.POSTED
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Abzug ist keine gebuchte Abschlagsrechnung dieses Ausstellers.",
            )
        if Decimal(str(d["gross"])) != partial.gross:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Abzugsbetrag entspricht nicht der Abschlagsrechnung."
            )
        deducted += partial.gross
    if deducted > invoice.gross:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Abschläge höher als die Schlussrechnung.")
    return invoice.gross - deducted


async def post(session: AsyncSession, invoice: Invoice, user_id: uuid.UUID | None) -> JournalEntry:
    if invoice.posting_status is PostingStatus.POSTED:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die Rechnung ist bereits gebucht.")
    if invoice.review_status not in (ReviewStatus.CLOSED_OK, ReviewStatus.CLOSED_WITH_RESERVATION):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Die Prüfung ist nicht abgeschlossen (PÜ05)."
        )
    if invoice.released_by is None or invoice.released_hash != payment_hash(invoice):
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Rechnungsfreigabe fehlt oder ist durch Änderung entwertet.",
        )
    if invoice.duplicate_of_id is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Mögliche Doppelrechnung ist ungeklärt.")
    ledger = await session.get(Ledger, invoice.ledger_id)
    if ledger is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if ledger.vat_mode is not VatMode.NONE and invoice.vat:
        # D45: a VAT option without a released tax treatment never posts input tax by itself;
        # the lock carries its own problem code so it is visible to callers and jobs.
        raise ProblemError(
            ErrorCodes.ACC_VAT_NOT_RELEASED,
            detail="Vorsteuerbehandlung für diesen Buchungskreis ist nicht freigegeben (M14-02).",
        )
    creditor = await creditor_account(session, ledger, invoice.provider_contact_id)
    invoice.creditor_account_id = creditor.id
    lines = list(
        (
            await session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
        ).all()
    )
    total = await expense_amount(session, invoice)
    credit_note = invoice.kind is InvoiceKind.CREDIT_NOTE
    factor = total / invoice.gross if invoice.gross else Decimal(1)
    # Without input tax deduction the gross amount is the cost (vat_mode none).
    parts = [((ln.net + ln.vat) * factor).quantize(CENT, rounding=ROUND_HALF_UP) for ln in lines]
    if parts:
        parts[-1] += total - sum(parts, Decimal("0.00"))  # stable rest cent on the last line (B06)
    journal: list[acc.LineIn] = []
    for ln, amount in zip(lines, parts, strict=True):
        if amount == 0:
            continue
        journal.append(
            acc.LineIn(
                ln.account_id,
                Decimal("0") if credit_note else amount,
                amount if credit_note else Decimal("0"),
                ln.text,
                ln.vat_percent,
                ln.vat,
                ln.net,
                ln.unit_id,
            )
        )
    journal.append(
        acc.LineIn(
            creditor.id,
            total if credit_note else Decimal("0"),
            Decimal("0") if credit_note else total,
        )
    )
    entry = JournalEntry(
        tenant_id=invoice.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=invoice.invoice_date,
        due_date=invoice.due_date,
        accrual_date=invoice.service_from,
        text=f"Rechnung {invoice.number}"[:500],
        kind=EntryKind.INVOICE,
        reference=invoice.number,
        document_id=invoice.document_id,
        invoice_id=invoice.id,
        source=EntrySource.MANUAL,
    )
    await acc.write_draft(session, ledger, entry, journal, [])
    await acc.post(session, ledger, entry, user_id)
    invoice.posting_status, invoice.journal_entry_id = PostingStatus.POSTED, entry.id
    await session.flush()
    return entry


def discount(invoice: Invoice, pay_date: date) -> Decimal:
    """Cash discount if paid by the discount date; the payable stays at gross until paid."""
    if (
        invoice.discount_percent is None
        or invoice.discount_until is None
        or pay_date > invoice.discount_until
    ):
        return Decimal("0.00")
    return (invoice.gross * invoice.discount_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
