"""Letting API (M26): rent increase process, vacancies, exposé draft, prospects.

The source register (annex C) holds no rent law norms. The rent increase check is arithmetic
on values entered with their source; it never states that an increase is lawful. Sending the
demand is a legally relevant statement and needs G3 plus a documented legal review (M26-01)."""

import copy
import io
import re
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.documents.models import Document, DocumentLink
from mhvp.letting import flow_import as flow
from mhvp.letting import openimmo, openimmo_schema
from mhvp.letting.models import FlowImportRun, Listing, Prospect, RentIncreaseCase
from mhvp.platform.models import Tenant, User

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
    Energy certificate data come from the property (A63), the asking rent from the newest
    rental listing of the unit; both are reported as missing when not recorded. Whether the
    listed values satisfy the Pflichtangaben of an advertisement stays open (M26-03)."""
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        unit = await session.get(Unit, unit_id)
        if unit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        prop = await session.get(Property, unit.property_id)
        if prop is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        listing = await session.scalar(
            select(Listing)
            .where(Listing.unit_id == unit.id, Listing.kind == "rental")
            .order_by(Listing.created_at.desc())
            .limit(1)
        )
        energy = openimmo.expose_energy_fields(prop)
        rent = openimmo.expose_rent_fields(listing)
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
        missing += [f"energy_certificate.{k}" for k, v in energy.items() if v in (None, "")]
        missing += [f"asking_rent.{k}" for k, v in rent.items() if v in (None, "")]
        return {
            "status": "draft",
            "fields": fields,
            "energy_certificate": energy,
            "asking_rent": rent,
            "listing_id": listing.id if listing else None,
            "missing": missing,
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


_OBJECT_TYPES = "^(wohnung|haus|gewerbe|stellplatz|grundstueck)$"
_ADDRESS_RELEASE = "^(vollstaendig|nur_plz_ort)$"
_ENERGY_STATUS = "^(liegt_vor|nicht_erforderlich|in_erstellung)$"
_ENERGY_TYPE = "^(bedarf|verbrauch)$"
_FEATURE_KEYS = {
    "balkon",
    "terrasse",
    "garten",
    "keller",
    "aufzug",
    "einbaukueche",
    "gaeste_wc",
    "barrierefrei",
    "moebliert",
    "wg_geeignet",
    "haustiere_erlaubt",
}


def _validate_features(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    unknown = set(value) - _FEATURE_KEYS
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Ausstattungsmerkmale: {sorted(unknown)}"
        )
    return {k: bool(v) for k, v in value.items()}


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
    object_type: str = Field(default="wohnung", pattern=_OBJECT_TYPES)
    address_release: str = Field(default="vollstaendig", pattern=_ADDRESS_RELEASE)
    heating_type: str | None = Field(default=None, max_length=32)
    energy_source: str | None = Field(default=None, max_length=32)
    heating_costs: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    heating_in_additional_costs: bool = False
    hoa_fee: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parking_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    energy_status: str = Field(default="in_erstellung", pattern=_ENERGY_STATUS)
    energy_type: str | None = Field(default=None, pattern=_ENERGY_TYPE)
    energy_value: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    energy_class: str | None = Field(default=None, max_length=4)
    energy_year_of_installation: int | None = Field(default=None, ge=1800, le=2100)
    energy_valid_until: date | None = None
    energy_includes_hot_water: bool = False
    energy_issued_on: date | None = None
    energy_building_year: int | None = Field(default=None, ge=1500, le=2100)
    features: dict[str, Any] = Field(default_factory=dict)
    commission_type: str | None = Field(default=None, max_length=16)


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
    object_type: str | None = Field(default=None, pattern=_OBJECT_TYPES)
    address_release: str | None = Field(default=None, pattern=_ADDRESS_RELEASE)
    heating_type: str | None = Field(default=None, max_length=32)
    energy_source: str | None = Field(default=None, max_length=32)
    heating_costs: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    heating_in_additional_costs: bool | None = None
    hoa_fee: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    parking_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    energy_status: str | None = Field(default=None, pattern=_ENERGY_STATUS)
    energy_type: str | None = Field(default=None, pattern=_ENERGY_TYPE)
    energy_value: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    energy_class: str | None = Field(default=None, max_length=4)
    energy_year_of_installation: int | None = Field(default=None, ge=1800, le=2100)
    energy_valid_until: date | None = None
    energy_includes_hot_water: bool | None = None
    energy_issued_on: date | None = None
    energy_building_year: int | None = Field(default=None, ge=1500, le=2100)
    features: dict[str, Any] | None = None
    commission_type: str | None = Field(default=None, max_length=16)


def _compute_warm_rent(listing: Listing) -> None:
    """Warm rent (Warmmiete) for rental listings only. Rule M28-01: warm_rent =
    price + additional_costs + heating_costs, unless heating_costs is already included in
    additional_costs (heating_in_additional_costs), and only when price is set.

    Example (docstring, hand computed): price=800.00, additional_costs=150.00,
    heating_costs=60.00, heating_in_additional_costs=False
    -> warm_rent = 800.00 + 150.00 + 60.00 = 1010.00 EUR.
    With heating_in_additional_costs=True -> warm_rent = 800.00 + 150.00 = 950.00 EUR
    (heating_costs not added again, as it is part of additional_costs).
    """
    if listing.kind != "rental" or listing.price is None:
        listing.warm_rent = None
        return
    additional = listing.additional_costs or Decimal("0")
    heating = listing.heating_costs or Decimal("0")
    if listing.heating_in_additional_costs:
        if (
            listing.heating_costs is not None
            and listing.additional_costs is not None
            and listing.heating_costs > listing.additional_costs
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Heizkosten dürfen die Nebenkosten nicht übersteigen.",
            )
        listing.warm_rent = listing.price + additional
    else:
        listing.warm_rent = listing.price + additional + heating


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
        "energy": openimmo.property_energy_prefill(prop),
    }


def _listing_warnings(listing: Listing) -> list[str]:
    warnings: list[str] = []
    if listing.status == "active" and listing.energy_status == "in_erstellung":
        warnings.append(
            "Energieausweis liegt noch nicht vor (Status in_erstellung); Aktivierung "
            "ist zulässig, der Ausweis ist nachzureichen."
        )
    return warnings


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
        "object_type": listing.object_type,
        "address_release": listing.address_release,
        "heating_type": listing.heating_type,
        "energy_source": listing.energy_source,
        "heating_costs": listing.heating_costs,
        "heating_in_additional_costs": listing.heating_in_additional_costs,
        "warm_rent": listing.warm_rent,
        "hoa_fee": listing.hoa_fee,
        "parking_price": listing.parking_price,
        "energy_status": listing.energy_status,
        "energy_type": listing.energy_type,
        "energy_value": listing.energy_value,
        "energy_class": listing.energy_class,
        "energy_year_of_installation": listing.energy_year_of_installation,
        "energy_valid_until": listing.energy_valid_until,
        "energy_includes_hot_water": listing.energy_includes_hot_water,
        "energy_issued_on": listing.energy_issued_on,
        "energy_building_year": listing.energy_building_year,
        "features": listing.features,
        "commission_type": listing.commission_type,
        "external_uuid": listing.external_uuid,
        "external_ref": listing.external_ref,
        "flowfact_entity_id": listing.flowfact_entity_id,
        "source": listing.source,
        "warnings": _listing_warnings(listing),
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
        data["features"] = _validate_features(data.get("features"))
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
        # A63: energy certificate of the property is copied unless the caller set a status.
        if "energy_status" not in body.model_fields_set:
            for key, value in prefill["energy"].items():
                if getattr(body, key, None) is None or key == "energy_status":
                    setattr(listing, key, value)
        _compute_warm_rent(listing)
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


@router.get(
    "/listings/openimmo.zip",
    summary="OpenImmo-Sammelexport aktiver Anzeigen (XML, Bilder soweit verknüpft)",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def get_listings_openimmo_zip(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(Listing, Property, Unit)
                .join(Property, Property.id == Listing.property_id)
                .join(Unit, Unit.id == Listing.unit_id)
                .where(Listing.status == "active")
                .order_by(Listing.created_at.desc())
                .limit(500)
            )
        ).all()
        contact = await _export_contact(session, principal)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for listing, prop, unit in rows:
                images = await _listing_images(session, request, listing.id)
                xml = openimmo.build_openimmo_xml(
                    listing, prop, unit, contact=contact, images=images
                )
                archive.writestr(f"{listing.id}/listing.xml", xml)
                for image in images:
                    archive.writestr(f"{listing.id}/images/{image.filename}", image.data)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="listings-openimmo.zip"'},
    )


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
        if "features" in changes:
            changes["features"] = _validate_features(changes["features"])
        for key, value in changes.items():
            setattr(listing, key, value)
        warm_rent_fields = {
            "price",
            "additional_costs",
            "heating_costs",
            "heating_in_additional_costs",
        }
        if warm_rent_fields & set(changes):
            _compute_warm_rent(listing)
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
                if listing.kind == "rental" and listing.warm_rent is None:
                    raise ProblemError(
                        ErrorCodes.VALIDATION,
                        detail="Warmmiete kann nicht berechnet werden (Preis fehlt).",
                    )
                if listing.energy_status == "liegt_vor" and (
                    listing.energy_type is None
                    or listing.energy_value is None
                    or listing.energy_class is None
                ):
                    raise ProblemError(
                        ErrorCodes.VALIDATION,
                        detail=(
                            "Energieausweis liegt_vor erfordert Energieart, Kennwert und "
                            "Energieeffizienzklasse."
                        ),
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


# OpenImmo export (M26-02, docs/rules/M26-02.md): read only, no portal upload -----------


async def _listing_and_property(session: Any, listing_id: uuid.UUID) -> tuple[Listing, Any, Any]:
    from mhvp.properties.models import Property, Unit

    listing = await session.get(Listing, listing_id)
    if listing is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    prop = await session.get(Property, listing.property_id)
    unit = await session.get(Unit, listing.unit_id)
    if prop is None or unit is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return listing, prop, unit


async def _export_contact(session: Any, principal: TenantPrincipal) -> openimmo.ExportContact:
    """Provider and contact person for the export: tenant name as Firma, the exporting
    user as Kontaktperson (docs/rules/M26-02.md). API key callers have no user and are
    reported as missing contact by the check; nothing is invented."""
    # Column selects only: the User row carries an encrypted TOTP secret bound to the
    # platform scope, which must not be loaded inside a tenant transaction.
    company = (
        await session.execute(select(Tenant.name).where(Tenant.id == principal.tenant_id))
    ).scalar_one_or_none()
    name: str | None = None
    email: str | None = None
    if principal.user_id is not None:
        row = (
            await session.execute(
                select(User.display_name, User.email).where(User.id == principal.user_id)
            )
        ).one_or_none()
        if row is not None:
            name, email = row
    return openimmo.ExportContact(company=company, name=name, email=email)


async def _listing_images(session: Any, request: Request, listing_id: uuid.UUID) -> list[Any]:
    """Image documents linked to the listing via document_link (entity_type listing)."""
    documents = (
        await session.execute(
            select(Document)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(
                DocumentLink.entity_type == "listing",
                DocumentLink.entity_id == listing_id,
                Document.mime_type.ilike("image/%"),
            )
            .order_by(Document.created_at)
        )
    ).scalars()
    blobs = _blobs_store(request)
    images: list[openimmo.ExportImage] = []
    seen: set[str] = set()
    for document in documents:
        filename = document.filename.replace("/", "_").replace("\\", "_")
        if filename in seen:
            filename = f"{document.id}-{filename}"
        seen.add(filename)
        images.append(
            openimmo.ExportImage(
                filename=filename,
                mime_type=document.mime_type,
                data=blobs.get(document.storage_ref),
                title=document.title,
            )
        )
    return images


def _schema_result(request: Request, xml: bytes) -> openimmo_schema.SchemaResult:
    """Schema check of the built document against the operator's XSD (setting
    ``openimmo_xsd_path``) or, without one, the documented structure (M26-02)."""
    return openimmo_schema.validate_openimmo(xml, request.app.state.settings.openimmo_xsd_path)


def _ensure_exportable(
    result: openimmo.CompletenessResult,
    force: bool,
    schema: openimmo_schema.SchemaResult | None = None,
) -> None:
    """Export lock (M26): an incomplete listing or a document that fails the schema check
    is exported only with force=true."""
    if force or (result.complete and (schema is None or schema.valid)):
        return
    if not result.complete:
        detail = (
            "Die Anzeige ist für den OpenImmo-Export unvollständig. Fehlende Angaben ergänzen "
            "oder den Export ausdrücklich mit force=true auslösen (trotzdem exportieren)."
        )
    else:
        detail = (
            "Die OpenImmo-Datei besteht die Schemaprüfung nicht. Fehler beheben oder den "
            "Export ausdrücklich mit force=true auslösen (trotzdem exportieren)."
        )
    payload = result.to_dict()
    if schema is not None:
        payload["schema"] = schema.to_dict()
    raise ProblemError(ErrorCodes.VALIDATION, detail=detail, extensions={"openimmo": payload})


@router.get(
    "/listings/{listing_id}/openimmo-check",
    summary="OpenImmo-Export: Vollständigkeitsprüfung (fehlende Pflichtfelder)",
)
async def openimmo_check(
    listing_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        listing, prop, unit = await _listing_and_property(session, listing_id)
        contact = await _export_contact(session, principal)
        result = openimmo.check_completeness(listing, prop, contact)
        images = await _listing_images(session, request, listing_id)
        xml = openimmo.build_openimmo_xml(listing, prop, unit, contact=contact, images=images)
        out = result.to_dict()
        out["image_count"] = len(images)
        out["schema"] = _schema_result(request, xml).to_dict()
        return out


@router.get(
    "/listings/{listing_id}/openimmo.xml",
    summary="OpenImmo 1.2.7 Export als XML (nur lesend, kein Portal-Upload)",
    response_class=Response,
    responses={
        200: {"content": {"application/xml": {}}},
        422: {"description": "unvollständig oder Schemafehler"},
    },
)
async def get_listing_openimmo(
    listing_id: uuid.UUID,
    request: Request,
    force: bool = Query(default=False, description="trotzdem exportieren"),
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        listing, prop, unit = await _listing_and_property(session, listing_id)
        contact = await _export_contact(session, principal)
        completeness = openimmo.check_completeness(listing, prop, contact)
        xml = openimmo.build_openimmo_xml(listing, prop, unit, contact=contact)
        _ensure_exportable(completeness, force, _schema_result(request, xml))
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="listing-{listing_id}.xml"'},
    )


@router.get(
    "/listings/{listing_id}/openimmo.zip",
    summary="OpenImmo 1.2.7 Export als ZIP (XML und verknüpfte Bilder, kein Portal-Upload)",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}},
        422: {"description": "unvollständig oder Schemafehler"},
    },
)
async def get_listing_openimmo_zip(
    listing_id: uuid.UUID,
    request: Request,
    force: bool = Query(default=False, description="trotzdem exportieren"),
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        listing, prop, unit = await _listing_and_property(session, listing_id)
        contact = await _export_contact(session, principal)
        completeness = openimmo.check_completeness(listing, prop, contact)
        images = await _listing_images(session, request, listing_id)
        xml = openimmo.build_openimmo_xml(listing, prop, unit, contact=contact, images=images)
        _ensure_exportable(completeness, force, _schema_result(request, xml))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("listing.xml", xml)
        for image in images:
            archive.writestr(f"images/{image.filename}", image.data)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="listing-{listing_id}.zip"'},
    )


def _blobs_store(request: Request) -> Any:
    from mhvp.documents.blobs import BlobStore

    return BlobStore(request.app.state.settings)


# FLOW import (M28 stage 4, docs/rules/M28-01.md) ----------------------------------------

FLOW_IMPORT_MAX_BYTES = 50 * 1024 * 1024


async def _match_unit(session: Any, match: dict[str, Any]) -> dict[str, Any]:
    """Propose a unit for a preview row: by object number (property.number) when
    ``verwaltungsobjekt_referenz`` names one, else by street, house number and postal code
    against Property; unit stays unmatched otherwise (docs/rules/M28-01.md)."""
    from mhvp.properties.models import Property, Unit

    result = dict(match)
    object_number = match.get("object_number")
    prop = None
    if object_number:
        m = re.search(r"(\d{3})", str(object_number))
        if m:
            prop = await session.scalar(select(Property).where(Property.number == m.group(1)))
    if prop is None and (match.get("basis") == "address"):
        # street/house_number/postal_code are carried on the row itself, not on match; the
        # caller passes them in via match["street"] etc.
        street = match.get("street")
        house_number = match.get("house_number")
        postal_code = match.get("postal_code")
        if street and postal_code:
            query = select(Property).where(
                Property.street.ilike(street), Property.postal_code == postal_code
            )
            if house_number:
                query = query.where(Property.house_number == house_number)
            prop = await session.scalar(query)
    if prop is None:
        result["unit_id"] = None
        result["property_id"] = None
        return result
    result["property_id"] = str(prop.id)
    result["property_number"] = prop.number
    unit_label = match.get("unit_label")
    unit = None
    if unit_label:
        unit = await session.scalar(
            select(Unit).where(
                Unit.property_id == prop.id,
                or_(Unit.label == unit_label, Unit.number == unit_label),
            )
        )
    result["unit_id"] = str(unit.id) if unit else None
    result["unit_number"] = unit.number if unit else None
    return result


@router.post(
    "/flow-import/preview", status_code=201, summary="FLOW-Datenbankexport (SQL-Dump) prüfen"
)
async def flow_import_preview(
    request: Request,
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    data = await file.read(FLOW_IMPORT_MAX_BYTES + 1)
    if len(data) > FLOW_IMPORT_MAX_BYTES:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Datei überschreitet 50 MB und wird nicht angenommen."
        )
    try:
        text_content = data.decode("utf-8")
    except UnicodeDecodeError:
        text_content = data.decode("latin-1")
    try:
        dump = flow.parse_dump(text_content)
    except flow.FlowDumpError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    previews = flow.build_previews(dump)
    async with tenant_tx(request, principal) as session:
        rows: list[dict[str, Any]] = []
        for preview in previews:
            row = preview.to_dict()
            match_input = dict(preview.match)
            match_input["street"] = preview.listing_fields.get("street")
            match_input["house_number"] = preview.listing_fields.get("house_number")
            match_input["postal_code"] = preview.listing_fields.get("postal_code")
            row["match"] = await _match_unit(session, match_input)
            if row["match"].get("unit_id") is None:
                row["problems"].append("Keine Einheit zugeordnet; vor Übernahme manuell auswählen.")
            rows.append(row)
        run = FlowImportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            filename=file.filename or "flow_export.sql",
            status="previewed",
            row_count=len(rows),
            rows=rows,
        )
        session.add(run)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="flow_import.previewed",
            entity_type="flow_import_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"row_count": run.row_count},
        )
        return {
            "id": run.id,
            "filename": run.filename,
            "status": run.status,
            "row_count": run.row_count,
            "rows": run.rows,
        }


def _run_out(run: FlowImportRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "filename": run.filename,
        "status": run.status,
        "row_count": run.row_count,
        "created_count": run.created_count,
        "skipped_count": run.skipped_count,
        "rows": run.rows,
        "applied_at": run.applied_at,
    }


@router.get("/flow-import/{run_id}", summary="FLOW-Importlauf")
async def get_flow_import_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(FlowImportRun, run_id)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _run_out(run)


class FlowImportItemIn(LettingBaseIn):
    index: int = Field(ge=0)
    action: str = Field(pattern="^(create|skip)$")
    unit_id: uuid.UUID | None = None


class FlowImportApplyIn(LettingBaseIn):
    items: list[FlowImportItemIn] = Field(min_length=1, max_length=2000)


@router.post("/flow-import/{run_id}/apply", summary="FLOW-Anzeigen übernehmen")
async def apply_flow_import(
    run_id: uuid.UUID,
    body: FlowImportApplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.properties.models import Unit

    async with tenant_tx(request, principal) as session:
        run = await session.get(FlowImportRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        # Deep copy: mutating the stored dicts in place would make the reassigned value
        # compare equal to the pre-existing one, and SQLAlchemy would then skip the UPDATE.
        rows = copy.deepcopy(run.rows)
        by_index = {row["index"]: row for row in rows}
        created = 0
        skipped = 0
        for item in body.items:
            row = by_index.get(item.index)
            if row is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail=f"Zeile {item.index} unbekannt.")
            if row.get("applied"):
                # Idempotency: applying a run twice creates nothing new.
                skipped += 1
                continue
            if item.action == "skip":
                row["applied"] = True
                row["outcome"] = "skipped"
                skipped += 1
                continue
            external_uuid = row.get("external_uuid")
            if external_uuid:
                existing = await session.scalar(
                    select(Listing).where(Listing.external_uuid == uuid.UUID(external_uuid))
                )
                if existing is not None:
                    row["applied"] = True
                    row["outcome"] = "skipped"
                    row["note"] = "external_uuid bereits vorhanden"
                    skipped += 1
                    continue
            unit_id = item.unit_id or (
                uuid.UUID(row["match"]["unit_id"]) if row["match"].get("unit_id") else None
            )
            if unit_id is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Zeile {item.index}: keine Einheit für die Übernahme ausgewählt.",
                )
            unit = await session.get(Unit, unit_id)
            if unit is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Einheit nicht gefunden.")
            fields = dict(row["listing_fields"])
            for key in ("street", "house_number", "postal_code", "city"):
                fields.pop(key, None)
            for key in (
                "price",
                "additional_costs",
                "heating_costs",
                "deposit",
                "hoa_fee",
                "parking_price",
                "energy_value",
            ):
                if fields.get(key) is not None:
                    fields[key] = Decimal(str(fields[key]))
            if fields.get("energy_valid_until"):
                fields["energy_valid_until"] = date.fromisoformat(
                    str(fields["energy_valid_until"])[:10]
                )
            if fields.get("rooms") is not None:
                fields["rooms"] = Decimal(str(fields["rooms"]))
            if fields.get("living_area_sqm") is not None:
                fields["living_area_sqm"] = Decimal(str(fields["living_area_sqm"]))
            fallback_title = f"FLOW-Import {row.get('external_ref') or ''}".strip()
            title = fields.pop("title", None) or fallback_title
            listing = Listing(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                unit_id=unit.id,
                property_id=unit.property_id,
                title=title,
                source="flow_import",
                external_uuid=uuid.UUID(external_uuid) if external_uuid else None,
                external_ref=row.get("external_ref"),
                **{k: v for k, v in fields.items() if k not in ("kind",)},
                kind=fields.get("kind", "rental"),
            )
            _compute_warm_rent(listing)
            session.add(listing)
            try:
                await session.flush()
            except IntegrityError as exc:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Anzeige konnte wegen einer bestehenden Zuordnung nicht angelegt "
                    "werden (external_uuid bereits vergeben).",
                ) from exc
            row["applied"] = True
            row["outcome"] = "created"
            row["listing_id"] = str(listing.id)
            created += 1
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="listing.created",
                entity_type="listing",
                entity_id=listing.id,
                actor_user_id=principal.user_id,
                payload={"source": "flow_import", "flow_import_run_id": str(run.id)},
            )
        run.rows = rows
        flag_modified(run, "rows")
        run.created_count += created
        run.skipped_count += skipped
        run.status = "applied"
        run.applied_at = datetime.now(UTC)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="flow_import.applied",
            entity_type="flow_import_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"created": created, "skipped": skipped},
        )
        return _run_out(run)


# Listing images (M26-02): documents linked to a listing via document_link ----------------


class ListingImageLinkIn(LettingBaseIn):
    document_id: uuid.UUID


def _image_out(document: Document, link: DocumentLink) -> dict[str, Any]:
    return {
        "document_id": str(document.id),
        "link_id": str(link.id),
        "title": document.title,
        "filename": document.filename,
        "mime_type": document.mime_type,
        "size": document.size,
        "created_at": document.created_at.isoformat(),
        "linked_at": link.created_at.isoformat(),
        "role": link.role.value,
    }


async def _listing_image_rows(session: Any, listing_id: uuid.UUID) -> list[dict[str, Any]]:
    """All image documents of the listing in link order (DocumentLink has no sort field, so
    the order of linking is the order of the export; docs/rules/M26-02.md)."""
    rows = (
        await session.execute(
            select(Document, DocumentLink)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(
                DocumentLink.entity_type == "listing",
                DocumentLink.entity_id == listing_id,
                Document.mime_type.ilike("image/%"),
            )
            .order_by(DocumentLink.created_at, DocumentLink.id)
        )
    ).all()
    return [_image_out(document, link) for document, link in rows]


@router.get("/listings/{listing_id}/images", summary="Bilder einer Anzeige")
async def list_listing_images(
    listing_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if await session.get(Listing, listing_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _listing_image_rows(session, listing_id)


@router.post(
    "/listings/{listing_id}/images",
    status_code=201,
    summary="Bild hochladen und mit der Anzeige verknüpfen",
)
async def upload_listing_image(
    listing_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    """Stores the file as a regular document (M6 rules: type check, size limit, mirrors)
    with a link `entity_type="listing"`, role attachment. Only image types are accepted here;
    other files go through the document upload. Returns the updated image list."""
    from mhvp.documents import services as document_services
    from mhvp.documents.models import DocumentSource, LinkRole

    limit = request.app.state.settings.document_max_bytes
    data = await file.read(limit + 1)
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if not mime.startswith("image/"):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Für Anzeigen sind nur Bilddateien vorgesehen."
        )
    document_services.check_upload(mime, data, limit)
    filename = (file.filename or "bild").replace("/", "_").replace("\\", "_")
    async with tenant_tx(request, principal) as session:
        if await session.get(Listing, listing_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await document_services.store_document(
            session,
            _blobs_store(request),
            tenant_id=principal.tenant_id,
            data=data,
            title=filename,
            filename=filename,
            mime_type=mime,
            source=DocumentSource.UPLOAD,
            category_id=None,
            links=[("listing", listing_id, LinkRole.ATTACHMENT)],
            created_by=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.created",
            entity_type="document",
            entity_id=document.id,
            actor_user_id=principal.user_id,
            payload={"size": document.size, "listing_id": str(listing_id)},
        )
        return await _listing_image_rows(session, listing_id)


@router.post(
    "/listings/{listing_id}/images/link",
    status_code=201,
    summary="Vorhandenes Bilddokument mit der Anzeige verknüpfen",
)
async def link_listing_image(
    listing_id: uuid.UUID,
    body: ListingImageLinkIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    from mhvp.documents.models import LinkRole

    async with tenant_tx(request, principal) as session:
        if await session.get(Listing, listing_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await session.get(Document, body.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
        if not document.mime_type.lower().startswith("image/"):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Das Dokument ist keine Bilddatei.")
        session.add(
            DocumentLink(
                tenant_id=principal.tenant_id,
                document_id=document.id,
                entity_type="listing",
                entity_id=listing_id,
                role=LinkRole.ATTACHMENT,
            )
        )
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Das Bild ist bereits mit der Anzeige verknüpft."
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.linked",
            entity_type="document",
            entity_id=document.id,
            actor_user_id=principal.user_id,
            payload={"target_type": "listing", "target_id": str(listing_id)},
        )
        return await _listing_image_rows(session, listing_id)


@router.delete(
    "/listings/{listing_id}/images/{document_id}",
    summary="Bild von der Anzeige lösen (Dokument bleibt erhalten)",
)
async def unlink_listing_image(
    listing_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    """Removes only the link to the listing; the document itself and its other links stay
    (deletion of documents follows the retention rules of module documents)."""
    async with tenant_tx(request, principal) as session:
        if await session.get(Listing, listing_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        links = (
            await session.scalars(
                select(DocumentLink).where(
                    DocumentLink.entity_type == "listing",
                    DocumentLink.entity_id == listing_id,
                    DocumentLink.document_id == document_id,
                )
            )
        ).all()
        if not links:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Verknüpfung fehlt.")
        for link in links:
            await session.delete(link)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.unlinked",
            entity_type="document",
            entity_id=document_id,
            actor_user_id=principal.user_id,
            payload={"target_type": "listing", "target_id": str(listing_id)},
        )
        await session.flush()
        return await _listing_image_rows(session, listing_id)


@router.get(
    "/listings/{listing_id}/images/{document_id}/content",
    summary="Bild einer Anzeige anzeigen",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}},
)
async def listing_image_content(
    listing_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        link = await session.scalar(
            select(DocumentLink).where(
                DocumentLink.entity_type == "listing",
                DocumentLink.entity_id == listing_id,
                DocumentLink.document_id == document_id,
            )
        )
        document = await session.get(Document, document_id) if link is not None else None
        if document is None or not document.mime_type.lower().startswith("image/"):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = _blobs_store(request).get(document.storage_ref)
    return Response(
        content=data,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.id}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
