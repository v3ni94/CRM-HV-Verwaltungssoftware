"""Operating cost statement for rental properties (7.6 A01 to A05, M17). Draft and calculation
only; issuing requires G3. Legal classification of costs is a human input (A02)."""

import hashlib
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import calc
from mhvp.billing.models import Statement, StatementCostItem, StatementSnapshot
from mhvp.core.problems import ErrorCodes, ProblemError

ADVANCE_CODES = ("operating_cost_advance", "heating_cost_advance")


async def legal_entity(session: AsyncSession, statement: Statement) -> Any:
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import LegalEntity

    ledger = await session.get(Ledger, statement.ledger_id)
    entity = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
    if entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return entity


async def occupants(session: AsyncSession, statement: Statement) -> list[dict[str, Any]]:
    """Tenancies per unit in the period plus vacancy gaps (vacancy stays with the owner, A05).
    In a SEV ledger only the units the owner held in the period belong to the statement
    (legal entity separation, 6.9.1)."""
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import LegalEntityKind, Unit

    entity = await legal_entity(session, statement)
    query = select(Unit).where(Unit.property_id == statement.property_id).order_by(Unit.number)
    if entity.kind is LegalEntityKind.SEV_OWNER:
        owned = select(Contract.unit_id).where(
            Contract.kind == ContractKind.OWNERSHIP,
            Contract.party_id == entity.party_id,
            Contract.start_date <= statement.period_to,
            (Contract.end_date.is_(None)) | (Contract.end_date >= statement.period_from),
        )
        query = query.where(Unit.id.in_(owned))
    units = (await session.scalars(query)).all()
    out: list[dict[str, Any]] = []
    for unit in units:
        leases = (
            await session.scalars(
                select(Contract)
                .where(Contract.unit_id == unit.id, Contract.kind == ContractKind.TENANCY)
                .order_by(Contract.start_date)
            )
        ).all()
        cursor = statement.period_from
        for lease in leases:
            span = calc.overlap(
                statement.period_from, statement.period_to, lease.start_date, lease.end_date
            )
            if span is None:
                continue
            if span[0] > cursor:
                out.append(
                    {
                        "key": f"vacancy:{unit.id}:{cursor.isoformat()}",
                        "unit_id": unit.id,
                        "unit_number": unit.number,
                        "contract_id": None,
                        "from": cursor,
                        "to": span[0] - timedelta(days=1),
                    }
                )
            out.append(
                {
                    "key": f"contract:{lease.id}",
                    "unit_id": unit.id,
                    "unit_number": unit.number,
                    "contract_id": lease.id,
                    "from": span[0],
                    "to": span[1],
                }
            )
            cursor = span[1] + timedelta(days=1)
        if cursor <= statement.period_to:
            out.append(
                {
                    "key": f"vacancy:{unit.id}:{cursor.isoformat()}",
                    "unit_id": unit.id,
                    "unit_number": unit.number,
                    "contract_id": None,
                    "from": cursor,
                    "to": statement.period_to,
                }
            )
    return out


async def weights(
    session: AsyncSession, key_id: uuid.UUID, occ: list[dict[str, Any]]
) -> list[calc.Share]:
    """Key value times days within each occupancy and value period (time valid values, 6.2)."""
    from mhvp.properties.models import UnitAllocationValue

    shares = []
    for o in occ:
        values = (
            await session.scalars(
                select(UnitAllocationValue).where(
                    UnitAllocationValue.unit_id == o["unit_id"],
                    UnitAllocationValue.allocation_key_id == key_id,
                )
            )
        ).all()
        weight = Decimal(0)
        covered = 0
        for v in values:
            span = calc.overlap(o["from"], o["to"], v.valid_from, v.valid_to)
            if span:
                n = calc.days(*span)
                weight += v.value * n
                covered += n
        if covered != calc.days(o["from"], o["to"]):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Schlüsselwert fehlt für Einheit {o['unit_number']} im Zeitraum.",
            )
        shares.append(calc.Share((o["unit_number"], o["key"]), weight))
    return shares


