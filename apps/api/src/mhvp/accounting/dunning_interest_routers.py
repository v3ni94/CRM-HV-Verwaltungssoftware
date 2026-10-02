"""Day count switch and Basiszinssatz hint of the default interest (AI03, GAH-110, GAH-113).

The day count is a tenant switch with the former calculation (days/365) as default; which
method a claim requires stays an open question (docs/OPEN_QUESTIONS.md AI03-01). The
Basiszinssatz is never fetched or assumed: the hint only reports that no rate is maintained
for the current half year, and the check points remind of the change dates (01.01., 01.07.)."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mhvp.accounting import dunning, rule_register
from mhvp.accounting.models import RuleVersion
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/dunning-interest", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")

BASE_RATE_RULE_ID = "AI03-Basiszinssatz"
QUESTION = "AI03-01"


class DunningInterestDayCountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day_count: Literal["act_365_fixed", "act_act"]


async def _out(session: Any) -> dict[str, Any]:
    today = local_today()
    rates = await dunning.interest_rates(session)
    latest = max((d for d, _ in rates), default=None)
    hint = dunning.base_rate_hint(rates, today)
    return {
        "day_count": await dunning.interest_day_count(session),
        "day_counts": dunning.DAY_COUNT_LABELS,
        "default_day_count": dunning.DAY_COUNT_FIXED,
        "question": QUESTION,
        "latest_rate_valid_from": latest,
        "current_half_year_from": dunning.base_rate_boundary(today),
        "next_change_dates": dunning.next_base_rate_dates(today),
        "base_rate_stale": hint is not None,
        "base_rate_hint": hint,
    }


@router.get(
    "",
    summary="Zinstagemethode und Hinweis zum Basiszinssatz",
    dependencies=[Depends(strict_query)],
)
async def get_dunning_interest(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await _out(session)


@router.put("", summary="Zinstagemethode setzen (Mandantenschalter)")
async def put_dunning_interest(
    body: DunningInterestDayCountIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        if row is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Mandanteneinstellungen sind nicht angelegt."
            )
        before = (row.sources or {}).get(dunning.DAY_COUNT_KEY, dunning.DAY_COUNT_FIXED)
        row.sources = {**(row.sources or {}), dunning.DAY_COUNT_KEY: body.day_count}
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="dunning.interest_day_count_changed",
            entity_type="tenant",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": body.day_count},
        )
        return await _out(session)


@router.post(
    "/base-rate-checkpoints",
    summary="Prüfpunkte zum Basiszinssatz (01.01. und 01.07.) als Entwurf anlegen",
)
async def seed_base_rate_checkpoints(
    request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> list[dict[str, Any]]:
    """Creates the check points of the next two change dates in the rule register (group
    Prüfpunkt); the lead time of the check point list is the Vorfrist. Idempotent per date."""
    async with tenant_tx(request, principal) as session:
        existing = (
            await session.scalars(
                select(RuleVersion).where(RuleVersion.rule_id == BASE_RATE_RULE_ID)
            )
        ).all()
        version = max((r.version for r in existing), default=0)
        created: list[RuleVersion] = []
        for day in dunning.next_base_rate_dates(local_today()):
            if any(r.effective_from == day for r in existing):
                continue
            version += 1
            row = RuleVersion(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                rule_id=BASE_RATE_RULE_ID,
                version=version,
                title=f"Prüfpunkt Basiszinssatz zum {day.strftime('%d.%m.%Y')} pflegen",
                effective_from=day,
                case_groups=[rule_register.CHECKPOINT_GROUP],
                source_status="Entwurf, Master-Prompt 7.5; Wert nur aus amtlicher Veröffentlichung",
                change_reason=(
                    "Hinweis ohne Rechtsfolge: neuen Basiszinssatz mit Quelle unter "
                    "Mahnwesen erfassen; die Plattform übernimmt keinen Wert selbst."
                ),
                status="draft",
            )
            session.add(row)
            await session.flush()
            created.append(row)
        return [
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "version": r.version,
                "title": r.title,
                "effective_from": r.effective_from,
                "status": r.status,
            }
            for r in created
        ]
