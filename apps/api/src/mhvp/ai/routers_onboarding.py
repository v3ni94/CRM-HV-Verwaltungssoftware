"""Onboarding helpers (10.2 step 4, M7-02): person match preview and tenant thresholds."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from mhvp.ai import person_match, takeover_defaults
from mhvp.ai.models import OnboardingMatchSetting
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings

router = APIRouter(tags=["KI Onboarding"])
READ = require_permission("ai:read")
SETTINGS = require_permission("tenant_settings:update")
SETTINGS_READ = require_permission("tenant_settings:read")


class OnboardingMatchIn(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    iban: str | None = Field(default=None, max_length=40)
    postal_code: str | None = Field(default=None, max_length=20)
    street: str | None = Field(default=None, max_length=200)


class OnboardingMatchCandidateOut(BaseModel):
    contact_id: str
    name: str
    score: float
    reasons: list[str]


class OnboardingMatchOut(BaseModel):
    decision: str
    candidates: list[OnboardingMatchCandidateOut]


class OnboardingMatchBatchIn(BaseModel):
    persons: list[OnboardingMatchIn] = Field(min_length=1, max_length=500)


class OnboardingMatchBatchOut(BaseModel):
    """One result per person, in the order of the request (preview table of the import)."""

    results: list[OnboardingMatchOut]
    link_threshold: Decimal
    suggest_threshold: Decimal


class OnboardingMatchSettingIn(BaseModel):
    link_threshold: Decimal = Field(ge=Decimal("0.01"), le=Decimal("1"), decimal_places=2)
    suggest_threshold: Decimal = Field(ge=Decimal("0.01"), le=Decimal("1"), decimal_places=2)

    @model_validator(mode="after")
    def _order(self) -> "OnboardingMatchSettingIn":
        if self.suggest_threshold > self.link_threshold:
            raise ValueError("suggest_threshold darf link_threshold nicht überschreiten")
        return self


class OnboardingMatchSettingOut(BaseModel):
    link_threshold: Decimal
    suggest_threshold: Decimal


@router.post(
    "/onboarding/person-match",
    summary="Personenabgleich gegen das Adressbuch (Vorschlag, schreibt nichts)",
)
async def person_match_preview(
    body: OnboardingMatchIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> OnboardingMatchOut:
    data: dict[str, Any] = body.model_dump()
    async with tenant_tx(request, principal) as session:
        result = await person_match.match_person(session, data)
    return OnboardingMatchOut(
        decision=result.decision,
        candidates=[
            OnboardingMatchCandidateOut(
                contact_id=str(c.contact_id), name=c.name, score=c.score, reasons=c.reasons
            )
            for c in result.candidates
        ],
    )


@router.post(
    "/onboarding/person-match-batch",
    summary="Personenabgleich für viele Personen als Vorschau (schreibt nichts)",
)
async def person_match_batch(
    body: OnboardingMatchBatchIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> OnboardingMatchBatchOut:
    """Table preview of the import dialog (10.2 step 4): per person the decision (link, suggest,
    none) and the best candidates with reasons under the thresholds of the tenant. Nothing is
    linked or created here; the apply step decides again with the same rules."""
    async with tenant_tx(request, principal) as session:
        link, suggest = await person_match.load_thresholds(session)
        results = [
            await person_match.match_person(session, person.model_dump()) for person in body.persons
        ]
    return OnboardingMatchBatchOut(
        results=[
            OnboardingMatchOut(
                decision=r.decision,
                candidates=[
                    OnboardingMatchCandidateOut(
                        contact_id=str(c.contact_id), name=c.name, score=c.score, reasons=c.reasons
                    )
                    for c in r.candidates
                ],
            )
            for r in results
        ],
        link_threshold=link,
        suggest_threshold=suggest,
    )


@router.get("/onboarding/match-settings", summary="Schwellwerte des Personenabgleichs")
async def get_match_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> OnboardingMatchSettingOut:
    async with tenant_tx(request, principal) as session:
        link, suggest = await person_match.load_thresholds(session)
    return OnboardingMatchSettingOut(link_threshold=link, suggest_threshold=suggest)


@router.put("/onboarding/match-settings", summary="Schwellwerte des Personenabgleichs setzen")
async def put_match_settings(
    body: OnboardingMatchSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> OnboardingMatchSettingOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(OnboardingMatchSetting))
        if row is None:
            row = OnboardingMatchSetting(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                link_threshold=body.link_threshold,
                suggest_threshold=body.suggest_threshold,
            )
            session.add(row)
        else:
            row.link_threshold = body.link_threshold
            row.suggest_threshold = body.suggest_threshold
            row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="onboarding_match_setting.updated",
            entity_type="onboarding_match_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "link_threshold": str(body.link_threshold),
                "suggest_threshold": str(body.suggest_threshold),
            },
        )
        return OnboardingMatchSettingOut(
            link_threshold=row.link_threshold, suggest_threshold=row.suggest_threshold
        )


class OnboardingTakeoverTicketDefaultsIn(BaseModel):
    """Empty values mean: tickets of the takeover checklist get no team or no assignee."""

    team_id: uuid.UUID | None = None
    assignee_user_id: uuid.UUID | None = None


class OnboardingTakeoverTicketDefaultsOut(OnboardingTakeoverTicketDefaultsIn):
    pass


@router.get(
    "/onboarding/takeover-ticket-defaults",
    summary="Standardteam und Zuständiger der Übernahme-Tickets",
)
async def get_takeover_ticket_defaults(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> OnboardingTakeoverTicketDefaultsOut:
    async with tenant_tx(request, principal) as session:
        values = await takeover_defaults.load(session)
    return OnboardingTakeoverTicketDefaultsOut(
        team_id=values.team_id, assignee_user_id=values.assignee_user_id
    )


@router.put(
    "/onboarding/takeover-ticket-defaults",
    summary="Standardteam und Zuständigen der Übernahme-Tickets setzen",
)
async def put_takeover_ticket_defaults(
    body: OnboardingTakeoverTicketDefaultsIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> OnboardingTakeoverTicketDefaultsOut:
    """V06-01: applies to tickets created from the takeover checklist after the change
    (existing tickets stay unchanged). Both values empty means no assignment."""
    async with tenant_tx(request, principal) as session:
        await takeover_defaults.validate(
            session, principal.tenant_id, body.team_id, body.assignee_user_id
        )
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        values = await takeover_defaults.save(
            session,
            row,
            takeover_defaults.TakeoverTicketDefaults(body.team_id, body.assignee_user_id),
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="onboarding_takeover_ticket_defaults.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "team_id": str(values.team_id) if values.team_id else None,
                "assignee_user_id": str(values.assignee_user_id)
                if values.assignee_user_id
                else None,
            },
        )
        return OnboardingTakeoverTicketDefaultsOut(
            team_id=values.team_id, assignee_user_id=values.assignee_user_id
        )
