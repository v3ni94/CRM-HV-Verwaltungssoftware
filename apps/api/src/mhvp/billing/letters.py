"""Tenant letters for an operating cost statement (7.6 A07, M17, task A34).

One letter per tenant (contract) from the statement's result snapshot only: the tenant's
share of costs, the advances due and paid, the result (Guthaben, Nachzahlung or ausgeglichen)
and a proposal for the new monthly advance. Nothing is calculated from live data and no AI
text is involved: every amount is read from ``statement_snapshot.results`` (A01, A07). The
letter is a draft on the tenant's letterhead (DIN 5008 via ``mhvp.documents.letters``); the
dispatch stays behind G3 and is not implemented (``send`` is always refused).

Proposal rule (A07): the master prompt keeps "neue Vorauszahlungsvorschläge" as a function
without prescribing a formula. Until the operator releases one (docs/OPEN_QUESTIONS.md
M17-05), the proposal is the tenant's costs of the period divided by twelve, rounded to the
cent, and is labelled as a proposal in the letter. A tenancy that ended within the period
gets no proposal (no future advances); a tenancy that started within the period gets the
proposal with the hint that the tenant's period is shorter than the statement period. A
change of the advances is a separate step under § 560 BGB (A04) and is never triggered here.
"""

import html
import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.models import Statement, StatementSnapshot
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.models import DocumentSource, LinkRole

DRAFT_LABEL = "Entwurf, kein Versand"
PROPOSAL_LABEL = "Vorschlag, Anpassung erfolgt gesondert"
MONTHS = Decimal(12)
CENT = Decimal("0.01")


def fmt_eur(value: Decimal) -> str:
    """``1.234,56 EUR`` (rule 10, section 4.1)."""
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


def advance_proposal(costs: Decimal) -> Decimal:
    """Costs of the period divided by twelve, rounded half up to the cent (see module doc)."""
    if costs <= 0:
        return Decimal("0.00")
    return (costs / MONTHS).quantize(CENT, rounding=ROUND_HALF_UP)


def result_kind(balance: Decimal) -> str:
    if balance > 0:
        return "nachzahlung"
    if balance < 0:
        return "guthaben"
    return "ausgeglichen"


@dataclass
class TenantLetter:
    contract_id: uuid.UUID
    unit_number: str
    contact_id: uuid.UUID
    contact_name: str
    letter: letters.Letter
    costs: Decimal
    advances_due: Decimal
    advances_paid: Decimal
    balance: Decimal
    result: str
    proposal: Decimal | None
    proposal_note: str | None
    hints: list[str]
    links: list[tuple[str, uuid.UUID]]
    filename: str
    document_id: uuid.UUID | None = None
    pdf: bytes = field(default=b"", repr=False)


def _body(
    *,
    greeting: str,
    object_line: str,
    period_from: date,
    period_to: date,
    tenant_from: date,
    tenant_to: date,
    costs: Decimal,
    advances_due: Decimal,
    advances_paid: Decimal,
    balance: Decimal,
    proposal: Decimal | None,
    proposal_note: str | None,
) -> str:
    lines = [
        html.escape(greeting),
        html.escape(
            f"für {object_line} erhalten Sie die Betriebskostenabrechnung für den Zeitraum "
            f"{fmt_date(period_from)} bis {fmt_date(period_to)}"
            + (
                f" (Ihr Nutzungszeitraum: {fmt_date(tenant_from)} bis {fmt_date(tenant_to)})"
                if (tenant_from, tenant_to) != (period_from, period_to)
                else ""
            )
            + ". Die Abrechnung mit den Einzelpositionen und Verteilerschlüsseln liegt bei."
        ),
        "\n".join(
            html.escape(row)
            for row in (
                f"Ihr Anteil an den Betriebskosten: {fmt_eur(costs)}",
                f"Vorauszahlungen laut Vertrag im Zeitraum: {fmt_eur(advances_due)}",
                f"Geleistete Vorauszahlungen: {fmt_eur(advances_paid)}",
            )
        ),
    ]
    kind = result_kind(balance)
    if kind == "nachzahlung":
        lines.append(
            html.escape(f"Ergebnis: Nachzahlung zu Ihren Lasten in Höhe von {fmt_eur(balance)}.")
        )
    elif kind == "guthaben":
        lines.append(
            html.escape(f"Ergebnis: Guthaben zu Ihren Gunsten in Höhe von {fmt_eur(-balance)}.")
        )
    else:
        lines.append(
            "Ergebnis: Die geleisteten Vorauszahlungen entsprechen Ihrem Kostenanteil, "
            "es ergibt sich weder ein Guthaben noch eine Nachzahlung."
        )
    if proposal is not None:
        lines.append(
            html.escape(
                f"Vorschlag für die neue monatliche Betriebskostenvorauszahlung: "
                f"{fmt_eur(proposal)} ({PROPOSAL_LABEL}). Grundlage ist Ihr Kostenanteil des "
                f"Abrechnungszeitraums geteilt durch zwölf Monate."
                + (f" {proposal_note}" if proposal_note else "")
            )
        )
    else:
        lines.append(
            html.escape(
                "Ein Vorschlag für eine neue Vorauszahlung entfällt, da das Mietverhältnis "
                "innerhalb des Abrechnungszeitraums geendet hat."
            )
        )
    lines.append(
        "Dieses Schreiben ist ein Entwurf. Zahlungs- und Erstattungsmodalitäten sowie "
        "Fristen werden mit der Ausgabe der Abrechnung mitgeteilt."
    )
    return "\n\n".join(lines)


