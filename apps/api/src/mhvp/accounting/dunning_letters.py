"""Dunning letters as PDF drafts (M16-02 partially, 7.5, DIN 5008 form B via
``mhvp.documents.letters``).

The sender is the managing company of the tenant (tenant settings, the same letterhead every
generated letter uses); the letter states on whose behalf it is written (the claim holder's
legal entity: the WEG for Hausgeld, the Vermieter for rent). Fee, interest and payment
deadline only ever come from the effective dunning settings of the property (tenant default
with object override, M16-10); nothing is assumed when a value is missing (0.1.3): a missing
fee means no fee line, a missing ``payment_days`` means no deadline date, a missing
``letter_text`` means the neutral standard paragraph. The letter never asserts default
(Verzug) on its own; interest, when configured, is shown as an approximation.

Dispatch stays locked: no endpoint sends a letter (G1/G2 closed, M16-02). Every PDF carries
``Entwurf`` in the info block; only a person can mark a case as sent (``mark_sent``).
"""

import html
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import dunning
from mhvp.accounting.models import DunningCase, Ledger
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.models import LinkRole

DRAFT_LABEL = "Entwurf, kein Versand"


def fmt_eur(value: Decimal) -> str:
    """``1.234,56 EUR`` (rule 10, section 4.1)."""
    quantized = value.quantize(Decimal("0.01"))
    sign = "-" if quantized < 0 else ""
    whole, cents = f"{abs(quantized):.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{'.'.join(groups)},{cents} EUR"


def fmt_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


@dataclass
class LetterDraft:
    letter: letters.Letter
    contact_id: uuid.UUID
    contact_name: str
    links: list[tuple[str, uuid.UUID]]
    level_text: str
    filename: str


def _body(
    *,
    greeting: str,
    claim_holder: str,
    object_line: str,
    open_items: list[dict[str, Any]],
    total: Decimal,
    fee: Decimal,
    interest: Decimal,
    payment_deadline: date | None,
    letter_text: str | None,
) -> str:
    lines = [
        f"für {object_line} führen wir im Auftrag von {claim_holder} nach unseren Unterlagen "
        "folgende offene Beträge:",
        "",
    ]
    for item in sorted(open_items, key=lambda i: str(i["due_date"])):
        due = date.fromisoformat(str(item["due_date"]))
        lines.append(f"Fällig am {fmt_date(due)}: {fmt_eur(Decimal(str(item['remaining'])))}")
    lines.append(f"Offener Betrag gesamt: {fmt_eur(total)}")
    grand_total = total
    if fee > 0:
        lines.append(f"Mahngebühr laut hinterlegter Mahnstufe: {fmt_eur(fee)}")
        grand_total += fee
    if interest > 0:
        lines.append(f"Verzugszinsen (Näherung, gesetzlicher Verzugszins): {fmt_eur(interest)}")
        grand_total += interest
    if grand_total != total:
        lines.append(f"Zu zahlender Gesamtbetrag: {fmt_eur(grand_total)}")
    paragraphs = ["\n".join(lines)]
    if letter_text:
        paragraphs.append(letter_text.strip())
    elif payment_deadline is not None:
        paragraphs.append(
            f"Bitte überweisen Sie den Gesamtbetrag von {fmt_eur(grand_total)} bis zum "
            f"{fmt_date(payment_deadline)} auf das Ihnen bekannte Konto."
        )
    else:
        paragraphs.append(
            f"Bitte gleichen Sie den Gesamtbetrag von {fmt_eur(grand_total)} auf das Ihnen "
            "bekannte Konto aus."
        )
    paragraphs.append(
        "Sollten Sie den Betrag in der Zwischenzeit bereits überwiesen haben, betrachten Sie "
        "dieses Schreiben bitte als gegenstandslos. Bei Fragen zu den offenen Positionen "
        "stehen wir Ihnen gern zur Verfügung."
    )
    return html.escape(greeting) + "\n\n" + "\n\n".join(html.escape(p) for p in paragraphs)


