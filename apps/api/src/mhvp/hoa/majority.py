"""Mehrheitsregeln je Beschlussgegenstand (M25-01): configuration and automatic check.

A rule is a tenant default for one subject kind, optionally overridden for one community
(legal_entity_id). The check compares the recorded tally with the rule and yields "erreicht",
"nicht erreicht" or "nicht prüfbar" together with the applied rule as text. It is a display
and protocol note only; the resolution status is never changed automatically, the chair
announces the result. The rule contents come from the community documents and are to be
checked; no legal norm is asserted by the system."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import HoaMajorityRule, Resolution

router = APIRouter(prefix="/hoa", tags=["WEG"])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")

SUBJECT_KINDS = (
    "economic_plan",
    "annual_statement",
    "maintenance",
    "structural_change",
    "manager_appointment",
    "other",
)
SUBJECT_LABELS = {
    "economic_plan": "Wirtschaftsplan",
    "annual_statement": "Jahresabrechnung",
    "maintenance": "Erhaltung",
    "structural_change": "Bauliche Veränderung",
    "manager_appointment": "Verwalterbestellung",
    "other": "Sonstiges",
}
MAJORITY_TYPES = ("simple", "qualified_2_3", "qualified_3_4", "unanimous", "custom")
COUNTING_BASES = ("heads", "shares", "units")
# counting basis of a rule -> voting principle of the tally (meetings.py: head, mea, unit)
BASIS_TO_PRINCIPLE = {"heads": "head", "shares": "mea", "units": "unit"}
BASIS_LABELS = {"heads": "Köpfe", "shares": "Miteigentumsanteile", "units": "Einheiten"}
REACHED, NOT_REACHED, NOT_CHECKABLE = "erreicht", "nicht erreicht", "nicht prüfbar"
DEFAULT_HINT = "Standardregel, nicht fachlich freigegeben"
SUBJECT_PATTERN = "^(" + "|".join(SUBJECT_KINDS) + ")$"


class RuleSpec(BaseModel):
    """Plain rule values for the pure evaluation (a stored rule or the default)."""

    majority_type: str
    counting_basis: str
    custom_numerator: int | None = None
    custom_denominator: int | None = None
    source: str
    approved: bool = False
    default: bool = False


DEFAULT_RULE = RuleSpec(
    majority_type="simple",
    counting_basis="heads",
    source="Standardregel ohne hinterlegte Fundstelle, zu prüfen",
    default=True,
)


def threshold(rule: RuleSpec) -> Fraction | None:
    """Required share of yes votes among yes and no votes (at least), None for unanimity.
    Simple majority is handled as strictly more yes than no votes."""
    if rule.majority_type == "qualified_2_3":
        return Fraction(2, 3)
    if rule.majority_type == "qualified_3_4":
        return Fraction(3, 4)
    if rule.majority_type == "custom":
        if not rule.custom_numerator or not rule.custom_denominator:
            raise ValueError("custom rule without fraction")
        return Fraction(rule.custom_numerator, rule.custom_denominator)
    if rule.majority_type == "simple":
        return Fraction(1, 2)
    return None


def rule_text(rule: RuleSpec, subject_kind: str | None = None) -> str:
    kinds = {
        "simple": "einfache Mehrheit (mehr Ja als Nein)",
        "qualified_2_3": "qualifizierte Mehrheit von mindestens 2/3 der abgegebenen Stimmen",
        "qualified_3_4": "qualifizierte Mehrheit von mindestens 3/4 der abgegebenen Stimmen",
        "unanimous": "Allstimmigkeit aller Stimmberechtigten",
        "custom": (
            f"Mehrheit von mindestens {rule.custom_numerator}/{rule.custom_denominator}"
            " der abgegebenen Stimmen"
        ),
    }
    parts = [
        kinds.get(rule.majority_type, rule.majority_type),
        f"nach {BASIS_LABELS.get(rule.counting_basis, rule.counting_basis)}",
    ]
    if rule.majority_type != "unanimous":
        parts.append("Enthaltungen nicht gezählt")
    head = SUBJECT_LABELS.get(subject_kind or "", "")
    text = (f"{head}: " if head else "") + ", ".join(parts) + f"; Fundstelle: {rule.source}"
    if rule.default:
        text += f" ({DEFAULT_HINT})"
    elif not rule.approved:
        text += " (Regel noch nicht fachlich freigegeben)"
    return text


def _num(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def evaluate(
    rule: RuleSpec, votes: dict[str, Any] | None, subject_kind: str | None = None
) -> dict[str, Any]:
    """Pure check of a tally against a rule. `votes` holds principle (head, mea, unit), yes,
    no, abstain and for unanimity eligible (total weight of all eligible votes)."""
    out: dict[str, Any] = {
        "subject_kind": subject_kind,
        "rule_text": rule_text(rule, subject_kind),
        "standard_rule": rule.default,
        "approved": rule.approved,
        "reason": None,
    }

    def result(value: str, reason: str | None = None) -> dict[str, Any]:
        return out | {"result": value, "reason": reason}

    if subject_kind is None:
        return result(NOT_CHECKABLE, "Beschlussgegenstand nicht angegeben.")
    if not votes:
        return result(NOT_CHECKABLE, "Keine Auszählung erfasst.")
    yes, no, abstain = _num(votes.get("yes")), _num(votes.get("no")), _num(votes.get("abstain"))
    if yes is None or no is None or yes < 0 or no < 0:
        return result(NOT_CHECKABLE, "Auszählung unvollständig.")
    principle = votes.get("principle")
    expected = BASIS_TO_PRINCIPLE.get(rule.counting_basis)
    if principle != expected:
        return result(
            NOT_CHECKABLE,
            f"Zählbasis der Auszählung ({principle or 'unbekannt'}) weicht von der Regel"
            f" ({expected}) ab.",
        )
    if rule.majority_type == "unanimous":
        eligible = _num(votes.get("eligible"))
        if eligible is None or eligible <= 0:
            return result(NOT_CHECKABLE, "Gesamtzahl der Stimmberechtigten fehlt.")
        ok = yes == eligible and no == 0 and (abstain or 0) == 0
        return result(REACHED if ok else NOT_REACHED)
    try:
        share = threshold(rule)
    except ValueError:
        return result(NOT_CHECKABLE, "Regel ohne gültigen Bruch.")
    cast = yes + no
    if rule.majority_type == "simple" or share is None:
        ok = yes > no
    else:
        ok = cast > 0 and Fraction(yes) >= share * Fraction(cast)
    return result(REACHED if ok else NOT_REACHED)


def spec_of(row: HoaMajorityRule | None) -> RuleSpec:
    if row is None:
        return DEFAULT_RULE
    return RuleSpec(
        majority_type=row.majority_type,
        counting_basis=row.counting_basis,
        custom_numerator=row.custom_numerator,
        custom_denominator=row.custom_denominator,
        source=row.source,
        approved=row.approved_by is not None,
    )


async def find_rule(
    session: AsyncSession, legal_entity_id: uuid.UUID, subject_kind: str | None
) -> HoaMajorityRule | None:
    """Community override first, then the tenant default for the subject kind."""
    if subject_kind is None:
        return None
    rows = (
        await session.scalars(
            select(HoaMajorityRule).where(
                HoaMajorityRule.subject_kind == subject_kind,
                HoaMajorityRule.active.is_(True),
                (HoaMajorityRule.legal_entity_id == legal_entity_id)
                | HoaMajorityRule.legal_entity_id.is_(None),
            )
        )
    ).all()
    override = [r for r in rows if r.legal_entity_id is not None]
    pick = override or list(rows)
    return pick[0] if pick else None


async def check_resolution(
    session: AsyncSession, principal: TenantPrincipal, row: Resolution
) -> dict[str, Any]:
    """Evaluates, stores the check as protocol note and records an event. No status change."""
    rule = await find_rule(session, row.legal_entity_id, row.subject_kind)
    check = evaluate(spec_of(rule), row.votes, row.subject_kind) | {
        "rule_id": str(rule.id) if rule else None,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    row.majority_check = check
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="resolution.majority_checked",
        entity_type="resolution",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"result": check["result"], "rule_text": check["rule_text"]},
    )
    return check


# Endpoints ---------------------------------------------------------------------------------


class HoaSubjectRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_entity_id: uuid.UUID | None = None
    subject_kind: str = Field(pattern=SUBJECT_PATTERN)
    majority_type: str = Field(pattern="^(" + "|".join(MAJORITY_TYPES) + ")$")
    custom_numerator: int | None = Field(default=None, ge=1, le=1000)
    custom_denominator: int | None = Field(default=None, ge=1, le=1000)
    counting_basis: str = Field(pattern="^(heads|shares|units)$")
    source: str = Field(min_length=3, max_length=4000)

    @model_validator(mode="after")
    def _custom(self) -> "HoaSubjectRuleIn":
        if self.majority_type == "custom":
            if not self.custom_numerator or not self.custom_denominator:
                raise ValueError("Eigene Mehrheit braucht Zähler und Nenner.")
            if self.custom_numerator > self.custom_denominator:
                raise ValueError("Zähler größer als Nenner.")
        elif self.custom_numerator is not None or self.custom_denominator is not None:
            raise ValueError("Zähler und Nenner nur bei eigener Mehrheit.")
        return self


def _out(r: HoaMajorityRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "legal_entity_id": r.legal_entity_id,
        "subject_kind": r.subject_kind,
        "majority_type": r.majority_type,
        "custom_numerator": r.custom_numerator,
        "custom_denominator": r.custom_denominator,
        "counting_basis": r.counting_basis,
        "source": r.source,
        "created_by": r.created_by,
        "approved_by": r.approved_by,
        "approved_at": r.approved_at,
        "rule_text": rule_text(spec_of(r), r.subject_kind),
    }


async def _load(session: AsyncSession, rule_id: uuid.UUID) -> HoaMajorityRule:
    row = await session.get(HoaMajorityRule, rule_id, with_for_update=True)
    if row is None or not row.active:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _ensure_unique(
    session: AsyncSession, body: HoaSubjectRuleIn, skip: uuid.UUID | None
) -> None:
    q = select(HoaMajorityRule.id).where(
        HoaMajorityRule.subject_kind == body.subject_kind,
        HoaMajorityRule.active.is_(True),
        HoaMajorityRule.legal_entity_id.is_(None)
        if body.legal_entity_id is None
        else HoaMajorityRule.legal_entity_id == body.legal_entity_id,
    )
    if skip is not None:
        q = q.where(HoaMajorityRule.id != skip)
    if await session.scalar(q):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für diesen Beschlussgegenstand besteht bereits eine Regel."
        )


@router.get("/majority-rules/subject-rules", summary="Mehrheitsregeln je Beschlussgegenstand")
async def list_subject_rules(
    request: Request,
    legal_entity_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        q = select(HoaMajorityRule).where(HoaMajorityRule.active.is_(True))
        if legal_entity_id is not None:
            q = q.where(
                (HoaMajorityRule.legal_entity_id == legal_entity_id)
                | HoaMajorityRule.legal_entity_id.is_(None)
            )
        rows = await session.scalars(
            q.order_by(HoaMajorityRule.subject_kind, HoaMajorityRule.created_at).limit(500)
        )
        return [_out(r) for r in rows.all()]


@router.post(
    "/majority-rules/subject-rules",
    status_code=201,
    summary="Mehrheitsregel je Beschlussgegenstand anlegen",
)
async def create_subject_rule(
    body: HoaSubjectRuleIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _ensure_unique(session, body, None)
        row = HoaMajorityRule(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            active=True,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_majority_rule.created",
            entity_type="hoa_majority_rule",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload=body.model_dump(mode="json"),
        )
        return _out(row)


@router.put(
    "/majority-rules/subject-rules/{rule_id}",
    summary="Mehrheitsregel ändern (Freigabe entfällt)",
)
async def update_subject_rule(
    rule_id: uuid.UUID,
    body: HoaSubjectRuleIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, rule_id)
        await _ensure_unique(session, body, row.id)
        before = _out(row)
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        row.approved_by = None
        row.approved_at = None
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_majority_rule.updated",
            entity_type="hoa_majority_rule",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"before": before["rule_text"], "after": body.model_dump(mode="json")},
        )
        return _out(row)


@router.post(
    "/majority-rules/subject-rules/{rule_id}/approve",
    summary="Mehrheitsregel fachlich freigeben (zweite Person)",
)
async def approve_subject_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, rule_id)
        if principal.user_id in (row.created_by, row.updated_by):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Freigabe nur durch eine zweite Person.")
        row.approved_by = principal.user_id
        row.approved_at = datetime.now(UTC)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_majority_rule.approved",
            entity_type="hoa_majority_rule",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
        return _out(row)


@router.delete(
    "/majority-rules/subject-rules/{rule_id}",
    status_code=204,
    summary="Mehrheitsregel deaktivieren (bleibt nachvollziehbar)",
)
async def delete_subject_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, rule_id)
        row.active = False
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_majority_rule.deactivated",
            entity_type="hoa_majority_rule",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
    return Response(status_code=204)


@router.get(
    "/resolutions/{resolution_id}/majority-check",
    summary="Mehrheitsprüfung eines Beschlusses (nur Anzeige, keine Statusänderung)",
)
async def resolution_majority_check(
    resolution_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Resolution, resolution_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rule = await find_rule(session, row.legal_entity_id, row.subject_kind)
        current = evaluate(spec_of(rule), row.votes, row.subject_kind)
        return {"stored": row.majority_check, "current": current}
