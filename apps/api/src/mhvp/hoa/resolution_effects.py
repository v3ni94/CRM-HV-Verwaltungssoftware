"""Consequences of a resolution status change (AN19, GAK-204; 6.5, 7.8 W06, 15.1).

``on_status_changed`` is the consumer of ``resolution.status_changed``: when a resolution
becomes contested, annulled or void, every dependent economic plan, special levy and annual
statement is reported back (``dependents``) with the flag ``contested`` and the users with
``accounting:approve`` get a notification. Nothing is cancelled, reversed or recalculated
automatically (D54); the manager decides.

The review date of a possible contest is a deadline entry of the tenant's deadline type
``beschlussanfechtung`` (``workspace.deadline_entry``). The type has no duration by default;
the date is entered by the user. Only when the operator entered a duration on that type is the
date computed from the decision date, marked ``due_computed`` and "zu verifizieren". No legal
rule on the contest period is set here (question AN19-01, G4).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import EconomicPlan, HoaStatement, Resolution, SpecialLevy

CONTESTED = frozenset({"contested", "annulled", "void"})
NOTIFICATION_KIND = "hoa.resolution_contested"
DEADLINE_TYPE_CODE = "beschlussanfechtung"
DEADLINE_TYPE_NAME = "Beschluss: Prüfung Anfechtung"


async def dependents(session: AsyncSession, resolution: Resolution) -> list[dict[str, Any]]:
    """Economic plans, special levies and annual statements bound to the resolution."""
    flag = resolution.status in CONTESTED
    out: list[dict[str, Any]] = []
    plans = await session.scalars(
        select(EconomicPlan).where(EconomicPlan.resolution_id == resolution.id)
    )
    for plan in plans.all():
        out.append(
            {
                "type": "economic_plan",
                "id": plan.id,
                "label": plan.title or f"Wirtschaftsplan {plan.year}",
                "status": str(plan.status),
                "applied": plan.applied_at is not None,
                "contested": flag,
            }
        )
    levies = await session.scalars(
        select(SpecialLevy).where(SpecialLevy.resolution_id == resolution.id)
    )
    for levy in levies.all():
        out.append(
            {
                "type": "special_levy",
                "id": levy.id,
                "label": levy.purpose[:200],
                "status": levy.status,
                "applied": levy.applied_at is not None,
                "contested": flag,
            }
        )
    statements = await session.scalars(
        select(HoaStatement).where(HoaStatement.resolution_id == resolution.id)
    )
    for st in statements.all():
        out.append(
            {
                "type": "hoa_statement",
                "id": st.id,
                "label": f"Jahresabrechnung {st.year}",
                "status": str(st.status),
                "applied": bool(st.posted_entry_ids),
                "contested": flag,
            }
        )
    return out


async def on_status_changed(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    resolution: Resolution,
    old_status: str | None,
    new_status: str,
) -> int:
    """Notify the approvers when a resolution with dependents becomes contested, annulled or
    void. Returns the number of notifications written; never changes a dependent record."""
    if new_status not in CONTESTED or old_status == new_status:
        return 0
    deps = await dependents(session, resolution)
    if not deps:
        return 0
    from mhvp.banking.tasks import users_with_permission
    from mhvp.workspace.services import notify

    labels = {
        "contested": "angefochten",
        "annulled": "für ungültig erklärt",
        "void": "nichtig",
    }
    body = (
        f"Beschluss Nr. {resolution.number} ist {labels[new_status]}. Betroffen: "
        + ", ".join(d["label"] for d in deps)
        + ". Folgen prüfen; es wurde nichts storniert."
    )
    count = 0
    for user_id in await users_with_permission(session, tenant_id, "accounting:approve"):
        row = await notify(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            kind=NOTIFICATION_KIND,
            title=f"Beschluss Nr. {resolution.number}: Folgen prüfen",
            body=body,
            entity_type="resolution",
            entity_id=resolution.id,
        )
        count += int(row is not None)
    return count


async def review_deadline(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    resolution: Resolution,
    due_on: date | None,
    responsible_user_id: uuid.UUID | None,
    note: str | None,
) -> dict[str, Any]:
    """Deadline entry "Prüfung Anfechtung" for a resolution (see module docstring)."""
    from mhvp.accounting.models import Ledger
    from mhvp.workspace import deadlines, jobs
    from mhvp.workspace.models import DeadlineEntry, DeadlineType

    kind = await session.scalar(select(DeadlineType).where(DeadlineType.code == DEADLINE_TYPE_CODE))
    if kind is None:
        kind = DeadlineType(
            tenant_id=tenant_id,
            code=DEADLINE_TYPE_CODE,
            name=DEADLINE_TYPE_NAME,
            trigger="manual",
            is_system=True,
            is_active=True,
            source_note="Dauer nicht festgelegt (AN19-01); Datum durch Rechtsanwalt prüfen.",
            created_by=actor_user_id,
        )
        session.add(kind)
        await session.flush()
    computed = deadlines.compute_due(
        resolution.decided_on, kind.duration_months, kind.duration_days
    )
    if due_on is None and computed is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Prüfdatum angeben; für die Fristart ist keine Dauer hinterlegt.",
        )
    ledger = await session.scalar(
        select(Ledger).where(Ledger.legal_entity_id == resolution.legal_entity_id).limit(1)
    )
    property_id = ledger.property_id if ledger is not None else None
    entry = DeadlineEntry(
        tenant_id=tenant_id,
        created_by=actor_user_id,
        type_id=kind.id,
        title=f"Beschluss Nr. {resolution.number}: {resolution.subject}"[:300],
        trigger_on=resolution.decided_on,
        due_on=due_on or computed,
        due_computed=due_on is None,
        responsible_user_id=responsible_user_id,
        source_type="property",
        source_id=property_id or resolution.id,
        property_id=property_id,
        note=note,
        status="open",
    )
    session.add(entry)
    await session.flush()
    settings_row = await jobs.job_settings(session, tenant_id)
    await deadlines.materialize(
        session,
        entry,
        kind.name,
        jobs.lead_days_for(deadlines.CUSTOM_KIND, settings_row.deadline_lead_days),
    )
    return {
        "id": entry.id,
        "resolution_id": resolution.id,
        "due_on": entry.due_on,
        "due_computed": entry.due_computed,
        "verify": True,
        "deadline_type_id": kind.id,
    }
