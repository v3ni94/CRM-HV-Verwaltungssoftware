"""Draft heating statement endpoints (M17-02): inputs, consumption import, preview per unit,
feed into the operating cost statement, consumption information and the configurable rule
tables (CO2 steps, degree days). Everything is a draft; issuing stays behind G3."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.billing import heating_calc, heating_services
from mhvp.billing.models import HeatingRuleTable, HeatingRuleTableKind, Statement
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.problems import ErrorCodes, ProblemError

# M2-02/S16-02: statements outside the membership's property assignment answer 404.
STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
router = APIRouter(tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
H = "/statements/{statement_id}/heating"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HeatingSettingsIn(_In):
    consumption_share_percent: int = Field(
        default=heating_calc.CONSUMPTION_SHARE_DEFAULT,
        ge=heating_calc.CONSUMPTION_SHARE_MIN,
        le=heating_calc.CONSUMPTION_SHARE_MAX,
    )
    hot_water_method: str = Field(
        default="flat_percent", pattern="^(flat_percent|measured|formula)$"
    )
    hot_water_flat_percent: Decimal | None = Field(default=None, ge=0, le=100)
    hot_water_volume_m3: Decimal | None = Field(default=None, ge=0)
    hot_water_temperature_c: Decimal | None = Field(default=None, ge=0, le=100)
    hot_water_formula_factor: Decimal | None = Field(default=None, gt=0)
    total_energy_kwh: Decimal | None = Field(default=None, gt=0)
    heating_energy_kwh: Decimal | None = Field(default=None, ge=0)
    hot_water_energy_kwh: Decimal | None = Field(default=None, ge=0)


class Co2InputIn(_In):
    mode: str = Field(default="apply", pattern="^(apply|not_applicable)$")
    building_kind: str = Field(
        default="unknown", pattern="^(residential|non_residential|mixed|self_supply|unknown)$"
    )
    costs: Decimal | None = Field(default=None, ge=0)
    emissions_kg: Decimal | None = Field(default=None, ge=0)
    reference_area_m2: Decimal | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=2000)


class HeatingIn(_In):
    total_costs: Decimal | None = Field(default=None, gt=0)
    settings: HeatingSettingsIn = Field(default_factory=HeatingSettingsIn)
    co2: Co2InputIn = Field(default_factory=Co2InputIn)


class ConsumptionIn(_In):
    heating: Decimal | None = Field(default=None, ge=0)
    heating_kind: str = Field(default="actual", pattern="^(actual|estimated|missing)$")
    hot_water: Decimal | None = Field(default=None, ge=0)
    hot_water_kind: str = Field(default="actual", pattern="^(actual|estimated|missing)$")
    note: str | None = Field(default=None, max_length=500)


class UnitTotalIn(_In):
    heating: Decimal | None = Field(default=None, ge=0)
    hot_water: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class ConsumptionsIn(_In):
    """Manual entry: consumption per occupancy key (see /occupants) and optional unit totals
    for units whose occupancies have no intermediate reading (D25)."""

    consumptions: dict[str, ConsumptionIn] = Field(default_factory=dict)
    unit_totals: dict[uuid.UUID, UnitTotalIn] = Field(default_factory=dict)


class HeatingImportIn(_In):
    heating_kinds: list[str] = Field(default_factory=lambda: ["heating"])
    hot_water_kinds: list[str] = Field(default_factory=lambda: ["hot_water"])


class RuleTableIn(_In):
    kind: HeatingRuleTableKind
    valid_from: date
    rows: Any
    source: str = Field(min_length=3, max_length=2000)
    review_status: str = Field(default="zu_pruefen", pattern="^(zu_pruefen|freigegeben)$")
    note: str | None = Field(default=None, max_length=2000)


def _out(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "statement_id": row.statement_id,
        "total_costs": row.total_costs,
        "settings": row.settings,
        "co2": row.co2,
        "consumptions": row.consumptions,
        "unit_totals": row.unit_totals,
        "result": row.result,
        "result_hash": row.result_hash,
        "applied_item_id": row.applied_item_id,
        "status": "entwurf",
    }


async def _statement(session: Any, statement_id: uuid.UUID) -> Statement:
    st: Statement | None = await session.get(Statement, statement_id, with_for_update=True)
    if st is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return st


def _draft_only(st: Statement) -> None:
    from mhvp.billing.status import StatementStatus

    if st.status is not StatementStatus.DRAFT:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über eine neue Version änderbar."
        )


@router.get(H, summary="Heizkosten (Entwurf): Eingaben, Verbräuche, Ergebnis")
async def get_heating(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        return _out(row) | {
            "tables": await heating_services.effective_tables(session, st.period_from),
            "occupants": [
                {
                    "key": o.key,
                    "unit_id": o.unit_id,
                    "unit_number": o.unit_number,
                    "from": o.start.isoformat(),
                    "to": o.end.isoformat(),
                    "area": str(o.area),
                    "heating": None if o.heating is None else str(o.heating),
                    "hot_water": None if o.hot_water is None else str(o.hot_water),
                    "heating_kind": o.heating_kind,
                    "hot_water_kind": o.hot_water_kind,
                    "source": o.source,
                    "vacancy": o.is_vacancy,
                }
                for o in await _occupants_or_empty(session, st, row)
            ],
        }


async def _occupants_or_empty(session: Any, st: Statement, row: Any) -> list[Any]:
    try:
        return await heating_services.build_occupants(session, st, row)
    except ProblemError:
        return []


@router.put(H, summary="Heizkosten: Kosten, Einstellungen und CO2-Angaben setzen")
async def put_heating(
    statement_id: uuid.UUID,
    body: HeatingIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        _draft_only(st)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        row.total_costs = body.total_costs
        row.settings = {
            k: (str(v) if isinstance(v, Decimal) else v)
            for k, v in body.settings.model_dump().items()
            if v is not None
        }
        row.co2 = {
            k: (str(v) if isinstance(v, Decimal) else v)
            for k, v in body.co2.model_dump().items()
            if v is not None
        }
        row.result = None
        row.result_hash = None
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.put(f"{H}/consumptions", summary="Heizkosten: Verbräuche manuell erfassen")
async def put_consumptions(
    statement_id: uuid.UUID,
    body: ConsumptionsIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        _draft_only(st)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        merged = dict(row.consumptions)
        for key, c in body.consumptions.items():
            entry = {
                k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in c.model_dump().items()
                if v is not None
            }
            entry["source"] = "manual"
            merged[key] = entry
        totals = dict(row.unit_totals)
        for unit_id, u in body.unit_totals.items():
            totals[str(unit_id)] = {
                k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in u.model_dump().items()
                if v is not None
            } | {"source": "manual"}
        row.consumptions = merged
        row.unit_totals = totals
        row.result = None
        row.result_hash = None
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.post(f"{H}/import-consumptions", summary="Heizkosten: Verbräuche aus dem Messdienst")
async def import_consumptions(
    statement_id: uuid.UUID,
    body: HeatingImportIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        _draft_only(st)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        summary = await heating_services.import_from_metering(
            session,
            st,
            row,
            heating_kinds=tuple(body.heating_kinds),
            hot_water_kinds=tuple(body.hot_water_kinds),
        )
        return _out(row) | {"import": summary}


@router.post(f"{H}/calculate", summary="Heizkosten berechnen (Vorschau je Einheit, Entwurf)")
async def calculate_heating(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        _draft_only(st)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        await heating_services.calculate(session, st, row)
        return _out(row)


@router.post(f"{H}/apply", summary="Heizkosten als Position in die Abrechnung übernehmen")
async def apply_heating(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        item = await heating_services.apply(session, st, row, principal.user_id)
        return _out(row) | {"item": {"id": item.id, "amount": item.amount, "label": item.label}}


@router.get(f"{H}/consumption-info", summary="Verbrauchsinformation je Einheit (Entwurf)")
async def consumption_info(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        row = await heating_services.get_or_create(session, st, principal.user_id)
        return {
            "statement_id": st.id,
            "period_from": st.period_from,
            "period_to": st.period_to,
            "units": await heating_services.consumption_info(session, st, row),
            "process_note": (
                "Bereitstellung nach § 6a HeizkostenV erfolgt bis zum Portalmodul über den "
                "dokumentierten Ersatzprozess (H03); dieser Datensatz ist die Grundlage, kein "
                "Nachweis der Zustellung (D26)."
            ),
        }


@router.get("/billing/heating-rule-tables", summary="Regeltabellen Heizkosten (CO2, Gradtage)")
async def list_rule_tables(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(HeatingRuleTable).order_by(
                    HeatingRuleTable.kind, HeatingRuleTable.valid_from.desc()
                )
            )
        ).all()
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "valid_from": r.valid_from,
                "rows": r.rows,
                "source": r.source,
                "review_status": r.review_status,
                "note": r.note,
            }
            for r in rows
        ]


@router.put(
    "/billing/heating-rule-tables",
    summary="Regeltabelle Heizkosten hinterlegen (Quelle Pflicht, Status zu prüfen)",
)
async def put_rule_table(
    body: RuleTableIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    try:
        if body.kind is HeatingRuleTableKind.CO2_STEPS:
            heating_calc.validate_co2_steps(heating_services.co2_steps_from_rows(body.rows))
        else:
            heating_calc.validate_degree_days(heating_services.degree_days_from_rows(body.rows))
    except heating_calc.HeatingCalcError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(HeatingRuleTable).where(
                HeatingRuleTable.kind == body.kind.value,
                HeatingRuleTable.valid_from == body.valid_from,
            )
        )
        if row is None:
            row = HeatingRuleTable(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                kind=body.kind.value,
                valid_from=body.valid_from,
                rows=body.rows,
                source=body.source,
                review_status=body.review_status,
                note=body.note,
            )
            session.add(row)
        else:
            row.rows = body.rows
            row.source = body.source
            row.review_status = body.review_status
            row.note = body.note
            row.updated_by = principal.user_id
        await session.flush()
        return {"id": row.id, "kind": row.kind, "valid_from": row.valid_from}


# M17-09: metering service import endpoints share this router (no extra registration).
from mhvp.billing.heating_import_routers import router as _import_router  # noqa: E402

router.include_router(_import_router)
