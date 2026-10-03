"""Datenschutz API (section 16): Register, Löschprofile, Löschanträge, Verzeichnis-Entwurf."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts import consent_rules
from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.config import Settings
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Tenant
from mhvp.privacy import config_sources, erasure, proposals, register_doc
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
DataType = Literal[
    "contact",
    "portal_account",
    "communication",
    "ticket",
    "other",
    "domain_event",
    "platform_user",
    "bank_raw",
    "ai_run",
    "call_log",
    "webhook_delivery",
    "postal_job",
]
ThirdCountryStatus = Literal["open", "no", "yes"]
ResponsibilityActor = Literal["gdwe", "verwalter", "betreiber"]
ResponsibilityRole = Literal["open", "controller", "joint_controller", "processor", "not_involved"]


class PrivacyRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RegisterKind
    name: str = Field(min_length=1, max_length=200)
    role: (
        Literal["verantwortlicher", "gdwe", "verwalter", "betreiber", "auftragsverarbeiter"] | None
    ) = None
    purpose: str | None = None
    # Items are VARCHAR(100) in the table: longer values answer 422 instead of a database error.
    data_categories: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=50
    )
    data_subjects: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=50
    )
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
    # AE32 (S711-10): maintenance fields, all open unless the operator enters them. Without
    # ``third_country_status`` the status follows ``third_country`` (true: yes, false: open);
    # only an explicit ``no`` records that no third country transfer takes place.
    third_country_status: ThirdCountryStatus | None = None
    third_country_countries: str | None = Field(default=None, max_length=300)
    legal_basis: str | None = Field(default=None, max_length=4000)
    responsibilities: dict[ResponsibilityActor, ResponsibilityRole] | None = None
    responsibility_note: str | None = Field(default=None, max_length=4000)
    processor_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class PrivacyRegisterOut(PrivacyRegisterIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    third_country_status: ThirdCountryStatus
    responsibilities: dict[str, str]  # type: ignore[assignment]
    processor_ids: list[uuid.UUID]
    source_key: str | None = None
    source_detail: str | None = None


class PrivacyConfigSourceOut(BaseModel):
    key: str
    name: str
    service: str
    active: bool
    scope: Literal["tenant", "platform"]
    detail: str
    entry_id: uuid.UUID | None
    # GAE-34: read only display of the consent legal basis (/consent-legal-basis) of the
    # purposes this service serves; the register entry's own ``legal_basis`` text stays the
    # operator's maintenance field.
    consent_purposes: list[str] = Field(default_factory=list)
    consent_basis: dict[str, str] = Field(default_factory=dict)
    legal_basis: str | None = None


class PrivacyConfigSyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_inactive: bool | None = None


class PrivacyConfigSyncOut(BaseModel):
    created: list[PrivacyRegisterOut]
    updated: list[PrivacyRegisterOut]
    skipped_inactive: int


class PrivacyDeletionProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: DataType
    retention_months: int = Field(ge=0, le=1200)
    start_rule: str = Field(min_length=1, max_length=200)
    basis_note: str | None = None
    # AJ12 (GAI-501): nightly deletion proposals, default off; never deletes.
    auto_propose: bool | None = None


class PrivacyDeletionProfileOut(PrivacyDeletionProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    released: bool
    released_at: datetime | None
    auto_propose: bool | None = None


class PrivacyDeletionProposalOut(BaseModel):
    data_type: str
    released: bool
    auto_propose: bool
    retention_months: int
    cutoff: date
    candidates: int | None = None
    note: str | None = None


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


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def _register_values(
    session: AsyncSession, body: PrivacyRegisterIn, entry_id: uuid.UUID | None
) -> dict[str, object]:
    """Column values of a register entry; checks the AE32 maintenance fields."""
    data = body.model_dump()
    status = data.pop("third_country_status") or ("yes" if body.third_country else "open")
    data["third_country_status"] = status
    data["third_country"] = status == "yes"
    roles = {str(k): str(v) for k, v in (data.pop("responsibilities") or {}).items()}
    pids = list(dict.fromkeys(data.pop("processor_ids") or []))
    if body.kind != "processing_activity" and (roles or pids):
        raise ProblemError(
            ErrorCodes.PRIVACY_REGISTER_INVALID,
            detail=(
                "Rollen und Auftragsverarbeiter werden nur bei Verarbeitungstätigkeiten erfasst."
            ),
        )
    if pids:
        found = set(
            await session.scalars(
                select(PrivacyRegisterEntry.id).where(
                    PrivacyRegisterEntry.id.in_(pids),
                    PrivacyRegisterEntry.kind.in_(("processor", "sub_processor")),
                )
            )
        )
        if entry_id in pids or found != set(pids):
            raise ProblemError(
                ErrorCodes.PRIVACY_REGISTER_INVALID,
                detail="Mindestens ein zugeordneter Auftragsverarbeiter ist nicht im Register.",
            )
    data["responsibilities"] = roles
    data["processor_ids"] = pids
    return data


async def _register_rows(session: AsyncSession) -> list[PrivacyRegisterEntry]:
    return list(
        await session.scalars(
            select(PrivacyRegisterEntry).order_by(
                PrivacyRegisterEntry.kind, PrivacyRegisterEntry.name
            )
        )
    )


async def _tenant(session: AsyncSession, principal: TenantPrincipal) -> Tenant | None:
    return await session.get(Tenant, principal.tenant_id)


@router.get(
    "/privacy/register",
    summary="Register der Auftragsverarbeiter und Verarbeitungen",
    dependencies=[Depends(strict_query)],
)
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
        values = await _register_values(session, body, None)
        row = PrivacyRegisterEntry(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **values
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
        for key, value in (await _register_values(session, body, entry_id)).items():
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
        tenant = await _tenant(session, principal)
        rows = await _register_rows(session)
        detected = await config_sources.detect(
            session, _settings(request), tenant.slug if tenant else ""
        )
        text = register_doc.render(tenant.name if tenant else "", rows, local_today(), detected)
        return PrivacyRecordsDraft(
            title="Verzeichnis von Verarbeitungstätigkeiten",
            status="Entwurf",
            review_notice=register_doc.REVIEW_NOTICE,
            markdown=text,
        )


@router.get(
    "/privacy/processing-records/pdf",
    summary="Verarbeitungsverzeichnis als PDF-Entwurf",
    dependencies=[Depends(strict_query)],
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def processing_records_pdf(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        tenant = await _tenant(session, principal)
        rows = await _register_rows(session)
        detected = await config_sources.detect(
            session, _settings(request), tenant.slug if tenant else ""
        )
        today = local_today()
        pdf = register_doc.render_pdf(tenant.name if tenant else "", rows, today, detected)
    filename = f"verarbeitungsverzeichnis-entwurf-{today.isoformat()}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/privacy/register/config-sources",
    summary="Dienstleister laut Konfiguration (Einstellungen und Konnektoren)",
    dependencies=[Depends(strict_query)],
)
async def list_config_sources(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[PrivacyConfigSourceOut]:
    async with tenant_tx(request, principal) as session:
        tenant = await _tenant(session, principal)
        detected = await config_sources.detect(
            session, _settings(request), tenant.slug if tenant else ""
        )
        rows = {e.source_key: e for e in await _register_rows(session) if e.source_key}
        policy = await consent_rules.load_policy(session)
        out: list[PrivacyConfigSourceOut] = []
        for d in detected:
            purposes = config_sources.consent_purposes(d.key)
            entry = rows.get(d.key)
            out.append(
                PrivacyConfigSourceOut(
                    key=d.key,
                    name=d.name,
                    service=d.service,
                    active=d.active,
                    scope="platform" if d.scope == "platform" else "tenant",
                    detail=d.detail_text,
                    entry_id=entry.id if entry else None,
                    consent_purposes=purposes,
                    consent_basis={p: policy.basis_for(p) for p in purposes},
                    legal_basis=entry.legal_basis if entry else None,
                )
            )
        return out


@router.post(
    "/privacy/register/config-sources/sync",
    summary="Erkannte Dienstleister als Registereinträge übernehmen (Pflegefelder bleiben offen)",
)
async def sync_config_sources(
    body: PrivacyConfigSyncIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> PrivacyConfigSyncOut:
    async with tenant_tx(request, principal) as session:
        tenant = await _tenant(session, principal)
        detected = await config_sources.detect(
            session, _settings(request), tenant.slug if tenant else ""
        )
        result = await config_sources.sync(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            sources=detected,
            include_inactive=bool(body.include_inactive),
        )
        for row in result.created:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="privacy.register_created",
                entity_type="privacy_register_entry",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"source_key": row.source_key},
            )
        return PrivacyConfigSyncOut(
            created=[PrivacyRegisterOut.model_validate(r) for r in result.created],
            updated=[PrivacyRegisterOut.model_validate(r) for r in result.updated],
            skipped_inactive=result.skipped_inactive,
        )


@router.get(
    "/privacy/deletion-profiles",
    summary="Löschprofile je Datenart",
    dependencies=[Depends(strict_query)],
)
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
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                **body.model_dump(exclude_none=True),
            )
            session.add(row)
        else:
            for key, value in body.model_dump(exclude={"auto_propose"}).items():
                setattr(row, key, value)
            if body.auto_propose is not None:
                row.auto_propose = body.auto_propose
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


@router.get(
    "/privacy/erasure-requests",
    summary="Löschanträge (Art. 17)",
    dependencies=[Depends(strict_query)],
)
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


@router.get(
    "/privacy/deletion-proposals",
    summary="Löschvorschläge je Datenart (nur Arbeitsliste, löscht nichts)",
    dependencies=[Depends(strict_query)],
)
async def list_deletion_proposals(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[PrivacyDeletionProposalOut]:
    async with tenant_tx(request, principal) as session:
        rows = await proposals.preview(session, local_today())
        return [PrivacyDeletionProposalOut(**r) for r in rows]


@router.post(
    "/privacy/deletion-proposals/run",
    summary="Löschvorschläge jetzt erzeugen (nur Vorschläge, Vier-Augen)",
)
async def run_deletion_proposals(
    request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, object]:
    async with tenant_tx(request, principal) as session:
        return await proposals.run_proposals(session, principal.tenant_id, local_today())


@router.post(
    "/privacy/erasure-requests/{request_id}/accept",
    summary="Löschvorschlag als Antrag übernehmen (erste Person)",
)
async def accept_proposal(
    request_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> PrivacyErasureOut:
    async with tenant_tx(request, principal) as session:
        row = await erasure.accept_proposal(
            session, await _load(session, request_id), principal.user_id
        )
        return PrivacyErasureOut.model_validate(row)


# GAM-401 / GAM-405 (AP13): tenant switches of the erasure, default off (behaviour before AP13).
class PrivacyErasureSettingsOut(BaseModel):
    audit_redaction: bool
    erasure_coupling: bool


class PrivacyErasureSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_redaction: bool | None = None
    erasure_coupling: bool | None = None


@router.get(
    "/privacy/erasure-settings",
    summary="Schalter der Kontaktlöschung lesen (Prüfpfad, Sperrbezüge)",
    dependencies=[Depends(strict_query)],
)
async def get_erasure_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyErasureSettingsOut:
    from mhvp.platform.models import TenantSettings
    from mhvp.privacy import audit_redaction, erasure_coupling

    async with tenant_tx(request, principal) as session:
        sources = await session.scalar(select(TenantSettings.sources))
        return PrivacyErasureSettingsOut(
            audit_redaction=audit_redaction.enabled_from(sources),
            erasure_coupling=erasure_coupling.enabled_from(sources),
        )


@router.put(
    "/privacy/erasure-settings",
    summary="Schalter der Kontaktlöschung setzen (OPEN_QUESTIONS AP13-01, AP13-02)",
)
async def put_erasure_settings(
    body: PrivacyErasureSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> PrivacyErasureSettingsOut:
    """Both questions are open (AP13-01 audit trail without values, AP13-02 references that do
    not block); switching on is the operator's decision. Recorded as an event with the
    previous values."""
    from mhvp.platform.models import TenantSettings
    from mhvp.privacy import audit_redaction, erasure_coupling

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise _nf()
        sources = dict(row.sources or {})
        before = {
            "audit_redaction": audit_redaction.enabled_from(sources),
            "erasure_coupling": erasure_coupling.enabled_from(sources),
        }
        if body.audit_redaction is not None:
            sources[audit_redaction.SWITCH_KEY] = body.audit_redaction
        if body.erasure_coupling is not None:
            sources[erasure_coupling.SWITCH_KEY] = body.erasure_coupling
        row.sources = sources
        row.version += 1
        row.updated_by = principal.user_id
        after = {
            "audit_redaction": audit_redaction.enabled_from(sources),
            "erasure_coupling": erasure_coupling.enabled_from(sources),
        }
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="privacy.erasure_settings_updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": after},
        )
        return PrivacyErasureSettingsOut(**after)
