"""Further Immoware24 report types of the import assistant (13.1, M8-02, M8-03, M8-04, M8-06,
M8-07): SEPA overview, chart of accounts, historical bank transactions, document index,
historical tickets and open items.

Same pipeline as the other report types: the user maps the columns of the export to the
platform fields below (mapping template per report type, nothing about the real column
names is assumed), required fields are named, the test run reports per row and is rolled back,
and a repeated run creates nothing twice (keys in the docstring of each handler). Rows never
overwrite: present with the same values is ``unchanged``, with other values ``conflict``.

Nothing here posts, collects or dunns (G1 and G2 closed): bank transactions arrive as
``ignored`` history, open items and tickets land in read only ``migrated_*`` tables, a SEPA
mandate is recorded only with an existing evidence document.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    AccountCategory,
    AccountType,
    AccountVatOption,
    Ledger,
    LedgerAccount,
)
from mhvp.banking.camt import RawTransaction
from mhvp.banking.models import BankTransaction, TransactionStatus
from mhvp.banking.services import content_hash
from mhvp.contacts.models import ContactBankAccount, PartyMember
from mhvp.contacts.validation import InvalidValueError
from mhvp.contacts.validation import normalise_iban as validate_iban
from mhvp.contracts import services as contract_services
from mhvp.contracts.models import (
    Contract,
    ContractKind,
    DueDayRule,
    MandateSequence,
    MandateStatus,
    MandateType,
    PaymentInterval,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core import crypto
from mhvp.core.problems import ProblemError
from mhvp.documents.models import Document, DocumentLink, LinkRole
from mhvp.imports.fields import FIELDS, Field
from mhvp.imports.history_models import (
    MigratedBankLink,
    MigratedOpenItem,
    MigratedTicket,
    OpenItemHistoryKind,
)
from mhvp.imports.migration_models import MigratedJournalEntry
from mhvp.imports.models import ImportExternalKey, ReportType, RowStatus
from mhvp.imports.reconciliation import normalise_account_number, normalise_property_number
from mhvp.properties.models import LegalEntity, LegalEntityKind, Property, PropertyBankAccount

Result = tuple[RowStatus, str | None, uuid.UUID | None, list[str]]
SOURCE = "immoware24"
LEDGER_KINDS = tuple(k.value for k in LegalEntityKind if k is not LegalEntityKind.MANAGER)
INTERVALS = tuple(i.value for i in PaymentInterval)
DUE_DAY_RULES = tuple(r.value for r in DueDayRule)
MANDATE_TYPES = tuple(t.value for t in MandateType)
SEQUENCES = tuple(s.value for s in MandateSequence)
CATEGORIES = tuple(c.value for c in AccountCategory)
ACCOUNT_TYPES = tuple(t.value for t in AccountType)
VAT_OPTIONS = tuple(v.value for v in AccountVatOption)
OPEN_ITEM_KINDS = tuple(k.value for k in OpenItemHistoryKind)
DUE_REQUIRED_KINDS = (OpenItemHistoryKind.RECEIVABLE.value, OpenItemHistoryKind.SPECIAL_LEVY.value)
CENT = Decimal("0.01")

W3_FIELDS: dict[ReportType, tuple[Field, ...]] = {
    # M8-02: SEPA overview per object; interval and due day are required, a mandate is only
    # recorded when reference, creditor id, signature date, IBAN and an evidence document exist.
    ReportType.SEPA_OVERVIEW: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("unit_number", "text", True, label="Einheitennummer"),
        Field("contact_external_id", "text", True, label="Kontakt-ID Zahler"),
        Field("kind", "choice", True, ("tenancy", "ownership"), "Vertragsart"),
        Field("interval", "choice", True, INTERVALS, "Zahlweise (Intervall)"),
        Field("due_day", "decimal", True, label="Fälligkeitstag im Monat (1 bis 31)"),
        Field("due_day_rule", "choice", False, DUE_DAY_RULES, "Fälligkeitsregel"),
        Field("valid_from", "date", True, label="Gültig ab"),
        Field("mandate_reference", "text", label="Mandatsreferenz"),
        Field("creditor_id", "text", label="Gläubiger-ID"),
        Field("signed_at", "date", label="Unterschriftsdatum des Mandats"),
        Field("mandate_type", "choice", False, MANDATE_TYPES, "Mandatsart"),
        Field("sequence", "choice", False, SEQUENCES, "Sequenz"),
        Field("iban", "text", label="IBAN des Zahlers"),
        Field("evidence_document_id", "text", label="Nachweisdokument (Dokument-ID der Plattform)"),
    ),
    # M8-03: chart of accounts per object (ledger).
    ReportType.CHART_OF_ACCOUNTS: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("ledger_kind", "choice", False, LEDGER_KINDS, "Rechtsträgerart des Buchungskreises"),
        Field("number", "text", True, label="Kontonummer"),
        Field("name", "text", True, label="Kontobezeichnung"),
        Field("category", "choice", True, CATEGORIES, "Kontokategorie"),
        Field("account_type", "choice", True, ACCOUNT_TYPES, "Kontoart"),
        Field("vat_option", "choice", False, VAT_OPTIONS, "Umsatzsteueroption"),
    ),
    # M8-04: historical bank transactions, optionally with the journal entry identifier.
    ReportType.BANK_HISTORY: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("iban", "text", True, label="IBAN des Objektkontos"),
        Field("booking_date", "date", True, label="Buchungsdatum"),
        Field("value_date", "date", label="Wertstellung"),
        Field("amount", "decimal", True, label="Betrag (Gutschrift positiv)"),
        Field("counterpart_name", "text", label="Name Gegenseite"),
        Field("counterpart_iban", "text", label="IBAN Gegenseite"),
        Field("purpose", "text", label="Verwendungszweck"),
        Field("bank_reference", "text", label="Bankreferenz"),
        Field("end_to_end_id", "text", label="End-to-End-ID"),
        Field("journal_entry_id", "text", label="Buchungsnummer im Journal des Altsystems"),
    ),
    # M8-06: documents of the DMS with object number and contract reference.
    ReportType.DOCUMENT_INDEX: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("document_ref", "text", True, label="Dokument (Quell-ID oder Dateiname im DMS)"),
        Field("unit_number", "text", label="Einheitennummer"),
        Field(
            "contract_ref", "text", label="Vertragsbezug (Vertragsnummer Altsystem oder Plattform)"
        ),
    ),
    # M8-06: historical tickets, read only.
    ReportType.TICKET_HISTORY: (
        Field("source_ticket_id", "text", True, label="Ticketnummer im Altsystem"),
        Field("property_number", "text", True, label="Objektnummer"),
        Field("unit_number", "text", label="Einheitennummer"),
        Field("contact_external_id", "text", label="Kontakt-ID"),
        Field("title", "text", True, label="Betreff"),
        Field("status_text", "text", label="Status im Altsystem"),
        Field("created_on", "date", True, label="Angelegt am"),
        Field("closed_on", "date", label="Erledigt am"),
        Field("description", "text", label="Beschreibung"),
    ),
    # M8-07: open items with original due date and partial payments, credits, deposits,
    # reserves, loans and special levies.
    ReportType.OPEN_ITEMS: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("ledger_kind", "choice", False, LEDGER_KINDS, "Rechtsträgerart des Buchungskreises"),
        Field("kind", "choice", True, OPEN_ITEM_KINDS, "Art des Postens"),
        Field("source_item_id", "text", True, label="Posten-ID oder Belegnummer im Altsystem"),
        Field("unit_number", "text", label="Einheitennummer"),
        Field("contact_external_id", "text", label="Kontakt-ID"),
        Field("original_due_date", "date", label="Ursprungsfälligkeit"),
        Field("original_amount", "decimal", True, label="Ursprungsbetrag"),
        Field("paid_amount", "decimal", label="Bisher bezahlt (Teilzahlungen)"),
        Field("open_amount", "decimal", label="Offener Betrag"),
        Field("description", "text", label="Bezeichnung"),
        Field("resolution_ref", "text", label="Beschluss (Bezeichnung oder Version)"),
    ),
}

# Registers the target fields with the shared pipeline (``services`` imports this module).
FIELDS.update(W3_FIELDS)

# Amount field summed into the test run and apply report (source vs. created).
AMOUNT_FIELD: dict[ReportType, str] = {
    ReportType.BANK_HISTORY: "amount",
    ReportType.OPEN_ITEMS: "original_amount",
}


def handles(report_type: ReportType) -> bool:
    return report_type in W3_FIELDS


def _prop_number(value: Any) -> str:
    return normalise_property_number(value) or ""


async def _property(session: AsyncSession, number: Any) -> Property | None:
    row: Property | None = await session.scalar(
        select(Property).where(Property.number == _prop_number(number))
    )
    return row


async def _ledger(
    session: AsyncSession, prop: Property, kind: str | None
) -> tuple[Ledger | None, str | None]:
    """The ledger of the object; a second ledger (for example HOA and rental owner) needs the
    legal entity kind, a guess is never made."""
    query = (
        select(Ledger)
        .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
        .where(LegalEntity.property_id == prop.id)
    )
    if kind:
        query = query.where(LegalEntity.kind == LegalEntityKind(kind))
    ledgers = (await session.scalars(query)).all()
    if not ledgers:
        return None, f"Kein Buchungskreis zu Objekt {prop.number}"
    if len(ledgers) > 1:
        return None, "Mehrere Buchungskreise zum Objekt: Rechtsträgerart angeben"
    return ledgers[0], None


# SEPA overview --------------------------------------------------------------------------


async def _sepa(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: contract (object, unit, kind, party, start before valid-from) and valid-from of the
    schedule. Creates the payment schedule and, with complete evidence, the mandate."""
    from mhvp.imports import services as svc

    unit = await svc._unit(session, _prop_number(v["property_number"]), v["unit_number"])
    contact = await svc._contact(session, v["contact_external_id"])
    party = await svc._party_of(session, contact) if contact else None
    if unit is None or party is None:
        return RowStatus.INVALID, None, None, ["Einheit oder Vertragspartei fehlt"]
    due_day_value = Decimal(v["due_day"])
    if due_day_value != due_day_value.to_integral_value() or not 1 <= due_day_value <= 31:
        return (
            RowStatus.INVALID,
            None,
            None,
            ["Fälligkeitstag muss eine ganze Zahl von 1 bis 31 sein"],
        )
    due_day = int(due_day_value)
    valid_from = date.fromisoformat(v["valid_from"])
    contract = await session.scalar(
        select(Contract)
        .where(
            Contract.unit_id == unit.id,
            Contract.kind == ContractKind(v["kind"]),
            Contract.party_id == party.id,
            Contract.start_date <= valid_from,
        )
        .order_by(Contract.start_date.desc())
        .limit(1)
    )
    if contract is None:
        return RowStatus.INVALID, None, None, ["Kein passender Vertrag zum Gültig-ab-Datum"]
    interval = PaymentInterval(v["interval"])
    rule = DueDayRule(v.get("due_day_rule") or "day")
    notes: list[str] = []
    active = await session.scalar(
        select(PaymentSchedule)
        .where(PaymentSchedule.contract_id == contract.id, PaymentSchedule.valid_to.is_(None))
        .order_by(PaymentSchedule.valid_from.desc())
        .limit(1)
    )
    schedule_id: uuid.UUID
    if active is not None and (
        active.interval is interval and active.due_day == due_day and active.due_day_rule is rule
    ):
        status = RowStatus.UNCHANGED
        schedule_id = active.id
    else:
        later = await session.scalar(
            select(PaymentSchedule.id).where(
                PaymentSchedule.contract_id == contract.id,
                PaymentSchedule.valid_from >= valid_from,
            )
        )
        if later is not None:
            return (
                RowStatus.CONFLICT,
                "payment_schedule",
                later,
                ["Zahlungsplan mit gleichem oder späterem Beginn und anderen Werten vorhanden"],
            )
        row = PaymentSchedule(
            tenant_id=principal.tenant_id,
            contract_id=contract.id,
            interval=interval,
            due_day_rule=rule,
            due_day=due_day,
            valid_from=valid_from,
        )
        try:
            async with session.begin_nested():
                await contract_services.add_schedule(session, contract, row)
                await session.flush()
        except ProblemError as exc:
            return RowStatus.INVALID, None, None, [str(exc.detail)]
        status, schedule_id = RowStatus.CREATED, row.id
    notes += await _sepa_mandate(session, principal, v, contract, party.id)
    return status, "payment_schedule", schedule_id, notes


