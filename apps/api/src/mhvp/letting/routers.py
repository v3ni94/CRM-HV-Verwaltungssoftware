"""Letting API (M26): rent increase process, vacancies, exposé draft, prospects.

The source register (annex C) holds no rent law norms. The rent increase check is arithmetic
on values entered with their source; it never states that an increase is lawful. Sending the
demand is a legally relevant statement and needs G3 plus a documented legal review (M26-01)."""

import copy
import hashlib
import html
import io
import re
import secrets
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.events import emit
from mhvp.core.listparams import ListParams, ListSpec, sparse, strict_query
from mhvp.core.logging import get_logger
from mhvp.core.money import round_cents
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.core.uploads import read_limited
from mhvp.documents.letter_records import LetterRecordIn
from mhvp.documents.models import Document, DocumentLink
from mhvp.letting import basis_checks, openimmo, openimmo_import, openimmo_schema
from mhvp.letting import flow_import as flow
from mhvp.letting.broker_provider import (
    BrokerAmbiguousMatchError,
    BrokerListingPayload,
    BrokerUpstreamError,
    DocumentationRequiredError,
    get_provider,
)
from mhvp.letting.models import (
    BrokerTenantConfig,
    FlowImportRun,
    Listing,
    OpenImmoImportRun,
    Prospect,
    ProspectViewing,
    RentIncreaseCase,
    SelfDisclosureLink,
    VacancyCase,
)
from mhvp.letting.prospect_texts import list_templates, template_by_id
from mhvp.platform.models import Tenant, User
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/letting", tags=["letting"])
READ = require_permission("contracts:read")
log = get_logger("mhvp.letting")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")
APPROVE = require_permission("contracts:approve")
DELETE = require_permission("contracts:delete")
SETTINGS = require_permission("tenant_settings:update")
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
    # Inputs of the bases index, modernization, graduated (M26-02, see basis_checks).
    basis_data: dict[str, Any] = Field(default_factory=dict)


class RentIncreaseAction(LettingBaseIn):
    # ``receipt`` records the access date (Zugangsdatum) of a letter sent outside the
    # software while G3 keeps ``send`` locked; it changes no status (handbook Mieterhöhung,
    # gap "Zugangsdatum nur über die Schnittstelle").
    # ``set_block`` (GAK-202) writes the confirmed blocking date to the contract after apply.
    action: str = Field(pattern="^(approve|send|consent|reject|apply|cancel|receipt|set_block)$")
    document_id: uuid.UUID | None = None
    received_on: date | None = None
    block_until: date | None = None


class ProspectProfileIn(LettingBaseIn):
    """Search profile (wishes) of a prospect for the match with listings (M26-06)."""

    max_rent: Decimal | None = Field(default=None, gt=0, decimal_places=2)  # Kaltmiete
    max_warm_rent: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    min_rooms: Decimal | None = Field(default=None, gt=0)
    min_area_sqm: Decimal | None = Field(default=None, gt=0)
    move_in_by: date | None = None
    kinds: list[str] = Field(default_factory=list, max_length=2)
    required_features: list[str] = Field(default_factory=list, max_length=20)


class ProspectIn(LettingBaseIn):
    unit_id: uuid.UUID
    contact_id: uuid.UUID
    listing_id: uuid.UUID | None = None
    search_profile: ProspectProfileIn | None = None
    viewing_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    delete_after: date
    source: str = Field(default="manual", pattern="^(manual|portal|openimmo|flow)$")


class ProspectPatch(LettingBaseIn):
    listing_id: uuid.UUID | None = None
    search_profile: ProspectProfileIn | None = None
    status: str | None = Field(
        default=None, pattern="^(new|viewing|applied|accepted|rejected|withdrawn)$"
    )
    viewing_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    rejection_template_id: str | None = Field(default=None, max_length=32)


class ProspectViewingIn(LettingBaseIn):
    scheduled_at: datetime
    location: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)


class ProspectViewingPatch(LettingBaseIn):
    status: str | None = Field(
        default=None, pattern="^(proposed|confirmed|done|cancelled|no_show)$"
    )
    scheduled_at: datetime | None = None
    location: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)


class SelfDisclosureLinkIn(LettingBaseIn):
    valid_days: int = Field(default=14, ge=1, le=90)


# GAI-309: limits of the anonymous self disclosure payload (Produktschutz, not a legal rule).
SELF_DISCLOSURE_MAX_KEYS = 200
SELF_DISCLOSURE_MAX_DEPTH = 3
SELF_DISCLOSURE_MAX_KEY_LENGTH = 100
SELF_DISCLOSURE_MAX_STRING = 5000
SELF_DISCLOSURE_MAX_BYTES = 64 * 1024


def _check_self_disclosure_value(value: Any, depth: int, counter: list[int]) -> None:
    if depth > SELF_DISCLOSURE_MAX_DEPTH:
        raise ValueError("payload is nested too deeply")
    if isinstance(value, dict):
        for key, item in value.items():
            counter[0] += 1
            if counter[0] > SELF_DISCLOSURE_MAX_KEYS:
                raise ValueError("payload has too many fields")
            if len(str(key)) > SELF_DISCLOSURE_MAX_KEY_LENGTH:
                raise ValueError("payload field name is too long")
            _check_self_disclosure_value(item, depth + 1, counter)
    elif isinstance(value, list):
        for item in value:
            counter[0] += 1
            if counter[0] > SELF_DISCLOSURE_MAX_KEYS:
                raise ValueError("payload has too many fields")
            _check_self_disclosure_value(item, depth + 1, counter)
    elif isinstance(value, str) and len(value) > SELF_DISCLOSURE_MAX_STRING:
        raise ValueError("payload value is too long")


class SelfDisclosureSubmitIn(LettingBaseIn):
    consent_privacy: bool
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _limit_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(json.dumps(value, ensure_ascii=False).encode()) > SELF_DISCLOSURE_MAX_BYTES:
            raise ValueError("payload is too large")
        _check_self_disclosure_value(value, 1, [0])
        return value


class BrokerConfigIn(LettingBaseIn):
    api_key: str | None = Field(default=None, max_length=500)
    api_secret: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, max_length=300)
    enabled: bool = False
    # Provider specific configuration with no shared column (M28-02): flowfact expects
    # schema_rental/schema_sale, the FLOWFACT schema name per listing kind.
    settings: dict[str, Any] = Field(default_factory=dict)


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
        "basis_data": c.basis_data,
        "ai_check_id": c.ai_check_id,
        "rent_index_date": c.rent_index_date,
        "comparison_rent_per_sqm": c.comparison_rent_per_sqm,
        "living_area_sqm": c.living_area_sqm,
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
        cap = round_cents(case.reference_rent * (1 + case.cap_limit_percent / 100))
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
    if case.basis in basis_checks.MODELS:
        computed, basis_flags = basis_checks.check(
            case.basis,
            case.basis_data or {},
            current_rent=case.current_rent,
            target_rent=case.target_rent,
            effective_date=case.effective_date,
            has_agreement_document=case.source_document_id is not None,
        )
        out["basis"] = computed
        flags.extend(basis_flags)
    if not case.source_note and not case.source_document_id:
        flags.append("Quelle der erfassten Werte fehlt.")
    if block_until and case.effective_date <= block_until:
        flags.append(f"Mieterhöhungssperre bis {block_until:%d.%m.%Y}.")
    if case.earliest_effective_date and case.effective_date < case.earliest_effective_date:
        flags.append("Wirksamkeit vor dem erfassten frühesten Zeitpunkt.")
    out["flags"] = flags
    out["ok"] = not flags
    return out