async def build(
    session: AsyncSession, case: DunningCase, head: letters.Letterhead, letter_date: date
) -> LetterDraft:
    """Assemble the letter for a case from stored data only."""
    from mhvp.contacts.models import Party, PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import LegalEntity, Property, Unit

    if case.status == "excluded":
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für ausgeschlossene Fälle wird kein Mahnschreiben erzeugt."
        )
    ledger = await session.get(Ledger, case.ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    claim_holder = await session.get(LegalEntity, ledger.legal_entity_id)
    contract = await session.get(Contract, case.contract_id) if case.contract_id else None
    if contract is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Dem Mahnfall ist kein Vertrag zugeordnet."
        )
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
            ErrorCodes.VALIDATION, detail="Der Schuldner hat keinen Kontakt mit Anschrift."
        )
    contact, recipient_lines, recipient = await docs.recipient(session, member.contact_id)
    unit = await session.get(Unit, contract.unit_id) if contract.unit_id else None
    prop = await session.get(Property, ledger.property_id) if ledger.property_id else None

    settings = await dunning.settings_for(session, ledger.property_id)
    config = dunning.level_config(settings, case.level) if settings else None
    level_text = str(config.get("text") or f"Mahnstufe {case.level}") if config else "Mahnung"
    payment_days = config.get("payment_days") if config else None
    payment_deadline = (
        letter_date + timedelta(days=int(payment_days)) if payment_days is not None else None
    )
    letter_text = str(config.get("letter_text")) if config and config.get("letter_text") else None

    object_parts = []
    if prop is not None:
        object_parts.append(f"Objekt {prop.number} {prop.name}")
    if unit is not None:
        object_parts.append(f"Einheit {unit.label or unit.number}")
    object_line = ", ".join(object_parts) or f"Vertrag {contract.number}"
    holder_name = claim_holder.name if claim_holder is not None else "dem Forderungsinhaber"

    subject = html.escape(f"{level_text}: offene Forderungen, {object_line}")
    body = _body(
        greeting=str(recipient["anrede"]),
        claim_holder=holder_name,
        object_line=object_line,
        open_items=case.open_items,
        total=case.total,
        fee=case.fee_amount,
        interest=case.interest_amount,
        payment_deadline=payment_deadline,
        letter_text=letter_text,
    )
    info = [
        ("Status", DRAFT_LABEL),
        ("Unser Zeichen", f"MW-{str(case.id)[:8]}"),
        ("Mahnstufe", f"{case.level} {level_text}"),
    ]
    if prop is not None:
        info.append(("Objekt", f"{prop.number} {prop.name}"))
    signatory = [str(head.company.get("name", "")), f"im Auftrag von {holder_name}"]
    letter = letters.Letter(
        recipient_lines=recipient_lines,
        subject=subject,
        body=body,
        letter_date=letter_date,
        info=info,
        signatory=[s for s in signatory if s],
    )
    links: list[tuple[str, uuid.UUID]] = [("contract", contract.id)]
    if unit is not None:
        links.append(("unit", unit.id))
    if prop is not None:
        links.append(("property", prop.id))
    filename = f"{letter_date.isoformat()}_mahnung_stufe{case.level}_{contact.display_name}.pdf"
    return LetterDraft(
        letter=letter,
        contact_id=contact.id,
        contact_name=contact.display_name,
        links=links,
        level_text=level_text,
        filename=filename[:255],
    )


def render(head: letters.Letterhead, draft: LetterDraft) -> bytes:
    return letters.render_pdf(head, draft.letter)


async def store(
    session: AsyncSession,
    blobs: Any,
    *,
    case: DunningCase,
    draft: LetterDraft,
    pdf: bytes,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    """File the draft in the document index and link it to the case (11.3); nothing is sent."""
    from mhvp.documents.models import DocumentSource

    document = await docs.store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=pdf,
        title=f"{draft.level_text} (Entwurf), {draft.contact_name}",
        filename=draft.filename,
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=[("contact", draft.contact_id, LinkRole.GENERATED)]
        + [(t, i, LinkRole.GENERATED) for t, i in draft.links],
        created_by=user_id,
    )
    case.letter_document_id = document.id
    case.updated_by = user_id
    await session.flush()
    return document.id
