"""Payment runs (7.5 Zahllauf, 6.9.9, D06, D35 to D38).

Orders come from released and posted invoices. Two different persons approve a snapshot of
amount, payee, IBAN, execution date, invoice and bank account; a change invalidates approvals
(D35). The two approvers must be different persons: different user, different linked contact
and different e-mail (D36); a platform administrator never counts. Exporting a file (payment
initiation) requires release gate G2. Open items are settled only when the execution is proven
by an imported bank transaction (D06, D37: a partial debit settles only the confirmed part);
callbacks repeat without effect. A return (Rücklastschrift) never edits the posting: the
original entry is reversed, the reversal reopens the payable and may be linked to the return
credit on the statement (D38, rule 0.1.7).
"""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeElementTree  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    EntrySource,
    Invoice,
    JournalEntry,
    OpenItem,
    PostingStatus,
)
from mhvp.banking import matching
from mhvp.banking.models import (
    BankTransaction,
    OrderStatus,
    PaymentApproval,
    PaymentOrder,
    TransactionStatus,
)
from mhvp.core import crypto
from mhvp.core.problems import ErrorCodes, ProblemError

PAIN_FORMAT = "pain.001.001.09"  # default; agreed version per bank in PaymentBankConfig (M15-01)
REQUIRED_APPROVALS = 2


def snapshot(order: PaymentOrder) -> str:
    fields = {
        "amount": str(order.amount),
        "payee": order.counterpart_name,
        "iban": order.counterpart_iban_fingerprint,
        "date": order.execution_date.isoformat(),
        "invoice": str(order.invoice_id),
        "bank": str(order.property_bank_account_id),
        "purpose": order.purpose,
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


async def valid_approvals(session: AsyncSession, order: PaymentOrder) -> list[PaymentApproval]:
    rows = (
        await session.scalars(
            select(PaymentApproval).where(
                PaymentApproval.order_id == order.id, PaymentApproval.invalidated_at.is_(None)
            )
        )
    ).all()
    current = snapshot(order)
    return [a for a in rows if a.snapshot_hash == current]


async def invalidate(session: AsyncSession, order: PaymentOrder) -> None:
    now = datetime.now(UTC)
    for a in (
        await session.scalars(
            select(PaymentApproval).where(
                PaymentApproval.order_id == order.id, PaymentApproval.invalidated_at.is_(None)
            )
        )
    ).all():
        a.invalidated_at = now
    if order.status is OrderStatus.APPROVED:
        order.status = OrderStatus.DRAFT
    await session.flush()


async def order_from_invoice(
    session: AsyncSession,
    *,
    invoice: Invoice,
    bank_account_id: uuid.UUID,
    execution_date: date,
    user_id: uuid.UUID | None,
) -> PaymentOrder:
    from mhvp.accounting import invoices as inv_svc
    from mhvp.properties.models import PropertyBankAccount

    if invoice.posting_status is not PostingStatus.POSTED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nur gebuchte, freigegebene Rechnungen werden bezahlt."
        )
    if not invoice.payee_iban:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Rechnung ohne Empfänger-IBAN.")
    if any("IBAN weicht" in f for f in invoice.findings):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Abweichende IBAN ist nicht bestätigt (PÜ04)."
        )
    bank = await session.get(PropertyBankAccount, bank_account_id)
    from mhvp.accounting.models import Ledger

    ledger = await session.get(Ledger, invoice.ledger_id)
    if bank is None or ledger is None or bank.legal_entity_id != ledger.legal_entity_id:
        raise ProblemError(
            ErrorCodes.ACC_WRONG_ENTITY,
            detail="Zahlung nur vom Konto des Rechtsträgers der Rechnung.",
        )
    if bank.segregated:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Vom getrennten Kautionskonto werden keine Rechnungen bezahlt.",
        )
    item = await session.scalar(
        select(OpenItem).where(
            OpenItem.journal_entry_id == invoice.journal_entry_id, OpenItem.kind == "payable"
        )
    )
    if item is None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein offener Posten zur Rechnung.")
    rest = await acc.remaining(session, item.id)
    open_orders = (
        await session.scalars(
            select(PaymentOrder).where(
                PaymentOrder.open_item_id == item.id,
                PaymentOrder.status.not_in(
                    (
                        OrderStatus.REJECTED,
                        OrderStatus.CANCELLED,
                        OrderStatus.RETURNED,
                        OrderStatus.EXECUTED,
                        OrderStatus.PARTIALLY_EXECUTED,
                    )
                ),
            )
        )
    ).all()
    if open_orders:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für die Rechnung besteht bereits ein Zahlungsauftrag."
        )
    discount = (
        inv_svc.discount(invoice, execution_date) if rest == invoice.gross else Decimal("0.00")
    )
    order = PaymentOrder(
        tenant_id=invoice.tenant_id,
        created_by=user_id,
        ledger_id=invoice.ledger_id,
        property_bank_account_id=bank.id,
        invoice_id=invoice.id,
        open_item_id=item.id,
        amount=rest - discount,
        discount=discount,
        counterpart_name=(await _provider_name(session, invoice))[:140],
        counterpart_iban=invoice.payee_iban,
        counterpart_iban_fingerprint=crypto.fingerprint(invoice.payee_iban),
        purpose=f"Rechnung {invoice.number}"[:140],
        end_to_end_id=f"E2E{uuid.uuid4().hex[:28]}".upper(),
        execution_date=execution_date,
    )
    session.add(order)
    await session.flush()
    return order


