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
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    AccountType,
    DunningCase,
    DunningFeeInvoiceDraft,
    DunningMahnbescheidPrep,
    DunningRun,
    DunningSettings,
    EntryKind,
    EntrySource,
    JournalEntry,
    LeadingSystem,
    Ledger,
    LedgerAccount,
)
from mhvp.core.problems import ErrorCodes, ProblemError

CENT = Decimal("0.01")
FEE_ACCOUNT_NUMBER = "489000"
FEE_ACCOUNT_NAME = "Mahngebühren"


async def settings_for(
    session: AsyncSession, property_id: uuid.UUID | None
) -> DunningSettings | None:
    if property_id is not None:
        own = await session.scalar(
            select(DunningSettings).where(DunningSettings.property_id == property_id)
        )
        if own is not None:
            return own
    default: DunningSettings | None = await session.scalar(
        select(DunningSettings).where(DunningSettings.property_id.is_(None))
    )
    return default


async def last_level(session: AsyncSession, account_id: uuid.UUID) -> int:
    level = await session.scalar(
        select(DunningCase.level)
        .where(DunningCase.debtor_account_id == account_id, DunningCase.status == "sent")
        .order_by(DunningCase.level.desc())
        .limit(1)
    )
    return int(level or 0)


def preset_levels() -> list[dict[str, Any]]:
    """V7 Vorschlagswerte (Betreiberentscheidung 25.09.2026): Tage entschieden, Beträge offen."""
    return [
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


def interest_spread_presets() -> dict[str, str]:
    """§ 288 BGB unterscheidet Anspruchsarten (Verbraucher/Unternehmer); Werte nur als
    Vorschlag für ``interest_spread``, nie als Basiszinssatz (der bleibt Betreiberpflege)."""
    return {"verbraucher": "5", "unternehmer": "9"}


def fee_amount_for(settings: DunningSettings, level: int) -> Decimal | None:
    if settings.fee_from_level is None or level < settings.fee_from_level:
        return None
    config = next((lv for lv in settings.levels if int(lv["level"]) == level), None)
    if config is None:
        return None
    raw = config.get("fee_amount")
    if raw is None:
        return None
    return Decimal(str(raw))


def interest_amount_for(settings: DunningSettings, total: Decimal, days: int) -> Decimal:
    """Informational only (Nebenforderung), never booked automatically. Zero unless the
    operator both enabled interest and maintained a Basiszinssatz; the day count and formula
    are a generic approximation and are not a legal certification (0.2)."""
    if not settings.interest_enabled or settings.interest_base_rate is None or days <= 0:
        return Decimal("0.00")
    rate = settings.interest_base_rate + (settings.interest_spread or Decimal("0"))
    amount = total * rate / Decimal("100") * Decimal(days) / Decimal("365")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


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
        for account_id, overdue in sorted(by_account.items(), key=lambda kv: str(kv[0])):
            account = await session.get(LedgerAccount, account_id)
            contract_id = next((i["contract_id"] for i in overdue if i["contract_id"]), None)
            contract = await session.get(Contract, contract_id) if contract_id else None
            total = sum((i["remaining"] for i in overdue), Decimal("0.00"))
            oldest = min(i["due_date"] for i in overdue)
            days = (run_date - oldest).days
            level = await last_level(session, account_id) + 1
            reason = None
            if settings is None or not settings.levels:
                reason = "Keine Mahnstufen eingerichtet"
            elif contract is not None and contract.dunning_block:
                reason = f"Mahnsperre: {contract.dunning_block_reason or 'ohne Angabe'}"
            elif total < settings.threshold_amount:
                reason = "Unter der Mahngrenze"
            else:
                config = next((lv for lv in settings.levels if int(lv["level"]) == level), None)
                if config is None:
                    reason = (
                        "Höchste Mahnstufe erreicht: weitere Schritte nur nach Einzelfallprüfung"
                    )
                elif days < int(config["min_days_overdue"]):
                    reason = f"Noch nicht {config['min_days_overdue']} Tage überfällig"
            if reason is None and ledger.leading_system is not LeadingSystem.MHVP:
                reason = "Buchungskreis nicht führend: gemahnt wird im führenden System (6.9.10)"
            fee_amount = Decimal("0.00")
            interest_amount = Decimal("0.00")
            if reason is None and settings is not None:
                fee_amount = fee_amount_for(settings, level) or Decimal("0.00")
                interest_amount = interest_amount_for(settings, total, days)
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
                    reason=reason
                    if reason
                    else f"{days} Tage seit Fälligkeit, Konto {account.number if account else ''}",
                )
            )
            counts["excluded" if reason else "proposed"] += 1
    run.totals = counts
    await session.flush()
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
        if ledger is None or ledger.leading_system is not LeadingSystem.MHVP:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur das führende System darf mahnen.")
        ledgers[case.ledger_id] = ledger
    for case in cases:
        if case.fee_amount > 0:
            await _post_fee(session, case, ledgers[case.ledger_id], user_id)
    run.status, run.approved_by = "approved", user_id
    await session.flush()
    return run


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
