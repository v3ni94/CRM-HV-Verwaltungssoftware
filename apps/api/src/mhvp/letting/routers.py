"""Letting API (M26): rent increase process, vacancies, exposé draft, prospects.

The source register (annex C) holds no rent law norms. The rent increase check is arithmetic
on values entered with their source; it never states that an increase is lawful. Sending the
demand is a legally relevant statement and needs G3 plus a documented legal review (M26-01)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.letting.models import Listing, Prospect, RentIncreaseCase

router = APIRouter(prefix="/letting", tags=["letting"])
READ = require_permission("contracts:read")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")
APPROVE = require_permission("contracts:approve")
DELETE = require_permission("contracts:delete")
CENT = Decimal("0.01")
LEGAL_NOTE = (
    "Rechenprüfung auf Grundlage erfasster Werte. Keine Aussage zur Zulässigkeit; "
    "Rechtsgrundlagen sind nicht im Quellenregister hinterlegt (M26-01)."
)


class LettingBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComparisonFlatIn(LettingBaseIn):
    address: str = Field(min_length=3, max_length=300)
    living_area_sqm: Decimal | None = Field(default=None, gt=0)
    rent_per_sqm: Decimal = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class RentIncreaseIn(LettingBaseIn):
    contract_id: uuid.UUID
    basis: str = Field(pattern="^(mietspiegel|comparison|modernization|index|graduated)$")
    target_rent: Decimal = Field(gt=0, decimal_places=2)
    effective_date: date
    reference_rent: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    cap_limit_percent: Decimal | None = Field(default=None, ge=0, le=100)
    comparison_rent_per_sqm: Decimal | None = Field(default=None, gt=0)
    earliest_effective_date: date | None = None
    source_note: str | None = Field(default=None, max_length=4000)
    source_document_id: uuid.UUID | None = None
    justification: str | None = Field(
        default=None, pattern="^(mietspiegel|gutachten|vergleichswohnungen)$"
    )
    rent_index_name: str | None = Field(default=None, max_length=300)
    rent_index_date: date | None = None
    expert_document_id: uuid.UUID | None = None
    comparison_flats: list[ComparisonFlatIn] = Field(default_factory=list, max_length=20)


class RentIncreaseAction(LettingBaseIn):
    action: str = Field(pattern="^(approve|send|consent|reject|apply|cancel)$")
    document_id: uuid.UUID | None = None
    received_on: date | None = None


class ProspectIn(LettingBaseIn):
    unit_id: uuid.UUID
    contact_id: uuid.UUID
    viewing_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    delete_after: date


class ProspectPatch(LettingBaseIn):
    status: str | None = Field(
        default=None, pattern="^(new|viewing|applied|accepted|rejected|withdrawn)$"
    )
    viewing_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)


def _case_out(c: RentIncreaseCase) -> dict[str, Any]:
    return {
        "id": c.id,
        "contract_id": c.contract_id,
        "basis": c.basis,
        "current_rent": c.current_rent,
        "target_rent": c.target_rent,
        "effective_date": c.effective_date,
        "status": c.status,
        "check": c.check,
        "sent_at": c.sent_at,
        "received_on": c.received_on,
        "justification": c.justification,
        "rent_index_name": c.rent_index_name,
        "comparison_flats": c.comparison_flats,
        "new_payment_id": c.new_payment_id,
    }


async def _rent_payment(session: Any, contract_id: uuid.UUID, day: date) -> Any:
    from mhvp.contracts.models import ContractPayment

    return await session.scalar(
        select(ContractPayment).where(
            ContractPayment.contract_id == contract_id,
            ContractPayment.payment_type_code == "rent",
            ContractPayment.valid_from <= day,
            or_(ContractPayment.valid_to.is_(None), ContractPayment.valid_to >= day),
        )
    )


def _check(case: RentIncreaseCase, block_until: date | None) -> dict[str, Any]:
    increase = case.target_rent - case.current_rent
    percent = (increase / case.current_rent * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    flags: list[str] = []
    out: dict[str, Any] = {
        "increase": str(increase),
        "increase_percent": str(percent),
        "note": LEGAL_NOTE,
    }
    if increase <= 0:
        flags.append("Zielmiete liegt nicht über der aktuellen Miete.")
    if case.reference_rent is not None and case.cap_limit_percent is not None:
        cap = (case.reference_rent * (1 + case.cap_limit_percent / 100)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        out["cap_max_rent"] = str(cap)
        if case.target_rent > cap:
            flags.append(f"Zielmiete über erfasster Kappungsgrenze ({cap} EUR).")
    elif case.basis in ("mietspiegel", "comparison"):
        flags.append("Ausgangsmiete und Kappungsgrenze mit Quelle erfassen.")
    if case.basis in ("mietspiegel", "comparison"):
        if case.comparison_rent_per_sqm is None or case.living_area_sqm is None:
            flags.append("Vergleichsmiete je m² und Wohnfläche fehlen.")
        else:
            comparison = (case.comparison_rent_per_sqm * case.living_area_sqm).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            out["comparison_rent"] = str(comparison)
            if case.target_rent > comparison:
                flags.append(f"Zielmiete über erfasster Vergleichsmiete ({comparison} EUR).")
    if not case.source_note and not case.source_document_id:
        flags.append("Quelle der erfassten Werte fehlt.")
    if block_until and case.effective_date <= block_until:
        flags.append(f"Mieterhöhungssperre bis {block_until:%d.%m.%Y}.")
    if case.earliest_effective_date and case.effective_date < case.earliest_effective_date:
        flags.append("Wirksamkeit vor dem erfassten frühesten Zeitpunkt.")
    out["flags"] = flags
    out["ok"] = not flags
    return out


@router.post("/rent-increases", status_code=201, summary="Mieterhöhung anlegen und prüfen")
async def create_rent_increase(
    body: RentIncreaseIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Unit

    async with tenant_tx(request, principal) as session:
        contract = await session.get(Contract, body.contract_id)
        if contract is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if contract.kind is not ContractKind.TENANCY:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nur für Mietverträge.")
        payment = await _rent_payment(session, contract.id, body.effective_date)
        if payment is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Miete zum Stichtag erfasst.")
        unit = await session.get(Unit, contract.unit_id)
        from mhvp.letting.rentlaw import statutory_check
        from mhvp.properties.models import Property

        case = RentIncreaseCase(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            current_rent=payment.net,
            living_area_sqm=unit.living_area_sqm if unit else None,
            **(
                body.model_dump(mode="json")
                | {
                    "target_rent": body.target_rent,
                    "reference_rent": body.reference_rent,
                    "cap_limit_percent": body.cap_limit_percent,
                    "comparison_rent_per_sqm": body.comparison_rent_per_sqm,
                    "effective_date": body.effective_date,
                    "earliest_effective_date": body.earliest_effective_date,
                    "rent_index_date": body.rent_index_date,
                    "contract_id": body.contract_id,
                    "source_document_id": body.source_document_id,
                    "expert_document_id": body.expert_document_id,
                }
            ),
        )
        check = _check(case, contract.rent_increase_block_until)
        prop = await session.get(Property, contract.property_id)
        statutory = await statutory_check(session, case, contract, prop)
        check["statutory"] = statutory
        check["ok"] = check["ok"] and not statutory["flags"]
        case.check = check
        session.add(case)
        await session.flush()
        return _case_out(case)


@router.get("/rent-increases", summary="Mieterhöhungsfälle")
async def list_rent_increases(
    request: Request,
    contract_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(RentIncreaseCase).order_by(RentIncreaseCase.created_at.desc())
        if contract_id is not None:
            query = query.where(RentIncreaseCase.contract_id == contract_id)
        return [_case_out(c) for c in (await session.scalars(query.limit(200))).all()]


@router.get("/rent-increases/{case_id}", summary="Mieterhöhungsfall")
async def get_rent_increase(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _case_out(case)


@router.get("/rent-increases/{case_id}/letter", summary="Musterschreiben (Entwurf)")
async def rent_increase_letter(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.contracts.models import Contract
    from mhvp.letting.rentlaw import letter_text
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        contract = await session.get(Contract, case.contract_id)
        unit = await session.get(Unit, contract.unit_id) if contract else None
        prop = await session.get(Property, unit.property_id) if unit else None
        parts = [prop.street, prop.house_number] if prop else []
        street = " ".join(x for x in parts if x)
        places = [prop.postal_code, prop.city] if prop else []
        city = " ".join(x for x in places if x)
        address = ", ".join(x for x in [street, city] if x) or "[Anschrift]"
        label = (unit.label or unit.number) if unit else "[Einheit]"
        return letter_text(case, label, address)


NEXT = {
    "approve": ({"draft"}, "approved"),
    "send": ({"approved"}, "sent"),
    "consent": ({"sent"}, "consented"),
    "reject": ({"sent"}, "rejected"),
    "apply": ({"consented"}, "applied"),
    "cancel": ({"draft", "approved"}, "cancelled"),
}


@router.post("/rent-increases/{case_id}/actions", summary="Prozessschritt")
async def rent_increase_action(
    case_id: uuid.UUID,
    body: RentIncreaseAction,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    from mhvp.contracts import services as contract_services
    from mhvp.contracts.models import Contract, ContractPayment, PaymentReason

    if body.action == "send":
        await ensure_release_gate_open(
            ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
        )
    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id, with_for_update=True)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        allowed, target = NEXT[body.action]
        if case.status not in allowed:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail=f"{body.action} nicht möglich im Status {case.status}."
            )
        if body.action == "approve":
            if not case.check.get("ok"):
                raise ProblemError(ErrorCodes.CONFLICT, detail="Prüfung hat offene Hinweise.")
            if case.created_by == principal.user_id:
                raise ProblemError(
                    ErrorCodes.GATE_FOUR_EYES, detail="Freigabe durch eine andere Person."
                )
            case.approved_by = principal.user_id
        if body.action == "send":
            if body.document_id is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Dokumentierte rechtliche Prüfung des Schreibens fehlt (M26-01).",
                )
            case.legal_review_document_id = body.document_id
            case.sent_at = datetime.now(UTC)
            if body.received_on is not None:
                from mhvp.letting.rentlaw import deadlines, released_rules

                case.received_on = body.received_on
                rules = await released_rules(session)
                if "consent_months" in rules and "effective_month" in rules:
                    d = deadlines(
                        body.received_on,
                        int(rules["consent_months"]),
                        int(rules["effective_month"]),
                    )
                    case.check = case.check | {
                        "consent_until": d["consent_until"].isoformat(),
                        "effective_from": d["effective_from"].isoformat(),
                    }
                    if case.effective_date < d["effective_from"]:
                        case.check = case.check | {
                            "deadline_flag": "Wirksamkeit liegt vor dem gesetzlichen Beginn."
                        }
        if body.action == "consent":
            if body.document_id is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Nachweis der Zustimmung fehlt.")
            case.consent_document_id = body.document_id
        if body.action == "apply":
            old = await _rent_payment(session, case.contract_id, case.effective_date)
            if old is None or old.net != case.current_rent:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Miete hat sich seit Anlage geändert."
                )
            if old.valid_from >= case.effective_date:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Mietzeile beginnt am Stichtag.")
            gross = (case.target_rent * (1 + old.vat_percent / 100)).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            contract = await session.get(Contract, case.contract_id)
            if contract is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            new = ContractPayment(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                contract_id=case.contract_id,
                payment_type_code="rent",
                net=case.target_rent,
                vat_percent=old.vat_percent,
                gross=gross,
                valid_from=case.effective_date,
                reason=PaymentReason.INCREASE,
                document_id=case.consent_document_id,
            )
            if old.valid_to is not None:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Folgende Mietzeile vorhanden, manuell prüfen."
                )
            await contract_services.add_payment(session, contract, new)
            await session.flush()
            case.new_payment_id = new.id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"rent_increase.{target}",
            entity_type="rent_increase_case",
            entity_id=case.id,
            actor_user_id=principal.user_id,
            payload={"from": case.status, "to": target},
        )
        case.status = target
        await session.flush()
        return _case_out(case)


@router.get("/vacancies", summary="Leerstandsliste (Mietobjekte)")
async def vacancies(
    request: Request, as_of: date | None = None, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    from sqlalchemy import func

    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import ManagementType, Property, Unit

    day = as_of or datetime.now(UTC).date()
    async with tenant_tx(request, principal) as session:
        active = select(Contract.unit_id).where(
            Contract.kind == ContractKind.TENANCY,
            Contract.start_date <= day,
            or_(Contract.end_date.is_(None), Contract.end_date >= day),
        )
        rows = (
            await session.execute(
                select(Unit, Property)
                .join(Property, Property.id == Unit.property_id)
                .where(
                    Property.management_type == ManagementType.RENTAL,
                    Unit.is_fictional.is_(False),
                    Unit.id.not_in(active),
                )
                .order_by(Property.number, Unit.number)
            )
        ).all()
        out = []
        for unit, prop in rows:
            last_end = await session.scalar(
                select(func.max(Contract.end_date)).where(
                    Contract.unit_id == unit.id,
                    Contract.kind == ContractKind.TENANCY,
                    Contract.end_date < day,
                )
            )
            since = last_end + timedelta(days=1) if last_end else None
            out.append(
                {
                    "unit_id": unit.id,
                    "property_number": prop.number,
                    "unit_number": unit.number,
                    "unit_type": unit.unit_type,
                    "living_area_sqm": unit.living_area_sqm,
                    "vacant_since": since,
                    "vacant_days": (day - since).days + 1 if since else None,
                }
            )
        return out


@router.get("/units/{unit_id}/expose", summary="Exposé-Entwurf aus Stammdaten")
async def expose(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Draft only from master data; no personal data of former tenants, no invented text.
    Energy certificate data are required for ads but not modelled yet (M26-03)."""
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        unit = await session.get(Unit, unit_id)
        if unit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        prop = await session.get(Property, unit.property_id)
        if prop is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        fields = {
            "title": unit.label or f"{unit.unit_type} {unit.number}",
            "street": unit.street or prop.street,
            "house_number": unit.house_number or prop.house_number,
            "postal_code": unit.postal_code or prop.postal_code,
            "city": unit.city or prop.city,
            "unit_type": unit.unit_type,
            "rooms": unit.rooms,
            "living_area_sqm": unit.living_area_sqm,
            "floor": unit.floor,
            "features": unit.features,
            "last_modernization_year": unit.last_modernization_year,
        }
        missing = [k for k, v in fields.items() if v in (None, "")]
        return {
            "status": "draft",
            "fields": fields,
            "missing": [*missing, "energy_certificate", "asking_rent"],
            "note": "Entwurf. Pflichtangaben für Anzeigen vor Veröffentlichung prüfen (M26-03).",
        }