async def change_order(session: AsyncSession, order: PaymentOrder, changes: dict[str, Any]) -> bool:
    """Apply a change to a draft or approved order; returns whether the payment relevant
    snapshot changed (then approvals are void, D35). An amount must stay within the open item;
    the cash discount survives only while amount plus discount still equal the open amount. A
    new IBAN must be a released bank account of the payee (no unconfirmed IBAN, PÜ04)."""
    from mhvp.contacts.models import BankAccountApproval, ContactBankAccount
    from mhvp.contacts.validation import InvalidValueError, normalise_iban

    if order.status not in (OrderStatus.DRAFT, OrderStatus.APPROVED):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Eingereichte Aufträge sind unveränderlich.")
    before = snapshot(order)
    if (amount := changes.pop("amount", None)) is not None:
        amount = Decimal(amount).quantize(Decimal("0.01"))
        if amount <= 0:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Der Zahlbetrag muss positiv sein.")
        rest = await acc.remaining(session, order.open_item_id) if order.open_item_id else amount
        if amount > rest:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Der Zahlbetrag übersteigt den offenen Posten."
            )
        if amount + order.discount != rest:
            order.discount = Decimal("0.00")
        order.amount = amount
    if (iban := changes.pop("counterpart_iban", None)) is not None:
        try:
            iban = normalise_iban(iban)
        except InvalidValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
        fingerprint = crypto.fingerprint(iban)
        invoice = await session.get(Invoice, order.invoice_id) if order.invoice_id else None
        known = (
            await session.scalar(
                select(ContactBankAccount.id).where(
                    ContactBankAccount.contact_id == invoice.provider_contact_id,
                    ContactBankAccount.iban_fingerprint == fingerprint,
                    ContactBankAccount.approval_status == BankAccountApproval.APPROVED,
                )
            )
            if invoice is not None
            else None
        )
        if known is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Die IBAN ist nicht in den freigegebenen Stammdaten des Empfängers (PÜ04).",
            )
        order.counterpart_iban, order.counterpart_iban_fingerprint = iban, fingerprint
    for key, value in changes.items():
        setattr(order, key, value)
    changed = snapshot(order) != before
    if changed:
        await invalidate(session, order)
    await session.flush()
    return changed


async def _identity(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[str | None, uuid.UUID | None]:
    """(e-mail, linked contact) of a user in the tenant, the features the platform can compare
    to tell two accounts of one person apart (6.9.9, D36). The limit of this check is documented
    under M15-02: one person with two separate contacts is not detectable here."""
    from mhvp.platform.models import Membership, User

    row = (
        await session.execute(
            select(User.email, Membership.contact_id)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == tenant_id, User.id == user_id)
        )
    ).first()
    if row is None:
        return None, None
    email, contact_id = row
    return (email.strip().lower() if email else None), contact_id


