"""Dunning letters as PDF drafts (M16-02 partially, 7.5, DIN 5008 form B via
``mhvp.documents.letters``) and the PDF export of the Mahnbescheid preparation (A31, M16-07).

The sender is the managing company of the tenant (tenant settings, the same letterhead every
generated letter uses); the letter states on whose behalf it is written (the claim holder's
legal entity: the WEG for Hausgeld, the Vermieter for rent). Fee, interest and payment
deadline only ever come from the effective dunning settings of the property (tenant default
with object override, M16-10); nothing is assumed when a value is missing (0.1.3): a missing
fee means no fee line, a missing ``payment_days`` means no deadline date, a missing
``letter_text`` means the neutral standard paragraph of the level. The letter never asserts
default (Verzug) and names no legal consequences; interest, when configured, is shown as an
approximation.

Text modules (A33): every level has a neutral standard text (Zahlungserinnerung, 1., 2., 3.
Mahnung, keyed by level number) consisting of an intro paragraph, the Forderungsaufstellung
table (Posten, Fälligkeit, Betrag, Summe) and a request paragraph. ``letter_text`` per level
replaces the request paragraph and may use the placeholders of :data:`PLACEHOLDERS`.
``{frist}`` only yields a date when ``payment_days`` is set, ``{bankverbindung}`` only names an
account when one is released for the letter (M16-13, no storage yet: the caller passes
``bank_account=None`` and the sentence falls back to "auf das Ihnen bekannte Konto").

Dispatch stays locked: no endpoint sends a letter (G1/G2 closed, M16-02). Every PDF carries
``Entwurf`` in the info block; only a person can mark a case as sent (``mark_sent``).
"""

import html
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import dunning
from mhvp.accounting.models import (
    DunningCase,
    DunningMahnbescheidPrep,
    DunningRun,
    JournalEntry,
    Ledger,
    OpenItem,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.models import LinkRole

DRAFT_LABEL = "Entwurf, kein Versand"
MAHNBESCHEID_NOTICE = "Vorbereitung, Prüfung durch Rechtsanwalt erforderlich, kein Antrag"
TABLE_NAME = "forderungen"
HISTORY_TABLE = "historie"

# Placeholders a ``letter_text`` may use. ``frist`` and ``bankverbindung`` are phrases, not
# bare values, so that a text stays a complete sentence without them (M16-12, M16-13).
PLACEHOLDERS: dict[str, str] = {
    "frist": 'Phrase "bis zum TT.MM.JJJJ", leer ohne hinterlegte Zahlungsfrist (payment_days)',
    "bankverbindung": (
        'Phrase "auf das Konto ..." mit freigegebener Bankverbindung, sonst '
        '"auf das Ihnen bekannte Konto"'
    ),
    "gesamtbetrag": "zu zahlender Gesamtbetrag im Format 1.234,56 EUR",
    "forderungsinhaber": "Name des Forderungsinhabers (Rechtsträger)",
    "objekt": "Objekt und Einheit",
    "stufe": "Bezeichnung der Mahnstufe",
}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

# Neutral standard texts per level number (A-041): no assertion of default, no legal
# consequences, no fee or interest outside the configured values. The request paragraph is
# what ``letter_text`` replaces.
STANDARD_TEXTS: dict[int, dict[str, str]] = {
    1: {
        "intro": (
            "für {objekt} sind nach unseren Unterlagen die nachfolgend aufgeführten Beträge "
            "noch offen. Wir erinnern im Auftrag von {forderungsinhaber} an den Ausgleich."
        ),
        "request": (
            "Bitte überweisen Sie den Gesamtbetrag von {gesamtbetrag} {frist} {bankverbindung}."
        ),
    },
    2: {
        "intro": (
            "trotz unserer Zahlungserinnerung sind für {objekt} nach unseren Unterlagen die "
            "nachfolgend aufgeführten Beträge weiterhin offen. Im Auftrag von "
            "{forderungsinhaber} mahnen wir den Ausgleich an."
        ),
        "request": (
            "Bitte überweisen Sie den Gesamtbetrag von {gesamtbetrag} {frist} {bankverbindung}."
        ),
    },
    3: {
        "intro": (
            "auch nach unserer 1. Mahnung sind für {objekt} nach unseren Unterlagen die "
            "nachfolgend aufgeführten Beträge weiterhin offen. Im Auftrag von "
            "{forderungsinhaber} mahnen wir den Ausgleich erneut an."
        ),
        "request": (
            "Bitte überweisen Sie den Gesamtbetrag von {gesamtbetrag} {frist} "
            "{bankverbindung}. Sollten Sie die Forderung ganz oder teilweise für unberechtigt "
            "halten, teilen Sie uns dies bitte schriftlich mit."
        ),
    },
    4: {
        "intro": (
            "auch nach unserer 2. Mahnung sind für {objekt} nach unseren Unterlagen die "
            "nachfolgend aufgeführten Beträge weiterhin offen. Im Auftrag von "
            "{forderungsinhaber} fordern wir Sie letztmalig zum Ausgleich auf."
        ),
        "request": (
            "Bitte überweisen Sie den Gesamtbetrag von {gesamtbetrag} {frist} "
            "{bankverbindung}. Sollten Sie die Forderung ganz oder teilweise für unberechtigt "
            "halten oder eine Ratenzahlung wünschen, setzen Sie sich bitte umgehend mit uns "
            "in Verbindung."
        ),
    },
}

CLOSING_HINT = (
    "Sollten Sie den Betrag in der Zwischenzeit bereits überwiesen haben, betrachten Sie "
    "dieses Schreiben bitte als gegenstandslos. Bei Fragen zu den offenen Positionen "
    "stehen wir Ihnen gern zur Verfügung."
)

SAMPLE_ITEMS: list[dict[str, Any]] = [
    {"label": "Hausgeld Februar 2026", "due_date": "2026-02-03", "remaining": "350.00"},
    {"label": "Hausgeld März 2026", "due_date": "2026-03-03", "remaining": "350.00"},
]


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


def standard_text(level: int) -> dict[str, str]:
    """Standard text of a level number; levels above the ladder use the last module."""
    return STANDARD_TEXTS.get(level) or STANDARD_TEXTS[max(STANDARD_TEXTS)]


def check_letter_text(text: str) -> None:
    """Refuse unknown placeholders at save time (a typo never prints as ``{frsit}``)."""
    unknown = sorted({m for m in _PLACEHOLDER_RE.findall(text) if m not in PLACEHOLDERS})
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Unbekannte Platzhalter im Brieftext: {', '.join(unknown)}. Erlaubt sind: "
                f"{', '.join('{' + k + '}' for k in PLACEHOLDERS)}."
            ),
        )