async def advances(
    session: AsyncSession, statement: Statement, contract_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    """Advances due in the period and paid until today (A04: due and paid shown apart)."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import ItemStatus, OpenItem, ReceivableItem

    items = (
        await session.scalars(
            select(ReceivableItem).where(
                ReceivableItem.contract_id == contract_id,
                ReceivableItem.status == ItemStatus.POSTED,
                ReceivableItem.payment_type_code.in_(ADVANCE_CODES),
                ReceivableItem.period_month.between(statement.period_from, statement.period_to),
            )
        )
    ).all()
    due = sum((i.amount for i in items), Decimal("0.00"))
    paid = Decimal("0.00")
    for i in items:
        oi = await session.scalar(
            select(OpenItem).where(OpenItem.journal_entry_id == i.journal_entry_id)
        )
        if oi is not None:
            paid += oi.amount - await acc.remaining(session, oi.id)
    return due, paid


async def check_item(
    session: AsyncSession, statement: Statement, item: StatementCostItem, entity_kind: Any
) -> dict[str, Any]:
    """Locks per position (A02, A03, D21, D22). Returns the key facts kept in the snapshot.

    The allocability of a cost type is a human classification (M17-01): an account that is
    classified as not allocable, or not classified at all, never reaches the tenants, and the
    account name is no proof. A mixed invoice is only accepted as far as the allocable share
    is posted on the allocable account in the period (split proven by the posting). For a let
    condominium the general key copied from the tenant template (living area) is no
    distribution basis by itself (§ 556a Abs. 3 BGB); the key must be recorded for the
    property with its source in the position basis.
    """
    from mhvp.accounting.models import (
        AllocationCategory,
        EntryStatus,
        JournalEntry,
        JournalLine,
        LedgerAccount,
    )
    from mhvp.properties.models import AllocationKey, LegalEntityKind

    facts: dict[str, Any] = {"account": None, "allocation_key": None}
    if item.account_id is not None:
        account = await session.get(LedgerAccount, item.account_id)
        if account is None or account.ledger_id != statement.ledger_id:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"{item.label}: Konto gehört nicht zum Buchungskreis."
            )
        if account.allocation_category is AllocationCategory.NONE:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"{item.label}: Umlagefähigkeit des Kontos {account.number} ist nicht "
                    "eingeordnet; der Kontoname ist kein Nachweis (A02, M17-01)."
                ),
            )
        if account.allocation_category.value.startswith("non_allocable"):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"{item.label}: Konto {account.number} ist als nicht umlagefähig eingeordnet; "
                    "Verwaltung und Instandsetzung bleiben aus der Wohnraumbelastung (A02, D22)."
                ),
            )
        debit, credit = (
            await session.execute(
                select(
                    func.coalesce(func.sum(JournalLine.debit), 0),
                    func.coalesce(func.sum(JournalLine.credit), 0),
                )
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                .where(
                    JournalLine.account_id == account.id,
                    JournalEntry.status == EntryStatus.POSTED,
                    JournalEntry.booking_date.between(statement.period_from, statement.period_to),
                )
            )
        ).one()
        posted = Decimal(debit) - Decimal(credit)
        if item.amount > posted:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"{item.label}: Betrag {item.amount} übersteigt die im Zeitraum auf Konto "
                    f"{account.number} gebuchten Kosten {posted}; die Aufteilung einer "
                    "Mischrechnung muss gebucht und belegt sein (A02, D22)."
                ),
            )
        facts["account"] = {
            "number": account.number,
            "allocation_category": account.allocation_category.value,
            "posted_in_period": str(posted),
        }
    if item.allocation_key_id is not None:
        key = await session.get(AllocationKey, item.allocation_key_id)
        if key is None or key.property_id != statement.property_id:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"{item.label}: Schlüssel gehört nicht zum Objekt."
            )
        if entity_kind is LegalEntityKind.SEV_OWNER and key.is_template_derived:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"{item.label}: bei vermietetem Wohnungseigentum gilt ohne abweichende "
                    "Vereinbarung nicht automatisch der allgemeine Schlüssel "
                    f"{key.code} aus dem Muster; Verteilungsmaßstab mit Quelle und "
                    "Geltungsbeginn für das Objekt erfassen (§ 556a Abs. 3 BGB, A03, M17-01)."
                ),
            )
        facts["allocation_key"] = {
            "code": key.code,
            "name": key.name,
            "template_derived": key.is_template_derived,
        }
    return facts


async def calculate(
    session: AsyncSession, statement: Statement, user_id: uuid.UUID | None, today: date
) -> StatementSnapshot:
    from mhvp.properties.models import LegalEntityKind

    entity = await legal_entity(session, statement)
    if entity.kind not in (LegalEntityKind.RENTAL_OWNER, LegalEntityKind.SEV_OWNER):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Betriebskostenabrechnungen nur im Buchungskreis des Vermieters.",
        )
    items = (
        await session.scalars(
            select(StatementCostItem)
            .where(StatementCostItem.statement_id == statement.id)
            .order_by(StatementCostItem.created_at)
        )
    ).all()
    if not items:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Kostenpositionen erfasst.")
    occ = await occupants(session, statement)
    per_key: dict[str, Decimal] = {o["key"]: Decimal("0.00") for o in occ}
    positions = []
    for item in items:
        facts = await check_item(session, statement, item, entity.kind)
        if item.external_amounts:
            amounts = {k: Decimal(v) for k, v in item.external_amounts.items()}
            if sum(amounts.values(), Decimal("0")) != item.amount:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"{item.label}: Einzelbeträge ergeben nicht die Summe.",
                )
            unknown = set(amounts) - set(per_key)
            if unknown:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"{item.label}: unbekannte Nutzer {sorted(unknown)}.",
                )
            split = amounts
        elif item.heating:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"{item.label}: Heizkosten nur aus externer Abrechnung (H01).",
            )
        elif item.allocation_key_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"{item.label}: Umlageschlüssel fehlt."
            )
        else:
            dist = calc.distribute(item.amount, await weights(session, item.allocation_key_id, occ))
            split = {k[1]: v for k, v in dist.items()}
        for k, v in split.items():
            per_key[k] += v
        positions.append(
            {
                "label": item.label,
                "amount": str(item.amount),
                "basis": item.basis,
                **facts,
                "split": {k: str(v) for k, v in split.items()},
            }
        )
    results = []
    vacancy = Decimal("0.00")
    period_deadline = calc.deadline(statement.period_to)
    for o in occ:
        share = per_key[o["key"]]
        if o["contract_id"] is None:
            vacancy += share
            continue
        due, paid = await advances(session, statement, o["contract_id"])
        balance = share - paid
        results.append(
            {
                "contract_id": str(o["contract_id"]),
                "unit_number": o["unit_number"],
                "from": o["from"].isoformat(),
                "to": o["to"].isoformat(),
                "costs": str(share),
                "advances_due": str(due),
                "advances_paid": str(paid),
                "advances_open": str(due - paid),
                "balance": str(balance),  # > 0 additional payment, < 0 credit
                "late_claim_blocked": balance > 0
                and today > period_deadline
                and not statement.deadline_exception,
            }
        )
    inputs = {
        "period": [statement.period_from.isoformat(), statement.period_to.isoformat()],
        "occupants": [
            {
                **o,
                "unit_id": str(o["unit_id"]),
                "contract_id": str(o["contract_id"]) if o["contract_id"] else None,
                "from": o["from"].isoformat(),
                "to": o["to"].isoformat(),
            }
            for o in occ
        ],
        "positions": positions,
    }
    output = {
        "results": results,
        "vacancy_owner_share": str(vacancy),
        "total": str(sum((i.amount for i in items), Decimal("0.00"))),
        "deadline_orientation": period_deadline.isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps({"inputs": inputs, "results": output}, sort_keys=True).encode()
    ).hexdigest()
    snap = StatementSnapshot(
        tenant_id=statement.tenant_id,
        statement_id=statement.id,
        rule_version=calc.rule_version(statement.period_from),
        inputs=inputs,
        results=output,
        hash=digest,
        created_by=user_id,
    )
    session.add(snap)
    await session.flush()
    return snap


def check_issue(statement: Statement, snapshot: StatementSnapshot, delivered_at: date) -> None:
    """Issuing needs the day the statement reached the tenant (A04, D23, M17-04).

    Creation or calculation is never the access: the access day cannot lie before the
    calculation. Additional payments whose access lies after the deadline orientation stay
    locked without a recorded exception; the day of calculation does not matter for that.
    """
    from mhvp.workspace.services import local_date

    calculated_on = local_date(snapshot.created_at)
    if delivered_at < calculated_on:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Zugang {delivered_at.isoformat()} liegt vor der Berechnung "
                f"{calculated_on.isoformat()}; die Erstellung gilt nicht als Zugang (D23)."
            ),
        )
    period_deadline = calc.deadline(statement.period_to)
    late = [
        r["unit_number"]
        for r in snapshot.results["results"]
        if Decimal(r["balance"]) > 0 and (r["late_claim_blocked"] or delivered_at > period_deadline)
    ]
    if late and not statement.deadline_exception:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=(
                "Nachforderung nach Fristablauf ohne geprüfte Ausnahme "
                f"(Zugang {delivered_at.isoformat()}, Fristorientierung "
                f"{period_deadline.isoformat()}, Einheiten {', '.join(late)})."
            ),
        )
