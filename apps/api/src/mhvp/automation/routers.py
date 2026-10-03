"""Rule engine (/api/v1/automation, section 15.2, tasks A38 and A39).

Maintenance (rules, activation, test run) needs ``tenant_settings:update``; delete needs
``tenant_settings:delete`` (docs/rules/M2-07.md); the run log and the rule list are readable
with ``tenant_settings:read`` or ``tickets:read``. A test run evaluates a rule against a sample
event and returns the action previews; nothing is written.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.automation.job_schedule import validate_job
from mhvp.automation.models import (
    ACTION_TYPES,
    JOB_CATALOG,
    SETTABLE_TICKET_FIELDS,
    TRIGGER_KINDS,
    TRIGGER_SCHEDULE,
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_RETRY_SCHEDULE_SECONDS,
    AutomationRule,
    AutomationRun,
    AutomationWebhookDelivery,
    TenantJobSchedule,
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
    delivery_out,
    dry_run,
    public_actions,
    redeliver_webhook,
    schedule_context,
    seal_actions,
)
from mhvp.core.auth.principal import TenantPrincipal, get_principal, require_permission, tenant_tx
from mhvp.core.etag import check_if_match, etag_of, load_for_etag
from mhvp.core.events import emit
from mhvp.core.listparams import ListParams, ListSpec, sparse, strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/automation", tags=["Automatisierung"])
MANAGE = require_permission("tenant_settings:update")
DELETE = require_permission("tenant_settings:delete")
_READ_ANY = ("tenant_settings:read", "tickets:read")

# Event types offered by the form (free text stays allowed; the list is a help, not a limit).
KNOWN_EVENT_TYPES: tuple[str, ...] = (
    "ticket.created",
    "message.received",
    "ticket.merged",
    "ticket.status_changed",
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
# Condition field paths of a ticket that are computed, not stored (M9-08): Ticketalter and
# Fristbezug (Tage vor Termin), usable with ``gt``/``lt`` like any other field.
COMPUTED_TICKET_FIELDS: tuple[str, ...] = ("age_days", "due_in_days")


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
        "test_mode": rule.test_mode,
        "trigger_kind": rule.trigger_kind,
        "trigger_event_type": rule.trigger_event_type,
        "schedule": rule.schedule,
        "last_scheduled_at": rule.last_scheduled_at,
        "conditions": rule.conditions,
        "actions": public_actions(rule.actions),
        "owner_user_id": rule.owner_user_id,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _has_ai_task(rule: AutomationRule) -> bool:
    return any(isinstance(a, dict) and a.get("type") == "ai_task" for a in rule.actions or [])


async def mark_needs_ai_approval(
    session: AsyncSession, tenant_id: uuid.UUID, rules: list[AutomationRule]
) -> dict[uuid.UUID, bool]:
    """AM04-03: existing rules with an ``ai_task`` action whose last editor does not hold
    ``ai:approve`` (or has no active membership) are flagged ``needs_ai_approval``. Read only,
    execution stays bound to the tenant switch ``ai_automation.automation_ai_task``."""
    from mhvp.core.auth.permissions import effective_permissions
    from mhvp.platform.models import Membership

    verdict: dict[uuid.UUID, bool] = {}
    by_user: dict[uuid.UUID | None, bool] = {}
    for rule in rules:
        if not _has_ai_task(rule):
            continue
        editor = rule.updated_by or rule.created_by
        if editor not in by_user:
            ok = False
            if editor is not None:
                membership = await session.scalar(
                    select(Membership).where(
                        Membership.tenant_id == tenant_id, Membership.user_id == editor
                    )
                )
                if membership is not None:
                    perms, _ = await effective_permissions(session, tenant_id, membership.id)
                    ok = "ai:approve" in perms
            by_user[editor] = ok
        verdict[rule.id] = not by_user[editor]
    return verdict


def _run_out(
    run: AutomationRun,
    rule_name: str | None = None,
    deliveries: list[AutomationWebhookDelivery] | None = None,
) -> dict[str, Any]:
    """Run with its webhook delivery log (A82): one entry per ``webhook`` action, with the
    attempt count, the next attempt and the last result."""
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
        "webhook_deliveries": [delivery_out(d) for d in deliveries or []],
    }


async def _get_rule(
    session: AsyncSession, rule_id: uuid.UUID, *, lock: bool = False
) -> AutomationRule:
    if lock:  # AC01-01: row lock before the If-Match comparison
        locked: AutomationRule = await load_for_etag(
            session, AutomationRule, rule_id, detail="Regel nicht gefunden."
        )
        return locked
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


@router.get(
    "/rule-templates",
    summary="Regelvorlagen (Beispiele, nicht aktiv)",
    dependencies=[Depends(strict_query)],
)
async def rule_templates(
    principal: TenantPrincipal = Depends(_read_principal),
) -> list[dict[str, Any]]:
    from mhvp.automation.templates import RULE_TEMPLATES

    return [dict(t) for t in RULE_TEMPLATES]


@router.get(
    "/event-types",
    summary="Katalog der emittierten Ereignistypen (GAH-307)",
    dependencies=[Depends(strict_query)],
)
async def event_types(
    principal: TenantPrincipal = Depends(_read_principal),
) -> dict[str, Any]:
    from mhvp.automation.event_catalog import ALL_EVENT_TYPES

    return {"event_types": list(ALL_EVENT_TYPES)}


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
        # M9-08: computed ticket condition fields (Ticketalter, Fristbezug) and the webhook
        # retry plan, shown in the CRM delivery log.
        "computed_ticket_fields": list(COMPUTED_TICKET_FIELDS),
        "webhook_retry_schedule_seconds": list(WEBHOOK_RETRY_SCHEDULE_SECONDS),
        "webhook_max_attempts": WEBHOOK_MAX_ATTEMPTS,
    }


_RULE_LIST = ListSpec(  # GA04-05
    filters={
        "active": AutomationRule.active,
        "test_mode": AutomationRule.test_mode,
        "trigger_kind": AutomationRule.trigger_kind,
        "trigger_event_type": AutomationRule.trigger_event_type,
    },
    sort={"name": AutomationRule.name, "created_at": AutomationRule.created_at},
)


@router.get("/rules", summary="Regeln auflisten", dependencies=[Depends(strict_query)])
async def list_rules(
    request: Request,
    params: ListParams = Depends(_RULE_LIST.dependency),
    principal: TenantPrincipal = Depends(_read_principal),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            _RULE_LIST.apply(
                select(AutomationRule), params, (AutomationRule.name, AutomationRule.id)
            )
        )
        rule_list = list(rows)
        gaps = await mark_needs_ai_approval(session, principal.tenant_id, rule_list)
        out = [{**_rule_out(r), "needs_ai_approval": gaps.get(r.id, False)} for r in rule_list]
        return sparse(out, params, None)  # type: ignore[no-any-return]


def _assert_ai_task_permission(principal: TenantPrincipal, actions: Any) -> None:
    """GAJ-607 (AM04): an ``ai_task`` action is a lasting AI cost path; only a person with
    ``ai:approve`` may create or change rules containing one."""
    if principal.has("ai:approve"):
        return
    for action in actions or []:
        kind = action.get("type") if isinstance(action, dict) else getattr(action, "type", None)
        if kind == "ai_task":
            raise ProblemError(
                ErrorCodes.FORBIDDEN,
                detail="Regeln mit KI-Aufgabe erfordern das Recht ai:approve.",
            )


@router.post("/rules", status_code=201, summary="Regel anlegen")
async def create_rule(
    body: AutomationRuleIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _assert_unique_name(session, body.name, None)
        values = body.model_dump()
        _assert_ai_task_permission(principal, values["actions"])
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
    rule_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(_read_principal),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await _get_rule(session, rule_id)
        response.headers["ETag"] = etag_of(rule.updated_at)  # GA04-06
        gaps = await mark_needs_ai_approval(session, principal.tenant_id, [rule])
        return {**_rule_out(rule), "needs_ai_approval": gaps.get(rule.id, False)}


@router.patch("/rules/{rule_id}", summary="Regel ändern")
async def patch_rule(
    rule_id: uuid.UUID,
    body: AutomationRulePatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rule = await _get_rule(session, rule_id, lock=True)
        check_if_match(if_match, rule.updated_at)  # GA04-06
        values = body.model_dump(exclude_unset=True)
        _assert_ai_task_permission(principal, rule.actions)  # AN14-13: any change, not only actions
        if "name" in values and values["name"] is not None:
            await _assert_unique_name(session, values["name"], rule.id)
        if values.get("actions") is not None:
            _assert_ai_task_permission(principal, values["actions"])
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
        await session.flush()
        await session.refresh(rule, ["updated_at"])
        response.headers["ETag"] = etag_of(rule.updated_at)
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
        if body.active:  # AN14-13: enabling an ai_task rule needs ai:approve
            _assert_ai_task_permission(principal, rule.actions)
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
        runs = list(rows)
        deliveries: dict[uuid.UUID, list[AutomationWebhookDelivery]] = {}
        if runs:
            for delivery in await session.scalars(
                select(AutomationWebhookDelivery)
                .where(AutomationWebhookDelivery.run_id.in_([run.id for run, _ in runs]))
                .order_by(AutomationWebhookDelivery.action_index)
            ):
                deliveries.setdefault(delivery.run_id, []).append(delivery)
        return {
            "items": [_run_out(run, name, deliveries.get(run.id)) for run, name in runs],
            "total": int(total or 0),
        }


@router.post(
    "/webhook-deliveries/{delivery_id}/redeliver",
    status_code=202,
    summary="Regel-Webhook erneut zustellen",
)
async def redeliver_endpoint(
    delivery_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> Response:
    """Manual redelivery (A82, as ``/webhook-deliveries/{id}/redeliver`` of the platform):
    the delivery goes back to pending and is sent by the next beat pass; the attempt count
    stays. RLS limits the lookup to the caller's tenant."""
    async with tenant_tx(request, principal) as session:
        delivery = await session.get(AutomationWebhookDelivery, delivery_id)
        if delivery is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Zustellung nicht gefunden.")
        redeliver_webhook(delivery)
    return Response(status_code=202)