def fill(text: str, values: dict[str, str]) -> str:
    """Substitute placeholders; an empty phrase leaves no double spaces or blanks before
    punctuation behind."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Unbekannter Platzhalter {{{key}}} im Brieftext."
            )
        return values[key]

    out = _PLACEHOLDER_RE.sub(repl, text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([.,;:])", r"\1", out)
    return out.strip()


@dataclass
class ClaimTable:
    """Forderungsaufstellung: rows of (label, due date text, amount) plus the totals."""

    rows: list[tuple[str, str, Decimal]]
    total: Decimal
    fee: Decimal
    interest: Decimal

    @property
    def grand_total(self) -> Decimal:
        return self.total + self.fee + self.interest

    def as_table(self) -> letters.LetterTable:
        rows = [[label, due, fmt_eur(amount)] for label, due, amount in self.rows]
        if self.fee > 0 or self.interest > 0:
            rows.append(["Offene Forderungen gesamt", "", fmt_eur(self.total)])
        if self.fee > 0:
            rows.append(["Mahngebühr laut hinterlegter Mahnstufe", "", fmt_eur(self.fee)])
        if self.interest > 0:
            rows.append(
                ["Verzugszinsen (Näherung, gesetzlicher Verzugszins)", "", fmt_eur(self.interest)]
            )
        rows.append(["Summe", "", fmt_eur(self.grand_total)])
        return letters.LetterTable(
            header=["Posten", "Fälligkeit", "Betrag"],
            rows=rows,
            right_aligned=(2,),
            total_row=True,
            widths=(0.55, 0.2, 0.25),
        )

    def as_json(self) -> dict[str, Any]:
        table = self.as_table()
        return {"header": table.header, "rows": table.rows}


def claim_table(items: list[dict[str, Any]], fee: Decimal, interest: Decimal) -> ClaimTable:
    rows: list[tuple[str, str, Decimal]] = []
    for item in sorted(items, key=lambda i: str(i["due_date"])):
        due = date.fromisoformat(str(item["due_date"]))
        rows.append(
            (str(item.get("label") or "Forderung"), fmt_date(due), Decimal(str(item["remaining"])))
        )
    total = sum((amount for _, _, amount in rows), Decimal("0.00"))
    return ClaimTable(rows=rows, total=total, fee=fee, interest=interest)


def placeholder_values(
    *,
    grand_total: Decimal,
    claim_holder: str,
    object_line: str,
    level_text: str,
    payment_deadline: date | None,
    bank_account: str | None,
) -> dict[str, str]:
    return {
        "frist": f"bis zum {fmt_date(payment_deadline)}" if payment_deadline else "",
        "bankverbindung": (
            f"auf das Konto {bank_account}" if bank_account else "auf das Ihnen bekannte Konto"
        ),
        "gesamtbetrag": fmt_eur(grand_total),
        "forderungsinhaber": claim_holder,
        "objekt": object_line,
        "stufe": level_text,
    }


@dataclass
class LetterText:
    """The rendered text parts of a dunning letter (plain text, not yet escaped)."""

    greeting: str
    intro: str
    table: ClaimTable
    request: str
    closing_hint: str = CLOSING_HINT

    def body(self) -> str:
        marker = letters.TABLE_MARKER.format(name=TABLE_NAME)
        parts = [self.greeting, self.intro, marker, self.request, self.closing_hint]
        return "\n\n".join(html.escape(p) if p != marker else p for p in parts)

    def paragraphs(self) -> list[str]:
        return [self.greeting, self.intro, self.request, self.closing_hint]


def compose(
    *,
    level: int,
    level_text: str,
    greeting: str,
    claim_holder: str,
    object_line: str,
    items: list[dict[str, Any]],
    fee: Decimal,
    interest: Decimal,
    payment_deadline: date | None,
    letter_text: str | None,
    bank_account: str | None,
) -> LetterText:
    table = claim_table(items, fee, interest)
    values = placeholder_values(
        grand_total=table.grand_total,
        claim_holder=claim_holder,
        object_line=object_line,
        level_text=level_text,
        payment_deadline=payment_deadline,
        bank_account=bank_account,
    )
    module = standard_text(level)
    request = letter_text.strip() if letter_text and letter_text.strip() else module["request"]
    return LetterText(
        greeting=greeting,
        intro=fill(module["intro"], values),
        table=table,
        request=fill(request, values),
    )


def sample_preview(
    *,
    level: int,
    level_text: str | None,
    letter_text: str | None,
    fee_amount: Decimal | None,
    payment_days: int | None,
    letter_date: date,
    bank_account: str | None = None,
) -> dict[str, Any]:
    """Text of a level with sample items for the settings form (A33). Fee only when a value
    is given, deadline only from ``payment_days``, no bank account unless released."""
    text = compose(
        level=level,
        level_text=level_text or standard_level_text(level),
        greeting="Sehr geehrte Damen und Herren,",
        claim_holder="WEG Musterstraße 1",
        object_line="Objekt 000 Musterobjekt, Einheit 01",
        items=SAMPLE_ITEMS,
        fee=fee_amount or Decimal("0.00"),
        interest=Decimal("0.00"),
        payment_deadline=(
            letter_date + timedelta(days=int(payment_days)) if payment_days is not None else None
        ),
        letter_text=letter_text,
        bank_account=bank_account,
    )
    return {
        "level": level,
        "letter_date": letter_date,
        "paragraphs": text.paragraphs(),
        "table": text.table.as_json(),
        "standard_request": standard_text(level)["request"],
        "placeholders": PLACEHOLDERS,
        "hinweis": DRAFT_LABEL,
    }


def standard_level_text(level: int) -> str:
    names = {lv["level"]: str(lv["text"]) for lv in dunning.preset_levels()}
    return names.get(level, f"Mahnstufe {level}")


@dataclass
class LetterDraft:
    letter: letters.Letter
    contact_id: uuid.UUID
    contact_name: str
    links: list[tuple[str, uuid.UUID]]
    level_text: str
    filename: str
    title: str = ""


@dataclass
class CaseContext:
    """Stored data around a case that both the letter and the Mahnbescheid export need."""

    ledger: Ledger
    claim_holder_name: str
    claim_holder_kind: str
    contract: Any
    contact: Any
    recipient_lines: list[str]
    greeting: str
    object_line: str
    property_line: str | None
    settings: dunning.EffectiveSettings | None
    level_text: str
    payment_days: int | None
    letter_text: str | None
    items: list[dict[str, Any]]
    links: list[tuple[str, uuid.UUID]] = field(default_factory=list)


async def _labelled_items(
    session: AsyncSession, open_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Add the posting text of each open item as its label (nothing is invented: without a
    text the row reads "Forderung")."""
    out = []
    for item in open_items:
        label = None
        try:
            open_item = await session.get(OpenItem, uuid.UUID(str(item["open_item_id"])))
        except (KeyError, ValueError):
            open_item = None
        if open_item is not None:
            entry = await session.get(JournalEntry, open_item.journal_entry_id)
            label = entry.text if entry is not None and entry.text else None
            if label is None and open_item.component:
                label = f"Forderung {open_item.component}"
        out.append({**item, "label": label or "Forderung"})
    return out


