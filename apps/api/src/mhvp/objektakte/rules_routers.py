"""M35 Stufe 3 part 5 (Regeln-Einstellungsseite): CRUD for `ObjektakteClassificationRule`
(list, create, edit, activate/deactivate). The rule stage itself
(`mhvp.objektakte.classification.classify_document`) only reads active rules; this router is
how a tenant maintains them. Permissions (M35 Stufe 4, docs/rules/M35-03.md):
`objektakte:read` for the list, `objektakte:approve` for create/edit (rule maintenance is
configuration, not review work), `objektakte:delete` for delete (docs/rules/M2-07.md, tenant
admin only)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import DocumentCategory
from mhvp.objektakte.models import ClassificationPatternType, ObjektakteClassificationRule

router = APIRouter(prefix="/objektakte/classification-rules", tags=["objektakte-rules"])
READ = require_permission("objektakte:read")
MANAGE = require_permission("objektakte:approve")
DELETE = require_permission("objektakte:delete")


def _out(row: ObjektakteClassificationRule) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "pattern_type": row.pattern_type.value,
        "pattern_value": row.pattern_value,
        "target_category_id": (str(row.target_category_id) if row.target_category_id else None),
        "target_document_type": row.target_document_type,
        "priority": row.priority,
        "active": row.active,
        "confidence": float(row.confidence),
    }


@router.get("", summary="Klassifikationsregeln auflisten")
async def list_rules(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        stmt = select(ObjektakteClassificationRule).order_by(
            ObjektakteClassificationRule.priority.desc()
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [_out(r) for r in rows]


class ClassificationRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pattern_type: ClassificationPatternType
    pattern_value: str = Field(min_length=1, max_length=1000)
    target_category_id: uuid.UUID | None = None
    target_document_type: str | None = None
    priority: int = 100
    active: bool = True
    confidence: float = Field(default=0.8, ge=0, le=1)


class RulePatch(BaseModel):
    name: str | None = None
    pattern_type: ClassificationPatternType | None = None
    pattern_value: str | None = None
    target_category_id: uuid.UUID | None = None
    target_document_type: str | None = None
    priority: int | None = None
    active: bool | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


@router.post("", status_code=201, summary="Klassifikationsregel anlegen")
async def create_rule(
    body: ClassificationRuleIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        if body.target_category_id is not None:
            category = await session.get(DocumentCategory, body.target_category_id)
            if category is None:
                raise ProblemError(ErrorCodes.NOT_FOUND, detail="Dokumentkategorie nicht gefunden.")
        row = ObjektakteClassificationRule(
            tenant_id=principal.tenant_id,
            name=body.name,
            pattern_type=body.pattern_type,
            pattern_value=body.pattern_value,
            target_category_id=body.target_category_id,
            target_document_type=body.target_document_type,
            priority=body.priority,
            active=body.active,
            confidence=body.confidence,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _out(row)


@router.patch("/{rule_id}", summary="Klassifikationsregel ändern oder aktivieren/deaktivieren")
async def update_rule(
    rule_id: uuid.UUID,
    body: RulePatch,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ObjektakteClassificationRule, rule_id)
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        changes = body.model_dump(exclude_unset=True)
        if "target_category_id" in changes and changes["target_category_id"] is not None:
            category = await session.get(DocumentCategory, changes["target_category_id"])
            if category is None:
                raise ProblemError(ErrorCodes.NOT_FOUND, detail="Dokumentkategorie nicht gefunden.")
        for key, value in changes.items():
            setattr(row, key, value)
        await session.flush()
        await session.refresh(row)
        return _out(row)


@router.delete("/{rule_id}", status_code=204, summary="Klassifikationsregel löschen")
async def delete_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ObjektakteClassificationRule, rule_id)
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await session.delete(row)
