"""CRM endpoints of the monthly consumption information (rule H03): generated months per
property with missing data and the operator's verification list, the property switch and a
manual run for one month. Reading needs ``accounting:read``, the switch and the run
``properties:update``. The tenant switch lives in ``PATCH /tenant/settings``."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import consumption_info
from mhvp.billing.models import ConsumptionInfo
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import Property

router = APIRouter(tags=["Abrechnung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("properties:update")
P = "/properties/{property_id}/consumption-info"


class ConsumptionInfoSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ConsumptionInfoRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: date = Field(description="Any day of the month to generate (first day is stored).")


async def _property(session: AsyncSession, property_id: uuid.UUID) -> Property:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Objekt nicht gefunden.")
    return prop


def _settings_out(prop: Property, settings_row: TenantSettings | None) -> dict[str, Any]:
    return {
        "property_id": prop.id,
        "enabled": prop.consumption_info_enabled,
        "tenant_enabled": bool(settings_row and settings_row.consumption_info_enabled),
        "notifications_enabled": bool(
            settings_row and settings_row.consumption_info_notifications_enabled
        ),
        "template_verified": bool(settings_row and settings_row.consumption_info_template_verified),
        "rule_version": consumption_info.RULE_VERSION,
    }


@router.get(P, summary="Verbrauchsinformationen des Objekts (Monate, fehlende Daten)")
async def list_consumption_info(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        settings_row = await session.scalar(select(TenantSettings))
        rows = (
            await session.scalars(
                select(ConsumptionInfo)
                .where(ConsumptionInfo.property_id == prop.id)
                .order_by(ConsumptionInfo.month.desc(), ConsumptionInfo.unit_id)
            )
        ).all()
        months: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row.month.isoformat()
            bucket = months.setdefault(
                key, {"month": row.month, "units": 0, "incomplete": 0, "not_stored": 0}
            )
            bucket["units"] += 1
            if any(m in row.missing for m in ("heating_missing", "hot_water_missing")):
                bucket["incomplete"] += 1
            if "document_not_stored" in row.missing:
                bucket["not_stored"] += 1
        return {
            "settings": _settings_out(prop, settings_row),
            "months": list(months.values()),
            "rows": [consumption_info.staff_view(r) for r in rows],
            "to_verify": [
                {
                    "key": k,
                    "label": consumption_info.TO_VERIFY_LABELS[k],
                    "status": "zu verifizieren",
                }
                for k in consumption_info.TO_VERIFY
            ],
        }


@router.put(f"{P}/settings", summary="Objektschalter der Verbrauchsinformation")
async def put_settings(
    property_id: uuid.UUID,
    body: ConsumptionInfoSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        before = prop.consumption_info_enabled
        prop.consumption_info_enabled = body.enabled
        prop.updated_by = principal.user_id
        if before != body.enabled:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="billing.consumption_info_switch_changed",
                entity_type="property",
                entity_id=prop.id,
                actor_user_id=principal.user_id,
                payload={"enabled": body.enabled},
            )
        settings_row = await session.scalar(select(TenantSettings))
        return _settings_out(prop, settings_row)


@router.post(f"{P}/run", summary="Verbrauchsinformation für einen Monat erzeugen (manuell)")
async def run_month(
    property_id: uuid.UUID,
    body: ConsumptionInfoRunIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Generates the missing rows of the month for every unit of the property; stored months
    are skipped (idempotent). Needs both switches (tenant and property)."""
    from mhvp.documents.blobs import BlobStore

    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        settings_row = await session.scalar(select(TenantSettings))
        if settings_row is None or not settings_row.consumption_info_enabled:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Verbrauchsinformation ist für diesen Mandanten nicht eingeschaltet.",
            )
        if not prop.consumption_info_enabled:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Verbrauchsinformation ist für dieses Objekt nicht eingeschaltet.",
            )
        counts = await consumption_info.generate_property(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            prop=prop,
            month=body.month,
            actor=principal.user_id,
            trigger="manual",
            notify_tenants=bool(
                settings_row.consumption_info_notifications_enabled
                and settings_row.consumption_info_template_verified
            ),
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="billing.consumption_info_generated",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            payload={"month": consumption_info.month_start(body.month).isoformat(), **counts},
        )
        return {"month": consumption_info.month_start(body.month), **counts}
