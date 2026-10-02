"""Contract endpoints (/api/v1/contracts, /sepa-mandates, /deposits, occupancy)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.contacts.models import Contact, ContactBankAccount, Party, PartyMember
from mhvp.contacts.services import approval_block_reason, party_for_contact, recompute_for_party
from mhvp.contacts.validation import mask_iban
from mhvp.contracts import schemas as s
from mhvp.contracts import services as svc
from mhvp.contracts.models import (
    Contract,
    ContractAllocationValue,
    ContractKind,
    ContractPayment,
    ContractTerminationReading,
    DebtorAccountReservation,
    Deposit,
    DepositHintSetting,
    DepositMovement,
    MandateStatus,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_property_allowed,
    property_path_guard,
    session_allowed_property_ids,
)
from mhvp.core.bulk import BULK_MAX_ITEMS, BulkResultOut, run_bulk
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.events import diff, emit
from mhvp.core.listparams import (
    LIST_PARAMS_DOC,
    ListParams,
    apply_filters,
    apply_sort,
    check_include,
    embed,
    list_params,
    strict_query,
    valid_on,
)
from mhvp.core.pagination import PAGE_HEADERS, paginate
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError
from mhvp.documents.models import Document, DocumentLink, LinkRole
from mhvp.properties.models import AllocationKey, ManagementType, Property, Unit
from mhvp.properties.services import check_catalog, check_custom_fields, check_ledger_account

router = APIRouter(tags=["Verträge"], dependencies=[Depends(property_path_guard)])
READ = require_permission("contracts:read")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")
# Management approval of imported contracts (tenant_admin and administrator only).
APPROVE = require_permission("contracts:approve")
SETTINGS_READ_DEPOSIT = require_permission("tenant_settings:read")
SETTINGS_UPDATE_DEPOSIT = require_permission("tenant_settings:update")


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def _get(session: Any, model: Any, entity_id: uuid.UUID, *, lock: bool = False) -> Any:
    # AC01-01: lock=True loads FOR UPDATE before an If-Match comparison.
    row = await session.get(model, entity_id, with_for_update=True if lock else None)
    if row is None:
        raise _nf()
    # M2-02/S16-02: property assignment of the membership (404 outside it).
    if isinstance(getattr(row, "property_id", None), uuid.UUID):
        ensure_session_property_allowed(session, row.property_id)
    return row


async def _flush(session: Any, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise ProblemError(ErrorCodes.CONFLICT, detail=message) from None


async def _out(session: Any, contract: Contract) -> s.ContractOut:
    await session.flush()
    await session.refresh(contract)
    return (await _outs(session, [contract]))[0]


def _address(prop: Property) -> str | None:
    street = " ".join(p for p in (prop.street, prop.house_number) if p)
    place = " ".join(p for p in (prop.postal_code, prop.city) if p)
    return ", ".join(p for p in (street, place) if p) or None


async def _context(session: Any, contracts: Sequence[Contract]) -> dict[uuid.UUID, dict[str, Any]]:
    """Property, unit, party and member names per contract (four batched queries)."""
    props = {
        p.id: p
        for p in (
            await session.scalars(
                select(Property).where(Property.id.in_({c.property_id for c in contracts}))
            )
        ).all()
    }
    units = {
        u.id: u
        for u in (
            await session.scalars(select(Unit).where(Unit.id.in_({c.unit_id for c in contracts})))
        ).all()
    }
    party_ids = {c.party_id for c in contracts}
    parties = {
        p.id: p for p in (await session.scalars(select(Party).where(Party.id.in_(party_ids)))).all()
    }
    members: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for party_id, contact_id, name, role in (
        await session.execute(
            select(PartyMember.party_id, Contact.id, Contact.display_name, PartyMember.role)
            .join(Contact, Contact.id == PartyMember.contact_id)
            .where(PartyMember.party_id.in_(party_ids))
            .order_by(PartyMember.party_id, PartyMember.role, Contact.display_name)
        )
    ).all():
        members.setdefault(party_id, []).append(
            {"contact_id": contact_id, "name": name or "", "role": str(role)}
        )
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for c in contracts:
        prop, unit, party = props.get(c.property_id), units.get(c.unit_id), parties.get(c.party_id)
        out[c.id] = {
            "property_number": prop.number if prop else None,
            "property_name": prop.name if prop else None,
            "property_address": _address(prop) if prop else None,
            "unit_number": unit.number if unit else None,
            "unit_label": unit.label if unit else None,
            "party_name": party.name if party else None,
            "members": members.get(c.party_id, []),
        }
    return out


async def _outs(session: Any, contracts: Sequence[Contract]) -> list[s.ContractOut]:
    """Output of several contracts with three batched queries (debtor accounts, payments,
    schedules) instead of three per row (performance review 26.09.2026)."""
    if not contracts:
        return []
    ids = [c.id for c in contracts]
    accounts = {
        a.id: a
        for a in (
            await session.scalars(
                select(DebtorAccountReservation).where(
                    DebtorAccountReservation.id.in_({c.debtor_account_id for c in contracts})
                )
            )
        ).all()
    }
    payments: dict[uuid.UUID, list[ContractPayment]] = {}
    for p in (
        await session.scalars(
            select(ContractPayment)
            .where(ContractPayment.contract_id.in_(ids))
            .order_by(ContractPayment.payment_type_code, ContractPayment.valid_from)
        )
    ).all():
        payments.setdefault(p.contract_id, []).append(p)
    schedules: dict[uuid.UUID, list[PaymentSchedule]] = {}
    for x in (
        await session.scalars(
            select(PaymentSchedule)
            .where(PaymentSchedule.contract_id.in_(ids))
            .order_by(PaymentSchedule.valid_from)
        )
    ).all():
        schedules.setdefault(x.contract_id, []).append(x)
    ctx = await _context(session, contracts)
    out = []
    for contract in contracts:
        data = {c.key: getattr(contract, c.key) for c in Contract.__table__.columns}
        out.append(
            s.ContractOut.model_validate(
                {
                    **data,
                    "debtor_account": s.DebtorAccountOut.model_validate(
                        accounts[contract.debtor_account_id]
                    ),
                    "payments": [
                        s.PaymentOut.model_validate(p) for p in payments.get(contract.id, [])
                    ],
                    "schedules": [
                        s.ScheduleOut.model_validate(x) for x in schedules.get(contract.id, [])
                    ],
                    **ctx.get(contract.id, {}),
                }
            )
        )
    return out


CONTRACT_EVENT_ALIASES: dict[str, str] = {
    "contract.updated": "contract.changed",
    "contract.versioned": "contract.changed",
    "contract.schedule_updated": "contract.changed",
    "contract.payment_added": "contract_payment.changed",
    "contract.payment_updated": "contract_payment.changed",
}


async def _event(
    session: Any,
    principal: TenantPrincipal,
    type_: str,
    entity_id: uuid.UUID,
    *,
    changes: dict[str, Any] | None = None,
    **payload: Any,
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type=type_.split(".")[0],
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={k: str(v) if v is not None else None for k, v in payload.items()},
        changes=changes,
    )
    # Spec names of section 12 in addition to the detailed types (assumption A-GA04-03).
    alias = CONTRACT_EVENT_ALIASES.get(type_)
    if alias is not None:
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=alias,
            entity_type="contract",
            entity_id=entity_id,
            actor_user_id=principal.user_id,
            payload={"source_type": type_, "contract_id": str(entity_id)},
        )


def _plain(values: dict[str, Any]) -> dict[str, Any]:
    """JSON safe copy for the audit diff (dates, UUIDs and Decimals as text)."""
    return {
        k: (None if v is None else v if isinstance(v, bool | int | str) else str(v))
        for k, v in values.items()
    }


async def _create(
    session: Any,
    principal: TenantPrincipal,
    body: s.ContractIn,
    supersedes: uuid.UUID | None = None,
) -> Contract:
    unit = await _get(session, Unit, body.unit_id)
    prop = await _get(session, Property, unit.property_id)
    party = await _get(session, Party, body.party_id)
    creditor = await svc.creditor_entity(
        session, prop, unit, body.kind, body.start_date, body.legal_entity_id
    )
    await svc.check_mandate(session, body.sepa_mandate_id, body.direct_debit, party.id, creditor)
    if body.sev_enabled and prop.management_type is not ManagementType.HOA_WITH_SEV:
        raise svc.invalid("SEV ist nur in Objekten mit der Verwaltungsart WEG mit SEV möglich.")
    if body.sev_fee_debtor_party_id is not None:
        await _get(session, Party, body.sev_fee_debtor_party_id)
    account = await svc.debtor_account(session, principal.tenant_id, creditor, party, unit)
    data = body.model_dump(exclude={"legal_entity_id"})
    data["custom_fields"] = await check_custom_fields(
        session,
        "contract",
        body.custom_fields,
        management_type=prop.management_type,
        contract_kind=body.kind.value,
        create=True,
    )
    if body.sev_enabled and data["sev_fee_debtor_party_id"] is None:
        data["sev_fee_debtor_party_id"] = party.id
    contract = Contract(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        property_id=prop.id,
        legal_entity_id=creditor,
        debtor_account_id=account.id,
        number=await svc.contract_number(session, principal.tenant_id),
        supersedes_contract_id=supersedes,
        **data,
    )
    session.add(contract)
    await _flush(
        session,
        "Für die Einheit besteht im Zeitraum bereits ein Vertrag dieser Art "
        "(Mietverhältnis oder Eigentum).",
    )
    await recompute_for_party(session, party.id)
    return contract


# Contracts -----------------------------------------------------------------------------


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _search_condition(q: str) -> Any:
    """Every word of ``q`` must match one of the searchable columns (ILIKE on plain columns;
    each subquery is itself under the tenant RLS policy, so no foreign rows can match)."""
    conditions = []
    for word in q.split()[:5]:
        like = _like(word)
        conditions.append(
            or_(
                Contract.number.ilike(like),
                Contract.party_id.in_(select(Party.id).where(Party.name.ilike(like))),
                Contract.party_id.in_(
                    select(PartyMember.party_id)
                    .join(Contact, Contact.id == PartyMember.contact_id)
                    .where(
                        or_(
                            Contact.display_name.ilike(like),
                            Contact.company_name.ilike(like),
                            Contact.first_name.ilike(like),
                            Contact.last_name.ilike(like),
                        )
                    )
                ),
                Contract.property_id.in_(
                    select(Property.id).where(
                        or_(
                            Property.number.ilike(like),
                            Property.name.ilike(like),
                            Property.street.ilike(like),
                            Property.city.ilike(like),
                            Property.postal_code.ilike(like),
                        )
                    )
                ),
                Contract.unit_id.in_(
                    select(Unit.id).where(or_(Unit.number.ilike(like), Unit.label.ilike(like)))
                ),
            )
        )
    return and_(*conditions)


_CONTRACT_FILTERS = {
    "kind": Contract.kind,
    "property_id": Contract.property_id,
    "unit_id": Contract.unit_id,
    "party_id": Contract.party_id,
    "legal_entity_id": Contract.legal_entity_id,
    "direct_debit": Contract.direct_debit,
    "dunning_block": Contract.dunning_block,
    "vat_option": Contract.vat_option,
    "sev_enabled": Contract.sev_enabled,
    "approval_status": Contract.approval_status,
    "start_date": Contract.start_date,
    "end_date": Contract.end_date,
}
_CONTRACT_SORT = {
    "number": Contract.number,
    "start_date": Contract.start_date,
    "end_date": Contract.end_date,
    "termination_date": Contract.termination_date,
    "kind": Contract.kind,
    "created_at": Contract.created_at,
    "updated_at": Contract.updated_at,
}


@router.get(
    "/contracts",
    summary="Verträge",
    responses=PAGE_HEADERS,
    response_model=list[s.ContractOut],
    description=LIST_PARAMS_DOC
    + " include: party (Vertragspartei mit Mitgliedern), property (Objekt).",
    dependencies=[Depends(strict_query)],
)
async def list_contracts(
    request: Request,
    response: Response,
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    party_id: uuid.UUID | None = None,
    kind: ContractKind | None = None,
    active_on: date | None = None,
    status: Literal["active", "ended", "upcoming"] | None = Query(
        default=None,
        description="Laufzeitstatus zum Stichtag as_of: active, ended (Ende vor dem Stichtag), "
        "upcoming (Beginn nach dem Stichtag)",
    ),
    as_of: date | None = Query(default=None, description="Stichtag für status, Standard heute"),
    q: str | None = Query(
        default=None,
        max_length=200,
        description="Freitextsuche: Vertragsnummer, Name der Vertragspartei oder eines "
        "Mitglieds (Mieter, Eigentümer), Objektnummer, Objektname, Objektanschrift, Einheit",
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=1000,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    params: ListParams = Depends(list_params),
    principal: TenantPrincipal = Depends(READ),
) -> Any:
    """Verträge nach Nummer und Version. Paginierung wie ``GET /tickets``: die Antwort bleibt
    eine Liste, Gesamtzahl und Seite stehen in ``X-Total-Count``, ``X-Page``, ``X-Page-Size``.
    ``status=ended`` liefert beendete Verträge (Ende vor dem Stichtag)."""
    includes = check_include(params, ("party", "property"))
    async with tenant_tx(request, principal) as session:
        query = apply_filters(select(Contract), params, _CONTRACT_FILTERS)
        if status is not None:
            day = as_of or datetime.now(UTC).date()
            if status == "ended":
                query = query.where(Contract.end_date.is_not(None), Contract.end_date < day)
            elif status == "upcoming":
                query = query.where(Contract.start_date > day)
            else:
                query = query.where(
                    Contract.start_date <= day,
                    or_(Contract.end_date.is_(None), Contract.end_date >= day),
                )
        for column, value in (
            (Contract.property_id, property_id),
            (Contract.unit_id, unit_id),
            (Contract.party_id, party_id),
            (Contract.kind, kind),
        ):
            if value is not None:
                query = query.where(column == value)
        if active_on is not None:
            query = query.where(
                Contract.start_date <= active_on,
                or_(Contract.end_date.is_(None), Contract.end_date >= active_on),
            )
        if q and q.strip():
            query = query.where(_search_condition(q))
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            query = query.where(Contract.property_id.in_(list(allowed)))
        rows = await paginate(
            session,
            apply_sort(
                query, params, _CONTRACT_SORT, (Contract.number, Contract.version, Contract.id)
            ),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        embedded: dict[str, Any] = {}
        if "property" in includes:
            from mhvp.properties.refs import property_refs

            props = await property_refs(session, [c.property_id for c in rows])
            embedded["property"] = lambda item: props.get(uuid.UUID(item["property_id"]))
        if "party" in includes:
            parties = await _party_refs(session, {c.party_id for c in rows})
            embedded["party"] = lambda item: parties.get(uuid.UUID(item["party_id"]))
        return embed(await _outs(session, rows), params, s.ContractOut, embedded, response=response)


async def _party_refs(session: Any, party_ids: set[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Q12 include=party: contract party with its members (contact id, name, role)."""
    if not party_ids:
        return {}
    out: dict[uuid.UUID, dict[str, Any]] = {
        p.id: {"id": p.id, "name": p.name, "members": []}
        for p in (await session.scalars(select(Party).where(Party.id.in_(party_ids)))).all()
    }
    rows = await session.execute(
        select(PartyMember.party_id, PartyMember.role, Contact.id, Contact.display_name)
        .join(Contact, Contact.id == PartyMember.contact_id)
        .where(PartyMember.party_id.in_(party_ids))
        .order_by(Contact.display_name, Contact.id)
    )
    for party_id, role, contact_id, name in rows.all():
        if party_id in out:
            out[party_id]["members"].append({"contact_id": contact_id, "name": name, "role": role})
    return out