_MANDATE_KEYS = (
    "mandate_reference",
    "creditor_id",
    "signed_at",
    "iban",
    "evidence_document_id",
)


async def _sepa_mandate(
    session: AsyncSession,
    principal: Any,
    v: dict[str, Any],
    contract: Contract,
    party_id: uuid.UUID,
) -> list[str]:
    """Mandate recording with evidence; every gap is a note, never a guess (13.1, 4.5)."""
    given = [k for k in _MANDATE_KEYS if v.get(k)]
    if not given:
        return []
    missing = [k for k in _MANDATE_KEYS if not v.get(k)]
    if missing:
        return [f"Mandat nicht angelegt, Angaben fehlen: {', '.join(missing)}"]
    existing = await session.scalar(
        select(SepaMandate).where(
            SepaMandate.creditor_id == v["creditor_id"],
            SepaMandate.reference == v["mandate_reference"],
        )
    )
    if existing is not None:
        ok = existing.party_id == party_id and existing.legal_entity_id == contract.legal_entity_id
        return [] if ok else ["Mandat mit dieser Referenz gehört zu einer anderen Partei"]
    try:
        iban = validate_iban(v["iban"])
    except InvalidValueError as exc:
        return [f"Mandat nicht angelegt, IBAN ungültig: {exc}"]
    try:
        document_id = uuid.UUID(str(v["evidence_document_id"]))
    except ValueError:
        return ["Mandat nicht angelegt, Nachweisdokument ist keine Dokument-ID"]
    if await session.get(Document, document_id) is None:
        return ["Mandat nicht angelegt, Nachweisdokument nicht gefunden"]
    account = await session.scalar(
        select(ContactBankAccount)
        .join(PartyMember, PartyMember.contact_id == ContactBankAccount.contact_id)
        .where(
            PartyMember.party_id == party_id,
            ContactBankAccount.iban_fingerprint == crypto.fingerprint(iban),
        )
        .limit(1)
    )
    if account is None:
        return ["Mandat nicht angelegt, IBAN ist beim Kontakt nicht hinterlegt"]
    mandate_type = MandateType(v.get("mandate_type") or "core")
    try:
        await contract_services.check_b2b(session, party_id, mandate_type)
    except ProblemError as exc:
        return [f"Mandat nicht angelegt: {exc.detail}"]
    notes: list[str] = []
    if getattr(account, "approval_status", "approved") != "approved":
        notes.append("Freigabe der IBAN am Kontakt (Vier-Augen) steht noch aus")
    if not v.get("sequence"):
        notes.append("Sequenz nicht angegeben, 'recurring' angenommen (A-Q08-01)")
    mandate = SepaMandate(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        party_id=party_id,
        legal_entity_id=contract.legal_entity_id,
        contact_bank_account_id=account.id,
        reference=v["mandate_reference"],
        creditor_id=v["creditor_id"],
        signed_at=date.fromisoformat(v["signed_at"]),
        type=mandate_type,
        sequence=MandateSequence(v.get("sequence") or "recurring"),
        status=MandateStatus.ACTIVE,
        document_id=document_id,
    )
    session.add(mandate)
    await session.flush()
    if contract.sepa_mandate_id is None:
        contract.sepa_mandate_id = mandate.id
        contract.direct_debit = True
        await session.flush()
    return notes


