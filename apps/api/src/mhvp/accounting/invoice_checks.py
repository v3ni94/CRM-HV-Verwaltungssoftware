"""Further deterministic checks of the incoming invoice (7.9.1 PÜ01 to PÜ05, M14-01 to M14-09).

Every function returns findings (hints) only; nothing here changes a review status, releases,
posts or pays (PÜ05: no status turns "green" without an actual review). The checklist of
mandatory data follows the enumeration of PÜ01 in the master prompt; it is a product checklist,
not a legal statement on the mandatory content of an invoice (R21, docs/rules/M14-PU.md).
"""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Invoice, InvoiceKind, Ledger, PostingStatus

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def mandatory_checklist(invoice: Invoice) -> list[dict[str, Any]]:
    """PÜ01 enumeration as a checklist: item, label, present. Shown at the invoice."""
    items = [
        ("original", "Originalrechnung", invoice.document_id is not None),
        ("issuer", "Rechnungsaussteller", invoice.provider_contact_id is not None),
        ("recipient", "Rechnungsempfänger", bool(invoice.recipient_name)),
        ("service_place", "Leistungsort", bool(invoice.service_place)),
        ("service_period", "Leistungszeit", invoice.service_from is not None),
        ("number", "Rechnungsnummer", bool(invoice.number)),
        ("amounts", "Beträge", invoice.gross is not None),
        (
            "tax_data",
            "Steuerangaben des Ausstellers",
            bool(invoice.issuer_vat_id or invoice.issuer_tax_number),
        ),
        (
            "order",
            "Bezug zu Auftrag oder Vertrag",
            bool(
                invoice.order_reference
                or invoice.service_contract_id
                or getattr(invoice, "work_order_id", None)
            ),
        ),
    ]
    return [{"item": k, "label": label, "present": ok} for k, label, ok in items]


def completeness_findings(invoice: Invoice, fiscal_year_start_month: int = 1) -> list[str]:
    """PÜ01: missing place and tax data of the issuer, plausibility of the service period."""
    out: list[str] = []
    if not invoice.service_place:
        out.append("Leistungsort fehlt (PÜ01)")
    if not (invoice.issuer_vat_id or invoice.issuer_tax_number):
        out.append("Steuerangaben des Ausstellers fehlen (USt-IdNr. oder Steuernummer, PÜ01)")
    if invoice.service_from and invoice.service_to and invoice.service_to < invoice.service_from:
        out.append("Leistungszeitraum: Ende liegt vor dem Beginn")
    if invoice.service_from and (invoice.service_from - invoice.invoice_date).days > 366:
        out.append("Leistungszeitraum beginnt mehr als ein Jahr nach dem Rechnungsdatum")
    if invoice.service_from and invoice.service_to:
        start_year = _fiscal_year(invoice.service_from, fiscal_year_start_month)
        if _fiscal_year(invoice.service_to, fiscal_year_start_month) != start_year:
            out.append(
                "Leistungszeitraum reicht über das Wirtschaftsjahr hinaus: Abgrenzung prüfen"
            )
    return out


def _fiscal_year(day: date, start_month: int) -> int:
    return day.year if day.month >= start_month else day.year - 1


