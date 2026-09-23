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
from mhvp.letting.models import Prospect, RentIncreaseCase

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


class RentIncreaseAction(LettingBaseIn):
    action: str = Field(pattern="^(approve|send|consent|reject|apply|cancel)$")
    document_id: uuid.UUID | None = None


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
        case = RentIncreaseCase(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            current_rent=payment.net,
            living_area_sqm=unit.living_area_sqm if unit else None,
            **body.model_dump(),
        )
        case.check = _check(case, contract.rent_increase_block_until)
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