async def ensure_different_person(
    session: AsyncSession, order: PaymentOrder, user_id: uuid.UUID, others: set[uuid.UUID]
) -> None:
    """Four eyes need two persons, not two accounts (D36): the new approver must differ from every
    other approver in user id, e-mail and linked contact."""
    if user_id in others:
        return  # the same account repeating a click is handled by the caller (B08)
    email, contact_id = await _identity(session, order.tenant_id, user_id)
    for other in others:
        other_email, other_contact = await _identity(session, order.tenant_id, other)
        same_email = email is not None and email == other_email
        same_contact = contact_id is not None and contact_id == other_contact
        if same_email or same_contact:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail=(
                    "Ein zweites Benutzerkonto derselben Person zählt nicht als zweite Freigabe "
                    "(gleiche E-Mail oder gleiche Kontaktperson)."
                ),
            )


async def _provider_name(session: AsyncSession, invoice: Invoice) -> str:
    from mhvp.contacts.models import Contact

    contact = await session.get(Contact, invoice.provider_contact_id)
    return contact.display_name if contact else "Empfänger"


async def approve(
    session: AsyncSession, order: PaymentOrder, user_id: uuid.UUID, is_platform_admin: bool
) -> PaymentOrder:
    if order.status not in (OrderStatus.DRAFT, OrderStatus.APPROVED):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Auftrag kann nicht mehr freigegeben werden."
        )
    if is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Plattformadministratoren zählen nicht als Freigabeinstanz.",
        )
    valid = await valid_approvals(session, order)
    if any(a.user_id == user_id for a in valid):
        return order  # repeated click (B08)
    # The creator may be one of the two approvers; the two approvers must be two persons (D36).
    await ensure_different_person(session, order, user_id, {a.user_id for a in valid})
    session.add(
        PaymentApproval(
            tenant_id=order.tenant_id,
            order_id=order.id,
            user_id=user_id,
            snapshot_hash=snapshot(order),
        )
    )
    await session.flush()
    if len({a.user_id for a in await valid_approvals(session, order)}) >= REQUIRED_APPROVALS:
        order.status = OrderStatus.APPROVED
    await session.flush()
    return order


PAIN001_VERSIONS = ("pain.001.001.03", "pain.001.001.09")
PAIN008_VERSIONS = ("pain.008.001.02", "pain.008.001.08")
SUBMISSION_CHANNELS = ("file", "fints", "ebics")


def _namespace(version: str) -> str:
    return f"urn:iso:std:iso:20022:tech:xsd:{version}"


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, tag)
    if text is not None:
        element.text = text
    return element


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def control_sum(orders: list[PaymentOrder]) -> Decimal:
    return sum((o.amount for o in orders), Decimal("0.00"))