def stated_discount(invoice: Invoice) -> Decimal | None:
    if invoice.discount_percent is None:
        return None
    return (invoice.gross * invoice.discount_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def payable_amount(invoice: Invoice, deducted: Decimal = ZERO) -> Decimal:
    """Gross minus deducted partial invoices, prepayments and security retention (PÜ03).
    The expense posting stays at the invoice effect; a retention stays a liability."""
    return (
        invoice.gross
        - deducted
        - (invoice.prepaid_amount or ZERO)
        - (invoice.retention_amount or ZERO)
    )


def amount_findings(invoice: Invoice) -> list[str]:
    """PÜ03: stated cash discount recomputed, payments on account, retention, tax markers."""
    out: list[str] = []
    expected = stated_discount(invoice)
    if invoice.discount_amount is not None:
        if expected is None:
            out.append("Skontobetrag angegeben, aber kein Skontosatz")
        elif expected != invoice.discount_amount:
            out.append(f"Skonto nachgerechnet {expected} statt angegeben {invoice.discount_amount}")
    for label, value in (
        ("Anzahlung", invoice.prepaid_amount),
        ("Sicherheitseinbehalt", invoice.retention_amount),
    ):
        if value is not None and value < 0:
            out.append(f"{label} ist negativ")
    deducted = sum((Decimal(str(d.get("gross", "0"))) for d in invoice.deductions), ZERO)
    if payable_amount(invoice, deducted) < 0:
        out.append("Abzüge, Anzahlungen und Einbehalt übersteigen den Rechnungsbetrag")
    if invoice.reverse_charge:
        out.append("Reverse Charge gekennzeichnet: Fachprüfung durch Steuerberater (PÜ03, R23)")
        # GA08-01 (7.11 S01): own release point, never an automatic application.
        out.append(
            "Möglicher Fall des § 13b UStG: gesonderter Freigabepunkt (R23), keine Automatik; "
            "Normzuordnung und Steuerschuldnerschaft vor der Freigabe vom Steuerberater bestätigen"
        )
        if invoice.vat != 0:
            out.append("Reverse Charge gekennzeichnet, aber Umsatzsteuer ausgewiesen")
    if invoice.construction_withholding:
        out.append(
            "Bauleistung mit möglicher Bauabzugsteuer gekennzeichnet: Freistellung prüfen (R23)"
        )
    return out


async def contract_findings(session: AsyncSession, invoice: Invoice) -> list[str]:
    """PÜ02: the linked service contract belongs to the issuer and covers the service period."""
    if invoice.service_contract_id is None:
        return []
    from mhvp.contracts.service_contracts import ServiceContract

    contract = await session.get(ServiceContract, invoice.service_contract_id)
    if contract is None:
        return ["Verknüpfter Dienstleistervertrag nicht gefunden"]
    out: list[str] = []
    if contract.provider_contact_id != invoice.provider_contact_id:
        out.append("Dienstleistervertrag gehört zu einem anderen Aussteller")
    start = invoice.service_from or invoice.invoice_date
    end = invoice.service_to or start
    if start < contract.starts_at:
        out.append("Leistungszeitraum beginnt vor dem Vertragsbeginn")
    last = contract.cancelled_at or contract.ends_at
    if last is not None and end > last:
        out.append("Leistungszeitraum liegt nach dem Vertragsende oder der Kündigung")
    return out


async def conflict_findings(session: AsyncSession, invoice: Invoice) -> list[str]:
    """PÜ02: affiliated issuer or conflict of interest (hint only, no judgement): the issuer
    carries the name of a legal entity of the tenant (group company, manager), is recorded
    as owner, manager or board member, belongs to the party of the ledger's legal entity, or
    is related to such a contact."""
    from mhvp.contacts.models import (
        Contact,
        ContactRelation,
        ContactType,
        ContactTypeCode,
        PartyMember,
    )
    from mhvp.properties.models import LegalEntity

    provider = await session.get(Contact, invoice.provider_contact_id)
    if provider is None:
        return []
    out: list[str] = []
    ledger = await session.get(Ledger, invoice.ledger_id)
    own = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
    name = _norm(provider.display_name)
    entities = (await session.scalars(select(LegalEntity))).all()
    for entity in entities:
        if name and _norm(entity.name) == name:
            out.append(
                f"Aussteller trägt den Namen eines Rechtsträgers der Verwaltung: {entity.name}"
                " (verbundenes Unternehmen prüfen)"
            )
            break
    watched = {"eigentuemer": "Eigentümer", "verwalter": "Verwalter"}
    for role in provider.roles or []:
        if role in watched:
            out.append(
                f"Aussteller ist zugleich als {watched[role]} geführt (Interessenkonflikt prüfen)"
            )
    types = set(
        (
            await session.scalars(
                select(ContactType.type).where(ContactType.contact_id == provider.id)
            )
        ).all()
    )
    if ContactTypeCode.BOARD_MEMBER in types:
        out.append("Aussteller ist als Beiratsmitglied geführt (Interessenkonflikt prüfen)")
    members: set[uuid.UUID] = set()
    if own is not None and own.party_id is not None:
        members = set(
            (
                await session.scalars(
                    select(PartyMember.contact_id).where(PartyMember.party_id == own.party_id)
                )
            ).all()
        )
        if provider.id in members:
            out.append("Aussteller gehört zum Rechtsträger des Buchungskreises")
    related = set(
        (
            await session.scalars(
                select(ContactRelation.related_contact_id).where(
                    ContactRelation.contact_id == provider.id
                )
            )
        ).all()
    ) | set(
        (
            await session.scalars(
                select(ContactRelation.contact_id).where(
                    ContactRelation.related_contact_id == provider.id
                )
            )
        ).all()
    )
    if related & members:
        out.append("Aussteller steht in Beziehung zu einem Mitglied des Rechtsträgers")
    if related:
        flagged = await session.scalar(
            select(func.count())
            .select_from(ContactType)
            .where(
                ContactType.contact_id.in_(related),
                ContactType.type.in_([ContactTypeCode.BOARD_MEMBER, ContactTypeCode.MANAGER]),
            )
        )
        if flagged:
            out.append("Aussteller steht in Beziehung zu Beirat oder Verwaltung")
    return out


async def reference_findings(session: AsyncSession, invoice: Invoice) -> list[str]:
    """PÜ01/PÜ05: a credit note needs its original; the effect on the open item is checked."""
    if invoice.kind is not InvoiceKind.CREDIT_NOTE:
        return []
    if invoice.reference_invoice_id is None:
        return ["Gutschrift ohne Bezug zur Ursprungsrechnung"]
    original = await session.get(Invoice, invoice.reference_invoice_id)
    if original is None:
        return ["Ursprungsrechnung der Gutschrift nicht gefunden"]
    out: list[str] = []
    if (
        original.provider_contact_id != invoice.provider_contact_id
        or original.ledger_id != invoice.ledger_id
    ):
        out.append("Ursprungsrechnung gehört zu anderem Aussteller oder Buchungskreis")
    if original.kind is InvoiceKind.CREDIT_NOTE:
        out.append("Bezug auf eine Gutschrift statt auf eine Rechnung")
    if original.posting_status is not PostingStatus.POSTED:
        out.append("Ursprungsrechnung ist nicht gebucht: kein offener Posten zum Ausgleich")
    other = await session.scalar(
        select(func.coalesce(func.sum(Invoice.gross), 0)).where(
            Invoice.reference_invoice_id == original.id,
            Invoice.kind == InvoiceKind.CREDIT_NOTE,
            Invoice.id != invoice.id,
            Invoice.posting_status != PostingStatus.REVERSED,
        )
    )
    if Decimal(other or 0) + invoice.gross > original.gross:
        out.append(f"Gutschriften übersteigen die Ursprungsrechnung ({original.gross} EUR brutto)")
    return out


async def duplicate_findings(session: AsyncSession, invoice: Invoice) -> list[str]:
    """PÜ04: the same file received twice (mail, DMS, upload) by content hash, and a changed
    IBAN against the superseded version."""
    from mhvp.documents.models import Document

    out: list[str] = []
    doc_ids = [invoice.document_id] if invoice.document_id else []
    doc_ids += [uuid.UUID(str(d)) for d in invoice.attachment_document_ids or []]
    if doc_ids:
        hashes = set(
            (await session.scalars(select(Document.sha256).where(Document.id.in_(doc_ids)))).all()
        )
        if hashes:
            same_docs = select(Document.id).where(Document.sha256.in_(hashes))
            clash = await session.scalar(
                select(Invoice.number).where(
                    Invoice.id != invoice.id,
                    Invoice.document_id.in_(same_docs),
                    Invoice.document_id.not_in(doc_ids),
                    Invoice.id != invoice.supersedes_id
                    if invoice.supersedes_id
                    else Invoice.id == Invoice.id,
                )
            )
            if clash:
                out.append(
                    f"Inhaltsgleiche Datei liegt bereits bei Rechnung {clash} (E-Mail, DMS oder"
                    " Upload): Doppelrechnung oder korrigierte Version prüfen"
                )
    if invoice.supersedes_id:
        previous = await session.get(Invoice, invoice.supersedes_id)
        if (
            previous is not None
            and previous.payee_iban_fingerprint
            and invoice.payee_iban_fingerprint
            and previous.payee_iban_fingerprint != invoice.payee_iban_fingerprint
            and invoice.iban_confirmed_by is None
        ):
            out.append("IBAN weicht von der Vorversion der Rechnung ab: gesondert bestätigen")
    return out


async def all_findings(session: AsyncSession, invoice: Invoice) -> list[str]:
    ledger = await session.get(Ledger, invoice.ledger_id)
    start_month = ledger.fiscal_year_start_month if ledger else 1
    return [
        *completeness_findings(invoice, start_month),
        *amount_findings(invoice),
        *await contract_findings(session, invoice),
        *await conflict_findings(session, invoice),
        *await reference_findings(session, invoice),
        *await duplicate_findings(session, invoice),
        *await factual_findings(session, invoice),
    ]


async def factual_findings(session: AsyncSession, invoice: Invoice) -> list[str]:
    """M14-02: order, resolution, budget, recurring plan and line comparison (PÜ02). The
    responsibility proposal is returned by the factual check endpoint, not as a finding."""
    from mhvp.accounting import invoice_factual

    result = await invoice_factual.factual_check(session, invoice)
    return [
        f["message"]
        for f in result.findings
        if f["area"] != "responsibility" and f["code"] not in INFO_ONLY_CODES
    ]


# Shown by the factual check endpoint only, not stored at the invoice (no new warning for an
# invoice that keeps the free text order reference, M14-02).
INFO_ONLY_CODES = {"order_free_text"}