async def _auto_ai_check(
    session: Any, principal: TenantPrincipal, case: RentIncreaseCase
) -> uuid.UUID | None:
    """Q14-02: queues the AI plausibility run of a new or changed draft case when the tenant
    switch is on and a provider is released; never blocks the case itself."""
    from mhvp.ai import rent_increase_check

    try:
        # Reload so JSON columns hold the stored (serializable) values, as in the manual path.
        await session.refresh(case)
        return await rent_increase_check.auto_queue(
            session, tenant_id=principal.tenant_id, user_id=principal.user_id, case=case
        )
    except Exception:
        log.exception("rent increase auto ai check not queued", case_id=str(case.id))
        return None


async def _dispatch_auto_ai_check(
    request: Request, principal: TenantPrincipal, run_id: uuid.UUID | None
) -> None:
    if run_id is None:
        return
    from mhvp.billing.ai_check_routers import _dispatch

    try:
        await _dispatch(request, principal, run_id)
    except Exception:  # the case is saved; the run can be started by hand (POST .../ai-check)
        log.exception("rent increase auto ai check not dispatched", run_id=str(run_id))


@router.post("/rent-increases", status_code=201, summary="Mieterhöhung anlegen und prüfen")
async def create_rent_increase(
    body: RentIncreaseIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Unit

    try:
        basis_data = basis_checks.validate(body.basis, body.basis_data)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
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
                    "basis_data": basis_data,
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
        out = _case_out(case)
        auto_run_id = await _auto_ai_check(session, principal, case)
    await _dispatch_auto_ai_check(request, principal, auto_run_id)
    return out


@router.get("/rent-increases", summary="Mieterhöhungsfälle", dependencies=[Depends(strict_query)])
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


class RentIndexAdoptIn(LettingBaseIn):
    entry_id: uuid.UUID
    position: str = Field(pattern="^(min|mid|max)$")


class RentIncreaseAiCheckIn(LettingBaseIn):
    proposal_id: uuid.UUID | None = None


@router.post(
    "/rent-increases/{case_id}/adopt-rent-index",
    summary="Mietspiegelspanne in den Mieterhöhungsfall übernehmen",
)
async def adopt_rent_index(
    case_id: uuid.UUID,
    body: RentIndexAdoptIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """Takes one value of a maintained index row (lower bound, middle or upper bound) as the
    comparison rent per m² of a draft case, with index name, Stand and source note, and runs
    the check again. The choice of the position stays with the clerk; the platform does not
    decide the local comparative rent (M26-03)."""
    from mhvp.contracts.models import Contract
    from mhvp.letting.models import RentIndexEntry
    from mhvp.letting.rentlaw import statutory_check
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id, with_for_update=True)
        entry = await session.get(RentIndexEntry, body.entry_id)
        if case is None or entry is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if case.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur im Status draft änderbar.")
        value = {"min": entry.rent_min, "mid": entry.rent_mid, "max": entry.rent_max}[body.position]
        if value is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Der Mittelwert ist nicht erfasst.")
        case.comparison_rent_per_sqm = value
        case.rent_index_name = entry.index_name
        case.rent_index_date = entry.valid_from
        case.justification = "mietspiegel"
        note = (
            f"Mietspiegel {entry.index_name} ({entry.municipality}), "
            f"{body.position}: {entry.source_note}"
        )
        case.source_note = note[:2000]
        contract = await session.get(Contract, case.contract_id)
        check = _check(case, contract.rent_increase_block_until if contract else None)
        if contract is not None:
            prop = await session.get(Property, contract.property_id)
            statutory = await statutory_check(session, case, contract, prop)
            check["statutory"] = statutory
            check["ok"] = check["ok"] and not statutory["flags"]
        case.check = check
        await session.flush()
        out = _case_out(case)
        auto_run_id = await _auto_ai_check(session, principal, case)
    await _dispatch_auto_ai_check(request, principal, auto_run_id)
    return out


@router.put(
    "/rent-increases/{case_id}/ai-check",
    summary="KI-Prüfung mit dem Mieterhöhungsfall verknüpfen",
)
async def link_rent_increase_ai_check(
    case_id: uuid.UUID,
    body: RentIncreaseAiCheckIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.ai.models import AiProposal

    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.proposal_id is not None and await session.get(AiProposal, body.proposal_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        case.ai_check_id = body.proposal_id
        await session.flush()
        return _case_out(case)


@router.post(
    "/rent-increases/{case_id}/ai-check",
    status_code=202,
    summary="KI-Plausibilität des Mieterhöhungsfalls anstoßen (nur Hinweise)",
)
async def start_rent_increase_ai_check(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """M26-01: queues the AI task ``rent_increase_check`` through the gateway (release, DPA
    evidence, budget). The result is a hint proposal linked as ``ai_check_id``; the case, its
    status and its deterministic check stay unchanged (rule 0.1.6)."""
    from mhvp.ai import rent_increase_check
    from mhvp.billing.ai_check_routers import _dispatch
    from mhvp.core.events import emit

    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        run = rent_increase_check.queue_run(
            session, tenant_id=principal.tenant_id, user_id=principal.user_id, case=case
        )
        await session.flush()
        run_id = run.id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rent_increase.ai_check_requested",
            entity_type="rent_increase_case",
            entity_id=case.id,
            actor_user_id=principal.user_id,
            payload={"run_id": str(run_id)},
        )
    await _dispatch(request, principal, run_id)
    return await get_rent_increase_ai_check(case_id, request, principal)


@router.get("/rent-increases/{case_id}/ai-check", summary="KI-Plausibilität des Falls lesen")
async def get_rent_increase_ai_check(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.ai import rent_increase_check
    from mhvp.ai.models import AiProposal

    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        run = await rent_increase_check.latest_run(session, case_id)
        proposal = await session.get(AiProposal, case.ai_check_id) if case.ai_check_id else None
        return {
            "case_id": case_id,
            "ai_check_id": case.ai_check_id,
            "latest_run": (
                {
                    "id": run.id,
                    "status": run.status.value,
                    "error": run.error,
                    "model": run.model,
                    "created_at": run.created_at,
                }
                if run is not None
                else None
            ),
            "latest": (
                {
                    "id": proposal.id,
                    "entity_type": proposal.entity_type,
                    "decision": proposal.decision.value,
                    "created_at": proposal.created_at,
                    "proposed": proposal.proposed,
                }
                if proposal is not None
                else None
            ),
        }


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


class RentIncreaseLetterPdfIn(LetterRecordIn):
    """Letter on the letterhead; the recipient is the primary contact of the tenant party
    unless ``contact_id`` names another member of it."""

    contact_id: uuid.UUID | None = None


async def _case_context(session: Any, case: RentIncreaseCase) -> tuple[Any, Any, Any, str, str]:
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Property, Unit

    contract = await session.get(Contract, case.contract_id)
    unit = await session.get(Unit, contract.unit_id) if contract else None
    prop = await session.get(Property, unit.property_id) if unit else None
    parts = [prop.street, prop.house_number] if prop else []
    street = " ".join(x for x in parts if x)
    places = [prop.postal_code, prop.city] if prop else []
    city = " ".join(x for x in places if x)
    address = ", ".join(x for x in [street, city] if x) or "[Anschrift]"
    label = (unit.label or unit.number) if unit else "[Einheit]"
    return contract, unit, prop, label, address


@router.post(
    "/rent-increases/{case_id}/letter/pdf",
    status_code=201,
    summary="Mieterhöhungsschreiben auf dem Briefbogen ablegen (PDF, Versandnachweis, Ticket)",
)
async def rent_increase_letter_pdf(
    case_id: uuid.UUID,
    body: RentIncreaseLetterPdfIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """The letter of ``GET .../letter`` on the tenant letterhead, filed as a generated
    document of the case, contract, unit, property and tenant, with an optional ticket link
    and a dispatch record (channel, date, user, reference). The platform sends nothing: the
    process step ``send`` (status ``sent``) stays behind G3, a mail draft leaves only through
    the mail approval, and the portal channel is refused while G3 is closed. Until the legal
    review is documented the PDF carries the draft marking."""
    from mhvp.contacts.models import PartyMember, PartyRole
    from mhvp.documents import letter_records
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.letters import Letter
    from mhvp.letting.rentlaw import letter_body

    if body.dispatch is not None and body.dispatch.channel == "portal":
        await ensure_release_gate_open(
            ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
        )
    async with tenant_tx(request, principal) as session:
        case = await session.get(RentIncreaseCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        # AJ23 (GAI-303): the storage check follows the lookup, a foreign id answers 404.
        blobs = BlobStore(request.app.state.settings)
        if case.status in ("cancelled", "rejected"):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail=f"Kein Schreiben im Status {case.status}."
            )
        contract, unit, prop, label, address = await _case_context(session, case)
        if contract is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Mietvertrag fehlt.")
        members = list(
            await session.scalars(
                select(PartyMember)
                .where(PartyMember.party_id == contract.party_id)
                .order_by(PartyMember.role, PartyMember.created_at)
            )
        )
        member_ids = {m.contact_id for m in members}
        if body.contact_id is not None:
            if body.contact_id not in member_ids:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Der Empfänger gehört nicht zur Mietpartei."
                )
            contact_id = body.contact_id
        else:
            primary = next((m for m in members if m.role is PartyRole.PRIMARY), None)
            if primary is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Die Mietpartei hat keinen Hauptkontakt."
                )
            contact_id = primary.contact_id
        head = await doc_services.letterhead(session, blobs)
        contact, recipient_lines, data = await doc_services.recipient(session, contact_id)
        subject, lines, placeholders = letter_body(case, label, address)
        letter_date = body.letter_date or local_today()
        paragraphs = [html.escape(str(data["anrede"]))]
        block: list[str] = []
        for line in lines:
            if line == "":
                if block:
                    paragraphs.append("<br/>".join(html.escape(x) for x in block))
                    block = []
            else:
                block.append(line)
        if block:
            paragraphs.append("<br/>".join(html.escape(x) for x in block))
        draft = case.legal_review_document_id is None
        letter = Letter(
            recipient_lines=recipient_lines,
            subject=html.escape(subject),
            body="\n\n".join(paragraphs),
            letter_date=letter_date,
            info=[
                ("Mietvertrag", contract.number),
                ("Status", f"Fall {case.status}, {'Entwurf' if draft else 'rechtlich geprüft'}"),
            ],
            signatory=[s for s in (str(head.company.get("name", "")),) if s],
            draft_notice=(
                "ENTWURF, vor Versand rechtlich zu prüfen (M26-01); Versand hinter G3"
                if draft
                else None
            ),
        )
        links: list[tuple[str, uuid.UUID]] = [
            ("rent_increase_case", case.id),
            ("contract", contract.id),
            ("contact", contact.id),
        ]
        if unit is not None:
            links.append(("unit", unit.id))
        if prop is not None:
            links.append(("property", prop.id))
        document = await letter_records.store_letter(
            session,
            blobs,
            principal=principal,
            head=head,
            letter=letter,
            title=(
                f"Mieterhöhungsschreiben {contract.number}, {contact.display_name}"
                + (" (Entwurf)" if draft else "")
            ),
            filename=f"{letter_date.isoformat()}_mieterhoehung_{contract.number}.pdf",
            links=links,
        )
        if body.ticket_id is not None:
            await letter_records.link_ticket(
                session,
                principal=principal,
                document=document,
                ticket_id=body.ticket_id,
                note=f"Mieterhöhungsschreiben auf Briefbogen abgelegt: {document.title}",
            )
        dispatch = None
        if body.dispatch is not None:
            dispatch = await letter_records.record_dispatch(
                session,
                principal=principal,
                document=document,
                contact_id=contact.id,
                record=body.dispatch,
                entity_type="rent_increase_case",
                entity_id=case.id,
            )
        return {
            "case_id": case.id,
            "status": case.status,
            "document_id": document.id,
            "title": document.title,
            "filename": document.filename,
            "contact_id": contact.id,
            "ticket_id": body.ticket_id,
            "draft": draft,
            "placeholders": placeholders,
            "dispatch": letter_records.dispatch_out(dispatch),
            "hinweis": (
                "Das Schreiben ist abgelegt. Der Prozessschritt Versand erfassen bleibt hinter "
                "G3; die Plattform versendet nichts (E-Mail nur über die Mailfreigabe)."
            ),
        }


NEXT = {
    "approve": ({"draft"}, "approved"),
    "send": ({"approved"}, "sent"),
    "consent": ({"sent"}, "consented"),
    "reject": ({"sent"}, "rejected"),
    "apply": ({"consented"}, "applied"),
    "cancel": ({"draft", "approved"}, "cancelled"),
    # Access date only; the status stays (None = keep).
    "receipt": ({"draft", "approved", "sent"}, None),
    # GAK-202: confirmed blocking date on the contract; the status stays ``applied``.
    "set_block": ({"applied"}, None),
}

# GAK-202: payment reason of the new rent line from the basis of the case.
REASON_BY_BASIS = {"index": "index", "graduated": "graduated"}


async def _record_receipt(session: Any, case: RentIncreaseCase, received_on: date) -> None:
    """Store the access date and, only with released rules, the derived deadline hints
    (consent deadline, effective month); the rules stay drafts otherwise (M26-01)."""
    from mhvp.letting.rentlaw import deadlines, released_rules

    case.received_on = received_on
    rules = await released_rules(session)
    if "consent_months" in rules and "effective_month" in rules:
        d = deadlines(received_on, int(rules["consent_months"]), int(rules["effective_month"]))
        case.check = case.check | {
            "consent_until": d["consent_until"].isoformat(),
            "effective_from": d["effective_from"].isoformat(),
        }
        if case.effective_date < d["effective_from"]:
            case.check = case.check | {
                "deadline_flag": "Wirksamkeit liegt vor dem gesetzlichen Beginn."
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
                await _record_receipt(session, case, body.received_on)
        if body.action == "receipt":
            if body.received_on is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Zugangsdatum fehlt.")
            await _record_receipt(session, case, body.received_on)
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
                reason=PaymentReason(REASON_BY_BASIS.get(case.basis, PaymentReason.INCREASE.value)),
                document_id=case.consent_document_id,
            )
            if old.valid_to is not None:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Folgende Mietzeile vorhanden, manuell prüfen."
                )
            await contract_services.add_payment(session, contract, new)
            await session.flush()
            case.new_payment_id = new.id
            # GAK-202: blocking date only as proposal from the tenant switch (AN18-01).
            from mhvp.letting import increase_settings

            proposal = increase_settings.block_proposal(
                await increase_settings.load(session), case.basis, case.effective_date
            )
            case.check = case.check | {"block_proposal": proposal.isoformat() if proposal else None}
        if body.action == "set_block":
            if body.block_until is None or body.block_until < case.effective_date:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Sperrdatum fehlt oder liegt vor der Wirksamkeit der Erhöhung.",
                )
            contract = await session.get(Contract, case.contract_id, with_for_update=True)
            if contract is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            from mhvp.accounting.audit_events import record_change

            before = {"rent_increase_block_until": contract.rent_increase_block_until}
            contract.rent_increase_block_until = body.block_until
            case.check = case.check | {"block_set": body.block_until.isoformat()}
            await record_change(
                session,
                tenant_id=principal.tenant_id,
                actor_user_id=principal.user_id,
                type="contract.updated",
                entity_type="contract",
                entity_id=contract.id,
                before={k: v.isoformat() if v else None for k, v in before.items()},
                after={"rent_increase_block_until": body.block_until.isoformat()},
            )
        new_status = case.status if target is None else target
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"rent_increase.{body.action if target is None else target}",
            entity_type="rent_increase_case",
            entity_id=case.id,
            actor_user_id=principal.user_id,
            payload={"from": case.status, "to": new_status},
        )
        case.status = new_status
        await session.flush()
        return _case_out(case)


