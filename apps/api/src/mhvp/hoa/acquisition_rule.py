"""Allocation variant of the statement result on an owner change per acquisition kind
(AE10 / AA07-01, tenant rule).

Variants: ``manual_release`` (default, standing assumption M24-01 plus four eyes release, the
calculation stays unchanged), ``by_due_date`` (owner on the due date of the item) and
``by_resolution_date`` (owner on the resolution date). The software decides no legal rule: which
variant is correct per acquisition kind stays with legal advice (docs/OPEN_QUESTIONS.md AA07-01,
P01, gate G4). A variant other than the default only changes the proposed debtor of drafts."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import HoaAcquisitionRule
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")

DEFAULT_VARIANT = "manual_release"
VARIANTS = ("manual_release", "by_due_date", "by_resolution_date")
VARIANT_LABELS = {
    "manual_release": "Manuelle Freigabe",
    "by_due_date": "Zuordnung nach Fälligkeit",
    "by_resolution_date": "Zuordnung nach Abrechnungsbeschluss",
}
KINDS = ("purchase", "first_acquisition", "inheritance", "foreclosure", "gift", "other")
KIND_NAMES = {
    "purchase": "Kauf",
    "first_acquisition": "Ersterwerb",
    "inheritance": "Erbfall",
    "foreclosure": "Zwangsversteigerung",
    "gift": "Schenkung",
    "other": "Sonstiger Erwerb",
}
RULE_NOTE = (
    "Konfiguration zur fachlichen Prüfung, keine Rechtsregel. Standard ist die manuelle "
    "Freigabe; die Rechtsfrage je Erwerbsart ist offen (AA07-01, P01)."
)


class HoaAcqRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant: str = Field(min_length=1, max_length=24)
    source_note: str | None = Field(default=None, max_length=2000)


class HoaAcqRuleOut(BaseModel):
    """Response of a rule (GAI-304). ``extra="allow"`` keeps later fields visible."""

    model_config = ConfigDict(extra="allow")
    acquisition_kind: str
    kind_label: str
    variant: str
    variant_label: str
    is_default: bool
    source_note: str | None = None


def pick_day(
    variant: str, *, default_day: date, due_day: date | None, resolution_day: date | None
) -> date:
    """Day whose owner is the proposed debtor. The default keeps the existing day."""
    if variant == "by_due_date" and due_day is not None:
        return due_day
    if variant == "by_resolution_date" and resolution_day is not None:
        return resolution_day
    return default_day


async def resolve_variant(session: AsyncSession, kind: str | None) -> str:
    if kind is None:
        return DEFAULT_VARIANT
    row = await session.scalar(
        select(HoaAcquisitionRule).where(HoaAcquisitionRule.acquisition_kind == kind)
    )
    return row.allocation_variant if row is not None else DEFAULT_VARIANT


def _out(kind: str, row: Any) -> dict[str, Any]:
    variant = row.allocation_variant if row is not None else DEFAULT_VARIANT
    return {
        "acquisition_kind": kind,
        "kind_label": KIND_NAMES[kind],
        "variant": variant,
        "variant_label": VARIANT_LABELS[variant],
        "is_default": row is None,
        "source_note": row.source_note if row is not None else None,
    }


@router.get(
    "/acquisition-rules",
    summary="Zuordnungsregeln je Erwerbsart (AA07-01)",
    dependencies=[Depends(strict_query)],
)
async def list_rules(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rows = {
            r.acquisition_kind: r for r in (await session.scalars(select(HoaAcquisitionRule))).all()
        }
        return {
            "items": [_out(k, rows.get(k)) for k in KINDS],
            "variants": [{"code": v, "label": VARIANT_LABELS[v]} for v in VARIANTS],
            "note": RULE_NOTE,
        }


@router.put(
    "/acquisition-rules/{kind}",
    summary="Zuordnungsregel je Erwerbsart setzen",
    response_model=HoaAcqRuleOut,
)
async def put_rule(
    kind: str,
    body: HoaAcqRuleIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    if kind not in KINDS or body.variant not in VARIANTS:
        raise ProblemError(ErrorCodes.HOA_ACQUISITION_RULE_INVALID)
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(HoaAcquisitionRule).where(HoaAcquisitionRule.acquisition_kind == kind)
        )
        if row is None:
            row = HoaAcquisitionRule(
                tenant_id=principal.tenant_id,
                acquisition_kind=kind,
                created_by=principal.user_id,
            )
            session.add(row)
        row.allocation_variant = body.variant
        row.source_note = body.source_note
        row.updated_by = principal.user_id
        await session.flush()
        return _out(kind, row)