class ContractBulkIn(BaseModel):
    """Bulk action on contracts (S12-05): ``set_dunning_block`` sets or lifts the dunning
    block; setting it needs ``reason`` (same rule as ``PATCH /contracts/{id}/notes``)."""

    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX_ITEMS)
    action: Literal["set_dunning_block"]
    value: bool
    reason: str | None = Field(default=None, max_length=500)


@router.post(
    "/contracts/bulk",
    summary="Massenaktion Verträge mit Teilerfolgsbericht",
    response_model=BulkResultOut,
)
async def bulk_contracts(
    body: ContractBulkIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> BulkResultOut:
    """Each contract on its own (savepoint). A dunning block only stops proposals of the
    dunning run; nothing is posted or sent."""
    reason = (body.reason or "").strip() or None
    if body.value and reason is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Mahnsperre braucht eine Begründung",
            errors=[
                FieldError(
                    location=["body", "reason"],
                    field="reason",
                    code="required",
                    message="Mahnsperre braucht eine Begründung",
                )
            ],
        )
    async with tenant_tx(request, principal) as session:

        async def act(contract_id: uuid.UUID) -> None:
            contract = await _get(session, Contract, contract_id)
            before = {
                "dunning_block": contract.dunning_block,
                "dunning_block_reason": contract.dunning_block_reason,
            }
            after = {
                "dunning_block": body.value,
                "dunning_block_reason": reason if body.value else None,
            }
            if before == after:
                return
            contract.dunning_block = body.value
            contract.dunning_block_reason = after["dunning_block_reason"]
            contract.updated_by = principal.user_id
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="contract.updated",
                entity_type="contract",
                entity_id=contract.id,
                actor_user_id=principal.user_id,
                payload={"bulk": body.action},
                changes=diff(before, after),
            )

        return await run_bulk(body.ids, act, savepoint=session.begin_nested)


