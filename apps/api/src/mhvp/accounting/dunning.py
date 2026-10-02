"""Dunning runs (7.5 Mahnwesen, 6.9.10 D52).

Preview only lists overdue open receivables per debtor with the next level; dunning blocks,
thresholds and non leading ledgers are excluded with a reason. Due date and default are kept
apart: the preview proposes a reminder, it does not assert default (Verzug).

Fees and interest (operator decision 25.09.2026, V7 teilweise entschieden,
docs/OPEN_QUESTIONS.md V7, docs/plans/M16.md): the ladder (Zahlungserinnerung 7 days, always
free; 1. Mahnung 14 days; 2. Mahnung 28 days; 3. Mahnung/letzte Mahnung 42 days, then
Mahnbescheid vorbereiten) is decided. A fee amount per level is nullable and the fee stays
inactive until the operator enters a value (no default amount is ever assumed, 0.1.3);
``fee_from_level`` gates the earliest level a fee may apply to. Interest is the gesetzlicher
Verzugszins (Basiszinssatz plus Aufschlag) and stays disabled while ``interest_base_rate`` is
unmaintained; the Basiszinssatz changes half yearly and is never hardcoded here.

On approval (second person, leading ledger only, G1), a configured fee becomes a draft
receivable (Sollstellung) on the debtor's account within the claim holder's ledger, plus, when
the claim holder is not Hausverwaltung Müller GmbH itself, a draft HVM outgoing invoice to
that claim holder (WEG for Hausgeld, Vermieter/Eigentümer for rent). Both stay drafts behind
G1 and the existing four eyes release; interest is computed only as an informational Nebenforderung
for the Mahnbescheid preparation, never booked automatically.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import leading
from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    AccountType,
    DunningCase,
    DunningDeliveryProof,
    DunningFeeInvoiceDraft,
    DunningInterestRate,
    DunningItemBlock,
    DunningMahnbescheidPrep,
    DunningRun,
    DunningSettings,
    EntryKind,
    EntrySource,
    JournalEntry,
    Ledger,
    LedgerAccount,
)
from mhvp.contacts import recipients
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

CENT = Decimal("0.01")
FEE_ACCOUNT_NUMBER = "489000"
FEE_ACCOUNT_NAME = "Mahngebühren"


LEVEL_KEYS = frozenset(
    {"level", "min_days_overdue", "text", "fee_amount", "payment_days", "letter_text"}
)
# Keys of a level entry an object row may leave out to inherit them from the tenant level with
# the same number (M16-10). ``level`` and ``min_days_overdue`` are always required.
LEVEL_INHERITABLE = ("text", "fee_amount", "payment_days", "letter_text")
INHERITABLE_FIELDS = (
    "levels",
    "threshold_amount",
    "fee_from_level",
    "interest_enabled",
    "interest_base_rate",
    "interest_spread",
    "default_start_mode",
)

# Modes for the start of default (Verzugsbeginn, M16-03, docs/rules/M16-03.md). The
# assessment behind each mode is marked "zu prüfen durch Rechtsanwalt"; the platform only
# derives a date from stored facts and never asserts default in a letter.
DEFAULT_MODE_AFTER_NOTICE = "after_notice_30_days"
DEFAULT_MODE_CALENDAR = "calendar_due_date"
DEFAULT_MODE_AFTER_REMINDER = "after_reminder"
DEFAULT_MODES = (DEFAULT_MODE_AFTER_NOTICE, DEFAULT_MODE_CALENDAR, DEFAULT_MODE_AFTER_REMINDER)
DEFAULT_MODE_LABELS: dict[str, str] = {
    DEFAULT_MODE_AFTER_NOTICE: "30 Tage nach Fälligkeit und Zugang",
    DEFAULT_MODE_CALENDAR: "kalendermäßig bestimmt (Vertragsfälligkeit)",
    DEFAULT_MODE_AFTER_REMINDER: "erst nach Mahnung (Zugang der Mahnung)",
}
NOTICE_DAYS = 30
NO_BANK_ACCOUNT_WARNING = (
    "Kein Standardkonto des Forderungsinhabers hinterlegt: Mahnschreiben nicht freigebbar (M16-13)"
)


@dataclass
class EffectiveSettings:
    """Settings that apply to a property after inheritance (M16-10, docs/rules/M16-02.md).

    Every field is either the object's own value or the tenant default; ``sources`` records
    per field where it came from (``objekt`` or ``mandant``). Nothing here is invented: a
    field without a value on both rows stays ``None`` (or an empty ladder)."""

    property_id: uuid.UUID | None
    levels: list[dict[str, Any]] = field(default_factory=list)
    threshold_amount: Decimal = Decimal("0.00")
    fee_from_level: int | None = None
    interest_enabled: bool = False
    interest_base_rate: Decimal | None = None
    interest_spread: Decimal | None = None
    default_start_mode: str | None = None
    sources: dict[str, str] = field(default_factory=dict)
    tenant_row: DunningSettings | None = None
    property_row: DunningSettings | None = None


async def settings_row(
    session: AsyncSession, property_id: uuid.UUID | None
) -> DunningSettings | None:
    """The stored row for exactly this scope (tenant default when ``property_id`` is None)."""
    scope = (
        DunningSettings.property_id.is_(None)
        if property_id is None
        else DunningSettings.property_id == property_id
    )
    row: DunningSettings | None = await session.scalar(select(DunningSettings).where(scope))
    return row


def merge_levels(
    tenant_levels: list[dict[str, Any]] | None, own_levels: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Object ladder over tenant ladder: an object level entry replaces the tenant entry with
    the same number; keys it leaves out are taken from that tenant entry. Levels the object
    ladder does not list do not exist for the object (the object decides its own ladder)."""
    if own_levels is None:
        return [dict(lv) for lv in (tenant_levels or [])]
    by_number = {int(lv["level"]): lv for lv in (tenant_levels or [])}
    merged: list[dict[str, Any]] = []
    for own in own_levels:
        base = by_number.get(int(own["level"]), {})
        entry = dict(own)
        for key in LEVEL_INHERITABLE:
            if key not in entry and key in base:
                entry[key] = base[key]
        merged.append(entry)
    return sorted(merged, key=lambda lv: int(lv["level"]))