def pain001(
    batch_id: str,
    debtor_name: str,
    debtor_iban: str,
    orders: list[PaymentOrder],
    *,
    version: str = PAIN_FORMAT,
    debtor_bic: str | None = None,
    created_at: datetime | None = None,
) -> bytes:
    """Customer credit transfer initiation (CstmrCdtTrfInitn) in the ISO 20022 version agreed
    with the bank: pain.001.001.03 (DK until 2025) or pain.001.001.09 (DK from 11/2025). The
    two differ in the agent identifier (BIC versus BICFI) and the requested execution date
    (plain date versus Dt choice). Validated against the public XSDs in the tests; bank
    specific restrictions remain unverified (P05, M15-01)."""
    if version not in PAIN001_VERSIONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannte pain.001-Version {version}.")
    if not orders:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Aufträge im Sammler.")
    from mhvp.accounting.direct_debit import sepa_text

    ns = _namespace(version)
    modern = version == "pain.001.001.09"
    bic_tag = "BICFI" if modern else "BIC"
    ET.register_namespace("", ns)
    total = control_sum(orders)
    root = ET.Element(f"{{{ns}}}Document")
    init = _sub(root, "CstmrCdtTrfInitn")
    header = _sub(init, "GrpHdr")
    _sub(header, "MsgId", batch_id[:35])
    _sub(header, "CreDtTm", f"{created_at or datetime.now(UTC):%Y-%m-%dT%H:%M:%S}")
    _sub(header, "NbOfTxs", str(len(orders)))
    _sub(header, "CtrlSum", f"{total:.2f}")
    _sub(_sub(header, "InitgPty"), "Nm", sepa_text(debtor_name, 70))
    groups: dict[date, list[PaymentOrder]] = {}
    for o in orders:
        groups.setdefault(o.execution_date, []).append(o)
    for index, execution in enumerate(sorted(groups), start=1):
        batch = groups[execution]
        info = _sub(init, "PmtInf")
        _sub(info, "PmtInfId", f"{batch_id}-{index}"[:35])
        _sub(info, "PmtMtd", "TRF")
        _sub(info, "BtchBookg", "true")
        _sub(info, "NbOfTxs", str(len(batch)))
        _sub(info, "CtrlSum", f"{control_sum(batch):.2f}")
        _sub(_sub(_sub(info, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
        if modern:
            _sub(_sub(info, "ReqdExctnDt"), "Dt", execution.isoformat())
        else:
            _sub(info, "ReqdExctnDt", execution.isoformat())
        _sub(_sub(info, "Dbtr"), "Nm", sepa_text(debtor_name, 70))
        _sub(_sub(_sub(info, "DbtrAcct"), "Id"), "IBAN", debtor_iban)
        agent = _sub(_sub(info, "DbtrAgt"), "FinInstnId")
        if debtor_bic:
            _sub(agent, bic_tag, debtor_bic)
        else:
            _sub(_sub(agent, "Othr"), "Id", "NOTPROVIDED")
        _sub(info, "ChrgBr", "SLEV")
        for o in batch:
            tx = _sub(info, "CdtTrfTxInf")
            _sub(_sub(tx, "PmtId"), "EndToEndId", o.end_to_end_id[:35])
            amount = _sub(_sub(tx, "Amt"), "InstdAmt", f"{o.amount:.2f}")
            amount.set("Ccy", "EUR")
            _sub(_sub(tx, "Cdtr"), "Nm", sepa_text(o.counterpart_name, 70))
            _sub(_sub(_sub(tx, "CdtrAcct"), "Id"), "IBAN", o.counterpart_iban)
            _sub(_sub(tx, "RmtInf"), "Ustrd", sepa_text(o.purpose, 140))
    body = ET.tostring(root, encoding="unicode").encode()
    return b'<?xml version="1.0" encoding="UTF-8"?>' + body


def validate_pain001(data: bytes) -> list[str]:
    """Structural and arithmetic check of a pain.001 file (count and control sum per block
    and in total, unique EndToEndId, EUR amounts greater than 0). The XSD check runs in the
    tests; this check protects the stored file against manipulation before hand-out."""
    errors: list[str] = []
    try:
        root = SafeElementTree.fromstring(data)
    except (ET.ParseError, ValueError) as exc:
        return [f"XML nicht lesbar: {exc}"]
    version = next(
        (v for v in PAIN001_VERSIONS if root.tag == f"{{{_namespace(v)}}}Document"), None
    )
    if version is None:
        return ["Wurzelelement ist nicht Document in einem bekannten pain.001-Namensraum."]
    ns = {"p": _namespace(version)}
    init = root.find("p:CstmrCdtTrfInitn", ns)
    if init is None:
        return ["CstmrCdtTrfInitn fehlt."]
    header = init.find("p:GrpHdr", ns)
    if header is None:
        return ["GrpHdr fehlt."]
    for tag in ("MsgId", "CreDtTm", "NbOfTxs", "CtrlSum", "InitgPty/p:Nm"):
        if not (header.findtext(f"p:{tag}", namespaces=ns) or "").strip():
            errors.append(f"GrpHdr/{tag} fehlt.")
    infos = init.findall("p:PmtInf", ns)
    if not infos:
        errors.append("Kein PmtInf.")
    all_tx: list[ET.Element] = []
    total = Decimal("0.00")
    for info in infos:
        for tag in ("PmtInfId", "PmtMtd", "NbOfTxs", "CtrlSum", "Dbtr/p:Nm"):
            if not (info.findtext(f"p:{tag}", namespaces=ns) or "").strip():
                errors.append(f"PmtInf/{tag} fehlt.")
        if info.findtext("p:PmtMtd", namespaces=ns) != "TRF":
            errors.append("PmtInf/PmtMtd muss TRF sein.")
        date_text = info.findtext("p:ReqdExctnDt/p:Dt", namespaces=ns) or info.findtext(
            "p:ReqdExctnDt", namespaces=ns
        )
        if not (date_text or "").strip():
            errors.append("PmtInf/ReqdExctnDt fehlt.")
        if not (info.findtext("p:DbtrAcct/p:Id/p:IBAN", namespaces=ns) or "").strip():
            errors.append("PmtInf/DbtrAcct/Id/IBAN fehlt.")
        if info.find("p:DbtrAgt/p:FinInstnId", ns) is None:
            errors.append("PmtInf/DbtrAgt fehlt.")
        txs = info.findall("p:CdtTrfTxInf", ns)
        if str(len(txs)) != info.findtext("p:NbOfTxs", namespaces=ns):
            errors.append("PmtInf/NbOfTxs stimmt nicht mit der Anzahl der Überweisungen überein.")
        info_sum = Decimal("0.00")
        for tx in txs:
            for tag in ("PmtId/p:EndToEndId", "Cdtr/p:Nm", "CdtrAcct/p:Id/p:IBAN"):
                if not (tx.findtext(f"p:{tag}", namespaces=ns) or "").strip():
                    errors.append(f"CdtTrfTxInf/{tag} fehlt.")
            amount = tx.find("p:Amt/p:InstdAmt", ns)
            if amount is None or amount.get("Ccy") != "EUR":
                errors.append("CdtTrfTxInf/Amt/InstdAmt fehlt oder Währung ist nicht EUR.")
                continue
            try:
                value = Decimal(amount.text or "")
            except ArithmeticError:
                errors.append("CdtTrfTxInf/Amt/InstdAmt ist kein Betrag.")
                continue
            if value <= 0:
                errors.append("CdtTrfTxInf/Amt/InstdAmt muss größer als 0 sein.")
            info_sum += value
        if f"{info_sum:.2f}" != info.findtext("p:CtrlSum", namespaces=ns):
            errors.append("PmtInf/CtrlSum stimmt nicht mit der Summe der Überweisungen überein.")
        all_tx.extend(txs)
        total += info_sum
    if str(len(all_tx)) != header.findtext("p:NbOfTxs", namespaces=ns):
        errors.append("GrpHdr/NbOfTxs stimmt nicht mit der Anzahl der Überweisungen überein.")
    if f"{total:.2f}" != header.findtext("p:CtrlSum", namespaces=ns):
        errors.append("GrpHdr/CtrlSum stimmt nicht mit der Kontrollsumme überein.")
    e2e = [t.findtext("p:PmtId/p:EndToEndId", namespaces=ns) for t in all_tx]
    if len(set(e2e)) != len(e2e):
        errors.append("EndToEndId ist nicht eindeutig.")
    return errors


async def record_execution(
    session: AsyncSession,
    order: PaymentOrder,
    *,
    bank_transaction_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> PaymentOrder:
    """Execution proven by an imported bank debit on the ordering account settles the payable
    once (D06); a partial amount settles partially; repeated confirmation has no effect."""
    if (
        order.status in (OrderStatus.EXECUTED, OrderStatus.PARTIALLY_EXECUTED)
        and order.bank_transaction_id == bank_transaction_id
    ):
        return order
    if order.status not in (
        OrderStatus.SUBMITTED,
        OrderStatus.ACCEPTED_BY_BANK,
        OrderStatus.EXPORTED,
    ):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Auftrag wurde nicht eingereicht.")
    tx = await session.get(BankTransaction, bank_transaction_id, with_for_update=True)
    if tx is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankumsatz nicht gefunden.")
    if tx.property_bank_account_id != order.property_bank_account_id or tx.amount >= 0:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Umsatz ist keine Belastung des auftraggebenden Kontos.",
        )
    paid = -tx.amount
    if paid > order.amount:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Belastung höher als der Auftrag.")
    if tx.end_to_end_id and tx.end_to_end_id not in ("NOTPROVIDED", order.end_to_end_id):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Ende-zu-Ende-Referenz passt nicht zum Auftrag."
        )
    if tx.status is TransactionStatus.BOOKED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Bankumsatz ist bereits anderweitig gebucht."
        )
    settle = paid + (order.discount if paid == order.amount else Decimal("0.00"))
    counter = None
    if order.discount and paid == order.amount:
        counter = await _discount_account(session, order)
    entry = await matching.book_payment(
        session,
        tx,
        settlements=[(order.open_item_id, settle)] if order.open_item_id else [],
        counter_account_id=counter,
        user_id=user_id,
        source=EntrySource.BANK_IMPORT,
        text=order.purpose,
        discount=order.discount if counter else Decimal("0.00"),
    )
    order.executed_amount, order.bank_transaction_id, order.journal_entry_id = paid, tx.id, entry.id
    order.status = OrderStatus.EXECUTED if paid == order.amount else OrderStatus.PARTIALLY_EXECUTED
    await session.flush()
    return order


async def record_return(
    session: AsyncSession,
    order: PaymentOrder,
    *,
    reason: str | None,
    bank_transaction_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    booking_date: date,
) -> JournalEntry | None:
    """A returned payment (D38): the original posting is never edited; a reversal with reason
    and reference reopens the payable (0.1.7). The return credit on the statement, if given, must
    equal the executed amount and is marked booked with the reversal as its entry so that it
    cannot be booked twice;
    a differing amount (bank fees) is refused, fees are booked only with a separate document.
    Returns the reversal, or None when the order was already returned."""
    from mhvp.accounting.models import Ledger

    if order.status is OrderStatus.RETURNED:
        return None
    if order.journal_entry_id is None or order.status not in (
        OrderStatus.EXECUTED,
        OrderStatus.PARTIALLY_EXECUTED,
    ):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nur ausgeführte Aufträge können zurückkommen."
        )
    entry = await session.get(JournalEntry, order.journal_entry_id, with_for_update=True)
    ledger = await session.get(Ledger, order.ledger_id)
    if entry is None or ledger is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.CONFLICT)
    credit = None
    if bank_transaction_id is not None:
        credit = await session.get(BankTransaction, bank_transaction_id, with_for_update=True)
        if credit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankumsatz nicht gefunden.")
        if credit.property_bank_account_id != order.property_bank_account_id or credit.amount <= 0:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Umsatz ist keine Gutschrift auf dem auftraggebenden Konto.",
            )
        if credit.status in (TransactionStatus.BOOKED, TransactionStatus.IGNORED):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Bankumsatz ist bereits anderweitig gebucht."
            )
        if credit.amount != (order.executed_amount or order.amount):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Der Rückgabebetrag weicht vom ausgeführten Betrag ab. Gebühren werden nur "
                    "mit Beleg gesondert gebucht."
                ),
            )
    reversal = await acc.reverse(
        session,
        ledger,
        entry,
        user_id=user_id,
        reason=reason or "Rückgabe durch die Bank",
        booking_date=booking_date,
    )
    if credit is not None:  # the posted reversal stays untouched; the link lives on the credit
        credit.status, credit.journal_entry_id = TransactionStatus.BOOKED, reversal.id
    order.status = OrderStatus.RETURNED
    await session.flush()
    return reversal


async def _discount_account(session: AsyncSession, order: PaymentOrder) -> uuid.UUID:
    from mhvp.accounting.models import LedgerAccount

    account = await session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.ledger_id == order.ledger_id, LedgerAccount.number == "027000"
        )
    )
    if account is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Konto 027000 Durchlaufposten Skonti fehlt im Buchungskreis.",
        )
    return account