async def context(session: AsyncSession, case: DunningCase) -> CaseContext:
    from mhvp.contacts.models import Party, PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import LegalEntity, Property, Unit

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
    letter_text = str(config.get("letter_text")) if config and config.get("letter_text") else None

    object_parts = []
    property_line = None
    if prop is not None:
        property_line = f"{prop.number} {prop.name}"
        object_parts.append(f"Objekt {property_line}")
    if unit is not None:
        object_parts.append(f"Einheit {unit.label or unit.number}")
    links: list[tuple[str, uuid.UUID]] = [("contract", contract.id)]
    if unit is not None:
        links.append(("unit", unit.id))
    if prop is not None:
        links.append(("property", prop.id))
    return CaseContext(
        ledger=ledger,
        claim_holder_name=claim_holder.name if claim_holder else "dem Forderungsinhaber",
        claim_holder_kind=claim_holder.kind.value if claim_holder else "",
        contract=contract,
        contact=contact,
        recipient_lines=recipient_lines,
        greeting=str(recipient["anrede"]),
        object_line=", ".join(object_parts) or f"Vertrag {contract.number}",
        property_line=property_line,
        settings=settings,
        level_text=level_text,
        payment_days=int(payment_days) if payment_days is not None else None,
        letter_text=letter_text,
        items=await _labelled_items(session, case.open_items),
        links=links,
    )


