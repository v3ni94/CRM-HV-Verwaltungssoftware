"""Live mode per integration and tenant (GAL-207, rule INT-LIVE-01, migration 0459).

One switch row per tenant and integration (``integration_live_mode``). No row means today's
behaviour: productive calls allowed, no release gate bound. A tenant may lock the live mode
(``live_allowed=false``) or bind it to a release gate (``required_gate``); which gate a live
integration must be bound to is not decided here (open question AP02-01, Betreiber, G1/G2).

The overview reads the existing environment markers: lexoffice is always the productive
vendor API (host allowlist, GAL-202), LetterXpress has ``PostalSettings.mode`` (test/live) and
finAPI ``FinApiTenantConfig.sandbox``. Enforcement in this package: lexoffice export and
connection test (integrations) and LetterXpress settings and submission (communication).
finAPI is shown only (banking domain, open point of AP02).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import (
    ClosedReleaseGateResolver,
    ReleaseGate,
    ReleaseGateResolver,
    ensure_release_gate_open,
)
from mhvp.integrations.models import IntegrationLiveModeSetting

SWITCH_KEY = "integrations.live_mode"
INTEGRATIONS: tuple[str, ...] = ("lexoffice", "letterxpress", "finapi")
IntegrationName = Literal["lexoffice", "letterxpress", "finapi"]
GateName = Literal["G1", "G2", "G3", "G4", "G5"]

router = APIRouter(prefix="/integrations/live-modes", tags=["Schnittstellen"])
SETTINGS = require_permission("tenant_settings:update")
SETTINGS_READ = require_permission("tenant_settings:read")


class IntegrationLiveModeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    live_allowed: bool
    required_gate: GateName | None = None


class IntegrationLiveModeOut(BaseModel):
    integration: str
    live_allowed: bool
    required_gate: str | None
    # "live", "test" or "not_configured" as read from the integration's own settings.
    environment: str
    configured: bool


async def setting_for(
    session: AsyncSession, tenant_id: uuid.UUID, integration: str
) -> IntegrationLiveModeSetting | None:
    row: IntegrationLiveModeSetting | None = await session.scalar(
        select(IntegrationLiveModeSetting).where(
            IntegrationLiveModeSetting.tenant_id == tenant_id,
            IntegrationLiveModeSetting.integration == integration,
        )
    )
    return row


def resolver_of(request: Request | None) -> ReleaseGateResolver:
    if request is None:
        return ClosedReleaseGateResolver()
    resolver: ReleaseGateResolver = getattr(
        request.app.state, "release_gate_resolver", ClosedReleaseGateResolver()
    )
    return resolver


async def ensure_live_allowed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    integration: str,
    resolver: ReleaseGateResolver,
) -> None:
    """Raise ``INTEGRATION_LIVE_MODE_LOCKED`` unless a productive call is allowed."""
    row = await setting_for(session, tenant_id, integration)
    if row is None:
        return
    if not row.live_allowed:
        raise ProblemError(
            ErrorCodes.INTEGRATION_LIVE_MODE_LOCKED,
            detail=f"Der Live-Betrieb der Schnittstelle {integration} ist gesperrt.",
            extensions={"integration": integration},
        )
    if row.required_gate:
        try:
            await ensure_release_gate_open(ReleaseGate(row.required_gate), tenant_id, resolver)
        except ProblemError as exc:
            raise ProblemError(
                ErrorCodes.INTEGRATION_LIVE_MODE_LOCKED,
                detail=(
                    f"Der Live-Betrieb der Schnittstelle {integration} ist an die "
                    f"Freigabestufe {row.required_gate} gebunden, die nicht geöffnet ist."
                ),
                extensions={"integration": integration, "gate": row.required_gate},
            ) from exc


async def _environments(session: AsyncSession) -> dict[str, tuple[str, bool]]:
    from mhvp.banking.models import FinApiTenantConfig
    from mhvp.communication.models import PostalSettings
    from mhvp.integrations.models import LexofficeTenantConfig

    lex = (await session.scalars(select(LexofficeTenantConfig))).all()
    lex_on = any(c.enabled and c.api_key for c in lex)
    postal = await session.scalar(select(PostalSettings))
    postal_on = postal is not None and postal.provider == "letterxpress"
    fin = await session.scalar(select(FinApiTenantConfig))
    return {
        "lexoffice": ("live" if lex_on else "not_configured", lex_on),
        "letterxpress": (
            (postal.mode if postal is not None and postal_on else "not_configured"),
            postal_on,
        ),
        "finapi": (
            ("test" if fin.sandbox else "live") if fin is not None else "not_configured",
            fin is not None,
        ),
    }


async def _out(session: AsyncSession, tenant_id: uuid.UUID) -> list[IntegrationLiveModeOut]:
    envs = await _environments(session)
    out = []
    for name in INTEGRATIONS:
        row = await setting_for(session, tenant_id, name)
        env, configured = envs[name]
        out.append(
            IntegrationLiveModeOut(
                integration=name,
                live_allowed=row.live_allowed if row else True,
                required_gate=row.required_gate if row else None,
                environment=env,
                configured=configured,
            )
        )
    return out


@router.get("", summary="Live-Betrieb je Schnittstelle", dependencies=[Depends(strict_query)])
async def list_live_modes(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> list[IntegrationLiveModeOut]:
    async with tenant_tx(request, principal) as session:
        return await _out(session, principal.tenant_id)


@router.put("/{integration}", summary="Live-Betrieb einer Schnittstelle festlegen")
async def put_live_mode(
    integration: IntegrationName,
    body: IntegrationLiveModeIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> list[IntegrationLiveModeOut]:
    async with tenant_tx(request, principal) as session:
        row = await setting_for(session, principal.tenant_id, integration)
        before = (row.live_allowed, row.required_gate) if row else (True, None)
        if row is None:
            row = IntegrationLiveModeSetting(
                tenant_id=principal.tenant_id, integration=integration, created_by=principal.user_id
            )
            session.add(row)
        row.live_allowed = body.live_allowed
        row.required_gate = body.required_gate
        row.updated_by = principal.user_id
        await session.flush()
        after = (row.live_allowed, row.required_gate)
        if before != after:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="integration_live_mode.updated",
                entity_type="integration_live_mode",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"integration": integration, "live_allowed": after[0], "gate": after[1]},
            )
        return await _out(session, principal.tenant_id)
