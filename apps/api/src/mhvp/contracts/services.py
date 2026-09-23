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
    ContractKind,
    ContractPayment,
    DebtorAccountReservation,
    Deposit,
    DepositMovement,
    DepositMovementKind,
    MandateStatus,
    MandateType,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core.numbering import next_number
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.defaults import REDUCTION_PAYMENT_TYPES
from mhvp.properties.models import (
    BankAccountKind,
    LegalEntity,
    LegalEntityKind,
    ManagementType,
    Property,
    PropertyBankAccount,
    PropertyOwner,
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
    return f"{await next_number(session, tenant_id, 'contract'):06d}"


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


async def end_contract(session: AsyncSession, contract: Contract, end: date) -> None:
    """End a contract; later payments and schedules are rejected, open ones are closed."""
    if end < contract.start_date:
        raise invalid("Das Vertragsende liegt vor dem Vertragsbeginn.")
    models: tuple[Any, ...] = (ContractPayment, PaymentSchedule)
    for model in models:
        later = await session.scalar(
            select(model.id).where(model.contract_id == contract.id, model.valid_from > end)
        )
        if later is not None:
            raise invalid("Nach dem Vertragsende gibt es noch Zahlungen oder Zahlungspläne.")
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
