"""Rule engine (/api/v1/automation, section 15.2, tasks A38 and A39).

Maintenance (rules, activation, test run) needs ``tenant_settings:update``; delete needs
``tenant_settings:delete`` (docs/rules/M2-07.md); the run log and the rule list are readable
with ``tenant_settings:read`` or ``tickets:read``. A test run evaluates a rule against a sample
event and returns the action previews; nothing is written.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.automation.models import (
    ACTION_TYPES,
    SETTABLE_TICKET_FIELDS,
    TRIGGER_KINDS,
    TRIGGER_SCHEDULE,
    AutomationRule,
    AutomationRun,
)
from mhvp.automation.rules import RELATED_FIELDS, normalise, related_groups
from mhvp.automation.schedule import FREQUENCIES
from mhvp.automation.schemas import (
    AI_TASKS,
    AutomationActivateIn,
    AutomationRuleIn,
    AutomationRulePatch,
    TestEventIn,
    check_trigger,
    require_webhook_secrets,
)
from mhvp.automation.services import (
    build_context,
    carry_secrets,
    dry_run,
    public_actions,
    schedule_context,
    seal_actions,
)
from mhvp.core.auth.principal import TenantPrincipal, get_principal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/automation", tags=["Automatisierung"])
MANAGE = require_permission("tenant_settings:update")
DELETE = require_permission("tenant_settings:delete")
_READ_ANY = ("tenant_settings:read", "tickets:read")

# Event types offered by the form (free text stays allowed; the list is a help, not a limit).
KNOWN_EVENT_TYPES: tuple[str, ...] = (
    "ticket.created",
    "ticket.merged",
    "sla.escalated",
    "contact.updated",
    "document.created",
    "property.created",
    "unit.created",
    "listing.created",
    "import_run.applied",
    "payment_order.returned",
    "portal_account.invited",
)


async def _read_principal(request: Request) -> TenantPrincipal:
    """Read access with either ``tenant_settings:read`` or ``tickets:read``."""
    principal = await get_principal(request)
    if principal.tenant_id is None or not any(principal.has(p) for p in _READ_ANY):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing permission tenant_settings:read."
        )
    return TenantPrincipal(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        permissions=principal.permissions,
        roles=principal.roles,
        api_key_id=principal.api_key_id,
        is_platform_admin=principal.is_platform_admin,
        platform_access_reason=principal.platform_access_reason,
        legal_entity_ids=principal.legal_entity_ids,
    )


def _rule_out(rule: AutomationRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "active": rule.active,
        "trigger_kind": rule.trigger_kind,
        "trigger_event_type": rule.trigger_event_type,
        "schedule": rule.schedule,
        "last_scheduled_at": rule.last_scheduled_at,
        "conditions": rule.conditions,
        "actions": public_actions(rule.actions),
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _run_out(run: AutomationRun, rule_name: str | None = None) -> dict[str, Any]:
    return {
        "id": run.id,
        "rule_id": run.rule_id,
        "rule_name": rule_name,
        "event_id": run.event_id,
        "event_type": run.event_type,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "error": run.error,
        "actions": run.actions,
    }


async def _get_rule(session: AsyncSession, rule_id: uuid.UUID) -> AutomationRule:
    rule = await session.get(AutomationRule, rule_id)
    if rule is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Regel nicht gefunden.")
    return rule


async def _assert_unique_name(session: AsyncSession, name: str, exclude: uuid.UUID | None) -> None:
    query = select(AutomationRule.id).where(AutomationRule.name == name)
    if exclude is not None:
        query = query.where(AutomationRule.id != exclude)
    if await session.scalar(query) is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Eine Regel mit diesem Namen existiert.")


@router.get("/meta", summary="Bekannte Ereignistypen, Auslöser und Aktionen")
async def meta(principal: TenantPrincipal = Depends(_read_principal)) -> dict[str, Any]:
    return {
        "event_types": list(KNOWN_EVENT_TYPES),
        "trigger_kinds": list(TRIGGER_KINDS),
        "schedule_frequencies": list(FREQUENCIES),
        "action_types": list(ACTION_TYPES),
        "ai_tasks": list(AI_TASKS),
        "settable_ticket_fields": list(SETTABLE_TICKET_FIELDS),
        "condition_ops": ["eq", "ne", "contains", "gt", "lt"],
        # A81: related master data a condition may read, grouped for the form.
        "related_fields": {group: list(fields) for group, fields in RELATED_FIELDS.items()},
    }


@router.get("/rules", summary="Regeln auflisten")
async def list_rules(
    request: Request, principal: TenantPrincipal = Depends(_read_principal)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(AutomationRule).order_by(AutomationRule.name, AutomationRule.id)
        )
        return [_rule_out(r) for r in rows]


@router.post("/rules", status_code=201, summary="Regel anlegen")
async def create_rule(
    body: AutomationRuleIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _assert_unique_name(session, body.name, None)
        values = body.model_dump()
        values["actions"] = seal_actions(values["actions"])
        rule = AutomationRule(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            **values,
        )
        session.add(rule)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="automation_rule.created",
            entity_type="automation_rule",
            entity_id=rule.id,
            actor_user_id=principal.user_id,
            payload={"name": rule.name, "active": rule.active},
        )
        return _rule_out(rule)


@router.get("/rules/{rule_id}", summary="Regel lesen")
async def get_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(_read_principal)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _rule_out(await _get_rule(session, rule_id))


@router.patch("/rules/{rule_id}", summary="Regel ändern")
async def patch_rule(
    rule_id: uuid.UUID,
    body: AutomationRulePatch,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await _get_rule(session, rule_id)
        values = body.model_dump(exclude_unset=True)
        if "name" in values and values["name"] is not None:
            await _assert_unique_name(session, values["name"], rule.id)
        if values.get("actions") is not None:
            carried = carry_secrets(values["actions"], rule.actions)
            try:
                require_webhook_secrets(carried)
            except ValueError as exc:
                raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
            values["actions"] = seal_actions(carried)
        merged = {
            "trigger_kind": values.get("trigger_kind", rule.trigger_kind),
            "trigger_event_type": values.get("trigger_event_type", rule.trigger_event_type),
            "schedule": values.get("schedule", rule.schedule),
            "actions": values.get("actions", rule.actions),
        }
        try:
            check_trigger(
                merged["trigger_kind"],
                merged["trigger_event_type"],
                merged["schedule"],
                merged["actions"],
            )
        except ValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
        if merged["trigger_kind"] != rule.trigger_kind or "schedule" in values:
            # A changed schedule starts a fresh watermark (next due moment, not the past one).
            values["last_scheduled_at"] = None
        before = {k: getattr(rule, k) for k in values}
        for key, value in values.items():
            setattr(rule, key, value)
        rule.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="automation_rule.updated",
            entity_type="automation_rule",
            entity_id=rule.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(values)},
            changes={
                k: {
                    "old": public_actions(before[k]) if k == "actions" else normalise(before[k]),
                    "new": public_actions(values[k]) if k == "actions" else normalise(values[k]),
                }
                for k in values
                if before[k] != values[k]
            },
        )
        await session.flush()
        await session.refresh(rule)
        return _rule_out(rule)


@router.post("/rules/{rule_id}/activate", summary="Regel aktivieren oder deaktivieren")
async def activate_rule(
    rule_id: uuid.UUID,
    body: AutomationActivateIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await _get_rule(session, rule_id)
        if rule.active != body.active:
            rule.active = body.active
            rule.updated_by = principal.user_id
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="automation_rule.updated",
                entity_type="automation_rule",
                entity_id=rule.id,
                actor_user_id=principal.user_id,
                payload={"fields": ["active"]},
                changes={"active": {"old": not body.active, "new": body.active}},
            )
        await session.flush()
        await session.refresh(rule)
        return _rule_out(rule)


@router.delete("/rules/{rule_id}", status_code=204, summary="Regel löschen (nur Administrator)")
async def delete_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> None:
    async with tenant_tx(request, principal) as session:
        rule = await _get_rule(session, rule_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="automation_rule.deleted",
            entity_type="automation_rule",
            entity_id=rule.id,
            actor_user_id=principal.user_id,
            payload={"name": rule.name},
        )
        await session.delete(rule)


@router.post("/rules/{rule_id}/test", summary="Testlauf gegen ein Beispielereignis (ohne Wirkung)")
async def dry_run_rule(
    rule_id: uuid.UUID,
    body: TestEventIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await _get_rule(session, rule_id)
        if rule.trigger_kind == TRIGGER_SCHEDULE:
            due = body.due_at or datetime.now(UTC)
            # The sample of a schedule rule is a due moment; ``type`` must be ``schedule.due``.
            context = schedule_context(rule, due)
            context["type"] = body.type
            if body.entity:
                context["entity"] = body.entity
        else:
            context = await build_context(
                session,
                type=body.type,
                entity_type=body.entity_type,
                entity_id=body.entity_id,
                payload=body.payload,
                actor_user_id=principal.user_id,
                entity_override=body.entity or None,
                related=related_groups(rule.conditions),
                tenant_id=principal.tenant_id,
            )
        result = await dry_run(
            session,
            tenant_id=principal.tenant_id,
            rule=rule,
            context=context,
            settings=request.app.state.settings,
        )
        # Belt and braces: a dry run writes nothing, and nothing pending is committed.
        await session.rollback()
        return result


@router.get("/runs", summary="Ausführungsprotokoll")
async def list_runs(
    request: Request,
    rule_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(_read_principal),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        query = select(AutomationRun, AutomationRule.name).join(
            AutomationRule, AutomationRule.id == AutomationRun.rule_id
        )
        count_query = select(func.count()).select_from(AutomationRun)
        if rule_id is not None:
            query = query.where(AutomationRun.rule_id == rule_id)
            count_query = count_query.where(AutomationRun.rule_id == rule_id)
        if status:
            query = query.where(AutomationRun.status == status)
            count_query = count_query.where(AutomationRun.status == status)
        rows = await session.execute(
            query.order_by(AutomationRun.started_at.desc(), AutomationRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await session.scalar(count_query)
        return {
            "items": [_run_out(run, name) for run, name in rows],
            "total": int(total or 0),
        }
