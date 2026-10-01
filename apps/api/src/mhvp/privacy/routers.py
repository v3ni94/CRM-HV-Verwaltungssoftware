"""Datenschutz API (section 16): Register, Löschprofile, Löschanträge, Verzeichnis-Entwurf."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Tenant
from mhvp.privacy import erasure, register_doc
from mhvp.privacy.models import (
    PrivacyDeletionProfile,
    PrivacyErasureRequest,
    PrivacyRegisterEntry,
)

router = APIRouter(tags=["Datenschutz"])
READ = require_permission("privacy:read")
MANAGE = require_permission("privacy:manage")
APPROVE = require_permission("privacy:approve")

RegisterKind = Literal["processor", "sub_processor", "processing_activity", "responsibility"]
AvvStatus = Literal["none", "requested", "confirmed", "not_required"]
DataType = Literal["contact", "portal_account", "communication", "ticket", "other"]


class PrivacyRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RegisterKind
    name: str = Field(min_length=1, max_length=200)
    role: (
        Literal["verantwortlicher", "gdwe", "verwalter", "betreiber", "auftragsverarbeiter"] | None
    ) = None
    purpose: str | None = None
    data_categories: list[str] = Field(default_factory=list, max_length=50)
    data_subjects: list[str] = Field(default_factory=list, max_length=50)
    recipients: str | None = None
    third_country: bool = False
    third_country_note: str | None = None
    avv_status: AvvStatus = "none"
    avv_confirmed_on: date | None = None
    avv_document_id: uuid.UUID | None = None
    retention_note: str | None = None
    legal_review_status: Literal["open", "reviewed"] = "open"
    legal_reviewed_on: date | None = None
    active: bool = True


class PrivacyRegisterOut(PrivacyRegisterIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class PrivacyDeletionProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: DataType
    retention_months: int = Field(ge=0, le=1200)
    start_rule: str = Field(min_length=1, max_length=200)
    basis_note: str | None = None


class PrivacyDeletionProfileOut(PrivacyDeletionProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    released: bool
    released_at: datetime | None


class PrivacyErasureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID
    received_on: date
    reason: str | None = Field(default=None, max_length=1000)


class PrivacyDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=1000)


class PrivacyErasureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    status: str
    received_on: date
    reason: str | None
    blockers: list[dict[str, object]]
    decided_at: datetime | None
    executed_at: datetime | None
    result: dict[str, object] | None


class PrivacyRecordsDraft(BaseModel):
    title: str
    status: str
    review_notice: str
    markdown: str


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.NOT_FOUND)


@router.get("/privacy/register", summary="Register der Auftragsverarbeiter und Verarbeitungen")
async def list_register(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[PrivacyRegisterOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(PrivacyRegisterEntry).order_by(
                PrivacyRegisterEntry.kind, PrivacyRegisterEntry.name
            )
        )
        return [PrivacyRegisterOut.model_validate(r) for r in rows]


@router.post("/privacy/register", status_code=201, summary="Registereintrag anlegen")
async def create_register(
    body: PrivacyRegisterIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> PrivacyRegisterOut:
    async with tenant_tx(request, principal) as session:
        row = PrivacyRegisterEntry(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="privacy.register_created",
            entity_type="privacy_register_entry",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
        return PrivacyRegisterOut.model_validate(row)


@router.put("/privacy/register/{entry_id}", summary="Registereintrag ändern")
async def update_register(
    entry_id: uuid.UUID,
    body: PrivacyRegisterIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> PrivacyRegisterOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(PrivacyRegisterEntry, entry_id)
        if row is None:
            raise _nf()
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await session.flush()
        return PrivacyRegisterOut.model_validate(row)


@router.get(
    "/privacy/processing-records", summary="Verarbeitungsverzeichnis als Entwurf generieren"
)
async def processing_records(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyRecordsDraft:
    async with tenant_tx(request, principal) as session:
        tenant = await session.get(Tenant, principal.tenant_id)
        rows = list(
            await session.scalars(
                select(PrivacyRegisterEntry).order_by(
                    PrivacyRegisterEntry.kind, PrivacyRegisterEntry.name
                )
            )
        )
        text = register_doc.render(tenant.name if tenant else "", rows, datetime.now(UTC).date())
        return PrivacyRecordsDraft(
            title="Verzeichnis von Verarbeitungstätigkeiten",
            status="Entwurf",
            review_notice=register_doc.REVIEW_NOTICE,
            markdown=text,
        )


@router.get("/privacy/deletion-profiles", summary="Löschprofile je Datenart")
async def list_profiles(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[PrivacyDeletionProfileOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(PrivacyDeletionProfile).order_by(PrivacyDeletionProfile.data_type)
        )
        return [PrivacyDeletionProfileOut.model_validate(r) for r in rows]


@router.put(
    "/privacy/deletion-profiles", summary="Löschprofil anlegen oder ändern (setzt Freigabe zurück)"
)
async def upsert_profile(
    body: PrivacyDeletionProfileIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> PrivacyDeletionProfileOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(PrivacyDeletionProfile).where(PrivacyDeletionProfile.data_type == body.data_type)
        )
        if row is None:
            row = PrivacyDeletionProfile(
                tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
            )
            session.add(row)
        else:
            for key, value in body.model_dump().items():
                setattr(row, key, value)
            row.released, row.released_by, row.released_at = False, None, None
            row.updated_by = principal.user_id
        await session.flush()
        return PrivacyDeletionProfileOut.model_validate(row)


@router.post(
    "/privacy/deletion-profiles/{profile_id}/release", summary="Löschprofil freigeben (Vier-Augen)"
)
async def release_profile(
    profile_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> PrivacyDeletionProfileOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(PrivacyDeletionProfile, profile_id)
        if row is None:
            raise _nf()
        if row.updated_by == principal.user_id or (
            row.updated_by is None and row.created_by == principal.user_id
        ):
            raise ProblemError(ErrorCodes.PRIVACY_FOUR_EYES)
        row.released, row.released_by, row.released_at = True, principal.user_id, datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="privacy.deletion_profile_released",
            entity_type="privacy_deletion_profile",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
        return PrivacyDeletionProfileOut.model_validate(row)


@router.get("/privacy/erasure-requests", summary="Löschanträge (Art. 17)")
async def list_requests(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[PrivacyErasureOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(PrivacyErasureRequest)
            .order_by(PrivacyErasureRequest.created_at.desc())
            .limit(200)
        )
        return [PrivacyErasureOut.model_validate(r) for r in rows]


@router.post(
    "/privacy/erasure-requests", status_code=201, summary="Löschantrag erfassen und Sperren prüfen"
)
async def create_request(
    body: PrivacyErasureIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> PrivacyErasureOut:
    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, body.contact_id) is None:
            raise _nf()
        row = await erasure.create_request(
            session,
            tenant_id=principal.tenant_id,
            contact_id=body.contact_id,
            received_on=body.received_on,
            reason=body.reason,
            user_id=principal.user_id,
        )
        return PrivacyErasureOut.model_validate(row)


async def _load(session: AsyncSession, request_id: uuid.UUID) -> PrivacyErasureRequest:
    # Row lock: two parallel approve/execute calls are serialised and the second one sees the
    # changed status (SECURITY-2026-10-01, Befund 6).
    row = await session.get(PrivacyErasureRequest, request_id, with_for_update=True)
    if row is None:
        raise _nf()
    return row


@router.post("/privacy/erasure-requests/{request_id}/approve", summary="Freigeben (zweite Person)")
async def approve_request(
    request_id: uuid.UUID,
    body: PrivacyDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> PrivacyErasureOut:
    async with tenant_tx(request, principal) as session:
        row = await erasure.approve(
            session, await _load(session, request_id), principal.user_id, body.note
        )
        return PrivacyErasureOut.model_validate(row)


@router.post("/privacy/erasure-requests/{request_id}/reject", summary="Ablehnen (zweite Person)")
async def reject_request(
    request_id: uuid.UUID,
    body: PrivacyDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> PrivacyErasureOut:
    async with tenant_tx(request, principal) as session:
        row = await erasure.reject(
            session, await _load(session, request_id), principal.user_id, body.note
        )
        return PrivacyErasureOut.model_validate(row)


@router.post("/privacy/erasure-requests/{request_id}/execute", summary="Anonymisierung ausführen")
async def execute_request(
    request_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> PrivacyErasureOut:
    async with tenant_tx(request, principal) as session:
        row = await erasure.execute(session, await _load(session, request_id), principal.user_id)
        return PrivacyErasureOut.model_validate(row)