async def build(
    session: AsyncSession,
    statement: Statement,
    snapshot: StatementSnapshot,
    head: letters.Letterhead,
    letter_date: date,
    *,
    contract_id: uuid.UUID | None = None,
) -> list[TenantLetter]:
    """Assemble one letter per tenant from the snapshot only (no recalculation)."""
    from mhvp.contacts.models import Party, PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Property, Unit

    prop = await session.get(Property, statement.property_id)
    rows = [
        r
        for r in snapshot.results.get("results", [])
        if contract_id is None or str(r["contract_id"]) == str(contract_id)
    ]
    if not rows:
        raise ProblemError(
            ErrorCodes.RESOURCE_NOT_FOUND,
            detail="Kein Mieterergebnis im Snapshot der Abrechnung.",
        )
    out: list[TenantLetter] = []
    for row in rows:
        cid = uuid.UUID(str(row["contract_id"]))
        contract = await session.get(Contract, cid)
        if contract is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht gefunden.")
        party = await session.get(Party, contract.party_id)
        member = (
            await session.scalar(
                select(PartyMember)
                .where(PartyMember.party_id == party.id)
                .order_by(PartyMember.created_at)
                .limit(1)
            )
            if party is not None
            else None
        )
        if member is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Einheit {row['unit_number']}: der Mieter hat keinen Kontakt mit Anschrift."
                ),
            )
        contact, recipient_lines, recipient = await docs.recipient(session, member.contact_id)
        unit = await session.get(Unit, contract.unit_id)

        costs = Decimal(row["costs"])
        advances_due = Decimal(row["advances_due"])
        advances_paid = Decimal(row["advances_paid"])
        balance = Decimal(row["balance"])
        tenant_from = date.fromisoformat(row["from"])
        tenant_to = date.fromisoformat(row["to"])
        ended = tenant_to < statement.period_to
        proposal = None if ended else advance_proposal(costs)
        proposal_note = (
            "Ihr Nutzungszeitraum ist kürzer als der Abrechnungszeitraum; der Vorschlag ist "
            "daher gesondert zu prüfen."
            if proposal is not None and tenant_from > statement.period_from
            else None
        )
        hints: list[str] = []
        if row.get("late_claim_blocked"):
            hints.append(
                "Nachforderung gesperrt: Fristorientierung überschritten, geprüfte Ausnahme "
                "erforderlich (A04, M17-04). Kein Versand."
            )
        if proposal_note:
            hints.append(proposal_note)

        object_parts = []
        if prop is not None:
            object_parts.append(f"Objekt {prop.number} {prop.name}")
        object_parts.append(
            f"Einheit {unit.label or unit.number}" if unit else f"Einheit {row['unit_number']}"
        )
        object_line = ", ".join(object_parts)
        kind = result_kind(balance)
        subject = html.escape(
            f"Betriebskostenabrechnung {fmt_date(statement.period_from)} bis "
            f"{fmt_date(statement.period_to)}: "
            + {"nachzahlung": "Nachzahlung", "guthaben": "Guthaben", "ausgeglichen": "Ergebnis"}[
                kind
            ]
            + f", {object_line}"
        )
        body = _body(
            greeting=str(recipient["anrede"]),
            object_line=object_line,
            period_from=statement.period_from,
            period_to=statement.period_to,
            tenant_from=tenant_from,
            tenant_to=tenant_to,
            costs=costs,
            advances_due=advances_due,
            advances_paid=advances_paid,
            balance=balance,
            proposal=proposal,
            proposal_note=proposal_note,
        )
        info = [
            ("Status", DRAFT_LABEL),
            ("Unser Zeichen", f"BK-{str(statement.id)[:8]}-{row['unit_number']}"),
            ("Abrechnung", f"Version {statement.version}, Stand {snapshot.hash[:12]}"),
        ]
        if prop is not None:
            info.append(("Objekt", f"{prop.number} {prop.name}"))
        letter = letters.Letter(
            recipient_lines=recipient_lines,
            subject=subject,
            body=body,
            letter_date=letter_date,
            info=info,
            signatory=[s for s in (str(head.company.get("name", "")),) if s],
        )
        links: list[tuple[str, uuid.UUID]] = [("contract", contract.id)]
        if unit is not None:
            links.append(("unit", unit.id))
        if prop is not None:
            links.append(("property", prop.id))
        filename = (
            f"{letter_date.isoformat()}_betriebskosten_{row['unit_number']}_"
            f"{contact.display_name}.pdf"
        )
        out.append(
            TenantLetter(
                contract_id=contract.id,
                unit_number=str(row["unit_number"]),
                contact_id=contact.id,
                contact_name=contact.display_name,
                letter=letter,
                costs=costs,
                advances_due=advances_due,
                advances_paid=advances_paid,
                balance=balance,
                result=kind,
                proposal=proposal,
                proposal_note=proposal_note,
                hints=hints,
                links=links,
                filename=filename[:255],
            )
        )
    return out


