"""Kautionsabrechnung as a PDF draft (M5-02, docs/rules/M5-02-kautionsabrechnung.md).

Builds and stores the deposit settlement letter on the tenant's letterhead
(``mhvp.documents.letters``, DIN 5008): positions of the deposit basis, the interest per year
(mode and rate/days, when computed), deductions with their reason, the payout amount and the
tenant's bank account, masked (only the tenant transfers the amount later, and only after a
manual, gate-locked payout; the letter is never a payment instruction). The document is linked
to the contract and to the tenant's contact and stays a draft: it neither books nor pays
anything (G1/G3 unaffected, rule 0.1.7). The applicable interest rate and any Zinseszins
question stay a legal assessment to be confirmed (docs/rules/M5-02-kautionsabrechnung.md).
"""

from __future__ import annotations

import html
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.table_mapper import mask_iban
from mhvp.contacts import recipients
from mhvp.contacts.models import ContactBankAccount
from mhvp.contracts import deposit_settlement as ds
from mhvp.contracts.models import Contract, Deposit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.models import DocumentSource, LinkRole

DRAFT_LABEL = "Entwurf, kein Versand, keine Auszahlung"
CENT = Decimal("0.01")

INTEREST_MODE_LABELS: dict[str, str] = {
    "individual": "individuell je Jahr erfasst",
    "reference_rate": "gesetzlicher Referenzzinssatz je Jahr",
    "deposit_rates": "Zinssatz der Kaution mit Gültigkeit ab Datum",
    "none": "ohne Verzinsung",
}


def fmt_eur(value: Decimal) -> str:
    quantized = value.quantize(CENT)
    sign = "-" if quantized < 0 else ""
    whole, cents = f"{abs(quantized):.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{'.'.join(groups)},{cents} EUR"


def fmt_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


async def _tenant_bank_account(
    session: AsyncSession, contact_id: uuid.UUID
) -> ContactBankAccount | None:
    result = await session.scalar(
        select(ContactBankAccount)
        .where(
            ContactBankAccount.contact_id == contact_id,
            ContactBankAccount.is_default.is_(True),
        )
        .limit(1)
    )
    return result if isinstance(result, ContactBankAccount) else None


def _interest_rows(row: ds.DepositSettlement) -> list[list[str]]:
    out: list[list[str]] = []
    for year in row.interest_years:
        rate = year.get("rate")
        rate_text = f"{Decimal(str(rate)):.5f} %" if rate is not None else "-"
        out.append(
            [
                str(year["year"]),
                rate_text,
                f"{year['days']} Tage",
                fmt_eur(Decimal(str(year["amount"]))),
            ]
        )
    return out


def _deduction_rows(row: ds.DepositSettlement) -> list[list[str]]:
    return [
        [str(d.get("label") or "Einbehalt"), fmt_eur(Decimal(str(d["amount"])))]
        for d in row.deductions
    ]


