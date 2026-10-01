"""Tenant and platform administration additions of package AA17 (GA01-07, 08, 10, 12).

* ``/tenant/delivery-default``: default delivery channel of the tenant (JSON ``sources``).
* ``/tenant/number-formats``: number circle formats per tenant, with preview (technical
  preparation, defaults as before, invoice scope locked, see ``mhvp.core.number_format``).
* ``/platform/tenants/{id}/domains`` and ``PATCH /platform/tenants/{id}``: customer domains
  (CNAME) and tenant status.
* ``/platform/oidc-clients``: OIDC relying parties (list, create, rotate secret, activate).
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mhvp.core.auth import oidc_clients
from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    require_permission,
    require_platform_admin,
    sessions,
    tenant_tx,
)
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.events import diff, emit
from mhvp.core.listparams import strict_query
from mhvp.core.logging import get_logger
from mhvp.core.number_format import (
    DEFAULT_FORMATS,
    INVOICE_FORMAT_RELEASED,
    LOCKED_SCOPES,
    SCOPES,
    SOURCES_KEY,
    NumberFormat,
    effective_formats,
    preview,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import (
    OidcClient,
    PlatformAuditEvent,
    Tenant,
    TenantDomain,
    TenantSettings,
    TenantStatus,
)

router = APIRouter(tags=["Mandant"])
_log = get_logger(__name__)
READ = require_permission("tenant_settings:read")
UPDATE = require_permission("tenant_settings:update")
DELIVERY_CHANNELS = ("post", "email", "portal")
HOST_PATTERN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


async def _settings_row(session: Any) -> TenantSettings:
    row = await session.scalar(select(TenantSettings).with_for_update())
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row  # type: ignore[no-any-return]


async def _save_source(
    session: Any, principal: TenantPrincipal, row: TenantSettings, key: str, value: Any
) -> None:
    before = (row.sources or {}).get(key)
    row.sources = {**(row.sources or {}), key: value}
    row.version += 1
    row.updated_by = principal.user_id
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="tenant_settings.updated",
        entity_type="tenant_settings",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"fields": [key]},
        changes=diff({key: before}, {key: value}),
    )


# Delivery channel (GA01-08) ---------------------------------------------------------------


class DeliveryDefaultOut(BaseModel):
    default_delivery_channel: Literal["post", "email", "portal"]


class DeliveryDefaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_delivery_channel: Literal["post", "email", "portal"]


@router.get("/tenant/delivery-default", summary="Standard-Zustellweg")
async def get_delivery_default(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> DeliveryDefaultOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        value = (row.sources or {}).get("default_delivery_channel")
        return DeliveryDefaultOut(
            default_delivery_channel=value if value in DELIVERY_CHANNELS else "post"
        )


@router.put("/tenant/delivery-default", summary="Standard-Zustellweg setzen")
async def put_delivery_default(
    body: DeliveryDefaultIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> DeliveryDefaultOut:
    async with tenant_tx(request, principal) as session:
        row = await _settings_row(session)
        await _save_source(
            session, principal, row, "default_delivery_channel", body.default_delivery_channel
        )
        return DeliveryDefaultOut(default_delivery_channel=body.default_delivery_channel)


# Number formats (GA01-07) -----------------------------------------------------------------


class NumberFormatEntryOut(BaseModel):
    scope: str
    prefix: str
    digits: int
    start: int
    year_based: bool
    locked: bool
    is_default: bool
    preview: list[str]


class NumberFormatsOut(BaseModel):
    formats: list[NumberFormatEntryOut]


class NumberFormatsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formats: dict[str, NumberFormat]


class NumberFormatPreviewIn(NumberFormat):
    scope: str = Field(pattern=r"^(property|contract|document|ticket|invoice)$")


def _formats_out(sources: dict[str, Any] | None) -> NumberFormatsOut:
    effective = effective_formats(sources)
    return NumberFormatsOut(
        formats=[
            NumberFormatEntryOut(
                scope=scope,
                **effective[scope].model_dump(),
                locked=scope in LOCKED_SCOPES and not INVOICE_FORMAT_RELEASED,
                is_default=effective[scope] == DEFAULT_FORMATS[scope],
                preview=preview(effective[scope], datetime.now(UTC).date()),
            )
            for scope in SCOPES
        ]
    )


@router.get("/tenant/number-formats", summary="Nummernkreise des Mandanten")
async def get_number_formats(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> NumberFormatsOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _formats_out(row.sources)


@router.put("/tenant/number-formats", summary="Nummernkreise des Mandanten setzen")
async def put_number_formats(
    body: NumberFormatsIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> NumberFormatsOut:
    unknown = sorted(set(body.formats) - set(SCOPES))
    if unknown:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannter Nummernkreis: {unknown[0]}.")
    async with tenant_tx(request, principal) as session:
        row = await _settings_row(session)
        current = effective_formats(row.sources)
        for scope, fmt in body.formats.items():
            if scope in LOCKED_SCOPES and not INVOICE_FORMAT_RELEASED and fmt != current[scope]:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Der Rechnungsnummernkreis ist bis zur Freigabe durch den "
                    "Steuerberater gesperrt.",
                )
        stored = {
            scope: fmt.model_dump()
            for scope, fmt in {**current, **body.formats}.items()
            if fmt != DEFAULT_FORMATS[scope]
        }
        await _save_source(session, principal, row, SOURCES_KEY, stored)
        return _formats_out(row.sources)


@router.post("/tenant/number-formats/preview", summary="Vorschau eines Nummernkreises")
async def preview_number_format(
    body: NumberFormatPreviewIn, principal: TenantPrincipal = Depends(READ)
) -> dict[str, list[str]]:
    fmt = NumberFormat.model_validate(body.model_dump(exclude={"scope"}))
    return {"preview": preview(fmt, datetime.now(UTC).date())}


# Platform audit (AB13) ---------------------------------------------------------------------


def _audit(
    session: Any,
    principal: Principal,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Persist a platform action in the append-only ``platform_audit_event`` (no secrets)."""
    session.add(
        PlatformAuditEvent(
            actor_user_id=principal.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload or {},
        )
    )


class PlatformAuditEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: str
    payload: dict[str, Any]


class PlatformAuditPage(BaseModel):
    items: list[PlatformAuditEventOut]
    total: int
    limit: int
    offset: int


@router.get(
    "/platform/audit-events",
    summary="Plattformaudit auflisten",
    dependencies=[Depends(strict_query)],
)
async def list_platform_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None, max_length=100),
    _: Principal = Depends(require_platform_admin),
) -> PlatformAuditPage:
    async with platform_transaction(sessions(request)) as session:
        stmt = select(PlatformAuditEvent)
        count = select(func.count()).select_from(PlatformAuditEvent)
        if action:
            stmt = stmt.where(PlatformAuditEvent.action == action)
            count = count.where(PlatformAuditEvent.action == action)
        rows = await session.scalars(
            stmt.order_by(PlatformAuditEvent.occurred_at.desc(), PlatformAuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await session.scalar(count) or 0
        return PlatformAuditPage(
            items=[
                PlatformAuditEventOut(
                    id=r.id,
                    occurred_at=r.occurred_at,
                    actor_user_id=r.actor_user_id,
                    action=r.action,
                    target_type=r.target_type,
                    target_id=r.target_id,
                    payload=r.payload,
                )
                for r in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )


# Customer domains and tenant status (GA01-10) ----------------------------------------------


class TenantDomainOut(BaseModel):
    id: uuid.UUID
    host: str
    purpose: str
    cname_hint: str


class TenantDomainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(min_length=4, max_length=253)
    purpose: Literal["portal", "crm", "api"] = "portal"


class TenantStatusPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "suspended"]


def _domain_out(request: Request, row: TenantDomain) -> TenantDomainOut:
    crm = getattr(request.app.state.settings, "web_crm_url", None) or ""
    target = re.sub(r"^https?://", "", crm).split("/")[0].split(":")[0] or "<Plattformhost>"
    return TenantDomainOut(
        id=row.id,
        host=row.host,
        purpose=row.purpose,
        cname_hint=f"CNAME {row.host} -> {target}",
    )


@router.get(
    "/platform/tenants/{tenant_id}/domains",
    summary="Kundendomains des Mandanten",
    dependencies=[Depends(strict_query)],
)
async def list_tenant_domains(
    tenant_id: uuid.UUID, request: Request, _: Principal = Depends(require_platform_admin)
) -> list[TenantDomainOut]:
    async with platform_transaction(sessions(request)) as session:
        if await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(TenantDomain)
            .where(TenantDomain.tenant_id == tenant_id)
            .order_by(TenantDomain.host)
        )
        return [_domain_out(request, r) for r in rows]


@router.post(
    "/platform/tenants/{tenant_id}/domains", status_code=201, summary="Kundendomain hinzufügen"
)
async def add_tenant_domain(
    tenant_id: uuid.UUID,
    body: TenantDomainIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> TenantDomainOut:
    host = body.host.strip().lower().rstrip(".")
    if not HOST_PATTERN.match(host):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ungültiger Hostname.")
    async with platform_transaction(sessions(request)) as session:
        if await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if await session.scalar(select(TenantDomain.id).where(TenantDomain.host == host)):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Hostname ist bereits vergeben.")
        row = TenantDomain(tenant_id=tenant_id, host=host, purpose=body.purpose)
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Hostname ist bereits vergeben."
            ) from None
        _log.warning(
            "tenant_domain_added",
            actor_user_id=str(principal.user_id),
            tenant_id=str(tenant_id),
            host=host,
            purpose=body.purpose,
        )
        _audit(
            session,
            principal,
            "tenant_domain_added",
            "tenant",
            str(tenant_id),
            {"host": host, "purpose": body.purpose},
        )
        return _domain_out(request, row)


@router.delete(
    "/platform/tenants/{tenant_id}/domains/{domain_id}",
    status_code=204,
    summary="Kundendomain entfernen",
)
async def delete_tenant_domain(
    tenant_id: uuid.UUID,
    domain_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> None:
    async with platform_transaction(sessions(request)) as session:
        row = await session.scalar(
            select(TenantDomain).where(
                TenantDomain.id == domain_id, TenantDomain.tenant_id == tenant_id
            )
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        host = row.host
        await session.delete(row)
        _log.warning(
            "tenant_domain_removed",
            actor_user_id=str(principal.user_id),
            tenant_id=str(tenant_id),
            host=host,
        )
        _audit(
            session, principal, "tenant_domain_removed", "tenant", str(tenant_id), {"host": host}
        )


@router.patch("/platform/tenants/{tenant_id}", summary="Mandantenstatus ändern (sperren)")
async def patch_tenant_status(
    tenant_id: uuid.UUID,
    body: TenantStatusPatch,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, str]:
    async with platform_transaction(sessions(request)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        before = tenant.status.value
        tenant.status = TenantStatus(body.status)
        _log.warning(
            "tenant_status_changed",
            actor_user_id=str(principal.user_id),
            tenant_id=str(tenant_id),
            changes=diff({"status": before}, {"status": body.status}),
        )
        _audit(
            session,
            principal,
            "tenant_status_changed",
            "tenant",
            str(tenant_id),
            {"from": before, "to": body.status},
        )
        return {"id": str(tenant.id), "slug": tenant.slug, "status": body.status}


# OIDC clients (GA01-12) -------------------------------------------------------------------


class OidcClientOut(BaseModel):
    client_id: str
    name: str
    redirect_uris: list[str]
    public: bool
    active: bool


class OidcClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    public: bool = False


class OidcClientSecretOut(OidcClientOut):
    client_secret: str | None = Field(description="wird nur einmal angezeigt")


def _client_out(row: OidcClient) -> OidcClientOut:
    return OidcClientOut(
        client_id=row.client_id,
        name=row.name,
        redirect_uris=list(row.redirect_uris),
        public=row.client_secret_hash is None,
        active=row.active,
    )


def _oidc_problem(exc: oidc_clients.OidcClientError) -> ProblemError:
    code = ErrorCodes.CONFLICT if "already exists" in str(exc) else ErrorCodes.VALIDATION
    if "not found" in str(exc):
        code = ErrorCodes.RESOURCE_NOT_FOUND
    return ProblemError(code, detail=str(exc))


@router.get(
    "/platform/oidc-clients", summary="OIDC-Clients auflisten", dependencies=[Depends(strict_query)]
)
async def list_oidc_clients(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> list[OidcClientOut]:
    async with platform_transaction(sessions(request)) as session:
        return [_client_out(r) for r in await oidc_clients.list_clients(session)]


@router.post("/platform/oidc-clients", status_code=201, summary="OIDC-Client anlegen")
async def create_oidc_client(
    body: OidcClientCreate,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> OidcClientSecretOut:
    async with platform_transaction(sessions(request)) as session:
        try:
            secret = await oidc_clients.create_client(
                session,
                client_id=body.client_id,
                name=body.name,
                redirect_uris=body.redirect_uris,
                public=body.public,
            )
        except oidc_clients.OidcClientError as exc:
            raise _oidc_problem(exc) from None
        await session.flush()
        row = await oidc_clients._get(session, body.client_id)
        assert row is not None  # noqa: S101 - inserted above
        _log.warning(
            "oidc_client_created", actor_user_id=str(principal.user_id), client_id=body.client_id
        )
        _audit(
            session,
            principal,
            "oidc_client_created",
            "oidc_client",
            body.client_id,
            {"name": body.name, "redirect_uris": body.redirect_uris, "public": body.public},
        )
        return OidcClientSecretOut(**_client_out(row).model_dump(), client_secret=secret)


@router.post(
    "/platform/oidc-clients/{client_id}/rotate-secret", summary="OIDC-Client-Secret erneuern"
)
async def rotate_oidc_client_secret(
    client_id: str, request: Request, principal: Principal = Depends(require_platform_admin)
) -> OidcClientSecretOut:
    async with platform_transaction(sessions(request)) as session:
        try:
            secret = await oidc_clients.rotate_secret(session, client_id)
        except oidc_clients.OidcClientError as exc:
            raise _oidc_problem(exc) from None
        row = await oidc_clients._get(session, client_id)
        assert row is not None  # noqa: S101 - rotate_secret found it
        _log.warning(
            "oidc_client_secret_rotated", actor_user_id=str(principal.user_id), client_id=client_id
        )
        _audit(session, principal, "oidc_client_secret_rotated", "oidc_client", client_id)
        return OidcClientSecretOut(**_client_out(row).model_dump(), client_secret=secret)


@router.post("/platform/oidc-clients/{client_id}/{action}", summary="OIDC-Client (de)aktivieren")
async def set_oidc_client_active(
    client_id: str,
    action: Literal["activate", "deactivate"],
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> OidcClientOut:
    async with platform_transaction(sessions(request)) as session:
        try:
            await oidc_clients.set_active(session, client_id, action == "activate")
        except oidc_clients.OidcClientError as exc:
            raise _oidc_problem(exc) from None
        row = await oidc_clients._get(session, client_id)
        assert row is not None  # noqa: S101 - set_active found it
        _log.warning(
            f"oidc_client_{action}d", actor_user_id=str(principal.user_id), client_id=client_id
        )
        _audit(session, principal, f"oidc_client_{action}d", "oidc_client", client_id)
        return _client_out(row)
