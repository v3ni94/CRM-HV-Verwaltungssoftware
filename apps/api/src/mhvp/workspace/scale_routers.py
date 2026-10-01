"""Scale monitoring API for platform administrators (AE36, AC09-01, ADR 0021).

* ``GET /platform/ops/scale``: current figures, thresholds, triggers reached and the last
  weekly measurements.
* ``PATCH /platform/ops/scale/settings``: thresholds and the alarm switch (proposals of ADR 0021,
  decision AC09-01 open); every change is written to the platform audit.
* ``POST /platform/ops/scale/snapshot``: measures now and stores the measurement of the current
  week (what the weekly job does).

Nothing here rebuilds, moves or deletes data.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.events import diff
from mhvp.core.listparams import strict_query
from mhvp.core.logging import get_logger
from mhvp.platform.models import PlatformAuditEvent
from mhvp.platform.scale_models import PlatformScaleSnapshot
from mhvp.workspace import scale

router = APIRouter(prefix="/platform/ops/scale", tags=["Betrieb"])
_log = get_logger("mhvp.workspace.scale")
HISTORY_WEEKS = 12

NOTE = (
    "Die Schwellen sind Vorschläge aus ADR 0021 (offene Entscheidung AC09-01). Ein erreichter "
    "Auslöser meldet nur: Es wird nichts umgebaut, verschoben oder gelöscht."
)


class OpsScaleSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows_threshold: int | None = Field(default=None, ge=1, le=10**12)
    size_gb_threshold: int | None = Field(default=None, ge=1, le=100_000)
    p95_ms_threshold: int | None = Field(default=None, ge=1, le=600_000)
    p95_deep_ms_threshold: int | None = Field(default=None, ge=1, le=600_000)
    p95_weeks: int | None = Field(default=None, ge=1, le=52)
    restore_seconds_threshold: int | None = Field(default=None, ge=1, le=10**7)
    tenants_review_threshold: int | None = Field(default=None, ge=1, le=100_000)
    alarm_enabled: bool | None = None


def _redis(request: Request) -> Any:
    resources = getattr(request.app.state, "resources", None)
    return getattr(resources, "redis", None)


def _percent(value: float, limit: float) -> float:
    return round(value / limit * 100, 1) if limit else 0.0


def _view(
    setting: Any,
    thresholds: scale.Thresholds,
    current: scale.Measurement,
    triggers: list[scale.Trigger],
    history: list[PlatformScaleSnapshot],
) -> dict[str, Any]:
    limit_bytes = thresholds.size_gb * scale.GIB
    tables = [
        {
            "table": name,
            "rows": stat["rows"],
            "bytes": stat["bytes"],
            "exact": stat["exact"],
            "rows_percent": _percent(stat["rows"], thresholds.rows),
            "size_percent": _percent(stat["bytes"], limit_bytes),
        }
        for name, stat in current.tables.items()
    ]
    latency = [
        {
            "key": key,
            "samples": current.latency[key]["samples"],
            "p95_ms": current.latency[key]["p95_ms"],
            "threshold_ms": thresholds.p95_deep_ms if key in scale.DEEP_KEYS else thresholds.p95_ms,
        }
        for key in scale.LATENCY_KEYS
    ]
    return {
        "settings": scale.settings_out(setting),
        "tables": tables,
        "latency": latency,
        "min_samples": scale.MIN_SAMPLES,
        "deep_offset": scale.DEEP_OFFSET,
        "restore": {
            "seconds": current.restore_seconds,
            "threshold_seconds": thresholds.restore_seconds,
        },
        "tenants": {
            "productive": current.tenants_productive,
            "demo": current.tenants_demo,
            "review_threshold": thresholds.tenants_review,
        },
        "triggers": [t.as_dict() for t in triggers],
        "history": [scale.snapshot_out(r) for r in history],
        "note": NOTE,
    }


async def _history(request: Request) -> list[PlatformScaleSnapshot]:
    async with platform_transaction(sessions(request)) as session:
        rows = await scale.load_history(session, exclude_week=None, limit=HISTORY_WEEKS)
        session.expunge_all()
    return rows


@router.get(
    "",
    summary="Skalierung: Kennzahlen und Auslöser der Jahrespartitionierung",
    dependencies=[Depends(strict_query)],
)
async def get_scale(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    setting, thresholds, current, triggers = await scale.live_view(
        sessions(request), _redis(request)
    )
    return _view(setting, thresholds, current, triggers, await _history(request))


@router.patch("/settings", summary="Skalierung: Schwellen und Alarmschalter ändern")
async def patch_scale_settings(
    body: OpsScaleSettingsPatch,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    async with platform_transaction(sessions(request)) as session:
        row = await scale.get_settings_row(session)
        before = {name: getattr(row, name) for name in changes}
        for name, value in changes.items():
            setattr(row, name, value)
        after = {name: getattr(row, name) for name in changes}
        if before != after:
            row.version += 1
            row.updated_by = principal.user_id
            session.add(
                PlatformAuditEvent(
                    actor_user_id=principal.user_id,
                    action="scale.settings_changed",
                    target_type="scale",
                    target_id="settings",
                    payload={"changes": diff(before, after), "version": row.version},
                )
            )
            await session.flush()
            await session.refresh(row)
            _log.warning(
                "scale_settings_changed",
                actor_user_id=str(principal.user_id),
                changes=diff(before, after),
                version=row.version,
            )
        return scale.settings_out(row)


@router.post("/snapshot", summary="Skalierung: Messung jetzt speichern (laufende Woche)")
async def post_scale_snapshot(
    request: Request, principal: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    result = await scale.snapshot_once(
        sessions(request), _redis(request), source="manual", actor_user_id=principal.user_id
    )
    return {
        "iso_week": result.iso_week,
        "triggers": [t.as_dict() for t in result.triggers],
        "new_triggers": [t.key for t in result.new_triggers],
        "notified": result.notified,
    }