async def build_letter(
    session: AsyncSession,
    *,
    row: ds.DepositSettlement,
    deposit: Deposit,
    contract: Contract,
    letter_date: date,
    head: letters.Letterhead,
) -> tuple[letters.Letter, uuid.UUID, str]:
    """Assemble the settlement letter. Returns (letter, tenant contact id, unit line)."""
    from mhvp.properties.models import Property, Unit

    debtor_id = await recipients.debtor_contact_id(session, contract.party_id)
    if debtor_id is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Für den Mieter ist kein Kontakt mit Anschrift erfasst."
        )
    contact, recipient_lines, _ = await docs.recipient(session, debtor_id)
    unit = await session.get(Unit, contract.unit_id)
    prop = await session.get(Property, contract.property_id) if unit is not None else None
    unit_line = " ".join(
        p
        for p in (
            getattr(prop, "street", None),
            getattr(prop, "house_number", None),
            f"Einheit {unit.number}" if unit is not None and unit.number else None,
        )
        if p
    )

    account = await _tenant_bank_account(session, debtor_id)
    account_line = (
        f"{account.holder or contact.display_name}, IBAN {mask_iban(account.iban)}"
        if account is not None
        else "keine Bankverbindung des Mieters hinterlegt"
    )

    interest_mode_label = INTEREST_MODE_LABELS.get(row.interest_mode.value, row.interest_mode.value)
    tables = {
        "basis": letters.LetterTable(
            header=["Position", "Betrag"],
            rows=[
                ["Einzahlungen", fmt_eur(row.principal_paid)],
                ["abzüglich Verrechnungen", fmt_eur(-row.offsets_recorded)],
                ["abzüglich bisheriger Auszahlungen", fmt_eur(-row.payouts_recorded)],
                [
                    "Guthaben vor Zinsen",
                    fmt_eur(row.principal_paid - row.offsets_recorded - row.payouts_recorded),
                ],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
    }
    interest_rows = _interest_rows(row)
    if interest_rows:
        tables["zinsen"] = letters.LetterTable(
            header=["Jahr", "Satz", "Tage", "Zinsen"],
            rows=[*interest_rows, ["Summe Zinsen", "", "", fmt_eur(row.interest_total)]],
            right_aligned=(3,),
            total_row=True,
            widths=(0.2, 0.25, 0.25, 0.3),
        )
    deduction_rows = _deduction_rows(row)
    if deduction_rows:
        tables["einbehalte"] = letters.LetterTable(
            header=["Einbehalt (Begründung)", "Betrag"],
            rows=[*deduction_rows, ["Summe Einbehalte", fmt_eur(row.deductions_total)]],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        )
    tables["auszahlung"] = letters.LetterTable(
        header=["Ermittlung des Auszahlungsbetrags", "Betrag"],
        rows=[
            [
                "Guthaben vor Zinsen",
                fmt_eur(row.principal_paid - row.offsets_recorded - row.payouts_recorded),
            ],
            ["zuzüglich Zinsen gesamt", fmt_eur(row.interest_total)],
            ["abzüglich Einbehalte gesamt", fmt_eur(-row.deductions_total)],
            ["Auszahlungsbetrag", fmt_eur(row.payout_amount)],
        ],
        right_aligned=(1,),
        total_row=True,
        widths=(0.7, 0.3),
    )

    subject = f"Kautionsabrechnung {unit_line}".strip()
    paragraphs = [
        "Sehr geehrte Damen und Herren,",
        f"zum Ende des Mietverhältnisses {unit_line} erhalten Sie die Abrechnung Ihrer "
        f"Mietkaution zum {fmt_date(row.settlement_date)}. Grundlage sind die erfassten "
        "Einzahlungen, Verrechnungen und Auszahlungen des Kautionskontos.",
        letters.TABLE_MARKER.format(name="basis"),
    ]
    if "zinsen" in tables:
        paragraphs.append(
            f"Verzinsung ({interest_mode_label}), jahresweise ermittelt (Regel M5-02, Zinssatz "
            "als Einschätzung, keine rechtsverbindliche Feststellung):"
        )
        paragraphs.append(letters.TABLE_MARKER.format(name="zinsen"))
    else:
        paragraphs.append(f"Verzinsung: {interest_mode_label}.")
    if "einbehalte" in tables:
        paragraphs.append("Einbehalte mit Begründung:")
        paragraphs.append(letters.TABLE_MARKER.format(name="einbehalte"))
    paragraphs.append(letters.TABLE_MARKER.format(name="auszahlung"))
    paragraphs.append(
        f"Die Auszahlung erfolgt auf das Konto {account_line}. Dieses Schreiben ist ein "
        "Entwurf und weder eine Zahlungsanweisung noch ein Zahlungsversprechen; die "
        "Auszahlung bleibt ein gesonderter, freizugebender Vorgang."
    )
    if row.note:
        paragraphs.append(html.escape(row.note))

    letter = letters.Letter(
        recipient_lines=recipient_lines,
        subject=subject,
        body="\n\n".join(p if p.startswith("[[table:") else html.escape(p) for p in paragraphs),
        letter_date=letter_date,
        info=[
            ("Zinsart", interest_mode_label),
            ("Auszahlungsbetrag", fmt_eur(row.payout_amount)),
        ],
        signatory=[str(head.company.get("name", ""))],
        tables=tables,
        draft_notice=DRAFT_LABEL,
    )
    return letter, debtor_id, unit_line


async def store(
    session: AsyncSession,
    blobs: Any,
    *,
    row: ds.DepositSettlement,
    contract: Contract,
    tenant_contact_id: uuid.UUID,
    letter_date: date,
    pdf: bytes,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    """File the settlement letter in the document index, linked to contract and contact."""
    document = await docs.store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=pdf,
        title=f"Kautionsabrechnung (Entwurf), {contract.number}",
        filename=f"{letter_date.isoformat()}_kautionsabrechnung_{contract.number}.pdf",
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=[
            ("contract", contract.id, LinkRole.GENERATED),
            ("contact", tenant_contact_id, LinkRole.GENERATED),
        ],
        created_by=user_id,
    )
    row.document_id = document.id
    row.updated_by = user_id
    await session.flush()
    return document.id