def resolve(
    tenant_row: DunningSettings | None,
    property_row: DunningSettings | None,
    property_id: uuid.UUID | None,
) -> EffectiveSettings | None:
    """Field level inheritance: an object row value wins when it is not NULL, otherwise the
    tenant default applies. Returns ``None`` when neither row exists."""
    if tenant_row is None and property_row is None:
        return None
    eff = EffectiveSettings(
        property_id=property_id, tenant_row=tenant_row, property_row=property_row
    )
    for name in INHERITABLE_FIELDS:
        own = getattr(property_row, name, None) if property_row is not None else None
        base = getattr(tenant_row, name, None) if tenant_row is not None else None
        if name == "levels":
            eff.levels = merge_levels(base, own)
            eff.sources[name] = "objekt" if own is not None else "mandant"
            continue
        value = own if own is not None else base
        eff.sources[name] = "objekt" if own is not None else "mandant"
        if name == "threshold_amount":
            eff.threshold_amount = Decimal(value) if value is not None else Decimal("0.00")
        elif name == "interest_enabled":
            eff.interest_enabled = bool(value) if value is not None else False
        else:
            setattr(eff, name, value)
    return eff


async def settings_for(
    session: AsyncSession, property_id: uuid.UUID | None
) -> EffectiveSettings | None:
    """Effective settings for a property (tenant default merged with the object override)."""
    tenant_row = await settings_row(session, None)
    property_row = await settings_row(session, property_id) if property_id is not None else None
    return resolve(tenant_row, property_row, property_id)


def level_config(settings: EffectiveSettings, level: int) -> dict[str, Any] | None:
    return next((lv for lv in settings.levels if int(lv["level"]) == level), None)


async def last_level(session: AsyncSession, account_id: uuid.UUID) -> int:
    level = await session.scalar(
        select(DunningCase.level)
        .where(DunningCase.debtor_account_id == account_id, DunningCase.status == "sent")
        .order_by(DunningCase.level.desc())
        .limit(1)
    )
    return int(level or 0)


REMINDER_LEVEL = 1
"""Zahlungserinnerung: always without fee and interest (M16-14, V7, D40)."""

DEFAULT_PAYMENT_DAYS: dict[int, int] = {1: 14, 2: 10, 3: 7}
"""Default payment deadline per level in days after the letter date (M16-12). Levels
without an entry get no default; the letter then asks for payment without a date."""


def preset_levels() -> list[dict[str, Any]]:
    """V7 Vorschlagswerte (Betreiberentscheidung 25.09.2026): Tage entschieden, Beträge offen.
    Zahlungsfristen nach M16-12 (14, 10, 7 Tage), Stufe 4 ohne Vorgabewert."""
    levels: list[dict[str, Any]] = [
        {"level": 1, "min_days_overdue": 7, "text": "Zahlungserinnerung", "fee_amount": None},
        {"level": 2, "min_days_overdue": 14, "text": "1. Mahnung", "fee_amount": None},
        {"level": 3, "min_days_overdue": 28, "text": "2. Mahnung", "fee_amount": None},
        {
            "level": 4,
            "min_days_overdue": 42,
            "text": "3. Mahnung / letzte Mahnung",
            "fee_amount": None,
        },
    ]
    for lv in levels:
        lv["payment_days"] = DEFAULT_PAYMENT_DAYS.get(int(lv["level"]))
    return levels


def interest_spread_presets() -> dict[str, str]:
    """§ 288 BGB unterscheidet Anspruchsarten (Verbraucher/Unternehmer); Werte nur als
    Vorschlag für ``interest_spread``, nie als Basiszinssatz (der bleibt Betreiberpflege)."""
    return {"verbraucher": "5", "unternehmer": "9"}


def fee_amount_for(settings: EffectiveSettings, level: int) -> Decimal | None:
    if settings.fee_from_level is None or level < settings.fee_from_level:
        return None
    config = level_config(settings, level)
    if config is None:
        return None
    raw = config.get("fee_amount")
    if raw is None:
        return None
    return Decimal(str(raw))