@router.post("/contracts", status_code=201, summary="Vertrag anlegen")
async def create_contract(
    body: s.ContractIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _create(session, principal, body)
        await _event(session, principal, "contract.created", contract.id, kind=body.kind.value)
        return await _out(session, contract)


# Approval of imported contracts (Betreiberauftrag 26.09.2026, migration 0133) --------------


async def _pending_out(session: Any, rows: Sequence[Contract]) -> list[s.PendingContractOut]:
    if not rows:
        return []
    props = {
        p.id: p
        for p in (
            await session.scalars(
                select(Property).where(Property.id.in_({c.property_id for c in rows}))
            )
        ).all()
    }
    units = {
        u.id: u
        for u in (
            await session.scalars(select(Unit).where(Unit.id.in_({c.unit_id for c in rows})))
        ).all()
    }
    parties = {
        p.id: p
        for p in (
            await session.scalars(select(Party).where(Party.id.in_({c.party_id for c in rows})))
        ).all()
    }
    amounts: dict[uuid.UUID, Decimal] = {}
    starts = {c.id: c.start_date for c in rows}
    for p in (
        await session.scalars(
            select(ContractPayment).where(ContractPayment.contract_id.in_(list(starts)))
        )
    ).all():
        start = starts[p.contract_id]
        if p.valid_from <= start and (p.valid_to is None or p.valid_to >= start):
            amounts[p.contract_id] = amounts.get(p.contract_id, Decimal("0.00")) + p.gross
    return [
        s.PendingContractOut(
            id=c.id,
            number=c.number,
            kind=c.kind,
            property_id=c.property_id,
            property_number=props[c.property_id].number,
            property_name=props[c.property_id].name,
            unit_id=c.unit_id,
            unit_number=units[c.unit_id].number,
            party_id=c.party_id,
            party_name=parties[c.party_id].name,
            start_date=c.start_date,
            monthly_amount=amounts.get(c.id, Decimal("0.00")),
            source=c.source,
            notes=c.notes,
        )
        for c in rows
    ]


@router.get(
    "/contracts/pending-approval",
    summary="Importverträge mit ausstehender Freigabe",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def pending_approval(
    request: Request,
    response: Response,
    source: str | None = None,
    property_id: uuid.UUID | None = None,
    kind: ContractKind | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=5000),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.PendingContractOut]:
    """Verträge mit ``approval_status = pending``. Ihre Zahlungspläne erzeugen im
    Sollstellungslauf keine Forderungen, bis die Geschäftsführung sie freigibt."""
    async with tenant_tx(request, principal) as session:
        query = select(Contract).where(Contract.approval_status == "pending")
        for column, value in (
            (Contract.source, source),
            (Contract.property_id, property_id),
            (Contract.kind, kind),
        ):
            if value is not None:
                query = query.where(column == value)
        rows = await paginate(
            session,
            query.order_by(Contract.number, Contract.version),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        return await _pending_out(session, rows)


@router.post("/contracts/approve", summary="Importverträge freigeben")
async def approve_contracts(
    body: s.ApproveIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> s.ApproveOut:
    """Gibt ausstehende Verträge frei (``ids`` oder ``all`` mit optionaler ``source``). Jeder
    Vertrag erhält ``approved_by``/``approved_at`` und ein Ereignis ``contract.approved``.
    Bereits entschiedene Verträge werden übergangen (wiederholter Klick ohne Wirkung)."""
    async with tenant_tx(request, principal) as session:
        query = select(Contract).where(Contract.approval_status == "pending")
        if body.all:
            if body.source is not None:
                query = query.where(Contract.source == body.source)
        else:
            query = query.where(Contract.id.in_(body.ids))
        rows = (await session.scalars(query.order_by(Contract.number).with_for_update())).all()
        now = datetime.now(UTC)
        for contract in rows:
            contract.approval_status = "approved"
            contract.approved_by = principal.user_id
            contract.approved_at = now
            contract.updated_by = principal.user_id
            await _event(
                session,
                principal,
                "contract.approved",
                contract.id,
                source=contract.source,
                approved_by=principal.user_id,
                approved_at=now.isoformat(),
            )
        await session.flush()
        return s.ApproveOut(approved=len(rows), ids=[c.id for c in rows])


@router.post("/contracts/{contract_id}/reject-import", summary="Importvertrag ablehnen")
async def reject_import(
    contract_id: uuid.UUID,
    body: s.RejectImportIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> s.RejectImportOut:
    """Fehlzuordnung: beendet den ausstehenden Vertrag zum Beginn (``end_date = start_date``,
    Zahlungen und Zahlungspläne ebenso) und markiert ihn ``rejected``. Er erzeugt keine
    Sollstellung; die Einheit ist ab dem Folgetag für die richtige Zuordnung frei."""
    async with tenant_tx(request, principal) as session:
        contract = await session.get(Contract, contract_id, with_for_update=True)
        if contract is None:
            raise _nf()
        if contract.approval_status != "pending":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Vertrag wartet nicht auf Freigabe.")
        await svc.end_contract(session, contract, contract.start_date)
        now = datetime.now(UTC)
        contract.approval_status = "rejected"
        contract.approved_by = principal.user_id
        contract.approved_at = now
        contract.termination_reason = body.reason or "Fehlzuordnung aus dem Import abgelehnt"
        contract.updated_by = principal.user_id
        await session.flush()
        await recompute_for_party(session, contract.party_id)
        await _event(
            session,
            principal,
            "contract.import_rejected",
            contract.id,
            source=contract.source,
            end_date=contract.end_date,
            reason=body.reason,
        )
        return s.RejectImportOut(
            id=contract.id, approval_status="rejected", end_date=contract.start_date
        )


@router.get("/contracts/{contract_id}", summary="Vertrag lesen")
async def get_contract(
    contract_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        # S12-04: lock token from updated_at (version is the business version, ADR 0012).
        response.headers["ETag"] = etag_of(contract.updated_at)
        return await _out(session, contract)


_NOTES_FIELDS = ("notes", "dunning_block", "dunning_block_reason")


@router.patch("/contracts/{contract_id}/notes", summary="Bemerkungen und Mahnsperre ändern")
async def patch_contract_notes(
    contract_id: uuid.UUID,
    body: s.ContractNotesPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    """In place update without a new contract version (AP8): remarks, dunning block and its
    reason only. Payments, terms and parties keep the version path (``POST .../versions``)."""
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id, lock=True)
        check_if_match(if_match, contract.updated_at)
        before = {k: getattr(contract, k) for k in _NOTES_FIELDS}
        after = before | body.model_dump(exclude_unset=True)
        if after["dunning_block"] and not (after["dunning_block_reason"] or "").strip():
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Mahnsperre braucht eine Begründung",
                errors=[
                    FieldError(
                        location=["body", "dunning_block_reason"],
                        field="dunning_block_reason",
                        code="required",
                        message="Mahnsperre braucht eine Begründung",
                    )
                ],
            )
        for key, value in after.items():
            setattr(contract, key, value)
        contract.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contract.updated",
            entity_type="contract",
            entity_id=contract.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(body.model_dump(exclude_unset=True))},
            changes=diff(before, after),
        )
        await session.refresh(contract, ["updated_at"])
        response.headers["ETag"] = etag_of(contract.updated_at)
        return await _out(session, contract)


@router.get(
    "/contracts/{contract_id}/versions",
    summary="Vertragsversionen",
    dependencies=[Depends(strict_query)],
)
async def contract_versions(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ContractOut]:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(Contract)
                .where(Contract.number == contract.number)
                .order_by(Contract.version)
            )
        ).all()
        return await _outs(session, rows)