def render(head: letters.Letterhead, drafts: list[TenantLetter]) -> None:
    for draft in drafts:
        draft.pdf = letters.render_pdf(head, draft.letter)


def bundle(drafts: list[TenantLetter]) -> bytes:
    """One PDF with all letters in unit order (A07: gebündelte Ausgabe)."""
    writer = PdfWriter()
    for draft in drafts:
        for page in PdfReader(io.BytesIO(draft.pdf)).pages:
            writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


async def store(
    session: AsyncSession,
    blobs: Any,
    *,
    statement: Statement,
    drafts: list[TenantLetter],
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> None:
    """File each letter as a generated document linked to contract, unit, property and
    contact (11.3). Drafts only; nothing is sent and the statement status stays as it is."""
    for draft in drafts:
        document = await docs.store_document(
            session,
            blobs,
            tenant_id=tenant_id,
            data=draft.pdf,
            title=(
                f"Betriebskostenabrechnung {statement.period_from.year} (Entwurf), "
                f"{draft.contact_name}, Einheit {draft.unit_number}"
            ),
            filename=draft.filename,
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("contact", draft.contact_id, LinkRole.GENERATED)]
            + [(t, i, LinkRole.GENERATED) for t, i in draft.links],
            created_by=user_id,
        )
        draft.document_id = document.id
    await session.flush()


def summary(draft: TenantLetter) -> dict[str, Any]:
    return {
        "contract_id": draft.contract_id,
        "unit_number": draft.unit_number,
        "contact_id": draft.contact_id,
        "contact_name": draft.contact_name,
        "costs": str(draft.costs),
        "advances_due": str(draft.advances_due),
        "advances_paid": str(draft.advances_paid),
        "balance": str(draft.balance),
        "result": draft.result,
        "advance_proposal": str(draft.proposal) if draft.proposal is not None else None,
        "advance_proposal_label": PROPOSAL_LABEL if draft.proposal is not None else None,
        "hints": draft.hints,
        "document_id": draft.document_id,
        "filename": draft.filename,
    }