def _prospect_out(p: Prospect) -> dict[str, Any]:
    return {
        "id": p.id,
        "unit_id": p.unit_id,
        "contact_id": p.contact_id,
        "status": p.status,
        "viewing_at": p.viewing_at,
        "notes": p.notes,
        "delete_after": p.delete_after,
    }


@router.post("/prospects", status_code=201, summary="Interessent erfassen")
async def create_prospect(
    body: ProspectIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    if body.delete_after <= datetime.now(UTC).date():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Löschdatum muss in der Zukunft liegen.")
    async with tenant_tx(request, principal) as session:
        row = Prospect(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _prospect_out(row)


@router.get("/prospects", summary="Interessenten je Einheit")
async def list_prospects(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(Prospect).where(Prospect.unit_id == unit_id).order_by(Prospect.created_at)
        )
        return [_prospect_out(p) for p in rows.all()]


@router.patch("/prospects/{prospect_id}", summary="Interessent ändern")
async def patch_prospect(
    prospect_id: uuid.UUID,
    body: ProspectPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Prospect, prospect_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        await session.flush()
        return _prospect_out(row)


@router.delete("/prospects/{prospect_id}", status_code=204, summary="Interessent löschen")
async def delete_prospect(
    prospect_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Prospect, prospect_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)


# Makler (M28-01, stage 2): listings for rent and sale. FLOWFACT is not connected;
# publication_status stays a placeholder until the interface documentation is available.


class ListingIn(LettingBaseIn):
    unit_id: uuid.UUID
    kind: str = Field(pattern="^(rental|sale)$")
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    additional_costs: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    deposit: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    available_from: date | None = None
    commission_note: str | None = Field(default=None, max_length=200)
    energy_note: str | None = Field(default=None, max_length=200)
    living_area_sqm: Decimal | None = Field(default=None, gt=0)
    rooms: Decimal | None = Field(default=None, gt=0)
    floor: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)


class ListingPatch(LettingBaseIn):
    status: str | None = Field(default=None, pattern="^(draft|active|reserved|inactive)$")
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    additional_costs: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    deposit: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    available_from: date | None = None
    commission_note: str | None = Field(default=None, max_length=200)
    energy_note: str | None = Field(default=None, max_length=200)
    living_area_sqm: Decimal | None = Field(default=None, gt=0)
    rooms: Decimal | None = Field(default=None, gt=0)
    floor: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)


async def _listing_prefill(session: Any, unit_id: uuid.UUID) -> dict[str, Any]:
    from mhvp.properties.models import Property, Unit

    unit = await session.get(Unit, unit_id)
    if unit is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    prop = await session.get(Property, unit.property_id)
    if prop is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    street_parts = [prop.street, prop.house_number]
    street = " ".join(x for x in street_parts if x)
    place_parts = [prop.postal_code, prop.city]
    place = " ".join(x for x in place_parts if x)
    address = ", ".join(x for x in [street, place] if x)
    unit_label = unit.label or unit.number
    title = ", ".join(x for x in [address, unit_label] if x) or unit_label
    return {
        "property_id": prop.id,
        "unit_id": unit.id,
        "title": title,
        "living_area_sqm": unit.living_area_sqm,
        "rooms": unit.rooms,
        "floor": unit.floor,
    }


def _listing_out(
    listing: Listing, prop_number: str | None, unit_number: str | None
) -> dict[str, Any]:
    return {
        "id": listing.id,
        "property_id": listing.property_id,
        "unit_id": listing.unit_id,
        "property_number": prop_number,
        "unit_number": unit_number,
        "kind": listing.kind,
        "status": listing.status,
        "title": listing.title,
        "description": listing.description,
        "price": listing.price,
        "additional_costs": listing.additional_costs,
        "deposit": listing.deposit,
        "available_from": listing.available_from,
        "commission_note": listing.commission_note,
        "energy_note": listing.energy_note,
        "living_area_sqm": listing.living_area_sqm,
        "rooms": listing.rooms,
        "floor": listing.floor,
        "publication_status": listing.publication_status,
        "publication_ref": listing.publication_ref,
        "published_at": listing.published_at,
        "notes": listing.notes,
    }


@router.get("/listings/prefill", summary="Vorbelegung für eine neue Anzeige")
async def listing_prefill(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await _listing_prefill(session, unit_id)


@router.post("/listings", status_code=201, summary="Anzeige anlegen")
async def create_listing(
    body: ListingIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        prefill = await _listing_prefill(session, body.unit_id)
        data = body.model_dump(exclude={"unit_id", "kind"})
        listing = Listing(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            unit_id=body.unit_id,
            property_id=prefill["property_id"],
            kind=body.kind,
            title=data.pop("title") or prefill["title"],
            living_area_sqm=(
                data.pop("living_area_sqm")
                if body.living_area_sqm is not None
                else prefill["living_area_sqm"]
            ),
            rooms=data.pop("rooms") if body.rooms is not None else prefill["rooms"],
            floor=data.pop("floor") if body.floor is not None else prefill["floor"],
            **{k: v for k, v in data.items() if k not in ("living_area_sqm", "rooms", "floor")},
        )
        session.add(listing)
        await session.flush()
        prop = await session.get(Property, listing.property_id)
        unit = await session.get(Unit, listing.unit_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="listing.created",
            entity_type="listing",
            entity_id=listing.id,
            actor_user_id=principal.user_id,
            payload={"kind": listing.kind, "unit_id": str(listing.unit_id)},
        )
        return _listing_out(listing, prop.number if prop else None, unit.number if unit else None)


@router.get("/listings", summary="Anzeigen")
async def list_listings(
    request: Request,
    kind: str | None = None,
    status: str | None = None,
    property_id: uuid.UUID | None = None,
    q: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        query = (
            select(Listing, Property, Unit)
            .join(Property, Property.id == Listing.property_id)
            .join(Unit, Unit.id == Listing.unit_id)
            .order_by(Listing.created_at.desc())
        )
        if kind is not None:
            query = query.where(Listing.kind == kind)
        if status is not None:
            query = query.where(Listing.status == status)
        if property_id is not None:
            query = query.where(Listing.property_id == property_id)
        if q:
            like = f"%{q}%"
            query = query.where(or_(Listing.title.ilike(like), Property.number.ilike(like)))
        rows = (await session.execute(query.limit(500))).all()
        return [_listing_out(listing, prop.number, unit.number) for listing, prop, unit in rows]


@router.get("/listings/{listing_id}", summary="Anzeige")
async def get_listing(
    listing_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        prop = await session.get(Property, listing.property_id)
        unit = await session.get(Unit, listing.unit_id)
        return _listing_out(listing, prop.number if prop else None, unit.number if unit else None)


@router.patch("/listings/{listing_id}", summary="Anzeige ändern")
async def patch_listing(
    listing_id: uuid.UUID,
    body: ListingPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id, with_for_update=True)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        changes = body.model_dump(exclude_none=True)
        new_status = changes.pop("status", None)
        for key, value in changes.items():
            setattr(listing, key, value)
        if new_status is not None and new_status != listing.status:
            if new_status == "active":
                if not listing.title or listing.price is None:
                    raise ProblemError(
                        ErrorCodes.VALIDATION, detail="Titel und Preis sind für Aktiv nötig."
                    )
                if listing.kind == "rental" and listing.available_from is None:
                    raise ProblemError(
                        ErrorCodes.VALIDATION,
                        detail="Verfügbar ab ist für Vermietungsanzeigen nötig.",
                    )
                other = await session.scalar(
                    select(Listing).where(
                        Listing.unit_id == listing.unit_id,
                        Listing.kind == listing.kind,
                        Listing.status == "active",
                        Listing.id != listing.id,
                    )
                )
                if other is not None:
                    raise ProblemError(
                        ErrorCodes.CONFLICT,
                        detail="Für diese Einheit und Art ist bereits eine Anzeige aktiv.",
                    )
            old_status = listing.status
            listing.status = new_status
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="listing.status_changed",
                entity_type="listing",
                entity_id=listing.id,
                actor_user_id=principal.user_id,
                payload={"from": old_status, "to": new_status},
            )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="listing.updated",
            entity_type="listing",
            entity_id=listing.id,
            actor_user_id=principal.user_id,
            payload={"fields": list(changes.keys())},
        )
        prop = await session.get(Property, listing.property_id)
        unit = await session.get(Unit, listing.unit_id)
        return _listing_out(listing, prop.number if prop else None, unit.number if unit else None)


@router.delete("/listings/{listing_id}", status_code=204, summary="Anzeige löschen")
async def delete_listing(
    listing_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> None:
    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if listing.status != "draft":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur Anzeigen im Entwurf können gelöscht werden."
            )
        await session.delete(listing)