VACANCY_STATUS = "^(open|advertised|viewing|rented|renovation|blocked)$"


class VacancyCaseIn(LettingBaseIn):
    status: str | None = Field(default=None, pattern=VACANCY_STATUS)
    responsible_user_id: uuid.UUID | None = None
    follow_up_on: date | None = None
    target_rent: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    monthly_costs: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)


def _per_day(monthly: Decimal, days: int) -> Decimal:
    """Monthly amount as pro rata for ``days`` with 12 months over 365 days."""
    return (monthly * 12 / 365 * days).quantize(CENT, rounding=ROUND_HALF_UP)


def _vacancy_row(
    unit: Any,
    prop: Any,
    case: Any,
    listing: Any,
    since: date | None,
    day: date,
) -> dict[str, Any]:
    days = (day - since).days + 1 if since else None
    target = (case.target_rent if case else None) or (listing.price if listing else None)
    costs = case.monthly_costs if case else None
    return {
        "unit_id": unit.id,
        "property_number": prop.number,
        "unit_number": unit.number,
        "unit_type": unit.unit_type,
        "living_area_sqm": unit.living_area_sqm,
        "vacant_since": since,
        "vacant_days": days,
        "status": case.status if case else "open",
        "responsible_user_id": case.responsible_user_id if case else None,
        "follow_up_on": case.follow_up_on if case else None,
        "follow_up_due": bool(case and case.follow_up_on and case.follow_up_on <= day),
        "target_rent": target,
        "target_rent_source": (
            "vacancy_case" if case and case.target_rent else "listing" if listing else None
        ),
        "monthly_costs": costs,
        # Entgangene Miete und Leerstandskosten: Monatswert x 12 / 365 x Leerstandstage.
        "lost_rent": _per_day(target, days) if target and days else None,
        "vacancy_costs": _per_day(costs, days) if costs and days else None,
        "note": case.note if case else None,
        "listing_id": listing.id if listing else None,
    }