# Chart of accounts ----------------------------------------------------------------------


async def _chart_account(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: ledger of the object and six digit account number (shorter numbers are zero padded,
    A-047). Existing accounts are never changed. New accounts carry review status ``entwurf``:
    tax classification stays with a person."""
    prop = await _property(session, v["property_number"])
    if prop is None:
        return RowStatus.INVALID, None, None, [f"Objekt {v['property_number']} fehlt"]
    ledger, problem = await _ledger(session, prop, v.get("ledger_kind"))
    if ledger is None:
        return RowStatus.INVALID, None, None, [problem or "Buchungskreis fehlt"]
    number = normalise_account_number(v["number"])
    if number is None or len(number) != 6:
        return RowStatus.INVALID, None, None, [f"Kontonummer {v['number']!r} nicht sechsstellig"]
    existing = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == number
        )
    )
    if existing is not None:
        same = (
            existing.category.value == v["category"]
            and existing.type.value == v["account_type"]
            and existing.name.strip() == v["name"].strip()[:200]
        )
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "ledger_account",
            existing.id,
            [] if same else ["Konto vorhanden mit abweichenden Angaben"],
        )
    account = LedgerAccount(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        ledger_id=ledger.id,
        number=number,
        name=v["name"].strip()[:200],
        category=AccountCategory(v["category"]),
        type=AccountType(v["account_type"]),
        vat_option=AccountVatOption(v.get("vat_option") or "none"),
        review_status="entwurf",
        review_note="Import Immoware24, Einordnung prüfen",
        is_system=False,
    )
    session.add(account)
    await session.flush()
    return RowStatus.CREATED, "ledger_account", account.id, []


# Historical bank transactions -----------------------------------------------------------


async def _bank_history(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: object account (IBAN), bank reference, without one a hash of the row with its
    occurrence number in the file (two equal payments stay two). The transaction arrives as
    ``ignored``: it is history, no posting, no matching. The link to the migrated journal entry
    is completed by a repeated run once that journal is imported."""
    prop = await _property(session, v["property_number"])
    if prop is None:
        return RowStatus.INVALID, None, None, [f"Objekt {v['property_number']} fehlt"]
    try:
        iban = validate_iban(v["iban"])
    except InvalidValueError as exc:
        return RowStatus.INVALID, None, None, [f"IBAN ungültig: {exc}"]
    account = await session.scalar(
        select(PropertyBankAccount).where(
            PropertyBankAccount.iban_fingerprint == crypto.fingerprint(iban)
        )
    )
    if account is None:
        return RowStatus.INVALID, None, None, ["Objektkonto mit dieser IBAN nicht hinterlegt"]
    if account.property_id != prop.id:
        return RowStatus.INVALID, None, None, ["Die IBAN gehört zu einem anderen Objekt"]
    booking = date.fromisoformat(v["booking_date"])
    ledger = await session.scalar(
        select(Ledger).where(Ledger.legal_entity_id == account.legal_entity_id)
    )
    notes: list[str] = []
    if ledger is not None and ledger.migration_cutoff is not None:
        if booking > ledger.migration_cutoff:
            return (
                RowStatus.INVALID,
                None,
                None,
                ["Umsatz liegt nach dem Stichtag der Migration (laufender Bankabruf)"],
            )
    else:
        notes.append("Stichtag der Migration am Buchungskreis fehlt, Doppelerfassung nicht geprüft")
    counterpart_iban = None
    if v.get("counterpart_iban"):
        try:
            counterpart_iban = validate_iban(v["counterpart_iban"])
        except InvalidValueError:
            notes.append("IBAN der Gegenseite ungültig, nicht übernommen")
    raw_tx = RawTransaction(
        bank_reference=v.get("bank_reference"),
        booking_date=booking,
        value_date=date.fromisoformat(v["value_date"]) if v.get("value_date") else None,
        amount=Decimal(v["amount"]).quantize(CENT),
        currency="EUR",
        counterpart_name=(v.get("counterpart_name") or None),
        counterpart_iban=counterpart_iban,
        counterpart_bic=None,
        purpose=v.get("purpose"),
        end_to_end_id=v.get("end_to_end_id"),
        mandate_reference=None,
        creditor_id=None,
        transaction_code=None,
    )
    digest = content_hash(account.iban_fingerprint, raw_tx)
    reference = v.get("bank_reference")
    if not reference:
        seen: dict[str, int] = ctx.setdefault("seen", {})
        seen[digest] = seen.get(digest, 0) + 1
        reference = f"MIG:{digest[:40]}:{seen[digest]}"
    existing = await session.scalar(
        select(BankTransaction).where(
            BankTransaction.property_bank_account_id == account.id,
            BankTransaction.bank_reference == reference,
        )
    )
    entry_id: uuid.UUID | None = None
    source_entry = v.get("journal_entry_id")
    if source_entry and ledger is not None:
        entry_id = await session.scalar(
            select(MigratedJournalEntry.id).where(
                MigratedJournalEntry.ledger_id == ledger.id,
                MigratedJournalEntry.source == SOURCE,
                MigratedJournalEntry.source_entry_id == source_entry,
            )
        )
    if existing is not None:
        link = await session.scalar(
            select(MigratedBankLink).where(MigratedBankLink.bank_transaction_id == existing.id)
        )
        if link is None and source_entry:
            session.add(
                MigratedBankLink(
                    tenant_id=principal.tenant_id,
                    bank_transaction_id=existing.id,
                    journal_entry_id=entry_id,
                    source_entry_id=source_entry,
                    source_file_id=ctx.get("source_file_id"),
                    row_number=ctx.get("row_number"),
                )
            )
            await session.flush()
        elif link is not None and link.journal_entry_id is None and entry_id is not None:
            link.journal_entry_id = entry_id
            await session.flush()
        if existing.amount != raw_tx.amount or existing.booking_date != booking:
            return (
                RowStatus.CONFLICT,
                "bank_transaction",
                existing.id,
                ["Umsatz mit dieser Referenz vorhanden mit anderem Betrag oder Datum"],
            )
        return RowStatus.UNCHANGED, "bank_transaction", existing.id, notes
    tx = BankTransaction(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        property_bank_account_id=account.id,
        legal_entity_id=account.legal_entity_id,
        bank_reference=reference,
        booking_date=booking,
        value_date=raw_tx.value_date,
        amount=raw_tx.amount,
        currency="EUR",
        counterpart_name=raw_tx.counterpart_name,
        counterpart_iban=counterpart_iban,
        counterpart_iban_fingerprint=crypto.fingerprint(counterpart_iban)
        if counterpart_iban
        else None,
        purpose=raw_tx.purpose,
        end_to_end_id=raw_tx.end_to_end_id,
        hash=digest,
        raw={
            "migration": {
                "source": SOURCE,
                "history": True,
                "row_number": ctx.get("row_number"),
                "journal_entry_ref": source_entry,
            }
        },
        status=TransactionStatus.IGNORED,
    )
    session.add(tx)
    await session.flush()
    if source_entry:
        session.add(
            MigratedBankLink(
                tenant_id=principal.tenant_id,
                bank_transaction_id=tx.id,
                journal_entry_id=entry_id,
                source_entry_id=source_entry,
                source_file_id=ctx.get("source_file_id"),
                row_number=ctx.get("row_number"),
            )
        )
        await session.flush()
        if entry_id is None:
            notes.append("Journalbuchung noch nicht importiert, Zuordnung offen")
    else:
        notes.append("Ohne Journalzuordnung")
    return RowStatus.CREATED, "bank_transaction", tx.id, notes


# Document index -------------------------------------------------------------------------


async def _document_index(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Links an existing DMS document (taken over before) to object, unit and contract.
    Key: document, entity and role; no document is created, moved or deleted."""
    prop = await _property(session, v["property_number"])
    if prop is None:
        return RowStatus.INVALID, None, None, [f"Objekt {v['property_number']} fehlt"]
    ref = v["document_ref"]
    docs = (
        await session.scalars(select(Document).where(Document.source_id == ref[:64]).limit(2))
    ).all()
    if not docs:
        docs = (
            await session.scalars(select(Document).where(Document.filename == ref).limit(2))
        ).all()
    if not docs:
        return RowStatus.INVALID, None, None, ["Dokument im DMS nicht gefunden (vorher übernehmen)"]
    if len(docs) > 1:
        return RowStatus.INVALID, None, None, ["Dokumentbezug nicht eindeutig (mehrere Treffer)"]
    document = docs[0]
    targets: list[tuple[str, uuid.UUID]] = [("property", prop.id)]
    if v.get("unit_number"):
        from mhvp.imports import services as svc

        unit = await svc._unit(session, prop.number, v["unit_number"])
        if unit is None:
            return RowStatus.INVALID, None, None, [f"Einheit {v['unit_number']} fehlt"]
        targets.append(("unit", unit.id))
    if v.get("contract_ref"):
        key = await session.scalar(
            select(ImportExternalKey.entity_id).where(
                ImportExternalKey.source_system == SOURCE,
                ImportExternalKey.entity_type == "contract",
                ImportExternalKey.external_key == v["contract_ref"][:100],
            )
        )
        contract_id = key or await session.scalar(
            select(Contract.id)
            .where(Contract.number == v["contract_ref"], Contract.property_id == prop.id)
            .limit(1)
        )
        if contract_id is None:
            return RowStatus.INVALID, None, None, ["Vertragsbezug nicht gefunden"]
        targets.append(("contract", contract_id))
    created = 0
    for entity_type, entity_id in targets:
        known = await session.scalar(
            select(DocumentLink.id).where(
                DocumentLink.document_id == document.id,
                DocumentLink.entity_type == entity_type,
                DocumentLink.entity_id == entity_id,
                DocumentLink.role == LinkRole.ATTACHMENT,
            )
        )
        if known is None:
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    created_by=principal.user_id,
                    document_id=document.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    role=LinkRole.ATTACHMENT,
                )
            )
            created += 1
    await session.flush()
    status = RowStatus.CREATED if created else RowStatus.UNCHANGED
    return status, "document", document.id, []


# Historical tickets ---------------------------------------------------------------------


async def _ticket_history(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: ticket number of the old system. Read only history, no live ticket (no SLA, no
    notification, no assignment)."""
    from mhvp.imports import services as svc

    prop = await _property(session, v["property_number"])
    if prop is None:
        return RowStatus.INVALID, None, None, [f"Objekt {v['property_number']} fehlt"]
    created_on = date.fromisoformat(v["created_on"])
    closed_on = date.fromisoformat(v["closed_on"]) if v.get("closed_on") else None
    if closed_on is not None and closed_on < created_on:
        return RowStatus.INVALID, None, None, ["Erledigt am liegt vor Angelegt am"]
    unit_id = contact_id = None
    if v.get("unit_number"):
        unit = await svc._unit(session, prop.number, v["unit_number"])
        if unit is None:
            return RowStatus.INVALID, None, None, [f"Einheit {v['unit_number']} fehlt"]
        unit_id = unit.id
    if v.get("contact_external_id"):
        contact = await svc._contact(session, v["contact_external_id"])
        if contact is None:
            return RowStatus.INVALID, None, None, ["Kontakt fehlt"]
        contact_id = contact.id
    existing = await session.scalar(
        select(MigratedTicket).where(
            MigratedTicket.source == SOURCE,
            MigratedTicket.source_ticket_id == v["source_ticket_id"][:100],
        )
    )
    if existing is not None:
        same = (
            existing.property_id == prop.id
            and existing.title == v["title"][:300]
            and existing.created_on == created_on
            and existing.closed_on == closed_on
        )
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "migrated_ticket",
            existing.id,
            [] if same else ["Ticket vorhanden mit abweichenden Angaben"],
        )
    row = MigratedTicket(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        source=SOURCE,
        source_ticket_id=v["source_ticket_id"][:100],
        property_id=prop.id,
        unit_id=unit_id,
        contact_id=contact_id,
        title=v["title"][:300],
        status_text=(v.get("status_text") or None),
        created_on=created_on,
        closed_on=closed_on,
        description=v.get("description"),
        source_file_id=ctx.get("source_file_id"),
    )
    session.add(row)
    await session.flush()
    return RowStatus.CREATED, "migrated_ticket", row.id, []


# Open items -----------------------------------------------------------------------------


async def _open_item(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: ledger, kind and item id of the old system. Amount rules: paid amount may not exceed
    the original amount (a credit is its own kind), the open amount is original minus paid and
    a stated open amount must agree. Stored read only next to the opening balance sums."""
    from mhvp.imports import services as svc

    prop = await _property(session, v["property_number"])
    if prop is None:
        return RowStatus.INVALID, None, None, [f"Objekt {v['property_number']} fehlt"]
    kind = v["kind"]
    original = Decimal(v["original_amount"]).quantize(CENT)
    paid = Decimal(v.get("paid_amount") or "0").quantize(CENT)
    if original < 0 or paid < 0:
        return (
            RowStatus.INVALID,
            None,
            None,
            ["Beträge ohne Vorzeichen angeben (Art des Postens bestimmt die Richtung)"],
        )
    if paid > original:
        return RowStatus.INVALID, None, None, ["Bezahlter Betrag übersteigt den Ursprungsbetrag"]
    open_amount = original - paid
    if v.get("open_amount") and Decimal(v["open_amount"]).quantize(CENT) != open_amount:
        return (
            RowStatus.INVALID,
            None,
            None,
            [f"Offener Betrag passt nicht zu Betrag und Teilzahlung (erwartet {open_amount})"],
        )
    if kind in DUE_REQUIRED_KINDS and not v.get("original_due_date"):
        return RowStatus.INVALID, None, None, ["Ursprungsfälligkeit fehlt"]
    ledger, problem = await _ledger(session, prop, v.get("ledger_kind"))
    if ledger is None:
        return RowStatus.INVALID, None, None, [problem or "Buchungskreis fehlt"]
    unit_id = contact_id = None
    if v.get("unit_number"):
        unit = await svc._unit(session, prop.number, v["unit_number"])
        if unit is None:
            return RowStatus.INVALID, None, None, [f"Einheit {v['unit_number']} fehlt"]
        unit_id = unit.id
    if v.get("contact_external_id"):
        contact = await svc._contact(session, v["contact_external_id"])
        if contact is None:
            return RowStatus.INVALID, None, None, ["Kontakt fehlt"]
        contact_id = contact.id
    due = date.fromisoformat(v["original_due_date"]) if v.get("original_due_date") else None
    item_id = v["source_item_id"][:100]
    existing = await session.scalar(
        select(MigratedOpenItem).where(
            MigratedOpenItem.ledger_id == ledger.id,
            MigratedOpenItem.source == SOURCE,
            MigratedOpenItem.kind == kind,
            MigratedOpenItem.source_item_id == item_id,
        )
    )
    if existing is not None:
        same = (
            existing.original_amount == original
            and existing.paid_amount == paid
            and existing.original_due_date == due
        )
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "migrated_open_item",
            existing.id,
            [] if same else ["Posten vorhanden mit abweichenden Werten"],
        )
    row = MigratedOpenItem(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        ledger_id=ledger.id,
        source=SOURCE,
        kind=kind,
        source_item_id=item_id,
        property_id=prop.id,
        unit_id=unit_id,
        contact_id=contact_id,
        original_due_date=due,
        original_amount=original,
        paid_amount=paid,
        open_amount=open_amount,
        description=(v.get("description") or None),
        resolution_ref=(v.get("resolution_ref") or None),
        cutoff_date=ledger.migration_cutoff,
        source_file_id=ctx.get("source_file_id"),
    )
    session.add(row)
    await session.flush()
    return RowStatus.CREATED, "migrated_open_item", row.id, []


HANDLERS: dict[ReportType, Any] = {
    ReportType.SEPA_OVERVIEW: _sepa,
    ReportType.CHART_OF_ACCOUNTS: _chart_account,
    ReportType.BANK_HISTORY: _bank_history,
    ReportType.DOCUMENT_INDEX: _document_index,
    ReportType.TICKET_HISTORY: _ticket_history,
    ReportType.OPEN_ITEMS: _open_item,
}


async def apply_row(
    session: AsyncSession,
    principal: Any,
    report_type: ReportType,
    values: dict[str, Any],
    ctx: dict[str, Any],
) -> Result:
    result: Result = await HANDLERS[report_type](session, principal, values, ctx)
    return result


async def open_item_summary(session: AsyncSession, ledger_id: uuid.UUID) -> dict[str, Any]:
    """Sums of the imported single items per kind (for the comparison with the opening
    balance sums and the Immoware24 figures)."""
    rows = (
        await session.execute(
            select(
                MigratedOpenItem.kind,
                func.count(),
                func.coalesce(func.sum(MigratedOpenItem.original_amount), 0),
                func.coalesce(func.sum(MigratedOpenItem.paid_amount), 0),
                func.coalesce(func.sum(MigratedOpenItem.open_amount), 0),
            )
            .where(MigratedOpenItem.ledger_id == ledger_id)
            .group_by(MigratedOpenItem.kind)
        )
    ).all()
    return {
        kind: {
            "count": count,
            "original": str(original),
            "paid": str(paid),
            "open": str(open_),
        }
        for kind, count, original, paid, open_ in rows
    }