async def build(
    session: AsyncSession,
    case: DunningCase,
    head: letters.Letterhead,
    letter_date: date,
    *,
    bank_account: str | None = None,
) -> LetterDraft:
    """Assemble the letter for a case from stored data only. ``bank_account`` is the released
    account text of the claim holder; until M16-13 is decided the caller passes ``None``."""
    if case.status == "excluded":
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für ausgeschlossene Fälle wird kein Mahnschreiben erzeugt."
        )
    ctx = await context(session, case)
    payment_deadline = (
        letter_date + timedelta(days=ctx.payment_days) if ctx.payment_days is not None else None
    )
    text = compose(
        level=case.level,
        level_text=ctx.level_text,
        greeting=ctx.greeting,
        claim_holder=ctx.claim_holder_name,
        object_line=ctx.object_line,
        items=ctx.items,
        fee=case.fee_amount,
        interest=case.interest_amount,
        payment_deadline=payment_deadline,
        letter_text=ctx.letter_text,
        bank_account=bank_account,
    )
    subject = html.escape(f"{ctx.level_text}: offene Forderungen, {ctx.object_line}")
    info = [
        ("Status", DRAFT_LABEL),
        ("Unser Zeichen", f"MW-{str(case.id)[:8]}"),
        ("Mahnstufe", f"{case.level} {ctx.level_text}"),
    ]
    if ctx.property_line:
        info.append(("Objekt", ctx.property_line))
    signatory = [str(head.company.get("name", "")), f"im Auftrag von {ctx.claim_holder_name}"]
    letter = letters.Letter(
        recipient_lines=ctx.recipient_lines,
        subject=subject,
        body=text.body(),
        letter_date=letter_date,
        info=info,
        signatory=[s for s in signatory if s],
        tables={TABLE_NAME: text.table.as_table()},
    )
    filename = f"{letter_date.isoformat()}_mahnung_stufe{case.level}_{ctx.contact.display_name}.pdf"
    return LetterDraft(
        letter=letter,
        contact_id=ctx.contact.id,
        contact_name=ctx.contact.display_name,
        links=ctx.links,
        level_text=ctx.level_text,
        filename=filename[:255],
        title=f"{ctx.level_text} (Entwurf), {ctx.contact.display_name}",
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
        title=draft.title or f"{draft.level_text} (Entwurf), {draft.contact_name}",
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


# Mahnbescheid preparation as PDF (A31, M16-07) ------------------------------------------

KIND_LABELS = {
    "hoa": "Wohnungseigentümergemeinschaft",
    "rental_owner": "Vermieter (Eigentümer)",
    "sev_owner": "Eigentümer (Sondereigentumsverwaltung)",
    "manager": "Verwaltung",
}

CASE_STATUS_LABELS = {"proposed": "vorgeschlagen", "excluded": "ausgeschlossen", "sent": "versandt"}
CHANNEL_LABELS = {"post": "Post", "email": "E-Mail", "portal": "Portal"}


async def _history(
    session: AsyncSession, case: DunningCase, settings: dunning.EffectiveSettings | None
) -> letters.LetterTable:
    """Every case of the same debtor account in the same ledger, oldest first, with the run
    date, level, status and the recorded manual delivery (M16-09)."""
    rows = (
        await session.execute(
            select(DunningCase, DunningRun.run_date)
            .join(DunningRun, DunningRun.id == DunningCase.run_id)
            .where(
                DunningCase.debtor_account_id == case.debtor_account_id,
                DunningCase.ledger_id == case.ledger_id,
            )
            .order_by(DunningRun.run_date, DunningCase.created_at)
        )
    ).all()
    out: list[list[str]] = []
    for row_case, run_date in rows:
        config = dunning.level_config(settings, row_case.level) if settings else None
        text = str(config.get("text")) if config and config.get("text") else ""
        delivery = ""
        if row_case.delivered_at is not None:
            channel = CHANNEL_LABELS.get(row_case.delivery_channel or "", row_case.delivery_channel)
            delivery = f"{fmt_date(row_case.delivered_at.date())} ({channel})"
        out.append(
            [
                fmt_date(run_date),
                f"{row_case.level} {text}".strip(),
                CASE_STATUS_LABELS.get(row_case.status, row_case.status),
                fmt_eur(row_case.total),
                delivery,
                "ja" if row_case.letter_document_id else "nein",
            ]
        )
    return letters.LetterTable(
        header=["Mahnlauf", "Stufe", "Status", "Offen", "Als versendet markiert", "Schreiben"],
        rows=out,
        right_aligned=(3,),
        widths=(0.14, 0.24, 0.15, 0.15, 0.2, 0.12),
    )


async def build_mahnbescheid(
    session: AsyncSession,
    case: DunningCase,
    prep: DunningMahnbescheidPrep,
    head: letters.Letterhead,
    letter_date: date,
) -> LetterDraft:
    """PDF of the preparation record on the tenant letterhead: claim table (Hauptforderung
    per item with due date; Nebenforderungen only when posted, so the fee only with a fee
    entry and interest never, because interest is never booked, 7.5), debtor, creditor
    (legal entity) and the dunning history. Prominent notice: preparation only, review by a
    lawyer required, no application."""
    ctx = await context(session, case)
    fee = case.fee_amount if case.fee_entry_id is not None else Decimal("0.00")
    table = claim_table(ctx.items, fee, Decimal("0.00"))
    history = await _history(session, case, ctx.settings)

    creditor = [ctx.claim_holder_name]
    kind = KIND_LABELS.get(ctx.claim_holder_kind)
    if kind:
        creditor.append(kind)
    if ctx.property_line:
        creditor.append(f"Objekt {ctx.property_line}")
    manager = str(head.company.get("name", ""))
    if manager:
        creditor.append(f"vertreten durch {manager} (Verwaltung)")

    paragraphs = [
        "Gläubiger (Antragsteller): " + ", ".join(creditor),
        "Schuldner (Antragsgegner): "
        + ", ".join(ctx.recipient_lines)
        + f". {prep.antragsgegner_snapshot.get('address_note', 'Anschrift zu prüfen')}.",
        f"Vertrag {ctx.contract.number}, {ctx.object_line}.",
        "Forderungsaufstellung (Hauptforderung je Posten mit Fälligkeit, Nebenforderungen nur "
        "soweit gebucht):",
        letters.TABLE_MARKER.format(name=TABLE_NAME),
    ]
    notes = []
    if case.fee_amount > 0 and case.fee_entry_id is None:
        notes.append(
            f"Die Mahngebühr von {fmt_eur(case.fee_amount)} ist nicht gebucht und daher nicht "
            "aufgenommen."
        )
    if case.interest_amount > 0:
        notes.append(
            f"Verzugszinsen (Näherung {fmt_eur(case.interest_amount)}) sind nicht gebucht und "
            "daher nicht aufgenommen; Zinsbeginn und Zinssatz sind durch den Rechtsanwalt zu "
            "prüfen."
        )
    else:
        notes.append(
            "Verzugszinsen sind nicht aufgenommen; Zinsbeginn und Zinssatz sind durch "
            "den Rechtsanwalt zu prüfen."
        )
    paragraphs.append(" ".join(notes))
    paragraphs += [
        "Mahnhistorie:",
        letters.TABLE_MARKER.format(name=HISTORY_TABLE),
        f"{MAHNBESCHEID_NOTICE}. Fristen sind nur Hinweise und zu prüfen; die Plattform "
        "prüft keine rechtliche Vollständigkeit und stellt keinen Antrag. Verzug wird nicht "
        f"behauptet. Internes Aktenzeichen {prep.aktenzeichen_intern}, Stand "
        f"{fmt_date(letter_date)}.",
    ]
    markers = {letters.TABLE_MARKER.format(name=n) for n in (TABLE_NAME, HISTORY_TABLE)}
    body = "\n\n".join(p if p in markers else html.escape(p) for p in paragraphs)
    subject = html.escape(
        f"Vorbereitung Mahnbescheid (kein Antrag): {ctx.claim_holder_name} gegen "
        f"{ctx.contact.display_name}"
    )
    info = [
        ("Status", "Vorbereitung, kein Antrag"),
        ("Unser Zeichen", prep.aktenzeichen_intern),
        ("Mahnstufe", f"{case.level} {ctx.level_text}"),
    ]
    letter = letters.Letter(
        recipient_lines=[
            "Interne Unterlage",
            "Vorbereitung gerichtliches Mahnverfahren",
            "zur Prüfung durch Rechtsanwalt",
        ],
        subject=subject,
        body=body,
        letter_date=letter_date,
        info=info,
        closing="Zusammengestellt aus den gespeicherten Daten, ohne rechtliche Prüfung.",
        signatory=[manager] if manager else [],
        tables={TABLE_NAME: table.as_table(), HISTORY_TABLE: history},
        notice=MAHNBESCHEID_NOTICE,
    )
    filename = f"{letter_date.isoformat()}_mahnbescheid_vorbereitung_{ctx.contact.display_name}.pdf"
    return LetterDraft(
        letter=letter,
        contact_id=ctx.contact.id,
        contact_name=ctx.contact.display_name,
        links=ctx.links,
        level_text=ctx.level_text,
        filename=filename[:255],
        title=f"Mahnbescheid-Vorbereitung (kein Antrag), {ctx.contact.display_name}",
    )


async def store_mahnbescheid(
    session: AsyncSession,
    blobs: Any,
    *,
    draft: LetterDraft,
    pdf: bytes,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    """File the export as a generated document linked to contact, contract, unit and
    property. The preparation row has no document column (would need a migration); the
    document is found through its links and the response carries its id."""
    from mhvp.documents.models import DocumentSource

    document = await docs.store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=pdf,
        title=draft.title,
        filename=draft.filename,
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=[("contact", draft.contact_id, LinkRole.GENERATED)]
        + [(t, i, LinkRole.GENERATED) for t, i in draft.links],
        created_by=user_id,
    )
    return document.id