@router.get(
    "/vacancies", summary="Leerstandsliste (Mietobjekte)", dependencies=[Depends(strict_query)]
)
async def vacancies(
    request: Request,
    as_of: date | None = None,
    follow_up_due: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    """Only management type RENTAL (no SEV units of a WEG). Lost rent and vacancy costs are
    pro rata of the recorded monthly values (12 / 365 per day); without a target rent (measure
    or rental listing) they stay empty, nothing is estimated (M26-04)."""
    from sqlalchemy import func

    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import ManagementType, Property, Unit

    day = as_of or local_today()
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
        cases = {c.unit_id: c for c in (await session.scalars(select(VacancyCase))).all()}
        listings: dict[uuid.UUID, Listing] = {}
        for lst in (
            await session.scalars(
                select(Listing)
                .where(Listing.kind == "rental", Listing.status != "inactive")
                .order_by(Listing.created_at)
            )
        ).all():
            listings[lst.unit_id] = lst  # newest wins
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
            row = _vacancy_row(unit, prop, cases.get(unit.id), listings.get(unit.id), since, day)
            if follow_up_due and not row["follow_up_due"]:
                continue
            out.append(row)
        return out


@router.put("/vacancies/{unit_id}", summary="Leerstandsmaßnahme erfassen oder ändern")
async def put_vacancy(
    unit_id: uuid.UUID,
    body: VacancyCaseIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.properties.models import ManagementType, Property, Unit

    async with tenant_tx(request, principal) as session:
        unit = await session.get(Unit, unit_id)
        prop = await session.get(Property, unit.property_id) if unit else None
        if unit is None or prop is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if prop.management_type is not ManagementType.RENTAL:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Leerstandsmaßnahmen nur für Mietobjekte."
            )
        if (
            body.responsible_user_id is not None
            and await session.get(User, body.responsible_user_id) is None
        ):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Verantwortlicher unbekannt.")
        case = await session.scalar(select(VacancyCase).where(VacancyCase.unit_id == unit_id))
        if case is None:
            case = VacancyCase(
                tenant_id=principal.tenant_id, created_by=principal.user_id, unit_id=unit_id
            )
            session.add(case)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(case, key, value)
        await session.flush()
        return {
            "unit_id": case.unit_id,
            "status": case.status,
            "responsible_user_id": case.responsible_user_id,
            "follow_up_on": case.follow_up_on,
            "target_rent": case.target_rent,
            "monthly_costs": case.monthly_costs,
            "note": case.note,
        }


@router.post(
    "/vacancies/{unit_id}/listing", status_code=201, summary="Anzeige aus dem Leerstand anlegen"
)
async def vacancy_listing(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Draft rental listing from the unit master data; the target rent of the measure becomes
    the asking rent when recorded. The measure moves to ``advertised`` only if it is still
    ``open``. Publishing stays a separate step."""
    from mhvp.properties.models import ManagementType, Property, Unit

    async with tenant_tx(request, principal) as session:
        unit = await session.get(Unit, unit_id)
        prop = await session.get(Property, unit.property_id) if unit else None
        if unit is None or prop is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if prop.management_type is not ManagementType.RENTAL:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nur für Mietobjekte.")
        case = await session.scalar(select(VacancyCase).where(VacancyCase.unit_id == unit_id))
        price = case.target_rent if case else None
    listing = await create_listing(
        ListingIn(unit_id=unit_id, kind="rental", price=price), request, principal
    )
    async with tenant_tx(request, principal) as session:
        case = await session.scalar(select(VacancyCase).where(VacancyCase.unit_id == unit_id))
        if case is None:
            session.add(
                VacancyCase(
                    tenant_id=principal.tenant_id,
                    created_by=principal.user_id,
                    unit_id=unit_id,
                    status="advertised",
                )
            )
        elif case.status == "open":
            case.status = "advertised"
    return listing


@router.get("/units/{unit_id}/expose", summary="Exposé-Entwurf aus Stammdaten")
async def expose(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Draft only from master data; no personal data of former tenants, no invented text.
    Energy certificate data come from the unit's building (A63, 4.3), the asking rent from
    the newest rental listing of the unit; both are reported as missing when not recorded.
    Whether the listed values satisfy the Pflichtangaben of an advertisement stays open
    (M26-03)."""
    from mhvp.properties.models import Building, Property, Unit

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
        energy = openimmo.expose_energy_fields(await session.get(Building, unit.building_id))
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


def _eur_text(value: Any) -> str:
    if value is None:
        return "auf Anfrage"
    return f"{Decimal(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


EXPOSE_MAX_IMAGES = 8


@router.post(
    "/units/{unit_id}/expose/pdf",
    status_code=201,
    summary="Exposé als PDF auf dem Briefbogen im DMS ablegen",
)
async def expose_pdf(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Exposé from master data and the newest rental listing (title and description of the
    advertisement), filed as generated document of unit, property and listing. Fields missing
    in the master data are listed in the document as open; nothing is invented. Image
    documents linked to the listing are embedded (M26-05), at most ``EXPOSE_MAX_IMAGES``."""
    from mhvp.documents import letter_records
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.letters import Letter, LetterTable

    data = await expose(unit_id, request, principal)
    blobs = BlobStore(request.app.state.settings)
    f, energy, rent = data["fields"], data["energy_certificate"], data["asking_rent"]
    async with tenant_tx(request, principal) as session:
        head = await doc_services.letterhead(session, blobs)
        listing = await session.get(Listing, data["listing_id"]) if data["listing_id"] else None
        from mhvp.properties.models import Unit

        unit = await session.get(Unit, unit_id)
        if unit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)

        def cell(value: Any) -> str:
            return "offen" if value in (None, "") else str(value)

        address = (
            " ".join(p for p in (f["street"], f["house_number"]) if p)
            + f", {cell(f['postal_code'])} {cell(f['city'])}"
        )
        tables = {
            "objekt": LetterTable(
                header=["Merkmal", "Angabe"],
                rows=[
                    ["Lage", address],
                    ["Art", cell(f["unit_type"])],
                    ["Zimmer", cell(f["rooms"])],
                    ["Wohnfläche in m²", cell(f["living_area_sqm"])],
                    ["Etage", cell(f["floor"])],
                    ["Letzte Modernisierung", cell(f["last_modernization_year"])],
                ],
                widths=(0.4, 0.6),
            ),
            "miete": LetterTable(
                header=["Kosten", "Betrag"],
                rows=[
                    ["Kaltmiete", _eur_text(rent["net_rent"])],
                    ["Nebenkosten", _eur_text(rent["additional_costs"])],
                    ["Heizkosten", _eur_text(rent["heating_costs"])],
                    ["Kaution", _eur_text(rent["deposit"])],
                ],
                right_aligned=(1,),
                widths=(0.6, 0.4),
            ),
            "energie": LetterTable(
                header=["Energieausweis", "Angabe"],
                rows=[[k, cell(v)] for k, v in energy.items()],
                widths=(0.5, 0.5),
            ),
        }
        body = []
        if listing is not None and listing.description:
            body.append(html.escape(listing.description))
        body += ["[[table:objekt]]", "[[table:miete]]", "[[table:energie]]"]
        if data["missing"]:
            body.append(
                "Offene Angaben vor Veröffentlichung: "
                + html.escape(", ".join(data["missing"]))
                + "."
            )
        expose_images: list[bytes] = []
        if listing is not None:
            found = await _listing_images(session, request, listing.id)
            expose_images = [
                i.data
                for i in found
                if i.mime_type.lower() in ("image/jpeg", "image/jpg", "image/png")
            ][:EXPOSE_MAX_IMAGES]
        today = local_today()
        title = (listing.title if listing and listing.title else None) or str(f["title"])
        letter = Letter(
            recipient_lines=[],
            subject=html.escape(f"Exposé: {title}"),
            body="\n\n".join(body),
            letter_date=today,
            tables=tables,
            closing="",
            draft_notice="ENTWURF, Pflichtangaben vor Veröffentlichung prüfen"
            if data["missing"]
            else None,
            images=expose_images,
        )
        links: list[tuple[str, uuid.UUID]] = [("unit", unit.id), ("property", unit.property_id)]
        if listing is not None:
            links.append(("listing", listing.id))
        document = await letter_records.store_letter(
            session,
            blobs,
            principal=principal,
            head=head,
            letter=letter,
            title=f"Exposé {title}",
            filename=f"{today.isoformat()}_expose_{unit.number}.pdf",
            links=links,
        )
        return {
            "document_id": document.id,
            "title": document.title,
            "filename": document.filename,
            "listing_id": data["listing_id"],
            "missing": data["missing"],
            "draft": bool(data["missing"]),
            "images_embedded": len(expose_images),
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
        "source": p.source,
        "rejection_template_id": p.rejection_template_id,
        "listing_id": p.listing_id,
        "search_profile": p.search_profile,
    }


@router.post("/prospects", status_code=201, summary="Interessent erfassen")
async def create_prospect(
    body: ProspectIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    if body.delete_after <= local_today():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Löschdatum muss in der Zukunft liegen.")
    async with tenant_tx(request, principal) as session:
        data = body.model_dump(exclude={"search_profile"})
        profile = (
            body.search_profile.model_dump(mode="json", exclude_defaults=True)
            if body.search_profile
            else {}
        )
        if body.listing_id is not None:
            listing = await session.get(Listing, body.listing_id)
            if listing is None or listing.unit_id != body.unit_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Die Anzeige gehört nicht zur Einheit."
                )
        row = Prospect(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            search_profile=profile,
            **data,
        )
        session.add(row)
        await session.flush()
        return _prospect_out(row)


_PROSPECT_LIST = ListSpec(  # GA04-05
    filters={
        "status": Prospect.status,
        "listing_id": Prospect.listing_id,
        "contact_id": Prospect.contact_id,
        "source": Prospect.source,
    },
    sort={"created_at": Prospect.created_at, "viewing_at": Prospect.viewing_at},
)


@router.get("/prospects", summary="Interessenten je Einheit", dependencies=[Depends(strict_query)])
async def list_prospects(
    unit_id: uuid.UUID,
    request: Request,
    params: ListParams = Depends(_PROSPECT_LIST.dependency),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = _PROSPECT_LIST.apply(
            select(Prospect).where(Prospect.unit_id == unit_id),
            params,
            (Prospect.created_at, Prospect.id),
        )
        rows = await session.scalars(query)
        return sparse([_prospect_out(p) for p in rows.all()], params, None)  # type: ignore[no-any-return]


@router.patch("/prospects/{prospect_id}", summary="Interessent ändern")
async def patch_prospect(
    prospect_id: uuid.UUID,
    body: ProspectPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Prospect, prospect_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        check_if_match(if_match, row.updated_at)  # GA04-06
        changes = body.model_dump(exclude_none=True, exclude={"search_profile"})
        if body.listing_id is not None:
            listing = await session.get(Listing, body.listing_id)
            if listing is None or listing.unit_id != row.unit_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Die Anzeige gehört nicht zur Einheit."
                )
        for key, value in changes.items():
            setattr(row, key, value)
        if body.search_profile is not None:
            row.search_profile = body.search_profile.model_dump(mode="json", exclude_defaults=True)
        await session.flush()
        await session.flush()
        await session.refresh(row, ["updated_at"])
        response.headers["ETag"] = etag_of(row.updated_at)
        return _prospect_out(row)


def _match(profile: dict[str, Any], listing: Listing) -> dict[str, list[str]]:
    """Compare a search profile with a listing: criteria met, not met, and not checkable
    because the listing or the profile lacks the value."""
    met: list[str] = []
    unmet: list[str] = []
    unknown: list[str] = []

    def compare(key: str, label: str, wish: Any, have: Any, ok: Any) -> None:
        if wish is None:
            return
        if have is None:
            unknown.append(label)
        elif ok(Decimal(str(wish)) if not isinstance(wish, date) else wish, have):
            met.append(label)
        else:
            unmet.append(label)

    compare("max_rent", "Kaltmiete", profile.get("max_rent"), listing.price, lambda w, h: h <= w)
    compare(
        "max_warm_rent",
        "Warmmiete",
        profile.get("max_warm_rent"),
        listing.warm_rent,
        lambda w, h: h <= w,
    )
    compare("min_rooms", "Zimmer", profile.get("min_rooms"), listing.rooms, lambda w, h: h >= w)
    compare(
        "min_area_sqm",
        "Wohnfläche",
        profile.get("min_area_sqm"),
        listing.living_area_sqm,
        lambda w, h: h >= w,
    )
    by = profile.get("move_in_by")
    if by:
        if listing.available_from is None:
            unknown.append("Bezug")
        elif listing.available_from <= date.fromisoformat(by):
            met.append("Bezug")
        else:
            unmet.append("Bezug")
    kinds = profile.get("kinds") or []
    if kinds:
        (met if listing.kind in kinds else unmet).append("Art")
    for feature in profile.get("required_features") or []:
        (met if (listing.features or {}).get(feature) else unmet).append(f"Ausstattung {feature}")
    return {"met": met, "unmet": unmet, "unknown": unknown}


@router.get(
    "/listings/{listing_id}/prospect-matches",
    summary="Interessenten zur Anzeige abgleichen und reihen",
    dependencies=[Depends(strict_query)],
)
async def prospect_matches(
    listing_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    """Candidates: prospects of the same unit, prospects linked to the listing and prospects
    of other units with a search profile (several units per prospect). Ranking: most criteria
    met, then fewest unmet, then earliest inquiry. A proposal for the clerk, no decision."""
    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = (
            await session.scalars(
                select(Prospect).where(
                    Prospect.status.in_(("new", "viewing", "applied")),
                    or_(
                        Prospect.unit_id == listing.unit_id,
                        Prospect.listing_id == listing.id,
                        Prospect.search_profile != {},
                    ),
                )
            )
        ).all()
        out: list[dict[str, Any]] = []
        for p in rows:
            result = _match(p.search_profile or {}, listing)
            out.append(
                {
                    "prospect_id": p.id,
                    "contact_id": p.contact_id,
                    "unit_id": p.unit_id,
                    "status": p.status,
                    "linked": p.listing_id == listing.id or p.unit_id == listing.unit_id,
                    "score": len(result["met"]),
                    "created_at": p.created_at,
                    **result,
                }
            )
        out.sort(key=lambda r: (-r["score"], len(r["unmet"]), r["created_at"]))
        return out


@router.delete("/prospects/{prospect_id}", status_code=204, summary="Interessent löschen")
async def delete_prospect(
    prospect_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Prospect, prospect_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        from mhvp.letting.prospect_erasure import propose_for

        # GAK-201: contact and documents only as deletion proposal (privacy process).
        outcome = await propose_for(session, principal.tenant_id, row, local_today())
        await session.delete(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="prospect.deleted",
            entity_type="prospect",
            entity_id=prospect_id,
            actor_user_id=principal.user_id,
            payload={"contact_erasure": outcome},
        )


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
    from mhvp.properties.models import Building, Property, Unit

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
        "energy": openimmo.building_energy_prefill(await session.get(Building, unit.building_id)),
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
        # A63: energy certificate of the building is copied unless the caller set a status;
        # explicitly given fields win.
        if "energy_status" not in body.model_fields_set:
            for key, value in prefill["energy"].items():
                if key == "energy_status" or key not in body.model_fields_set:
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


_LISTING_LIST = ListSpec(  # GA04-05
    filters={
        "unit_id": Listing.unit_id,
        "publication_status": Listing.publication_status,
        "object_type": Listing.object_type,
    },
    sort={
        "created_at": Listing.created_at,
        "available_from": Listing.available_from,
        "price": Listing.price,
        "title": Listing.title,
    },
)


@router.get("/listings", summary="Anzeigen", dependencies=[Depends(strict_query)])
async def list_listings(
    request: Request,
    kind: str | None = None,
    status: str | None = None,
    property_id: uuid.UUID | None = None,
    q: str | None = None,
    params: ListParams = Depends(_LISTING_LIST.dependency),
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
        query = _LISTING_LIST.apply(query, params, (Listing.created_at.desc(), Listing.id))
        rows = (await session.execute(query.limit(500))).all()
        result = [_listing_out(listing, prop.number, unit.number) for listing, prop, unit in rows]
        return sparse(result, params, None)  # type: ignore[no-any-return]


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
    listing_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        prop = await session.get(Property, listing.property_id)
        unit = await session.get(Unit, listing.unit_id)
        response.headers["ETag"] = etag_of(listing.updated_at)  # GA04-06
        return _listing_out(listing, prop.number if prop else None, unit.number if unit else None)


@router.patch("/listings/{listing_id}", summary="Anzeige ändern")
async def patch_listing(
    listing_id: uuid.UUID,
    body: ListingPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id, with_for_update=True)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        check_if_match(if_match, listing.updated_at)  # GA04-06
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
                # AN19 (GAK-208): sale listings only with the tenant switch (AN19-02).
                from mhvp.letting.sale_scope import ensure_sale_allowed

                await ensure_sale_allowed(session, listing.kind)
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
        await session.flush()
        await session.refresh(listing, ["updated_at"])
        response.headers["ETag"] = etag_of(listing.updated_at)
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
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="listing.deleted",
            entity_type="listing",
            entity_id=listing_id,
            actor_user_id=principal.user_id,
            payload={},
        )


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


@router.get(
    "/listings/{listing_id}/images",
    summary="Bilder einer Anzeige",
    dependencies=[Depends(strict_query)],
)
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
        await document_services.store_document(
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
            event_payload={"listing_id": listing_id},
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


# Prospect viewing appointments (Besichtigungstermine) ------------------------------------


def _viewing_out(v: ProspectViewing) -> dict[str, Any]:
    return {
        "id": v.id,
        "prospect_id": v.prospect_id,
        "scheduled_at": v.scheduled_at,
        "status": v.status,
        "location": v.location,
        "note": v.note,
    }


@router.post(
    "/prospects/{prospect_id}/viewings", status_code=201, summary="Besichtigungstermin anlegen"
)
async def create_prospect_viewing(
    prospect_id: uuid.UUID,
    body: ProspectViewingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        prospect = await session.get(Prospect, prospect_id)
        if prospect is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = ProspectViewing(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            prospect_id=prospect_id,
            scheduled_at=body.scheduled_at,
            location=body.location,
            note=body.note,
        )
        session.add(row)
        prospect.viewing_at = body.scheduled_at
        if prospect.status == "new":
            prospect.status = "viewing"
        await session.flush()
        return _viewing_out(row)


@router.get(
    "/prospects/{prospect_id}/viewings",
    summary="Besichtigungstermine je Interessent",
    dependencies=[Depends(strict_query)],
)
async def list_prospect_viewings(
    prospect_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        # AJ23 (GAI-303): an unknown or foreign prospect answers 404, not an empty list.
        if await session.get(Prospect, prospect_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(ProspectViewing)
            .where(ProspectViewing.prospect_id == prospect_id)
            .order_by(ProspectViewing.scheduled_at)
        )
        return [_viewing_out(v) for v in rows.all()]


@router.patch("/prospects/viewings/{viewing_id}", summary="Besichtigungstermin ändern")
async def patch_prospect_viewing(
    viewing_id: uuid.UUID,
    body: ProspectViewingPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ProspectViewing, viewing_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        await session.flush()
        return _viewing_out(row)


# Absage-Textbausteine (rejection templates) -----------------------------------------------


@router.get(
    "/prospects/rejection-templates",
    summary="Absage-Textbausteine",
    dependencies=[Depends(strict_query)],
)
async def get_rejection_templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, str]]:
    return list_templates()


class ProspectRejectIn(LettingBaseIn):
    template_id: str = Field(max_length=32)


@router.post("/prospects/{prospect_id}/reject", summary="Interessent mit Textbaustein absagen")
async def reject_prospect(
    prospect_id: uuid.UUID,
    body: ProspectRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Sets the prospect to `rejected` and returns the chosen text block for a mail draft
    (`mhvp.communication`); this endpoint never sends anything itself (rule 0.1.6)."""

    template = template_by_id(body.template_id)
    if template is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannter Textbaustein.")
    async with tenant_tx(request, principal) as session:
        row = await session.get(Prospect, prospect_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.status = "rejected"
        row.rejection_template_id = body.template_id
        await session.flush()
        out = _prospect_out(row)
        out["rejection_text"] = template["text"]
        return out


# Selbstauskunft (self-disclosure) portal link ----------------------------------------------

PRIVACY_NOTICE = (
    "Ihre Angaben werden ausschließlich zur Prüfung Ihrer Bewerbung um die genannte Wohnung "
    "verwendet und nach Abschluss des Bewerbungsverfahrens gelöscht, sofern kein Mietverhältnis "
    "zustande kommt. Eine Weitergabe an Dritte erfolgt nicht, außer soweit gesetzlich "
    "vorgeschrieben. Sie können Ihre Einwilligung jederzeit für die Zukunft widerrufen."
)


def _self_disclosure_out(link: SelfDisclosureLink, *, portal_url: str | None) -> dict[str, Any]:
    return {
        "id": link.id,
        "prospect_id": link.prospect_id,
        "expires_at": link.expires_at,
        "submitted_at": link.submitted_at,
        "consent_privacy": link.consent_privacy,
        "payload": link.payload,
        "portal_url": portal_url,
        "privacy_notice": PRIVACY_NOTICE,
    }


def _self_disclosure_token_digest(token: str) -> str:
    """S16-03: the link token is stored only as sha256 digest (it is the sole credential of
    the portal form). Legacy rows written before 1.50.x hold the plain token and still match
    through ``_self_disclosure_token_match``."""
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()


def _self_disclosure_token_match(token: str) -> Any:
    return SelfDisclosureLink.token.in_([_self_disclosure_token_digest(token), token])


def _self_disclosure_portal_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/portal/selbstauskunft/{token}"


@router.post(
    "/prospects/{prospect_id}/self-disclosure-link",
    status_code=201,
    summary="Selbstauskunft-Link erzeugen",
)
async def create_self_disclosure_link(
    prospect_id: uuid.UUID,
    body: SelfDisclosureLinkIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        prospect = await session.get(Prospect, prospect_id)
        if prospect is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        token = f"{principal.tenant_id.hex}.{secrets.token_urlsafe(24)}"
        link = SelfDisclosureLink(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            prospect_id=prospect_id,
            token=_self_disclosure_token_digest(token),
            expires_at=datetime.now(UTC) + timedelta(days=body.valid_days),
        )
        session.add(link)
        await session.flush()
        return _self_disclosure_out(link, portal_url=_self_disclosure_portal_url(request, token))


@router.get(
    "/prospects/{prospect_id}/self-disclosure-links",
    summary="Selbstauskunft-Links je Interessent",
    dependencies=[Depends(strict_query)],
)
async def list_self_disclosure_links(
    prospect_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        # AJ23 (GAI-303): an unknown or foreign prospect answers 404, not an empty list.
        if await session.get(Prospect, prospect_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(SelfDisclosureLink)
            .where(SelfDisclosureLink.prospect_id == prospect_id)
            .order_by(SelfDisclosureLink.created_at.desc())
        )
        return [_self_disclosure_out(link, portal_url=None) for link in rows.all()]


@router.get(
    "/self-disclosure/{token}",
    summary="Selbstauskunft-Formular lesen (Portal, ohne Anmeldung)",
)
async def read_self_disclosure(token: str, request: Request) -> dict[str, Any]:
    tenant_hex = token.split(".", 1)[0] if "." in token else ""
    try:
        tenant_id = uuid.UUID(hex=tenant_hex)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND) from exc
    from mhvp.core.auth.principal import sessions
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(sessions(request), tenant_id) as session:
        link = await session.scalar(
            select(SelfDisclosureLink).where(_self_disclosure_token_match(token))
        )
        if link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if link.expires_at < datetime.now(UTC):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Der Link ist abgelaufen.")
        return _self_disclosure_out(link, portal_url=None)


@router.post(
    "/self-disclosure/{token}",
    summary="Selbstauskunft absenden (Portal, ohne Anmeldung)",
)
async def submit_self_disclosure(
    token: str, body: SelfDisclosureSubmitIn, request: Request
) -> dict[str, Any]:
    if not body.consent_privacy:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Ohne Bestätigung des Datenschutzhinweises kann die Selbstauskunft nicht "
            "übermittelt werden.",
        )
    tenant_hex = token.split(".", 1)[0] if "." in token else ""
    try:
        tenant_id = uuid.UUID(hex=tenant_hex)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND) from exc
    from mhvp.core.auth.principal import sessions
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(sessions(request), tenant_id) as session:
        link = await session.scalar(
            select(SelfDisclosureLink).where(_self_disclosure_token_match(token))
        )
        if link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if link.expires_at < datetime.now(UTC):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Der Link ist abgelaufen.")
        if link.submitted_at is not None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Selbstauskunft wurde bereits übermittelt."
            )
        link.consent_privacy = True
        link.payload = body.payload
        link.submitted_at = datetime.now(UTC)
        await session.flush()
        # GAI-309: record the submission without any of its content.
        await emit(
            session,
            tenant_id=tenant_id,
            type="self_disclosure.submitted",
            entity_type="self_disclosure_link",
            entity_id=link.id,
            actor_user_id=None,
            payload={"prospect_id": str(link.prospect_id)},
        )
        return _self_disclosure_out(link, portal_url=None)


# BrokerProvider (M28-01 stage 3): tenant config, feature flag, sync -------------------------


async def _broker_config(
    session: Any, tenant_id: uuid.UUID, provider: str
) -> BrokerTenantConfig | None:
    result: BrokerTenantConfig | None = await session.scalar(
        select(BrokerTenantConfig).where(
            BrokerTenantConfig.tenant_id == tenant_id, BrokerTenantConfig.provider == provider
        )
    )
    return result


def _broker_config_out(config: BrokerTenantConfig | None, provider: str) -> dict[str, Any]:
    if config is None:
        return {
            "provider": provider,
            "enabled": False,
            "api_key_set": False,
            "base_url": None,
            "last_tested_at": None,
            "last_test_ok": None,
            "last_test_message": None,
            "settings": {},
        }
    return {
        "provider": config.provider,
        "enabled": config.enabled,
        "api_key_set": bool(config.api_key),
        "base_url": config.base_url,
        "last_tested_at": config.last_tested_at,
        "last_test_ok": config.last_test_ok,
        "last_test_message": config.last_test_message,
        "settings": config.settings,
    }


@router.get("/broker/{provider}/config", summary="Makler-Anbindung lesen")
async def get_broker_config(
    provider: str, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        config = await _broker_config(session, principal.tenant_id, provider)
        return _broker_config_out(config, provider)


@router.put("/broker/{provider}/config", summary="Makler-Anbindung einrichten")
async def put_broker_config(
    provider: str,
    body: BrokerConfigIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> dict[str, Any]:
    if provider not in ("flowfact", "propstack", "onoffice"):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannter Anbieter.")
    async with tenant_tx(request, principal) as session:
        config = await _broker_config(session, principal.tenant_id, provider)
        if config is None:
            config = BrokerTenantConfig(tenant_id=principal.tenant_id, provider=provider)
            session.add(config)
        if body.api_key is not None:
            config.api_key = body.api_key
        if body.api_secret is not None:
            config.api_secret = body.api_secret
        if body.base_url is not None:
            config.base_url = body.base_url
        if body.settings:
            config.settings = {**config.settings, **body.settings}
        config.enabled = body.enabled
        if config.enabled and not config.api_key:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Ohne Zugangsdaten kann die Anbindung nicht aktiviert werden.",
            )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="broker_config.updated",
            entity_type="broker_config",
            entity_id=config.id,
            actor_user_id=principal.user_id,
            payload={"provider": provider, "enabled": config.enabled},
        )
        return _broker_config_out(config, provider)


@router.post(
    "/listings/{listing_id}/broker/{provider}/sync",
    summary="Anzeige an den Makler-Provider übergeben",
)
async def sync_listing_to_broker(
    listing_id: uuid.UUID,
    provider: str,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Explicit, operator-triggered handover only (rule 0.1.6, never automatic). Fails with
    `BROKER_NOT_CONFIGURED` while the feature flag is off, `BROKER_DOCUMENTATION_REQUIRED` for
    a provider/operation with no verified endpoint contract, `BROKER_AMBIGUOUS_MATCH` when the
    provider's search-before-create finds more than one match, and `BROKER_UPSTREAM_ERROR` for
    any other rejection by the provider (see `mhvp.letting.broker_provider` module docstring:
    flowfact `create_or_update_listing` is implemented, other operations and providers are
    not)."""
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        listing = await session.get(Listing, listing_id)
        if listing is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        config = await _broker_config(session, principal.tenant_id, provider)
        if config is None or not config.enabled or not config.api_key:
            raise ProblemError(ErrorCodes.BROKER_NOT_CONFIGURED)
        from mhvp.letting.sale_scope import ensure_sale_allowed  # AN19 (GAK-208)

        await ensure_sale_allowed(session, listing.kind)
        prop = await session.get(Property, listing.property_id)
        client = get_provider(provider, api_key=config.api_key, settings=config.settings)
        payload = BrokerListingPayload(
            external_ref=str(listing.external_ref or listing.id),
            title=listing.title,
            kind=listing.kind,
            object_type=listing.object_type,
            price=str(listing.price) if listing.price is not None else None,
            living_area_sqm=(
                str(listing.living_area_sqm) if listing.living_area_sqm is not None else None
            ),
            rooms=str(listing.rooms) if listing.rooms is not None else None,
            status=listing.status,
            street=prop.street if prop else None,
            house_number=prop.house_number if prop else None,
            postal_code=prop.postal_code if prop else None,
            city=prop.city if prop else None,
            country=prop.country if prop else "DE",
        )
        try:
            result = client.create_or_update_listing(payload)
        except DocumentationRequiredError as exc:
            raise ProblemError(ErrorCodes.BROKER_DOCUMENTATION_REQUIRED, detail=str(exc)) from exc
        except BrokerAmbiguousMatchError as exc:
            raise ProblemError(ErrorCodes.BROKER_AMBIGUOUS_MATCH, detail=str(exc)) from exc
        except BrokerUpstreamError as exc:
            raise ProblemError(ErrorCodes.BROKER_UPSTREAM_ERROR, detail=str(exc)) from exc
        listing.publication_ref = result.provider_entity_id
        listing.publication_status = result.status
        listing.published_at = datetime.now(UTC)
        await session.flush()
        return {
            "listing_id": listing.id,
            "provider": provider,
            "provider_entity_id": result.provider_entity_id,
            "status": result.status,
        }


# OpenImmo import (M26-02 supplement): preview/apply, mirrors the FLOW import ----------------


@router.post(
    "/openimmo-import/preview",
    status_code=201,
    summary="OpenImmo-Datei einlesen (Vorschau, keine Übernahme)",
)
async def preview_openimmo_import(
    request: Request,
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    data = await read_limited(file, 20 * 1024 * 1024)
    filename = file.filename or "openimmo.xml"
    async with tenant_tx(request, principal) as session:
        existing = await session.scalars(
            select(Listing.external_ref).where(
                Listing.external_ref.is_not(None), Listing.source == "openimmo_import"
            )
        )
        existing_refs = {r for r in existing.all() if r}
        try:
            proposals = openimmo_import.parse_openimmo_upload(
                data, filename, existing_external_refs=existing_refs
            )
        except openimmo_import.OpenImmoImportError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
        rows = [openimmo_import.proposal_to_row(p) for p in proposals]
        run = OpenImmoImportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            filename=filename,
            row_count=len(rows),
            rows=rows,
        )
        session.add(run)
        await session.flush()
        return {
            "run_id": run.id,
            "filename": run.filename,
            "row_count": run.row_count,
            "rows": run.rows,
        }


class OpenImmoApplyIn(LettingBaseIn):
    property_id: uuid.UUID
    unit_id: uuid.UUID


@router.post(
    "/openimmo-import/{run_id}/rows/{row_id}/apply",
    status_code=201,
    summary="Einzelne Vorschauzeile freigeben und Anzeige anlegen",
)
async def apply_openimmo_import_row(
    run_id: uuid.UUID,
    row_id: str,
    body: OpenImmoApplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """One row at a time, after an operator has matched it to an existing property/unit
    (M28-01: no automatic unit assignment, same open point as the FLOW import). Duplicate
    `external_ref` rows (already imported) are refused."""

    async with tenant_tx(request, principal) as session:
        run = await session.get(OpenImmoImportRun, run_id)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = next((r for r in run.rows if r.get("row_id") == row_id), None)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.get("status") == "applied":
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zeile wurde bereits übernommen.")
        external_ref = row.get("external_ref")
        if external_ref:
            duplicate = await session.scalar(
                select(Listing).where(
                    Listing.external_ref == external_ref, Listing.source == "openimmo_import"
                )
            )
            if duplicate is not None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Diese OpenImmo-ID wurde bereits als Anzeige übernommen.",
                )
        listing = Listing(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=body.property_id,
            unit_id=body.unit_id,
            kind=row.get("kind") or "rental",
            status="draft",
            title=row.get("title") or "OpenImmo-Import",
            price=Decimal(row["price"]) if row.get("price") else None,
            living_area_sqm=(
                Decimal(row["living_area_sqm"]) if row.get("living_area_sqm") else None
            ),
            rooms=Decimal(row["rooms"]) if row.get("rooms") else None,
            object_type=row.get("object_type") or "wohnung",
            external_ref=external_ref,
            source="openimmo_import",
            notes=(
                f"OpenImmo-Import, Kontaktvorschlag: {row.get('contact_proposal')!r} "
                "(kein Kontakt automatisch angelegt, M26-02)."
            ),
        )
        session.add(listing)
        await session.flush()
        row["status"] = "applied"
        row["listing_id"] = str(listing.id)
        flag_modified(run, "rows")
        run.created_count = (run.created_count or 0) + 1
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="listing.openimmo_imported",
            entity_type="listing",
            entity_id=listing.id,
            actor_user_id=principal.user_id,
            payload={"run_id": str(run_id), "external_ref": external_ref},
        )
        return {"listing_id": listing.id, "run_id": run.id}


class LettingIncreaseSettingsIo(BaseModel):
    """Tenant switches of the rent increase process (GAK-202, GAK-203, AN18-01)."""

    model_config = ConfigDict(extra="forbid")
    block_months: dict[str, int] = Field(default_factory=dict)
    proposals: str = Field(default="off", pattern="^(off|draft)$")

    @field_validator("block_months")
    @classmethod
    def _bases(cls, value: dict[str, int]) -> dict[str, int]:
        from mhvp.letting.increase_settings import BASES

        for basis, months in value.items():
            if basis not in BASES or not 0 < months <= 120:
                raise ValueError(f"Ungültige Sperrdauer für {basis}.")
        return value


@router.get(
    "/rent-increase-settings",
    summary="Schalter Mieterhöhung (Sperrdauer, Vorschläge)",
    dependencies=[Depends(strict_query)],
)
async def get_rent_increase_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> LettingIncreaseSettingsIo:
    from mhvp.letting import increase_settings

    async with tenant_tx(request, principal) as session:
        value = await increase_settings.load(session)
    return LettingIncreaseSettingsIo(block_months=value.block_months, proposals=value.proposals)


@router.put("/rent-increase-settings", summary="Schalter Mieterhöhung setzen")
async def put_rent_increase_settings(
    body: LettingIncreaseSettingsIo,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> LettingIncreaseSettingsIo:
    """No legal duration is fixed by the platform: the operator enters the value per basis
    after legal review (AN18-01); without a value no blocking date is proposed."""
    from mhvp.accounting.audit_events import record_change
    from mhvp.letting import increase_settings
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        old = increase_settings.parse(row.sources)
        new = increase_settings.IncreaseSettings(dict(body.block_months), body.proposals)
        row.sources = increase_settings.store(row.sources, new)
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            type="tenant_settings.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            before={"block_months": old.block_months, "proposals": old.proposals},
            after={"block_months": new.block_months, "proposals": new.proposals},
        )
    return body


# AN19 (GAK-208): tenant switch for sale listings (default off, question AN19-02) -----------


class SaleMarketingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class SaleMarketingOut(BaseModel):
    enabled: bool
    switch: str
    open_question: str = "AN19-02"


@router.get(
    "/settings/sale-marketing",
    summary="Schalter Verkaufsinserate (Standard aus)",
    response_model=SaleMarketingOut,
)
async def get_sale_marketing(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.letting import sale_scope

    async with tenant_tx(request, principal) as session:
        return {"enabled": await sale_scope.is_enabled(session), "switch": sale_scope.SWITCH_KEY}


@router.put(
    "/settings/sale-marketing",
    summary="Schalter Verkaufsinserate setzen",
    response_model=SaleMarketingOut,
)
async def put_sale_marketing(
    body: SaleMarketingIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> dict[str, Any]:
    from mhvp.letting import sale_scope

    async with tenant_tx(request, principal) as session:
        before = await sale_scope.set_enabled(session, body.enabled)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="tenant_settings.sale_marketing_changed",
            entity_type="tenant_settings",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            payload={"from": before, "to": body.enabled},
        )
        return {"enabled": body.enabled, "switch": sale_scope.SWITCH_KEY}
