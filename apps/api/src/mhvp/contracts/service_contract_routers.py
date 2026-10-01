"""Service provider contract endpoints (/api/v1/service-contracts, M9-06).

Rights follow the contract area: read with contracts:read, create with contracts:create,
change with contracts:update, delete with contracts:delete (tenant_admin only, M2-07). The
computed dates are orientation only (``orientation_only`` is always true).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Self

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from mhvp.contacts.models import Contact
from mhvp.contracts.service_contracts import ServiceContract, terms_of
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_property_allowed,
    property_allowed,
    session_allowed_property_ids,
    session_principal,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import Property
from mhvp.workspace.services import local_date

router = APIRouter(tags=["Dienstleisterverträge"])
READ = require_permission("contracts:read")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")
DELETE = require_permission("contracts:delete")

UNIT_PATTERN = "^(days|months)$"


class _Terms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check(self) -> Self:
        starts = getattr(self, "starts_at", None)
        ends = getattr(self, "ends_at", None)
        if starts is not None and ends is not None and ends < starts:
            raise ValueError("Das Vertragsende liegt vor dem Beginn.")
        return self


class ServiceContractIn(_Terms):
    provider_contact_id: uuid.UUID
    property_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    starts_at: date
    ends_at: date | None = None
    notice_period_days: int = Field(ge=0, le=3650)
    notice_period_unit: str = Field(default="months", pattern=UNIT_PATTERN)
    auto_renewal_months: int | None = Field(default=None, ge=1, le=120)
    cancelled_at: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ServiceContractPatch(_Terms):
    provider_contact_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    starts_at: date | None = None
    ends_at: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=3650)
    notice_period_unit: str | None = Field(default=None, pattern=UNIT_PATTERN)
    auto_renewal_months: int | None = Field(default=None, ge=1, le=120)
    cancelled_at: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ServiceContractOut(BaseModel):
    id: uuid.UUID
    provider_contact_id: uuid.UUID
    # Display name of the linked provider contact (review backlog: no raw id in the CRM).
    provider_name: str
    property_id: uuid.UUID | None
    title: str
    starts_at: date
    ends_at: date | None
    notice_period_days: int
    notice_period_unit: str
    auto_renewal_months: int | None
    cancelled_at: date | None
    notes: str | None
    status: str
    next_possible_end: date | None
    latest_notice_date: date | None
    orientation_only: bool = True


def _out(row: ServiceContract, today: date, provider_name: str) -> ServiceContractOut:
    terms = terms_of(row, today)
    return ServiceContractOut(
        id=row.id,
        provider_contact_id=row.provider_contact_id,
        provider_name=provider_name,
        property_id=row.property_id,
        title=row.title,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        notice_period_days=row.notice_period_days,
        notice_period_unit=row.notice_period_unit,
        auto_renewal_months=row.auto_renewal_months,
        cancelled_at=row.cancelled_at,
        notes=row.notes,
        status=terms.status,
        next_possible_end=terms.next_end,
        latest_notice_date=terms.notice_deadline,
    )


def _today() -> date:
    return local_date(datetime.now(UTC))


async def _check_refs(session: Any, contact_id: uuid.UUID, property_id: uuid.UUID | None) -> str:
    """Validate the references and return the provider's display name."""
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Dienstleister ist unbekannt.")
    if property_id is not None and (
        await session.get(Property, property_id) is None
        or not property_allowed(session_principal(session), property_id)  # M2-02/S16-02
    ):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Objekt ist unbekannt.")
    return str(contact.display_name)


async def _provider_name(session: Any, contact_id: uuid.UUID) -> str:
    name = await session.scalar(select(Contact.display_name).where(Contact.id == contact_id))
    return str(name) if name is not None else ""


async def _get(session: Any, contract_id: uuid.UUID) -> ServiceContract:
    row = await session.get(ServiceContract, contract_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    # M2-02/S16-02: a contract without property is visible only to unrestricted members.
    ensure_session_property_allowed(session, row.property_id)
    return row  # type: ignore[no-any-return]


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, entity_id: uuid.UUID
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type="service_contract",
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={},
    )


@router.get("/service-contracts", summary="Dienstleisterverträge")
async def list_service_contracts(
    request: Request,
    property_id: uuid.UUID | None = None,
    provider_contact_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[ServiceContractOut]:
    async with tenant_tx(request, principal) as session:
        # One query with the provider name joined in (no N+1 lookup per row).
        query = select(ServiceContract, Contact.display_name).join(
            Contact, Contact.id == ServiceContract.provider_contact_id
        )
        if property_id is not None:
            query = query.where(ServiceContract.property_id == property_id)
        allowed = session_allowed_property_ids(session)  # M2-02/S16-02
        if allowed is not None:
            query = query.where(ServiceContract.property_id.in_(allowed))
        if provider_contact_id is not None:
            query = query.where(ServiceContract.provider_contact_id == provider_contact_id)
        rows = (
            await session.execute(query.order_by(ServiceContract.title, ServiceContract.id))
        ).all()
        today = _today()
        return [_out(row, today, str(name)) for row, name in rows]


@router.post("/service-contracts", status_code=201, summary="Dienstleistervertrag anlegen")
async def create_service_contract(
    body: ServiceContractIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> ServiceContractOut:
    async with tenant_tx(request, principal) as session:
        provider_name = await _check_refs(session, body.provider_contact_id, body.property_id)
        row = ServiceContract(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        await _event(session, principal, "service_contract.created", row.id)
        return _out(row, _today(), provider_name)


@router.get("/service-contracts/{contract_id}", summary="Dienstleistervertrag lesen")
async def get_service_contract(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> ServiceContractOut:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, contract_id)
        return _out(row, _today(), await _provider_name(session, row.provider_contact_id))


@router.patch("/service-contracts/{contract_id}", summary="Dienstleistervertrag ändern")
async def update_service_contract(
    contract_id: uuid.UUID,
    body: ServiceContractPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> ServiceContractOut:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, contract_id)
        changes = body.model_dump(exclude_unset=True)
        for required in (
            "provider_contact_id",
            "title",
            "starts_at",
            "notice_period_days",
            "notice_period_unit",
        ):
            if required in changes and changes[required] is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail=f"{required} ist erforderlich.")
        for key, value in changes.items():
            setattr(row, key, value)
        if row.ends_at is not None and row.ends_at < row.starts_at:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Das Vertragsende liegt vor dem Beginn."
            )
        provider_name = await _check_refs(session, row.provider_contact_id, row.property_id)
        row.updated_by = principal.user_id
        await session.flush()
        await _event(session, principal, "service_contract.updated", row.id)
        return _out(row, _today(), provider_name)


@router.delete(
    "/service-contracts/{contract_id}", status_code=204, summary="Dienstleistervertrag löschen"
)
async def delete_service_contract(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, contract_id)
        await session.delete(row)
        await session.flush()
        await _event(session, principal, "service_contract.deleted", contract_id)
    return Response(status_code=204)