def interest_amount_for(settings: EffectiveSettings, total: Decimal, days: int) -> Decimal:
    """Informational only (Nebenforderung), never booked automatically. Zero unless the
    operator both enabled interest and maintained a Basiszinssatz; the day count and formula
    are a generic approximation and are not a legal certification (0.2)."""
    if not settings.interest_enabled or settings.interest_base_rate is None or days <= 0:
        return Decimal("0.00")
    rate = settings.interest_base_rate + (settings.interest_spread or Decimal("0"))
    amount = total * rate / Decimal("100") * Decimal(days) / Decimal("365")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class InterestResult:
    """Interest over the default period split by Basiszinssatz periods (M16-02)."""

    amount: Decimal
    periods: list[dict[str, Any]]
    note: str | None = None


def interest_over_periods(
    rates: list[tuple[date, Decimal]],
    spread: Decimal | None,
    total: Decimal,
    start: date,
    end: date,
) -> InterestResult:
    """Pro rata interest from ``start`` (inclusive) to ``end`` (exclusive), one period per
    Basiszinssatz validity (``rates`` sorted or not, each valid until the day before the next
    ``valid_from``). A change of the Basiszinssatz during default splits the period (7.5). If
    part of the period lies before the first maintained rate, nothing is computed (no rate is
    assumed, 0.1.3). Same day count as before (days/365), rounded per period; not a legal
    certification (0.2)."""
    if end <= start or total <= 0:
        return InterestResult(Decimal("0.00"), [])
    ordered = sorted(rates)
    if not ordered or ordered[0][0] > start:
        return InterestResult(
            Decimal("0.00"),
            [],
            f"Kein Basiszinssatz für den Zeitraum ab {start.strftime('%d.%m.%Y')} gepflegt: "
            "Zinsen nicht berechnet",
        )
    extra = spread or Decimal("0")
    periods: list[dict[str, Any]] = []
    amount = Decimal("0.00")
    for idx, (valid_from, base) in enumerate(ordered):
        valid_to = ordered[idx + 1][0] if idx + 1 < len(ordered) else end
        seg_from, seg_to = max(start, valid_from), min(end, valid_to)
        if seg_to <= seg_from:
            continue
        days = (seg_to - seg_from).days
        rate = base + extra
        part = (total * rate / Decimal("100") * Decimal(days) / Decimal("365")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        amount += part
        periods.append(
            {
                "from": seg_from.isoformat(),
                "to": (seg_to - timedelta(days=1)).isoformat(),
                "days": days,
                "base_rate": str(base),
                "spread": str(extra),
                "rate": str(rate),
                "amount": str(part),
            }
        )
    return InterestResult(amount, periods)


async def interest_rates(session: AsyncSession) -> list[tuple[date, Decimal]]:
    rows = (
        await session.scalars(select(DunningInterestRate).order_by(DunningInterestRate.valid_from))
    ).all()
    return [(r.valid_from, r.base_rate) for r in rows]


def interest_for(
    settings: EffectiveSettings,
    rates: list[tuple[date, Decimal]],
    total: Decimal,
    start: date | None,
    end: date,
) -> InterestResult:
    """Interest of a case: the rate history (M16-02) wins; without any history the single
    ``interest_base_rate`` of the settings applies as before. Zero while interest is off."""
    if not settings.interest_enabled or start is None or end <= start:
        return InterestResult(Decimal("0.00"), [])
    if rates:
        return interest_over_periods(rates, settings.interest_spread, total, start, end)
    if settings.interest_base_rate is None:
        return InterestResult(Decimal("0.00"), [])
    return interest_over_periods(
        [(start, settings.interest_base_rate)], settings.interest_spread, total, start, end
    )


BLOCK_REASON_LABELS: dict[str, str] = {
    "installment_plan": "Ratenplan",
    "disputed": "bestrittener Posten",
    "set_off": "Aufrechnung",
    "litigation": "Prozess",
    "insolvency": "Insolvenz",
}


async def active_item_blocks(
    session: AsyncSession, open_item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Active structured blocks per open item (M16-03): item id to reason code."""
    if not open_item_ids:
        return {}
    rows = (
        await session.scalars(
            select(DunningItemBlock).where(
                DunningItemBlock.open_item_id.in_(open_item_ids),
                DunningItemBlock.released_at.is_(None),
            )
        )
    ).all()
    return {r.open_item_id: r.reason_code for r in rows}


def spread_suggestion(is_consumer: bool | None) -> dict[str, Any]:
    """Proposal of the Zinsaufschlag from the consumer flag of the debtor (M16-06, decision
    3 a). A proposal with a note only; it never changes ``interest_spread``. Whether § 288
    Abs. 2 applies depends on the kind of claim (Entgeltforderung) and all parties (R10)."""
    hint = (
        "Vorschlag aus dem Verbraucherkennzeichen des Schuldners, keine rechtliche Feststellung. "
        "§ 288 BGB unterscheidet Anspruchsarten und Beteiligte; Aufschlag durch Rechtsanwalt "
        "prüfen, die Einstellung wird nicht automatisch geändert."
    )
    presets = interest_spread_presets()
    if is_consumer is None:
        return {
            "profile": None,
            "spread": None,
            "hinweis": "Verbrauchereigenschaft des Schuldners nicht erfasst: kein Vorschlag. "
            + hint,
        }
    profile = "verbraucher" if is_consumer else "unternehmer"
    return {"profile": profile, "spread": presets[profile], "hinweis": hint}


def case_check_hints(case: DunningCase, today: date) -> list[str]:
    """Prüfhinweise zu Fristen und Verjährung (M16-04, 7.5): hints for a person, no computed
    limitation date (no limitation rule in the source register, annex C) and no automatic
    legal action."""
    hints: list[str] = []
    if case.due_date is not None:
        age = (today - case.due_date).days
        hints.append(
            f"Verjährung prüfen: älteste Fälligkeit {case.due_date.strftime('%d.%m.%Y')} "
            f"(Fälligkeitsjahr {case.due_date.year}, {age} Tage). Beginn, Dauer, Hemmung "
            "und Neubeginn durch Rechtsanwalt prüfen; die Plattform berechnet kein "
            "Verjährungsdatum."
        )
    if case.default_start is None:
        hints.append(
            "Verzugsbeginn nicht ableitbar: Zinsen und verzugsbezogene Schritte erst nach Prüfung."
        )
    if case.level >= 3:
        hints.append(
            "Fortgeschrittene Mahnstufe: gerichtliche Schritte (Mahnbescheid, Klage) nur nach "
            "gesondertem Auftrag und fallbezogener Prüfung; Fristen sind zu verifizieren und "
            "mit Vorfrist einzutragen."
        )
    if case.status == "sent" and case.received_on is None:
        hints.append("Zugang der Mahnung nicht erfasst: Zustellnachweis und Zugang prüfen.")
    return hints


@dataclass
class DefaultStart:
    """Result of the default start derivation for one case: ``start`` is ``None`` whenever a
    fact the mode needs is not recorded (nothing is assumed, 0.1.3); ``note`` says why."""

    mode: str | None
    start: date | None
    note: str


def _add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)


def default_start(
    mode: str | None,
    *,
    items: list[dict[str, Any]],
    reminder_received_on: date | None,
) -> DefaultStart:
    """Start of default (Verzugsbeginn) for the overdue items of one debtor, per mode
    (M16-03). Every derivation is an assessment to be verified by a lawyer, not a legal
    determination:

    - ``calendar_due_date``: the day after the contractually fixed due date of the oldest item.
    - ``after_notice_30_days``: for each item with a recorded receipt of the demand, the day
      after 30 days from the later of due date and receipt; the earliest such day counts. Items
      without a recorded receipt yield no start.
    - ``after_reminder``: the day after the recorded receipt of a dunning letter.
    - ``None``: no mode decided, no start."""
    due_dates = [i["due_date"] for i in items if i.get("due_date")]
    if mode is None:
        return DefaultStart(
            None, None, "Verzugsbeginn: Modus nicht festgelegt (Mandanteneinstellung)"
        )
    if mode == DEFAULT_MODE_CALENDAR:
        if not due_dates:
            return DefaultStart(mode, None, "Verzugsbeginn: keine Fälligkeit hinterlegt")
        return DefaultStart(
            mode, _add_days(min(due_dates), 1), "Verzugsbeginn: Tag nach kalendermäßiger Fälligkeit"
        )
    if mode == DEFAULT_MODE_AFTER_NOTICE:
        starts = [
            _add_days(max(i["due_date"], i["notice_received_on"]), NOTICE_DAYS + 1)
            for i in items
            if i.get("due_date") and i.get("notice_received_on")
        ]
        missing = sum(1 for i in items if not i.get("notice_received_on"))
        if not starts:
            return DefaultStart(
                mode, None, "Verzugsbeginn: Zugangsdatum der Zahlungsaufforderung nicht erfasst"
            )
        note = f"Verzugsbeginn: {NOTICE_DAYS} Tage nach Fälligkeit und Zugang"
        if missing:
            note += f", {missing} Posten ohne erfasstes Zugangsdatum"
        return DefaultStart(mode, min(starts), note)
    if mode == DEFAULT_MODE_AFTER_REMINDER:
        if reminder_received_on is None:
            return DefaultStart(mode, None, "Verzugsbeginn: Zugang einer Mahnung nicht erfasst")
        return DefaultStart(
            mode, _add_days(reminder_received_on, 1), "Verzugsbeginn: Tag nach Zugang der Mahnung"
        )
    return DefaultStart(mode, None, f"Verzugsbeginn: unbekannter Modus {mode}")


async def reminder_received_on(session: AsyncSession, account_id: uuid.UUID) -> date | None:
    """Earliest recorded receipt of a sent dunning letter for the debtor account."""
    value: date | None = await session.scalar(
        select(DunningCase.received_on)
        .where(
            DunningCase.debtor_account_id == account_id,
            DunningCase.status == "sent",
            DunningCase.received_on.is_not(None),
        )
        .order_by(DunningCase.received_on.asc())
        .limit(1)
    )
    return value


async def payment_account(session: AsyncSession, ledger: Ledger, on: date) -> Any | None:
    """The default bank account of the claim holder of ``ledger`` valid on ``on`` (M16-13):
    the letter names this account for payment. Never a deposit account, never the account of
    the managing company unless it holds the claim itself. ``None`` when none is flagged."""
    from mhvp.properties.models import BankAccountKind, PropertyBankAccount

    return await session.scalar(
        select(PropertyBankAccount).where(
            PropertyBankAccount.legal_entity_id == ledger.legal_entity_id,
            PropertyBankAccount.is_default.is_(True),
            PropertyBankAccount.kind != BankAccountKind.DEPOSIT,
            PropertyBankAccount.valid_from <= on,
            (PropertyBankAccount.valid_to.is_(None)) | (PropertyBankAccount.valid_to >= on),
        )
    )


def reminder_guard(
    level: int, fee_amount: Decimal, interest_amount: Decimal
) -> tuple[Decimal, Decimal, str | None]:
    """Second line of defence (M16-14): whatever the configuration says, a
    Zahlungserinnerung carries neither fee nor interest. Returns the amounts to use and a
    note for the case protocol when something had to be reset."""
    if level != REMINDER_LEVEL or (fee_amount == 0 and interest_amount == 0):
        return fee_amount, interest_amount, None
    note = (
        "Zahlungserinnerung ohne Gebühr und Zinsen: Konfiguration ergab Gebühr "
        f"{fee_amount} EUR und Zinsen {interest_amount} EUR, beides auf 0,00 EUR gesetzt"
    )
    return Decimal("0.00"), Decimal("0.00"), note


async def preview(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None, run_date: date
) -> DunningRun:
    from mhvp.contracts.models import Contract

    run = DunningRun(tenant_id=tenant_id, created_by=user_id, run_date=run_date)
    session.add(run)
    await session.flush()
    counts = {"proposed": 0, "excluded": 0}
    for ledger in (await session.scalars(select(Ledger).order_by(Ledger.name))).all():
        settings = await settings_for(session, ledger.property_id)
        items = [
            i
            for i in await acc.open_items(session, ledger, run_date)
            if i["kind"] == "receivable" and i["remaining"] > 0
        ]
        by_account: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for i in items:
            if i["due_date"] and i["due_date"] < run_date:
                by_account.setdefault(i["account_id"], []).append(i)
        unreviewed = await acc.unreviewed_auto_accounts(session, ledger)
        rates = await interest_rates(session)
        for account_id, all_overdue in sorted(by_account.items(), key=lambda kv: str(kv[0])):
            account = await session.get(LedgerAccount, account_id)
            # Structured blocks per item (M16-03): blocked items never enter the case.
            blocks = await active_item_blocks(session, [i["id"] for i in all_overdue])
            overdue = [i for i in all_overdue if i["id"] not in blocks]
            block_note = (
                "Gesperrte Posten ausgenommen: "
                + ", ".join(sorted({BLOCK_REASON_LABELS[c] for c in blocks.values()}))
                if blocks
                else None
            )
            if blocks:
                counts["item_blocked"] = counts.get("item_blocked", 0) + len(blocks)
            if not overdue:
                overdue = all_overdue
            contract_id = next((i["contract_id"] for i in overdue if i["contract_id"]), None)
            contract = await session.get(Contract, contract_id) if contract_id else None
            total = sum((i["remaining"] for i in overdue), Decimal("0.00"))
            oldest = min(i["due_date"] for i in overdue)
            days = (run_date - oldest).days
            level = await last_level(session, account_id) + 1
            reason = None
            if len(blocks) == len(all_overdue):
                reason = f"Mahnsperre je Posten: {block_note}"
            elif settings is None or not settings.levels:
                reason = "Keine Mahnstufen eingerichtet"
            elif contract is not None and contract.dunning_block:
                reason = f"Mahnsperre: {contract.dunning_block_reason or 'ohne Angabe'}"
            elif total < settings.threshold_amount:
                reason = "Unter der Mahngrenze"
            else:
                config = level_config(settings, level)
                if config is None:
                    reason = (
                        "Höchste Mahnstufe erreicht: weitere Schritte nur nach Einzelfallprüfung"
                    )
                elif days < int(config["min_days_overdue"]):
                    reason = f"Noch nicht {config['min_days_overdue']} Tage überfällig"
            if reason is None and account_id in unreviewed:
                # Rule M12-05: an automatic posting without completed review is no basis
                # for a reminder; the case is excluded, never silently postponed.
                reason = acc.UNREVIEWED_AUTO_REASON
                counts["auto_review_pending"] = counts.get("auto_review_pending", 0) + 1
            if reason is None and not await leading.is_leading(
                session, ledger, leading.LeadingKind.DUNNING, run_date
            ):
                reason = "Buchungskreis nicht führend: gemahnt wird im führenden System (6.9.10)"
            fee_amount = Decimal("0.00")
            interest_amount = Decimal("0.00")
            # Due date and default are kept apart (M16-03): interest, when configured, counts
            # only from a derivable default start, never from the due date.
            verzug = default_start(
                settings.default_start_mode if settings else None,
                items=overdue,
                reminder_received_on=await reminder_received_on(session, account_id),
            )
            interest_detail: list[dict[str, Any]] | None = None
            interest_note: str | None = None
            if reason is None and settings is not None:
                fee_amount = fee_amount_for(settings, level) or Decimal("0.00")
                # Interest is configured per ladder, not per level; the Zahlungserinnerung
                # never carries it (M16-14), so it starts at level 2.
                if level > REMINDER_LEVEL:
                    interest = interest_for(settings, rates, total, verzug.start, run_date)
                    interest_amount = interest.amount
                    interest_detail = interest.periods or None
                    interest_note = interest.note
            bank = await payment_account(session, ledger, run_date) if reason is None else None
            bank_warning = NO_BANK_ACCOUNT_WARNING if reason is None and bank is None else None
            fee_amount, interest_amount, guard_note = reminder_guard(
                level, fee_amount, interest_amount
            )
            if guard_note:
                counts["reminder_guard"] = counts.get("reminder_guard", 0) + 1
            case_reason = (
                reason
                if reason
                else f"{days} Tage seit Fälligkeit, Konto {account.number if account else ''}"
            )
            if guard_note:
                case_reason = f"{case_reason}. {guard_note}"
                interest_detail = None
            if reason is None:
                case_reason = f"{case_reason}. {verzug.note}"
                if block_note:
                    case_reason = f"{case_reason}. {block_note}"
                if interest_note:
                    case_reason = f"{case_reason}. {interest_note}"
                if bank_warning:
                    case_reason = f"{case_reason}. {bank_warning}"
                    counts["bank_account_missing"] = counts.get("bank_account_missing", 0) + 1
            if reason is None and contract is not None:
                # M23-07: the letter would reach the representative only; the warning is
                # visible in the preview and stays on the case until legal advice.
                debtor_id = await recipients.debtor_contact_id(session, contract.party_id)
                if debtor_id is not None and recipients.representative_only(
                    await recipients.resolve_recipients(session, [debtor_id], on=run_date),
                    debtor_id,
                ):
                    case_reason = f"{case_reason}. {recipients.REPRESENTATIVE_ONLY_WARNING}"
                    counts["representative_only"] = counts.get("representative_only", 0) + 1
            session.add(
                DunningCase(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    ledger_id=ledger.id,
                    contract_id=contract_id,
                    debtor_account_id=account_id,
                    level=level,
                    open_items=[
                        {
                            "open_item_id": str(i["id"]),
                            "due_date": i["due_date"].isoformat(),
                            "remaining": str(i["remaining"]),
                        }
                        for i in overdue
                    ],
                    total=total,
                    fee_amount=fee_amount,
                    interest_amount=interest_amount,
                    status="excluded" if reason else "proposed",
                    reason=case_reason,
                    due_date=oldest,
                    default_start=verzug.start,
                    default_mode=verzug.mode,
                    bank_account_id=bank.id if bank is not None else None,
                    bank_warning=bank_warning,
                    interest_detail=interest_detail,
                )
            )
            counts["excluded" if reason else "proposed"] += 1
    run.totals = counts
    await session.flush()
    # S12-01: one dunning_case.created per case of the run (proposal, nothing is sent).
    for case in (
        await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))
    ).all():
        await emit(
            session,
            tenant_id=tenant_id,
            type="dunning_case.created",
            entity_type="dunning_case",
            entity_id=case.id,
            actor_user_id=user_id,
            payload={"run_id": str(run.id), "level": case.level, "status": case.status},
        )
    return run


async def _fee_revenue_account(session: AsyncSession, ledger: Ledger) -> LedgerAccount:
    existing = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == FEE_ACCOUNT_NUMBER
        )
    )
    if existing is not None:
        return existing
    account = LedgerAccount(
        tenant_id=ledger.tenant_id,
        ledger_id=ledger.id,
        number=FEE_ACCOUNT_NUMBER,
        name=FEE_ACCOUNT_NAME,
        category=AccountCategory.REVENUE,
        type=AccountType.INCOME,
        is_system=True,
    )
    session.add(account)
    await session.flush()
    return account


async def _post_fee(
    session: AsyncSession, case: DunningCase, ledger: Ledger, user_id: uuid.UUID | None
) -> None:
    """Fee as draft receivable (Sollstellung) on the debtor's account of the claim holder's
    ledger, plus a draft HVM outgoing invoice to the claim holder unless HVM holds the claim
    itself (operator clarification 25.09.2026)."""
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    revenue = await _fee_revenue_account(session, ledger)
    entry = JournalEntry(
        tenant_id=case.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=case.created_at.date(),
        text=f"Mahngebühr, Stufe {case.level}, Fall {case.id}",
        kind=EntryKind.DUNNING_FEE,
        contract_id=case.contract_id,
        source=EntrySource.MANUAL,
        idempotency_key=f"dunning_fee:{case.id}",
    )
    lines = [
        acc.LineIn(case.debtor_account_id, case.fee_amount, Decimal("0")),
        acc.LineIn(revenue.id, Decimal("0"), case.fee_amount),
    ]
    await acc.write_draft(session, ledger, entry, lines, [])
    case.fee_entry_id = entry.id

    legal_entity = await session.get(LegalEntity, ledger.legal_entity_id)
    if legal_entity is not None and legal_entity.kind is not LegalEntityKind.MANAGER:
        hvm_ledger = await session.scalar(
            select(Ledger)
            .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
            .where(LegalEntity.kind == LegalEntityKind.MANAGER, Ledger.tenant_id == case.tenant_id)
        )
        if hvm_ledger is not None:
            draft = DunningFeeInvoiceDraft(
                tenant_id=case.tenant_id,
                case_id=case.id,
                issuer_ledger_id=hvm_ledger.id,
                recipient_legal_entity_id=legal_entity.id,
                amount=case.fee_amount,
                text=(
                    f"Mahngebühr Stufe {case.level} für Vertrag {case.contract_id}, "
                    "Entwurf, rechtliche Grundlage im Verwaltervertrag zu prüfen"
                ),
            )
            session.add(draft)
            await session.flush()
            case.fee_invoice_draft_id = draft.id


async def approve(
    session: AsyncSession, run: DunningRun, user_id: uuid.UUID, is_platform_admin: bool
) -> DunningRun:
    if run.status != "preview":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Lauf ist bereits freigegeben.")
    if run.created_by == user_id or is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
        )
    cases = (
        await session.scalars(
            select(DunningCase).where(
                DunningCase.run_id == run.id, DunningCase.status == "proposed"
            )
        )
    ).all()
    ledgers: dict[uuid.UUID, Ledger] = {}
    for case in cases:
        ledger = ledgers.get(case.ledger_id) or await session.get(Ledger, case.ledger_id)
        if ledger is None or not await leading.is_leading(
            session, ledger, leading.LeadingKind.DUNNING, run.run_date
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur das führende System darf mahnen.")
        ledgers[case.ledger_id] = ledger
    for case in cases:
        if case.fee_amount > 0:
            await _post_fee(session, case, ledgers[case.ledger_id], user_id)
    run.status, run.approved_by = "approved", user_id
    await session.flush()
    return run


DELIVERY_CHANNELS = ("post", "email", "portal")


async def mark_sent(
    session: AsyncSession,
    case: DunningCase,
    channel: str,
    user_id: uuid.UUID | None,
    received_on: date | None = None,
) -> DunningCase:
    """Minimal manual delivery record (M16-09): only this lets the ladder advance to the next
    level, since ``last_level`` only counts cases with status ``sent``. Proof of actual
    delivery (M16-02: letter generation, postal/e-mail evidence) stays a separate, open point;
    this only records that a person marked the case as sent, by which channel and when."""
    if case.status != "proposed":
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nur vorgeschlagene Fälle können als versendet gelten."
        )
    run = await session.get(DunningRun, case.run_id)
    if run is None or run.status != "approved":
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Mahnlauf muss zuerst freigegeben werden."
        )
    case.status = "sent"
    case.delivery_channel = channel
    case.delivered_at = datetime.now(UTC)
    # Receipt (Zugang) is a fact a person records; it is never derived from the send date.
    case.received_on = received_on
    case.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=case.tenant_id,
        type="dunning_case.sent",
        entity_type="dunning_case",
        entity_id=case.id,
        actor_user_id=user_id,
        payload={"level": case.level, "channel": channel},
    )
    return case


async def prepare_mahnbescheid(
    session: AsyncSession, case: DunningCase, user_id: uuid.UUID | None
) -> DunningMahnbescheidPrep:
    """Data set for a gerichtliches Mahnverfahren (7.5, M16): preparation only, no filing, no
    claim of completeness. Deadline hints stay ``zu prüfen`` (0.1.3)."""
    from mhvp.contacts.models import Contact, Party, PartyMember
    from mhvp.contracts.models import Contract

    existing = await session.scalar(
        select(DunningMahnbescheidPrep).where(DunningMahnbescheidPrep.case_id == case.id)
    )
    if existing is not None:
        return existing
    ledger = await session.get(Ledger, case.ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    contract = await session.get(Contract, case.contract_id) if case.contract_id else None
    party = await session.get(Party, contract.party_id) if contract else None
    contact_name, contact_id = None, None
    if party is not None:
        row = (
            await session.execute(
                select(Contact)
                .join(PartyMember, PartyMember.contact_id == Contact.id)
                .where(PartyMember.party_id == party.id)
                .limit(1)
            )
        ).first()
        if row is not None:
            contact = row[0]
            contact_id, contact_name = contact.id, contact.display_name
    snapshot = {
        "party_id": str(party.id) if party else None,
        "name": contact_name or (party.name if party else "unbekannt"),
        "contact_id": str(contact_id) if contact_id else None,
        "address_note": "Anschrift aus den Stammdaten zu prüfen",
    }
    nebenforderungen = []
    if case.fee_amount > 0:
        nebenforderungen.append(
            {"art": "Mahngebühr", "betrag": str(case.fee_amount), "stufe": case.level}
        )
    if case.interest_amount > 0:
        nebenforderungen.append(
            {
                "art": "Verzugszinsen",
                "betrag": str(case.interest_amount),
                "hinweis": "gesetzlicher Verzugszins, Näherung, rechtlich nicht geprüft",
            }
        )
    prep = DunningMahnbescheidPrep(
        tenant_id=case.tenant_id,
        case_id=case.id,
        antragsteller_legal_entity_id=ledger.legal_entity_id,
        antragsgegner_snapshot=snapshot,
        hauptforderung=case.total,
        nebenforderungen=nebenforderungen,
        zustelladresse=snapshot,
        aktenzeichen_intern=f"MB-{str(case.id)[:8]}",
        status="in_vorbereitung",
        created_by=user_id,
    )
    session.add(prep)
    await session.flush()
    return prep


def case_warnings(case: DunningCase) -> list[str]:
    """Warnings recorded in the case reason at preview time (M23-07) plus the missing payment
    account of the claim holder (M16-13)."""
    reason = case.reason or ""
    out = [w for w in (recipients.REPRESENTATIVE_ONLY_WARNING,) if w in reason]
    if case.bank_warning:
        out.append(case.bank_warning)
    return out


INTEREST_ACCOUNT_NUMBER = "489100"
INTEREST_ACCOUNT_NAME = "Verzugszinsen"


async def _interest_revenue_account(session: AsyncSession, ledger: Ledger) -> LedgerAccount:
    existing = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == INTEREST_ACCOUNT_NUMBER
        )
    )
    if existing is not None:
        return existing
    account = LedgerAccount(
        tenant_id=ledger.tenant_id,
        ledger_id=ledger.id,
        number=INTEREST_ACCOUNT_NUMBER,
        name=INTEREST_ACCOUNT_NAME,
        category=AccountCategory.REVENUE,
        type=AccountType.INCOME,
        is_system=True,
    )
    session.add(account)
    await session.flush()
    return account


async def create_interest_draft(
    session: AsyncSession, case: DunningCase, user_id: uuid.UUID | None
) -> JournalEntry:
    """Verzugszinsen as draft receivable (Sollstellungsentwurf) on the debtor's account in the
    claim holder's ledger (M16-05, decision 3 a). Only on the explicit request of a person
    after the run was approved, never automatically; the draft is released on the regular
    four eyes posting path behind G1. Idempotent per case."""
    if case.interest_entry_id is not None:
        existing = await session.get(JournalEntry, case.interest_entry_id)
        if existing is not None:
            return existing
    if case.status not in ("proposed", "sent"):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für ausgeschlossene Fälle gibt es keinen Zinsentwurf."
        )
    run = await session.get(DunningRun, case.run_id)
    if run is None or run.status != "approved":
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Mahnlauf muss zuerst freigegeben werden."
        )
    if case.interest_amount <= 0:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Fall weist keine Verzugszinsen aus.")
    # A block set after the run was approved stops the interest draft as well (M16-03).
    from mhvp.contracts.models import Contract

    contract = await session.get(Contract, case.contract_id) if case.contract_id else None
    if contract is not None and contract.dunning_block:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Mahnsperre am Vertrag: kein Zinsentwurf.")
    item_ids = [uuid.UUID(str(i["open_item_id"])) for i in case.open_items or []]
    if await active_item_blocks(session, item_ids):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Mahnsperre an einem Posten des Falls: kein Zinsentwurf."
        )
    ledger = await session.get(Ledger, case.ledger_id)
    if ledger is None or not await leading.is_leading(
        session, ledger, leading.LeadingKind.DUNNING, datetime.now(UTC).date()
    ):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Nur das führende System darf mahnen.")
    revenue = await _interest_revenue_account(session, ledger)
    entry = JournalEntry(
        tenant_id=case.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=datetime.now(UTC).date(),
        text=f"Verzugszinsen, Stufe {case.level}, Fall {case.id}, Entwurf zur Prüfung",
        kind=EntryKind.INTEREST,
        contract_id=case.contract_id,
        source=EntrySource.MANUAL,
        idempotency_key=f"dunning_interest:{case.id}",
    )
    lines = [
        acc.LineIn(case.debtor_account_id, case.interest_amount, Decimal("0")),
        acc.LineIn(revenue.id, Decimal("0"), case.interest_amount),
    ]
    await acc.write_draft(session, ledger, entry, lines, [])
    case.interest_entry_id = entry.id
    case.updated_by = user_id
    await session.flush()
    return entry


async def add_delivery_proof(
    session: AsyncSession,
    case: DunningCase,
    *,
    kind: str,
    proof_date: date,
    reference: str | None,
    document_id: uuid.UUID | None,
    note: str | None,
    user_id: uuid.UUID | None,
) -> DunningDeliveryProof:
    """Record evidence of dispatch or receipt (M16-01). Only for cases marked as sent; the
    evidence never sets the receipt date (Zugang) on its own."""
    if case.status != "sent":
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Zustellnachweise sind erst nach 'Als versendet markieren' möglich.",
        )
    if document_id is not None:
        from mhvp.documents.models import Document

        if await session.get(Document, document_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
    proof = DunningDeliveryProof(
        tenant_id=case.tenant_id,
        case_id=case.id,
        kind=kind,
        proof_date=proof_date,
        reference=reference,
        document_id=document_id,
        note=note,
        created_by=user_id,
    )
    session.add(proof)
    await session.flush()
    return proof


async def delivery_proofs(session: AsyncSession, case_id: uuid.UUID) -> list[DunningDeliveryProof]:
    return list(
        (
            await session.scalars(
                select(DunningDeliveryProof)
                .where(DunningDeliveryProof.case_id == case_id)
                .order_by(DunningDeliveryProof.proof_date, DunningDeliveryProof.created_at)
            )
        ).all()
    )