@router.post("/contracts/{contract_id}/versions", status_code=201, summary="Neue Vertragsversion")
async def new_version(
    contract_id: uuid.UUID,
    body: s.ContractVersionIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        old = await _get(session, Contract, contract_id)
        latest = await session.scalar(
            select(Contract.id).where(Contract.number == old.number, Contract.version > old.version)
        )
        if latest is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Es gibt bereits eine neuere Version.")
        if body.effective_date <= old.start_date or (
            old.end_date is not None and body.effective_date > old.end_date
        ):
            raise svc.invalid("Die neue Version muss innerhalb der Laufzeit nach Beginn starten.")
        changes = body.model_dump(exclude={"effective_date"}, exclude_unset=True)
        data = {
            c.key: getattr(old, c.key)
            for c in Contract.__table__.columns
            if c.key not in ("id", "created_at", "updated_at", "created_by", "updated_by")
        }
        data.update(changes)
        if data.get("dunning_block") and not data.get("dunning_block_reason"):
            raise svc.invalid("Mahnsperre braucht eine Begründung")
        await svc.check_mandate(
            session,
            data["sepa_mandate_id"],
            data["direct_debit"],
            old.party_id,
            old.legal_entity_id,
        )
        old_end = old.end_date
        old.end_date = body.effective_date - timedelta(days=1)
        await session.flush()
        data.update(
            start_date=body.effective_date,
            end_date=old_end,
            version=old.version + 1,
            supersedes_contract_id=old.id,
        )
        new = Contract(created_by=principal.user_id, **data)
        session.add(new)
        await _flush(session, "Die Version überschneidet sich mit einem anderen Vertrag.")
        await svc.move_open_rows(session, old, new, body.effective_date)
        await recompute_for_party(session, new.party_id)
        await _event(
            session,
            principal,
            "contract.versioned",
            new.id,
            changes=diff(
                _plain({k: getattr(old, k) for k in changes}),
                _plain({k: getattr(new, k) for k in changes}),
            ),
            previous=old.id,
            effective_date=body.effective_date,
        )
        return await _out(session, new)


@router.post("/contracts/{contract_id}/termination", summary="Vertrag beenden")
async def terminate(
    contract_id: uuid.UUID,
    body: s.TerminationIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        if contract.kind is ContractKind.OWNERSHIP:
            raise svc.invalid("Eigentum endet nur durch Eigentümerwechsel.")
        await svc.end_contract(session, contract, body.end_date)
        contract.termination_date = body.termination_date
        contract.termination_reason = body.termination_reason
        if body.move_out_on is not None:
            contract.move_out_on = body.move_out_on
        contract.updated_by = principal.user_id
        readings = await svc.record_termination_readings(
            session,
            contract,
            [(r.meter_id, r.value, r.read_at) for r in body.meter_readings],
            principal.user_id,
        )
        await _event(
            session,
            principal,
            "contract.terminated",
            contract.id,
            end_date=body.end_date,
            move_out_on=body.move_out_on,
            meter_readings=len(readings),
        )
        return await _out(session, contract)


@router.get(
    "/contracts/{contract_id}/termination-readings",
    summary="Zählerstände zur Vertragsbeendigung",
    dependencies=[Depends(strict_query)],
)
async def termination_readings(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.TerminationReadingOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(ContractTerminationReading)
                .where(ContractTerminationReading.contract_id == contract_id)
                .order_by(ContractTerminationReading.read_at, ContractTerminationReading.id)
            )
        ).all()
        return [s.TerminationReadingOut.model_validate(r) for r in rows]


# Contract related allocation values (4.5 Eigenschaften) --------------------------------


async def _allocation_values_out(
    session: Any, rows: Sequence[ContractAllocationValue]
) -> list[s.ContractAllocationValueOut]:
    if not rows:
        return []
    keys = {
        k.id: k
        for k in (
            await session.scalars(
                select(AllocationKey).where(
                    AllocationKey.id.in_({r.allocation_key_id for r in rows})
                )
            )
        ).all()
    }
    out = []
    for r in rows:
        item = s.ContractAllocationValueOut.model_validate(r)
        key = keys.get(r.allocation_key_id)
        if key is not None:
            item.allocation_key_code = key.code
            item.allocation_key_name = key.name
            item.unit_of_measure = key.unit_of_measure
        out.append(item)
    return out


@router.get(
    "/contracts/{contract_id}/allocation-values",
    summary="Umlagewerte des Vertrags",
    dependencies=[Depends(strict_query)],
)
async def list_allocation_values(
    contract_id: uuid.UUID,
    request: Request,
    as_of: date | None = Query(default=None, description="Stichtag: nur am Tag gültige Zeilen"),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.ContractAllocationValueOut]:
    """Vertragsbezogene Umlagewerte mit Zeitraum (z. B. Personen), alle Versionen der
    Vertragsnummer."""
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        ids = (
            await session.scalars(select(Contract.id).where(Contract.number == contract.number))
        ).all()
        rows = (
            await session.scalars(
                valid_on(
                    select(ContractAllocationValue).where(
                        ContractAllocationValue.contract_id.in_(ids)
                    ),
                    as_of,
                    ContractAllocationValue.valid_from,
                    ContractAllocationValue.valid_to,
                ).order_by(
                    ContractAllocationValue.allocation_key_id, ContractAllocationValue.valid_from
                )
            )
        ).all()
        return await _allocation_values_out(session, rows)


@router.post(
    "/contracts/{contract_id}/allocation-values",
    status_code=201,
    summary="Umlagewert am Vertrag erfassen",
)
async def add_allocation_value(
    contract_id: uuid.UUID,
    body: s.ContractAllocationValueIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractAllocationValueOut:
    """Schließt einen offenen Vorwert desselben Schlüssels am Vortag; Zeiträume je Schlüssel
    überschneiden sich nie. Keine Buchung, keine Abrechnungswirkung außerhalb der Module."""
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        open_row = await session.scalar(
            select(ContractAllocationValue).where(
                ContractAllocationValue.contract_id == contract.id,
                ContractAllocationValue.allocation_key_id == body.allocation_key_id,
                ContractAllocationValue.valid_to.is_(None),
                ContractAllocationValue.valid_from < body.valid_from,
            )
        )
        if open_row is not None:
            open_row.valid_to = body.valid_from - timedelta(days=1)
            open_row.updated_by = principal.user_id
            await session.flush()
        row = await svc.add_allocation_value(
            session, contract, body.allocation_key_id, body.value, body.valid_from, body.valid_to
        )
        row.created_by = principal.user_id
        await _flush(session, "Der Umlagewert überschneidet sich mit einem bestehenden Wert.")
        await _event(
            session,
            principal,
            "contract.allocation_value_added",
            contract.id,
            allocation_key_id=body.allocation_key_id,
            value=body.value,
            valid_from=body.valid_from,
        )
        return (await _allocation_values_out(session, [row]))[0]


def _transfer_invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.CONTRACT_OWNERSHIP_TRANSFER_INVALID, detail=detail)


def _check_transferable(old: Contract, title_transfer_date: date) -> None:
    if old.kind is not ContractKind.OWNERSHIP:
        raise _transfer_invalid("Nur Eigentumsverhältnisse können übertragen werden.")
    if old.end_date is not None:
        raise _transfer_invalid("Das Eigentumsverhältnis ist bereits beendet.")
    if title_transfer_date <= old.start_date:
        raise _transfer_invalid("Der Eigentumsübergang muss nach dem Beginn des Eigentums liegen.")


@router.get(
    "/contracts/{contract_id}/ownership-transfer/preview",
    summary="Eigentümerwechsel: Vorschau",
)
async def ownership_transfer_preview(
    contract_id: uuid.UUID,
    title_transfer_date: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> s.OwnershipTransferPreviewOut:
    """Shows what the transfer on the date would do: the current ownership ends the day before,
    the new one starts on the date, and the listed standing amounts (payments, payment schedule,
    allocation values valid on the date) are carried over from the date on. Read only. The
    annual statement is not split between seller and acquirer (rule W07, release point P01)."""
    async with tenant_tx(request, principal) as session:
        old = await _get(session, Contract, contract_id)
        _check_transferable(old, title_transfer_date)
        # Same refusal as the transfer itself: rows starting on or after the date block it.
        await svc.check_no_later_rows(session, old, title_transfer_date - timedelta(days=1))
        amounts = await svc.standing_amounts(session, old, title_transfer_date)
        party = await session.get(Party, old.party_id)
        return s.OwnershipTransferPreviewOut(
            contract_id=old.id,
            party_id=old.party_id,
            party_name=party.name if party else None,
            title_transfer_date=title_transfer_date,
            old_end_date=title_transfer_date - timedelta(days=1),
            new_start_date=title_transfer_date,
            payments=[s.PaymentOut.model_validate(p) for p in amounts.payments],
            schedules=[s.ScheduleOut.model_validate(x) for x in amounts.schedules],
            allocation_values=await _allocation_values_out(session, amounts.allocation_values),
        )


@router.post(
    "/contracts/{contract_id}/ownership-transfer", status_code=201, summary="Eigentümerwechsel"
)
async def ownership_transfer(
    contract_id: uuid.UUID,
    body: s.OwnershipTransferIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    """Ends the current ownership the day before the title transfer (D16, D17), creates the
    new ownership and, with ``carry_over_amounts``, copies the standing amounts valid on the
    title transfer date to the new contract from that date on (factual carry over, no split of
    the annual statement: rule W07 and release point P01 stay open). Open receivables stay with
    the seller (6.9.2, D15)."""
    async with tenant_tx(request, principal) as session:
        old = await _get(session, Contract, contract_id)
        _check_transferable(old, body.title_transfer_date)
        new_party_id = body.new_party_id
        if body.new_contact_id is not None:
            new_party_id = (
                await party_for_contact(
                    session, principal.tenant_id, principal.user_id, body.new_contact_id
                )
            ).id
        if new_party_id is None:  # pragma: no cover - the schema requires one of the two
            raise _transfer_invalid("Erwerber fehlt.")
        if new_party_id == old.party_id:
            raise _transfer_invalid("Der neue Eigentümer ist identisch mit dem bisherigen.")
        document = None
        if body.document_id is not None:
            document = await session.get(Document, body.document_id)
            if document is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
        end = body.title_transfer_date - timedelta(days=1)
        amounts = await svc.standing_amounts(session, old, body.title_transfer_date)
        await svc.end_contract(session, old, end)
        await svc.close_allocation_values(session, old, end, principal.user_id)
        old.updated_by = principal.user_id
        new = await _create(
            session,
            principal,
            s.ContractIn(
                kind=ContractKind.OWNERSHIP,
                unit_id=old.unit_id,
                party_id=new_party_id,
                start_date=body.title_transfer_date,
                title_transfer_date=body.title_transfer_date,
                benefit_burden_date=body.benefit_burden_date,
                acquisition_kind=body.acquisition_kind,
                special_succession_liability=body.special_succession_liability,
                sev_enabled=body.sev_enabled,
                notes=body.notes,
            ),
        )
        carried = {"payments": 0, "schedules": 0, "allocation_values": 0}
        if body.carry_over_amounts:
            carried = await svc.carry_over_standing_amounts(
                session, amounts, new, body.title_transfer_date, principal.user_id
            )
            await _flush(session, "Die übernommenen Sollbeträge überschneiden sich.")
        if document is not None:
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    document_id=document.id,
                    entity_type="contract",
                    entity_id=new.id,
                    role=LinkRole.EVIDENCE,
                )
            )
            await _flush(session, "Die Verknüpfung des Dokuments besteht bereits.")
        await _event(
            session,
            principal,
            "contract.ownership_transferred",
            new.id,
            previous=old.id,
            title_transfer_date=body.title_transfer_date,
            carried_payments=carried["payments"],
            carried_schedules=carried["schedules"],
            carried_allocation_values=carried["allocation_values"],
            document_id=body.document_id,
        )
        return await _out(session, new)


# Payments and schedules ----------------------------------------------------------------


@router.post("/contracts/{contract_id}/payments", status_code=201, summary="Sollstellung erfassen")
async def add_payment(
    contract_id: uuid.UUID,
    body: s.PaymentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PaymentOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        await check_catalog(session, "payment_type", body.payment_type_code)
        svc.check_amounts(body.payment_type_code, body.net, body.vat_percent, body.gross)
        await check_ledger_account(
            session, body.revenue_account_id, contract.property_id, "Das Ertragskonto"
        )
        await svc.check_payment_reserve(session, contract, body.reserve_id)
        row = ContractPayment(
            tenant_id=principal.tenant_id, contract_id=contract.id, **body.model_dump()
        )
        await svc.add_payment(session, contract, row)
        await _flush(session, "Die Zahlung überschneidet sich mit einer bestehenden Zahlung.")
        await _event(
            session,
            principal,
            "contract.payment_added",
            contract.id,
            payment_type=body.payment_type_code,
            gross=body.gross,
            valid_from=body.valid_from,
        )
        return s.PaymentOut.model_validate(row)


@router.get(
    "/contracts/{contract_id}/payments",
    summary="Zahlungshistorie",
    dependencies=[Depends(strict_query)],
)
async def payment_history(
    contract_id: uuid.UUID,
    request: Request,
    as_of: date | None = Query(default=None, description="Stichtag: nur am Tag gültige Zeilen"),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.PaymentOut]:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        ids = (
            await session.scalars(select(Contract.id).where(Contract.number == contract.number))
        ).all()
        query = valid_on(
            select(ContractPayment).where(ContractPayment.contract_id.in_(ids)),
            as_of,
            ContractPayment.valid_from,
            ContractPayment.valid_to,
        )
        rows = (
            await session.scalars(
                query.order_by(ContractPayment.valid_from, ContractPayment.payment_type_code)
            )
        ).all()
        return [s.PaymentOut.model_validate(r) for r in rows]


@router.post("/contracts/{contract_id}/schedules", status_code=201, summary="Zahlungsplan")
async def add_schedule(
    contract_id: uuid.UUID,
    body: s.ScheduleIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ScheduleOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        data = body.model_dump()
        if data["interval"] is None:
            data["interval"] = await svc.default_payment_interval(session, principal.tenant_id)
        row = PaymentSchedule(tenant_id=principal.tenant_id, contract_id=contract.id, **data)
        await svc.add_schedule(session, contract, row)
        await _flush(session, "Der Zahlungsplan überschneidet sich mit einem bestehenden.")
        return s.ScheduleOut.model_validate(row)


# SEPA mandates (recording only; collection stays locked until G2) ----------------------


async def _mandate_out(session: Any, mandate: SepaMandate) -> s.MandateOut:
    return (await _mandates_out(session, [mandate]))[0]


async def _mandates_out(session: Any, mandates: Sequence[SepaMandate]) -> list[s.MandateOut]:
    """One query for the bank accounts of all mandates (masked IBAN)."""
    if not mandates:
        return []
    accounts = {
        a.id: a
        for a in (
            await session.scalars(
                select(ContactBankAccount).where(
                    ContactBankAccount.id.in_({m.contact_bank_account_id for m in mandates})
                )
            )
        ).all()
    }
    out = []
    for mandate in mandates:
        row = s.MandateOut.model_validate(mandate)
        account = accounts.get(mandate.contact_bank_account_id)
        row.iban_masked = mask_iban(account.iban) if account is not None else None
        out.append(row)
    return out


@router.get(
    "/sepa-mandates",
    summary="SEPA-Mandate",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_mandates(
    request: Request,
    response: Response,
    party_id: uuid.UUID | None = None,
    status: MandateStatus | None = None,
    expiring_until: date | None = Query(
        default=None, description="Aktive Mandate mit valid_until bis zu diesem Datum (M5-05)"
    ),
    unused: bool | None = Query(default=None, description="true: noch nie verwendet"),
    as_of: date | None = Query(
        default=None,
        description="Stichtag: unterschrieben bis zum Tag und nicht vor dem Tag abgelaufen",
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=1000,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.MandateOut]:
    """Paginierung wie ``GET /tickets`` (Kopfzeilen ``X-Total-Count``, ``X-Page``,
    ``X-Page-Size``), Antwort bleibt eine Liste."""
    async with tenant_tx(request, principal) as session:
        query = select(SepaMandate)
        if party_id is not None:
            query = query.where(SepaMandate.party_id == party_id)
        if status is not None:
            query = query.where(SepaMandate.status == status)
        if expiring_until is not None:
            query = query.where(
                SepaMandate.status == MandateStatus.ACTIVE,
                SepaMandate.valid_until.is_not(None),
                SepaMandate.valid_until <= expiring_until,
            )
        if unused is not None:
            query = query.where(SepaMandate.last_used_at.is_(None) == unused)
        query = valid_on(query, as_of, SepaMandate.signed_at, SepaMandate.valid_until)
        rows = await paginate(
            session,
            query.order_by(SepaMandate.signed_at, SepaMandate.id),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        return await _mandates_out(session, rows)


@router.post("/sepa-mandates", status_code=201, summary="SEPA-Mandat erfassen")
async def create_mandate(
    body: s.MandateIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.MandateOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Party, body.party_id)
        account = await _get(session, ContactBankAccount, body.contact_bank_account_id)
        member = await session.scalar(
            select(PartyMember.id).where(
                PartyMember.party_id == body.party_id, PartyMember.contact_id == account.contact_id
            )
        )
        if member is None:
            raise svc.invalid("Das Konto gehört keinem Beteiligten der Vertragspartei.")
        if (unreleased := approval_block_reason(account)) is not None:
            raise svc.invalid(f"{unreleased}: kein Mandat auf nicht freigegebener IBAN (M5-01).")
        await svc.check_b2b(session, body.party_id, body.type)
        if body.valid_until is not None and body.valid_until < body.signed_at:
            raise svc.invalid("Das Mandat endet vor der Unterschrift.")
        for code in body.payment_type_codes:
            await check_catalog(session, "payment_type", code)
        mandate = SepaMandate(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(mandate)
        await _flush(session, "Die Mandatsreferenz ist für diese Gläubiger-ID bereits vergeben.")
        await _event(
            session, principal, "sepa_mandate.created", mandate.id, reference=body.reference
        )
        return await _mandate_out(session, mandate)


@router.post("/sepa-mandates/{mandate_id}/revoke", summary="SEPA-Mandat widerrufen")
async def revoke_mandate(
    mandate_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> s.MandateOut:
    async with tenant_tx(request, principal) as session:
        mandate = await _get(session, SepaMandate, mandate_id)
        mandate.status = MandateStatus.REVOKED
        mandate.revoked_at = datetime.now(UTC)
        users = (
            await session.scalars(
                select(Contract).where(
                    Contract.sepa_mandate_id == mandate.id, Contract.direct_debit.is_(True)
                )
            )
        ).all()
        for c in users:  # direct debit stops; the contract is flagged, not rewritten
            c.direct_debit = False
        await _event(session, principal, "sepa_mandate.revoked", mandate.id, contracts=len(users))
        return await _mandate_out(session, mandate)


# Deposits ------------------------------------------------------------------------------


async def _deposit_out(session: Any, deposit: Deposit) -> s.DepositOut:
    await session.flush()
    await session.refresh(deposit)
    return (await _deposits_out(session, [deposit]))[0]


async def _deposits_out(session: Any, deposits: Sequence[Deposit]) -> list[s.DepositOut]:
    """Movements of all deposits in one query."""
    if not deposits:
        return []
    movements: dict[uuid.UUID, list[DepositMovement]] = {}
    for m in (
        await session.scalars(
            select(DepositMovement)
            .where(DepositMovement.deposit_id.in_([d.id for d in deposits]))
            .order_by(DepositMovement.date)
        )
    ).all():
        movements.setdefault(m.deposit_id, []).append(m)
    hints = await svc.deposit_limit_hints(session, list(deposits))
    out = []
    for deposit in deposits:
        rows = movements.get(deposit.id, [])
        received, balance = svc.deposit_totals(deposit, rows)
        item = s.DepositOut.model_validate(deposit)
        item.received = received
        item.balance = balance
        item.outstanding = max(deposit.amount_due - received, Decimal("0.00"))
        item.limit_hints = hints.get(deposit.id, [])
        item.movements = []
        for m in rows:
            row = s.DepositMovementOut.model_validate(m)
            row.review_required = m.posting_id is None  # not yet a ledger posting (M10, G1)
            item.movements.append(row)
        out.append(item)
    return out


def _hint_setting_out(row: Any) -> s.DepositHintSettingOut:
    if row is None:
        return s.DepositHintSettingOut()
    return s.DepositHintSettingOut(
        deposit_limit_hint_enabled=row.enabled,
        factor_months=row.factor_months,
        max_installments=row.max_installments,
        rent_payment_codes=list(row.rent_payment_codes),
    )


@router.get(
    "/deposit-hint-settings",
    summary="Prüfhinweis Kaution: Mandantenschalter (Standard aus)",
    dependencies=[Depends(strict_query)],
)
async def get_deposit_hint_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ_DEPOSIT)
) -> s.DepositHintSettingOut:
    async with tenant_tx(request, principal) as session:
        return _hint_setting_out(await svc.deposit_hint_setting(session))


@router.put(
    "/deposit-hint-settings",
    summary="Prüfhinweis Kaution setzen (nicht sperrend, keine Rechtsentscheidung)",
)
async def put_deposit_hint_settings(
    body: s.DepositHintSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE_DEPOSIT),
) -> s.DepositHintSettingOut:
    async with tenant_tx(request, principal) as session:
        row = await svc.deposit_hint_setting(session)
        if row is None:
            row = DepositHintSetting(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        row.enabled = body.deposit_limit_hint_enabled
        row.factor_months = body.factor_months
        row.max_installments = body.max_installments
        row.rent_payment_codes = list(dict.fromkeys(body.rent_payment_codes))
        row.updated_by = principal.user_id
        await session.flush()
        out = _hint_setting_out(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="deposit_hint_setting.updated",
            entity_type="deposit_hint_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload=out.model_dump(mode="json"),
        )
        return out


@router.post("/contracts/{contract_id}/deposits", status_code=201, summary="Kaution erfassen")
async def create_deposit(
    contract_id: uuid.UUID,
    body: s.DepositIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.DepositOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        await svc.check_deposit_account(session, contract, body.property_bank_account_id)
        deposit = Deposit(
            tenant_id=principal.tenant_id, contract_id=contract.id, **body.model_dump()
        )
        session.add(deposit)
        await _event(session, principal, "deposit.created", contract.id, amount=body.amount_due)
        return await _deposit_out(session, deposit)


@router.get(
    "/contracts/{contract_id}/deposits", summary="Kautionen", dependencies=[Depends(strict_query)]
)
async def list_deposits(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.DepositOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(Deposit).where(Deposit.contract_id == contract_id).order_by(Deposit.id)
            )
        ).all()
        return await _deposits_out(session, rows)


@router.get(
    "/deposits",
    summary="Kautionsliste",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_all_deposits(
    request: Request,
    response: Response,
    property_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, description="Kautionsstatus, z. B. open"),
    outstanding_only: bool = Query(default=False, description="Nur mit offenem Sollbetrag"),
    limit: int = Query(default=200, ge=1, le=1000),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.DepositListRow]:
    """Kautionen über alle Verträge mit Objekt, Einheit, Partei, Sollbetrag, erhaltenem
    Betrag, Guthaben und offenem Betrag (Datensätze, keine Buchungen; M10, G1)."""
    async with tenant_tx(request, principal) as session:
        query = select(Deposit).join(Contract, Contract.id == Deposit.contract_id)
        if property_id is not None:
            query = query.where(Contract.property_id == property_id)
        if status is not None:
            query = query.where(Deposit.status == status)
        rows = await paginate(
            session,
            query.order_by(Contract.number, Deposit.valid_from, Deposit.id),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        totals = {d.id: d for d in await _deposits_out(session, rows)}
        contracts = {
            c.id: c
            for c in (
                await session.scalars(
                    select(Contract).where(Contract.id.in_({d.contract_id for d in rows}))
                )
            ).all()
        }
        props = {
            p.id: p
            for p in (
                await session.scalars(
                    select(Property).where(
                        Property.id.in_({c.property_id for c in contracts.values()})
                    )
                )
            ).all()
        }
        units = {
            u.id: u
            for u in (
                await session.scalars(
                    select(Unit).where(Unit.id.in_({c.unit_id for c in contracts.values()}))
                )
            ).all()
        }
        parties = {
            p.id: p
            for p in (
                await session.scalars(
                    select(Party).where(Party.id.in_({c.party_id for c in contracts.values()}))
                )
            ).all()
        }
        out = []
        for d in rows:
            c = contracts[d.contract_id]
            t = totals[d.id]
            if outstanding_only and t.outstanding <= 0:
                continue
            out.append(
                s.DepositListRow(
                    id=d.id,
                    contract_id=c.id,
                    contract_number=c.number,
                    property_id=c.property_id,
                    property_number=props[c.property_id].number,
                    unit_id=c.unit_id,
                    unit_number=units[c.unit_id].number,
                    party_id=c.party_id,
                    party_name=parties[c.party_id].name,
                    kind=d.kind,
                    status=d.status,
                    amount_due=d.amount_due,
                    received=t.received,
                    balance=t.balance,
                    outstanding=t.outstanding,
                    valid_from=d.valid_from,
                    valid_to=d.valid_to,
                    contract_end_date=c.end_date,
                )
            )
        return out


@router.post("/deposits/{deposit_id}/movements", status_code=201, summary="Kautionsbewegung")
async def add_deposit_movement(
    deposit_id: uuid.UUID,
    body: s.DepositMovementIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DepositOut:
    """Records a movement; it becomes a posting only with the ledger (M10) behind G1."""
    async with tenant_tx(request, principal) as session:
        deposit = await _get(session, Deposit, deposit_id)
        existing = list(
            (
                await session.scalars(
                    select(DepositMovement).where(DepositMovement.deposit_id == deposit.id)
                )
            ).all()
        )
        _, balance = svc.deposit_totals(deposit, existing)
        if body.kind.value in ("payout", "offset") and body.amount > balance:
            raise svc.invalid("Auszahlung oder Verrechnung übersteigt das Kautionsguthaben.")
        session.add(
            DepositMovement(
                tenant_id=principal.tenant_id, deposit_id=deposit.id, **body.model_dump()
            )
        )
        await _event(
            session,
            principal,
            "deposit.movement_recorded",
            deposit.id,
            kind=body.kind.value,
            amount=body.amount,
        )
        return await _deposit_out(session, deposit)


# Overviews -----------------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/occupancy",
    summary="Belegungsliste",
    dependencies=[Depends(strict_query)],
)
async def occupancy(
    property_id: uuid.UUID,
    request: Request,
    as_of: date = Query(default_factory=date.today),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.OccupancyRow]:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        units = (
            await session.scalars(
                select(Unit).where(Unit.property_id == property_id).order_by(Unit.number)
            )
        ).all()
        active = (
            await session.scalars(
                select(Contract).where(
                    Contract.property_id == property_id,
                    Contract.start_date <= as_of,
                    or_(Contract.end_date.is_(None), Contract.end_date >= as_of),
                )
            )
        ).all()
        names = {
            p.id: p.name
            for p in (
                await session.scalars(
                    select(Party).where(Party.id.in_({c.party_id for c in active}))
                )
            ).all()
        }
        by_unit: dict[tuple[uuid.UUID, ContractKind], Contract] = {
            (c.unit_id, c.kind): c for c in active
        }
        rows = []
        for u in units:
            tenancy = by_unit.get((u.id, ContractKind.TENANCY))
            owner = by_unit.get((u.id, ContractKind.OWNERSHIP))
            rows.append(
                s.OccupancyRow(
                    unit_id=u.id,
                    unit_number=u.number,
                    unit_label=u.label,
                    unit_type=u.unit_type.value,
                    tenancy_contract_id=tenancy.id if tenancy else None,
                    tenant_party=names.get(tenancy.party_id) if tenancy else None,
                    ownership_contract_id=owner.id if owner else None,
                    owner_party=names.get(owner.party_id) if owner else None,
                    # Vacancy applies to let units: rental properties or SEV ownership.
                    vacant=tenancy is None
                    and (
                        prop.management_type is ManagementType.RENTAL
                        or (owner is not None and owner.sev_enabled)
                    ),
                )
            )
        return rows


@router.get(
    "/properties/{property_id}/vacancies",
    summary="Leerstand zum Stichtag",
    dependencies=[Depends(strict_query)],
)
async def vacancies(
    property_id: uuid.UUID,
    request: Request,
    as_of: date = Query(default_factory=date.today),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.VacancyRow]:
    """Vermietbare Einheiten ohne Mietverhältnis zum Stichtag (Mietobjekte und SEV-Eigentum)
    mit Leerstandsbeginn (Tag nach dem letzten Mietende) und letztem Mietvertrag."""
    async with tenant_tx(request, principal) as session:
        occupancy_rows = await occupancy(property_id, request, as_of, principal)
        vacant = [r for r in occupancy_rows if r.vacant]
        if not vacant:
            return []
        unit_ids = [r.unit_id for r in vacant]
        previous: dict[uuid.UUID, Contract] = {}
        for c in (
            await session.scalars(
                select(Contract)
                .where(
                    Contract.unit_id.in_(unit_ids),
                    Contract.kind == ContractKind.TENANCY,
                    Contract.end_date.is_not(None),
                    Contract.end_date < as_of,
                )
                .order_by(Contract.end_date.desc())
            )
        ).all():
            previous.setdefault(c.unit_id, c)
        return [
            s.VacancyRow(
                unit_id=r.unit_id,
                unit_number=r.unit_number,
                unit_label=r.unit_label,
                unit_type=r.unit_type,
                vacant_since=(
                    prev.end_date + timedelta(days=1)
                    if (prev := previous.get(r.unit_id)) is not None and prev.end_date
                    else None
                ),
                previous_contract_id=prev.id if prev is not None else None,
                ownership_contract_id=r.ownership_contract_id,
                owner_party=r.owner_party,
            )
            for r in vacant
        ]
