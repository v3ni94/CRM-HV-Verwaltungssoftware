"""Text blocks with release workflow (AA11-01, AA11-02): /document-text-blocks."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import TEXT_BLOCK_CODES, LegalTextBlock
from mhvp.documents.text_blocks import POLICY_KEY, second_person_required

router = APIRouter(prefix="/document-text-blocks", tags=["Dokumente"])
READ = require_permission("documents:read")
CREATE = require_permission("documents:create")
UPDATE = require_permission("documents:update")
APPROVE = require_permission("documents:approve")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_WRITE = require_permission("tenant_settings:update")


class TextBlockCreate(BaseModel):
    code: str = Field(min_length=1, max_length=63)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    source_note: str | None = Field(default=None, max_length=500)


class TextBlockPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    source_note: str | None = Field(default=None, max_length=500)


class TextBlockPolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_second_person: bool
    # Switching the check off needs a reason (recorded in the audit event).
    reason: str | None = Field(default=None, max_length=500)


class TextBlockReject(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _out(r: LegalTextBlock) -> dict[str, Any]:
    return {
        "id": r.id,
        "code": r.code,
        "version": r.version,
        "title": r.title,
        "body": r.body,
        "source_note": r.source_note,
        "status": r.status,
        "created_by": r.created_by,
        "submitted_by": r.submitted_by,
        "submitted_at": r.submitted_at,
        "approved_by": r.approved_by,
        "approved_at": r.approved_at,
        "reject_reason": r.reject_reason,
    }


async def _row(session: Any, block_id: uuid.UUID) -> LegalTextBlock:
    row: LegalTextBlock | None = await session.get(LegalTextBlock, block_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _event(
    session: Any, principal: TenantPrincipal, action: str, row: LegalTextBlock
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"text_block.{action}",
        entity_type="text_block",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"code": row.code, "version": row.version, "status": row.status},
    )


async def _authors(session: Any, row: LegalTextBlock) -> set[uuid.UUID]:
    """Everybody who wrote the text of this version: creator, submitter, last editor and every
    editor recorded in the events (AE40: an editor of the draft must not release it)."""
    from mhvp.core.events import DomainEvent

    editors = await session.scalars(
        select(DomainEvent.actor_user_id).where(
            DomainEvent.entity_type == "text_block",
            DomainEvent.entity_id == row.id,
            DomainEvent.type.in_(("text_block.created", "text_block.updated")),
            DomainEvent.actor_user_id.is_not(None),
        )
    )
    found = {row.created_by, row.submitted_by, row.updated_by, *editors}
    return {u for u in found if u is not None}


def _need_status(row: LegalTextBlock, *allowed: str) -> None:
    if row.status not in allowed:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail=f"Aktion im Status {row.status} nicht möglich."
        )


@router.get("/codes", summary="Textbausteine: Codes und Freigabestand")
async def list_codes(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    _q: None = Depends(strict_query),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(select(LegalTextBlock).where(LegalTextBlock.status == "approved"))
        ).all()
        approved = {r.code: r for r in rows}
    return {
        "items": [
            {
                "code": code,
                "label": label,
                "released": code in approved,
                "approved_version": approved[code].version if code in approved else None,
                "display": None if code in approved else "Text nicht freigegeben",
            }
            for code, label in TEXT_BLOCK_CODES.items()
        ]
    }


@router.get("", summary="Textbausteine", dependencies=[Depends(strict_query)])
async def list_blocks(
    request: Request,
    code: str | None = None,
    status: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        stmt = select(LegalTextBlock).order_by(LegalTextBlock.code, LegalTextBlock.version.desc())
        if code:
            stmt = stmt.where(LegalTextBlock.code == code)
        if status:
            stmt = stmt.where(LegalTextBlock.status == status)
        return {"items": [_out(r) for r in (await session.scalars(stmt)).all()]}


async def _policy_row(session: Any) -> Any:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings).with_for_update())
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get(
    "/policy",
    summary="Textbausteine: Mandantenschalter Zweitpersonprüfung",
    dependencies=[Depends(strict_query)],
)
async def get_policy(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        sources = row.sources if row is not None else None
        raw = (sources or {}).get(POLICY_KEY)
        return {
            "require_second_person": second_person_required(sources),
            "reason": raw.get("reason") if isinstance(raw, dict) else None,
        }


@router.put("/policy", summary="Textbausteine: Zweitpersonprüfung ein oder aus")
async def put_policy(
    body: TextBlockPolicyIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> dict[str, Any]:
    """Default on. Switching off needs a reason of at least 10 characters; the release itself
    stays an explicit step by a user with ``documents:approve`` and is audited."""
    reason = (body.reason or "").strip()
    if not body.require_second_person and len(reason) < 10:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Für das Abschalten der Zweitpersonprüfung ist eine Begründung erforderlich.",
        )
    async with tenant_tx(request, principal) as session:
        row = await _policy_row(session)
        before = second_person_required(row.sources)
        row.sources = {
            **(row.sources or {}),
            POLICY_KEY: {
                "require_second_person": body.require_second_person,
                "reason": None if body.require_second_person else reason,
            },
        }
        row.version += 1
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="text_block.policy_updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "before": before,
                "after": body.require_second_person,
                "reason": None if body.require_second_person else reason,
            },
        )
        await session.flush()
        return {
            "require_second_person": body.require_second_person,
            "reason": None if body.require_second_person else reason,
        }


@router.get("/{block_id}", summary="Textbaustein")
async def get_block(
    block_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _row(session, block_id))


@router.post("", status_code=201, summary="Neue Version eines Textbausteins als Entwurf")
async def create_block(
    body: TextBlockCreate, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    if body.code not in TEXT_BLOCK_CODES:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannter Textbaustein-Code.")
    async with tenant_tx(request, principal) as session:
        latest = await session.scalar(
            select(func.max(LegalTextBlock.version)).where(LegalTextBlock.code == body.code)
        )
        row = LegalTextBlock(
            tenant_id=principal.tenant_id,
            code=body.code,
            version=(latest or 0) + 1,
            title=body.title,
            body=body.body,
            source_note=body.source_note,
            status="draft",
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await _event(session, principal, "created", row)
        return _out(row)


@router.patch("/{block_id}", summary="Entwurf bearbeiten")
async def patch_block(
    block_id: uuid.UUID,
    body: TextBlockPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, block_id)
        _need_status(row, "draft")
        for field, value in body.model_dump(exclude_unset=True).items():
            if value is not None or field == "source_note":
                setattr(row, field, value)
        row.updated_by = principal.user_id
        await _event(session, principal, "updated", row)
        return _out(row)


@router.post("/{block_id}/submit", summary="Zur Freigabe einreichen")
async def submit_block(
    block_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, block_id)
        _need_status(row, "draft")
        row.status, row.reject_reason = "submitted", None
        row.submitted_by, row.submitted_at = principal.user_id, datetime.now(UTC)
        await _event(session, principal, "submitted", row)
        return _out(row)


@router.post("/{block_id}/approve", summary="Freigeben (zweite Person)")
async def approve_block(
    block_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Four eyes (tenant switch require_second_person, default on): neither the author nor the
    submitter may release (Produktschutz). The
    previously approved version of the code becomes ``retired``."""
    async with tenant_tx(request, principal) as session:
        row = await _row(session, block_id)
        _need_status(row, "submitted")
        from mhvp.platform.models import TenantSettings

        sources = await session.scalar(select(TenantSettings.sources))
        second_person = second_person_required(sources)
        if principal.user_id is None:
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        if second_person and principal.user_id in await _authors(session, row):
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        for old in (
            await session.scalars(
                select(LegalTextBlock).where(
                    LegalTextBlock.code == row.code, LegalTextBlock.status == "approved"
                )
            )
        ).all():
            old.status = "retired"
        await session.flush()
        row.status = "approved"
        row.approved_by, row.approved_at = principal.user_id, datetime.now(UTC)
        await _event(session, principal, "approved", row)
        if not second_person:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="text_block.approved_without_second_person",
                entity_type="text_block",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"code": row.code, "version": row.version},
            )
        from mhvp.platform.legal_texts import follow_terms_version

        await follow_terms_version(session, row, principal)
        return _out(row)


@router.post("/{block_id}/reject", summary="Zurück in den Entwurf")
async def reject_block(
    block_id: uuid.UUID,
    body: TextBlockReject,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, block_id)
        _need_status(row, "submitted")
        row.status, row.reject_reason = "draft", body.reason
        await _event(session, principal, "rejected", row)
        return _out(row)


@router.post("/{block_id}/retire", summary="Freigabe zurückziehen")
async def retire_block(
    block_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, block_id)
        _need_status(row, "approved")
        row.status = "retired"
        await _event(session, principal, "retired", row)
        return _out(row)
