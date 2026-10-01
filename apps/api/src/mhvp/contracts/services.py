"""Contract services: creditor entity, debtor accounts, versions, payments, deposits (6.3, 6.9)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, ContactKind, Party, PartyMember
from mhvp.contracts.models import (
    Contract,
    ContractAllocationValue,
    ContractKind,
    ContractPayment,
    ContractTerminationReading,
    DebtorAccountReservation,
    Deposit,
    DepositMovement,
    DepositMovementKind,
    MandateStatus,
    MandateType,
    PaymentInterval,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core.numbering import next_number
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.defaults import REDUCTION_PAYMENT_TYPES
from mhvp.properties.models import (
    AllocationKey,
    BankAccountKind,
    LegalEntity,
    LegalEntityKind,
    ManagementType,
    Meter,
    MeterReading,
    Property,
    PropertyBankAccount,
    PropertyOwner,
    ReadingSource,
    Unit,
)

# Debtor accounts 090000 to 099999, six digits (section 7.2, annex A.1);
# one per party and unit in the creditor's books (6.9.2, E02).
DEBTOR_START, DEBTOR_END = 90000, 99999
CENT = Decimal("0.01")


def invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


async def active_ownership(
    session: AsyncSession, unit_id: uuid.UUID, as_of: date
) -> Contract | None:
    row: Contract | None = await session.scalar(
        select(Contract).where(
            Contract.unit_id == unit_id,
            Contract.kind == ContractKind.OWNERSHIP,
            Contract.start_date <= as_of,
            or_(Contract.end_date.is_(None), Contract.end_date >= as_of),
        )
    )
    return row


async def sev_entity(session: AsyncSession, prop: Property, party_id: uuid.UUID) -> uuid.UUID:
    """Legal entity of an owner letting the unit through the SEV (6.9.11)."""
    existing = await session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.property_id == prop.id,
            LegalEntity.party_id == party_id,
            LegalEntity.kind == LegalEntityKind.SEV_OWNER,
        )
    )
    if existing is not None:
        return existing
    party = await session.get(Party, party_id)
    if party is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    entity = LegalEntity(
        tenant_id=prop.tenant_id,
        kind=LegalEntityKind.SEV_OWNER,
        name=f"{party.name} (SEV {prop.number})",
        party_id=party_id,
        property_id=prop.id,
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def creditor_entity(
    session: AsyncSession,
    prop: Property,
    unit: Unit,
    kind: ContractKind,
    start: date,
    requested: uuid.UUID | None,
) -> uuid.UUID:
    """Creditor of the contract claims (6.9.1): never the management company by default."""
    if kind is ContractKind.OWNERSHIP:
        if prop.management_type is ManagementType.RENTAL:
            raise invalid("Eigentumsverhältnisse gibt es nur in WEG-Objekten.")
        hoa = await session.scalar(
            select(LegalEntity.id).where(
                LegalEntity.property_id == prop.id, LegalEntity.kind == LegalEntityKind.HOA
            )
        )
        if hoa is None:  # pragma: no cover - created with the property
            raise invalid("Die Gemeinschaft der Wohnungseigentümer fehlt.")
        return hoa
    if prop.management_type is ManagementType.HOA:
        # M5-03 (operator decision 26.09.2026, docs/OPEN_QUESTIONS.md, A-015): tenancies in pure
        # HOA properties stay rejected; rental management only via HOA_WITH_SEV.
        raise invalid(
            "In reinen WEG-Objekten verwaltet die Plattform keine Mietverhältnisse. "
            "Dafür ist die Verwaltungsart WEG mit SEV vorgesehen."
        )
    if prop.management_type is ManagementType.HOA_WITH_SEV:
        ownership = await active_ownership(session, unit.id, start)
        if ownership is None or not ownership.sev_enabled:
            raise invalid("Für die Einheit besteht zum Mietbeginn kein Eigentum mit SEV.")
        entity = await sev_entity(session, prop, ownership.party_id)
        if requested is not None and requested != entity:
            raise invalid("Vermieter ist der Eigentümer der Einheit mit SEV.")
        return entity
    owners = (
        await session.scalars(
            select(PropertyOwner.party_id).where(
                PropertyOwner.property_id == prop.id,
                PropertyOwner.valid_from <= start,
                or_(PropertyOwner.valid_to.is_(None), PropertyOwner.valid_to >= start),
            )
        )
    ).all()
    entities = (
        await session.scalars(
            select(LegalEntity.id).where(
                LegalEntity.property_id == prop.id,
                LegalEntity.kind == LegalEntityKind.RENTAL_OWNER,
                LegalEntity.party_id.in_(owners),
            )
        )
    ).all()
    if requested is not None:
        if requested not in entities:
            raise invalid(
                "Der angegebene Vermieter ist zum Mietbeginn nicht Eigentümer des Objekts."
            )
        return requested
    if len(entities) != 1:
        raise invalid(
            "Der Vermieter ist nicht eindeutig. Bitte legal_entity_id angeben "
            "oder den Eigentümer des Objekts erfassen."
        )
    return entities[0]


async def debtor_account(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
    party: Party,
    unit: Unit,
) -> DebtorAccountReservation:
    """One debtor account per party and unit in the creditor's books (D15)."""
    existing = await session.scalar(
        select(DebtorAccountReservation).where(
            DebtorAccountReservation.legal_entity_id == legal_entity_id,
            DebtorAccountReservation.party_id == party.id,
            DebtorAccountReservation.unit_id == unit.id,
        )
    )
    if existing is not None:
        return existing
    number = await next_number(session, tenant_id, f"debtor:{legal_entity_id}", start=DEBTOR_START)
    if number > DEBTOR_END:  # pragma: no cover - capacity limit
        raise invalid("Der Nummernkreis der Debitorenkonten ist erschöpft.")
    account = DebtorAccountReservation(
        tenant_id=tenant_id,
        legal_entity_id=legal_entity_id,
        party_id=party.id,
        unit_id=unit.id,
        number=f"{number:06d}",
        name=f"{unit.label or unit.number} {party.name}"[:400],
    )
    session.add(account)
    await session.flush()
    return account