# --- job schedules per tenant (S15-03) -----------------------------------------------------


class JobScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    run_at: str | None = Field(default=None, max_length=5, description="HH:MM, Europe/Berlin")


@router.get(
    "/job-schedules",
    summary="Standardjobs und Zeitpläne des Mandanten",
    dependencies=[Depends(strict_query)],
)
async def list_job_schedules(
    request: Request, principal: TenantPrincipal = Depends(_read_principal)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = {r.job_key: r for r in (await session.scalars(select(TenantJobSchedule))).all()}
        return [
            {
                "job_key": key,
                "label": label,
                "enabled": rows[key].enabled if key in rows else True,
                "run_at": rows[key].run_at if key in rows else None,
                "configured": key in rows,
            }
            for key, label in JOB_CATALOG.items()
        ]


@router.put("/job-schedules/{job_key}", summary="Standardjob des Mandanten konfigurieren")
async def put_job_schedule(
    job_key: str,
    body: JobScheduleIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    try:
        validate_job(job_key, body.run_at)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(TenantJobSchedule).where(TenantJobSchedule.job_key == job_key)
        )
        old = {"enabled": row.enabled, "run_at": row.run_at} if row else None
        if row is None:
            row = TenantJobSchedule(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                updated_by=principal.user_id,
                job_key=job_key,
            )
            session.add(row)
        row.enabled, row.run_at = body.enabled, body.run_at
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="tenant_job_schedule.updated",
            entity_type="tenant_job_schedule",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"job_key": job_key},
            changes={"old": old, "new": {"enabled": row.enabled, "run_at": row.run_at}},
        )
        return {"job_key": job_key, "enabled": row.enabled, "run_at": row.run_at}