async def contract_number(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    from mhvp.core.number_format import SOURCES_KEY, effective_formats, format_number
    from mhvp.platform.models import TenantSettings

    sources = await session.scalar(select(TenantSettings.sources))
    if not (sources or {}).get(SOURCES_KEY, {}).get("contract"):
        return f"{await next_number(session, tenant_id, 'contract'):06d}"
    # GA01-07: tenant specific format; the start value applies to a circle not yet in use.
    fmt = effective_formats(sources)["contract"]
    value = await next_number(session, tenant_id, "contract", start=fmt.start)
    return format_number(fmt, value)


async def check_mandate(
    session: AsyncSession,
    mandate_id: uuid.UUID | None,
    direct_debit: bool,
    party_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
) -> None:
    if not direct_debit:
        return
    if mandate_id is None:
        raise invalid("Lastschrift braucht ein erfasstes SEPA-Mandat.")
    mandate = await session.get(SepaMandate, mandate_id)
    if mandate is None or mandate.status is not MandateStatus.ACTIVE:
        raise invalid("Das SEPA-Mandat ist nicht aktiv.")
    if mandate.party_id != party_id or mandate.legal_entity_id != legal_entity_id:
        raise invalid("Das SEPA-Mandat gehört nicht zu Vertragspartei und Gläubiger.")


async def check_b2b(session: AsyncSession, party_id: uuid.UUID, mandate_type: MandateType) -> None:
    """Firmenlastschrift only if every member of the party is a company (A-014)."""
    if mandate_type is not MandateType.B2B:
        return
    kinds = (
        await session.scalars(
            select(Contact.kind)
            .join(PartyMember, PartyMember.contact_id == Contact.id)
            .where(PartyMember.party_id == party_id)
        )
    ).all()
    if not kinds or any(k is not ContactKind.COMPANY for k in kinds):
        raise invalid("Firmenlastschrift ist nur möglich, wenn alle Beteiligten Unternehmen sind.")


def check_amounts(payment_type: str, net: Decimal, vat_percent: Decimal, gross: Decimal) -> None:
    if (net < 0 or gross < 0) and payment_type not in REDUCTION_PAYMENT_TYPES:
        raise invalid("Negative Beträge sind nur bei Mietminderungen zulässig.")
    if (net < 0) != (gross < 0) and net != 0 and gross != 0:
        raise invalid("Netto und Brutto müssen dasselbe Vorzeichen haben.")
    expected = (net * (1 + vat_percent / 100)).quantize(CENT)
    if abs(expected - gross) > CENT:
        raise invalid(f"Brutto passt nicht zu Netto und Steuersatz (erwartet {expected}).")


async def check_payment_reserve(
    session: AsyncSession, contract: Contract, reserve_id: uuid.UUID | None
) -> None:
    """AE08 (P07-02): the earmarked reserve of a payment component must be an active reserve
    of the GdWE ledger of the contract's property. Binding only; nothing is posted."""
    if reserve_id is None:
        return
    from mhvp.accounting.models import Ledger
    from mhvp.hoa.models import HoaReserve

    reserve = await session.get(HoaReserve, reserve_id)
    ledger = await session.get(Ledger, reserve.ledger_id) if reserve is not None else None
    if reserve is None or ledger is None or ledger.property_id != contract.property_id:
        raise invalid("Die Rücklage gehört nicht zur Gemeinschaft dieses Vertrags.")
    if not reserve.active:
        raise invalid("Die Rücklage ist nicht aktiv.")


async def add_payment(session: AsyncSession, contract: Contract, row: ContractPayment) -> None:
    """Close an open payment of the same type on the day before the new one (history kept)."""
    if row.valid_from < contract.start_date or (
        contract.end_date is not None and row.valid_from > contract.end_date
    ):
        raise invalid("Die Zahlung liegt außerhalb der Vertragslaufzeit.")
    previous = await session.scalar(
        select(ContractPayment).where(
            ContractPayment.contract_id == contract.id,
            ContractPayment.payment_type_code == row.payment_type_code,
            ContractPayment.valid_to.is_(None),
            ContractPayment.valid_from < row.valid_from,
        )
    )
    if previous is not None:
        previous.valid_to = row.valid_from - timedelta(days=1)
        await session.flush()
    session.add(row)


async def default_payment_interval(session: AsyncSession, tenant_id: uuid.UUID) -> PaymentInterval:
    """M13-01a: Mandanten-Standard für die Zahlweise (``TenantSettings.receivable_rules
    .payment_interval``), den ein neuer Zahlungsplan übernimmt, wenn er selbst keine Angabe
    trägt. Ohne Mandantenvorgabe bleibt es bei monatlich (bisheriges Verhalten)."""
    from mhvp.platform.models import TenantSettings

    raw = await session.scalar(
        select(TenantSettings.receivable_rules).where(TenantSettings.tenant_id == tenant_id)
    )
    value = (raw or {}).get("payment_interval")
    try:
        return PaymentInterval(value) if value else PaymentInterval.MONTHLY
    except ValueError:
        return PaymentInterval.MONTHLY


async def add_schedule(session: AsyncSession, contract: Contract, row: PaymentSchedule) -> None:
    previous = await session.scalar(
        select(PaymentSchedule).where(
            PaymentSchedule.contract_id == contract.id,
            PaymentSchedule.valid_to.is_(None),
            PaymentSchedule.valid_from < row.valid_from,
        )
    )
    if previous is not None:
        previous.valid_to = row.valid_from - timedelta(days=1)
        await session.flush()
    session.add(row)


async def check_no_later_rows(session: AsyncSession, contract: Contract, end: date) -> None:
    """Payments or schedules starting after ``end`` block ending the contract there. Shared
    by ``end_contract`` and the ownership transfer preview, so the preview refuses exactly
    what the transfer would refuse (a row starting on the title transfer date included)."""
    models: tuple[Any, ...] = (ContractPayment, PaymentSchedule)
    for model in models:
        later = await session.scalar(
            select(model.id).where(model.contract_id == contract.id, model.valid_from > end)
        )
        if later is not None:
            raise invalid("Nach dem Vertragsende gibt es noch Zahlungen oder Zahlungspläne.")


async def end_contract(session: AsyncSession, contract: Contract, end: date) -> None:
    """End a contract; later payments and schedules are rejected, open ones are closed."""
    if end < contract.start_date:
        raise invalid("Das Vertragsende liegt vor dem Vertragsbeginn.")
    await check_no_later_rows(session, contract, end)
    models: tuple[Any, ...] = (ContractPayment, PaymentSchedule)
    for model in models:
        rows = (
            await session.scalars(
                select(model).where(
                    model.contract_id == contract.id,
                    or_(model.valid_to.is_(None), model.valid_to > end),
                )
            )
        ).all()
        for r in rows:
            r.valid_to = end
    contract.end_date = end
    await session.flush()


class StandingAmounts:
    """Payments, payment schedule and allocation values of a contract valid on a date
    (Eigentümerwechsel, D16, D17): what a new ownership carries over from that date on."""

    def __init__(
        self,
        payments: list[ContractPayment],
        schedules: list[PaymentSchedule],
        allocation_values: list[ContractAllocationValue],
    ) -> None:
        self.payments = payments
        self.schedules = schedules
        self.allocation_values = allocation_values
        # Original ends, taken before the old contract is ended (which closes these rows).
        rows: list[Any] = [*payments, *schedules, *allocation_values]
        self.valid_to: dict[uuid.UUID, date | None] = {r.id: r.valid_to for r in rows}


async def standing_amounts(
    session: AsyncSession, contract: Contract, as_of: date
) -> StandingAmounts:
    """Rows of the contract valid on ``as_of`` (period contains the date), ordered stably."""

    async def rows(model: Any, *order: Any) -> list[Any]:
        return list(
            (
                await session.scalars(
                    select(model)
                    .where(
                        model.contract_id == contract.id,
                        model.valid_from <= as_of,
                        or_(model.valid_to.is_(None), model.valid_to >= as_of),
                    )
                    .order_by(*order, model.valid_from)
                )
            ).all()
        )

    return StandingAmounts(
        payments=await rows(ContractPayment, ContractPayment.payment_type_code),
        schedules=await rows(PaymentSchedule),
        allocation_values=await rows(
            ContractAllocationValue, ContractAllocationValue.allocation_key_id
        ),
    )


def _carried_copy(
    row: Any,
    model: Any,
    new: Contract,
    as_of: date,
    valid_to: date | None,
    actor: uuid.UUID | None,
) -> Any:
    copy = model(
        **{
            c.key: getattr(row, c.key)
            for c in model.__table__.columns
            if c.key not in ("id", "created_at", "updated_at", "created_by", "updated_by")
        }
    )
    copy.contract_id = new.id
    copy.valid_from = as_of
    copy.valid_to = valid_to
    copy.created_by = actor
    return copy


async def carry_over_standing_amounts(
    session: AsyncSession,
    amounts: StandingAmounts,
    new: Contract,
    as_of: date,
    actor: uuid.UUID | None,
) -> dict[str, int]:
    """Factual carry over of the standing amounts to the new ownership from ``as_of`` on:
    each row is copied with ``valid_from = as_of`` and its original ``valid_to`` (open rows stay
    open). Amounts, allocation keys and schedule settings are taken over unchanged; no legal
    statement about who owes what (rule W07, release point P01 stay open), no posting."""
    groups: tuple[tuple[Any, list[Any]], ...] = (
        (ContractPayment, amounts.payments),
        (PaymentSchedule, amounts.schedules),
        (ContractAllocationValue, amounts.allocation_values),
    )
    for model, rows in groups:
        for row in rows:
            session.add(_carried_copy(row, model, new, as_of, amounts.valid_to[row.id], actor))
    await session.flush()
    return {
        "payments": len(amounts.payments),
        "schedules": len(amounts.schedules),
        "allocation_values": len(amounts.allocation_values),
    }


async def close_allocation_values(
    session: AsyncSession, contract: Contract, end: date, actor: uuid.UUID | None
) -> None:
    """Allocation values of an ended contract stop at its end (values starting after the end
    are left untouched, as before)."""
    rows = (
        await session.scalars(
            select(ContractAllocationValue).where(
                ContractAllocationValue.contract_id == contract.id,
                ContractAllocationValue.valid_from <= end,
                or_(
                    ContractAllocationValue.valid_to.is_(None),
                    ContractAllocationValue.valid_to > end,
                ),
            )
        )
    ).all()
    for r in rows:
        r.valid_to = end
        r.updated_by = actor
    await session.flush()


async def move_open_rows(
    session: AsyncSession, old: Contract, new: Contract, effective: date
) -> None:
    """On a new version, rows valid from ``effective`` move; spanning rows are split."""
    models: tuple[Any, ...] = (ContractPayment, PaymentSchedule)
    for model in models:
        rows = (
            await session.scalars(
                select(model).where(
                    model.contract_id == old.id,
                    or_(model.valid_to.is_(None), model.valid_to >= effective),
                )
            )
        ).all()
        for r in rows:
            if r.valid_from >= effective:
                r.contract_id = new.id
                continue
            copy = model(
                **{
                    c.key: getattr(r, c.key)
                    for c in model.__table__.columns
                    if c.key not in ("id", "created_at", "updated_at")
                }
            )
            copy.contract_id = new.id
            copy.valid_from = effective
            r.valid_to = effective - timedelta(days=1)
            await session.flush()
            session.add(copy)
    await session.flush()


async def check_deposit_account(
    session: AsyncSession, contract: Contract, account_id: uuid.UUID | None
) -> None:
    """Deposits sit on a segregated deposit account of the landlord (6.9.1, D56)."""
    if contract.kind is not ContractKind.TENANCY:
        raise invalid("Kautionen gibt es nur bei Mietverhältnissen.")
    if account_id is None:
        return
    account = await session.get(PropertyBankAccount, account_id)
    if (
        account is None
        or account.kind is not BankAccountKind.DEPOSIT
        or not account.segregated
        or account.legal_entity_id != contract.legal_entity_id
    ):
        raise invalid("Das Konto ist kein getrenntes Kautionskonto des Vermieters.")


def deposit_totals(deposit: Deposit, movements: list[DepositMovement]) -> tuple[Decimal, Decimal]:
    received = sum(
        (m.amount for m in movements if m.kind is DepositMovementKind.PAYMENT), Decimal("0.00")
    )
    interest = sum(
        (m.amount for m in movements if m.kind is DepositMovementKind.INTEREST), Decimal("0.00")
    )
    out = sum(
        (
            m.amount
            for m in movements
            if m.kind in (DepositMovementKind.PAYOUT, DepositMovementKind.OFFSET)
        ),
        Decimal("0.00"),
    )
    return received, received + interest - out


# P1 additions (Ergänzung CRM 4.5, migration 0150) ---------------------------------------


async def add_allocation_value(
    session: AsyncSession,
    contract: Contract,
    key_id: uuid.UUID,
    value: Decimal,
    valid_from: date,
    valid_to: date | None,
) -> ContractAllocationValue:
    """Contract related allocation value (e.g. persons); the key must belong to the property
    of the contract and the period must lie within the contract term."""
    key = await session.get(AllocationKey, key_id)
    if key is None or key.property_id != contract.property_id:
        raise invalid("Der Umlageschlüssel gehört nicht zum Objekt des Vertrags.")
    if valid_from < contract.start_date or (
        contract.end_date is not None and valid_from > contract.end_date
    ):
        raise invalid("Der Umlagewert muss innerhalb der Vertragslaufzeit beginnen.")
    row = ContractAllocationValue(
        tenant_id=contract.tenant_id,
        contract_id=contract.id,
        allocation_key_id=key.id,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    session.add(row)
    return row


async def record_termination_readings(
    session: AsyncSession,
    contract: Contract,
    readings: list[tuple[uuid.UUID, Decimal, date | None]],
    actor: uuid.UUID | None,
) -> list[ContractTerminationReading]:
    """Meter readings at the end of a contract: each becomes a ``meter_reading`` (source
    ``manual``) plus the link row. Meters must belong to the unit or the property of the
    contract; a second termination reading for the same meter is rejected."""
    if not readings or contract.end_date is None:
        return []
    out: list[ContractTerminationReading] = []
    for meter_id, value, read_at in readings:
        meter = await session.get(Meter, meter_id)
        if meter is None or meter.property_id != contract.property_id:
            raise invalid("Der Zähler gehört nicht zum Objekt des Vertrags.")
        if meter.unit_id is not None and meter.unit_id != contract.unit_id:
            raise invalid("Der Zähler gehört zu einer anderen Einheit.")
        exists = await session.scalar(
            select(ContractTerminationReading.id).where(
                ContractTerminationReading.contract_id == contract.id,
                ContractTerminationReading.meter_id == meter.id,
            )
        )
        if exists is not None:
            raise invalid("Für diesen Zähler ist zur Beendigung bereits ein Stand erfasst.")
        day = read_at or contract.end_date
        reading = MeterReading(
            tenant_id=contract.tenant_id,
            meter_id=meter.id,
            read_at=day,
            value=value,
            source=ReadingSource.MANUAL,
            notes=f"Vertragsende {contract.number}",
            created_by=actor,
        )
        session.add(reading)
        await session.flush()
        link = ContractTerminationReading(
            tenant_id=contract.tenant_id,
            contract_id=contract.id,
            meter_id=meter.id,
            meter_reading_id=reading.id,
            value=value,
            read_at=day,
            created_by=actor,
        )
        session.add(link)
        out.append(link)
    await session.flush()
    return out
