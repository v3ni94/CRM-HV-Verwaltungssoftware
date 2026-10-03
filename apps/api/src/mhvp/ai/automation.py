"""Tenant switches of the automatic AI runs (Q14-02, M7-07, package R09).

Both switches default to off. They live under the key ``ai_automation`` of the JSON document
``TenantSettings.objektakte_classification`` (same pattern as the ``local_model`` flag there),
because this package adds no migration; a dedicated column is an open point (docs/OPEN_QUESTIONS.md
R09-01). A switch never replaces the provider release: the gateway still requires a released
provider with DPA evidence, a budget and the masking of the input (rule 0.1.13).

* ``rent_increase_check``: a new or changed rent increase case in the status draft starts the AI
  task ``rent_increase_check`` (hints only, never a release, never a legal review).
* ``batch_mail_classification``: the nightly collective run classifies inbound mails that have
  no suggestion yet (``communication.batch_classify``).

Package AM04 (GAJ-605 to GAJ-607) adds three switches that default to on, because they cover
paths that ran unconditionally before (no silent loss of function); whether the default turns
to off is open (docs/OPEN_QUESTIONS.md AM04-01 to AM04-03):

* ``realtime_mail_classification``: the per mail suggestion (classification and reply draft)
  on inbound ticket mails (``communication.services._queue_suggestion``).
* ``master_data_change_proposals``: the per mail contact master data change proposal
  (``tickets.proposals.queue_for_message``); the deterministic Lexware copy check stays on.
* ``automation_ai_task``: the automation action ``ai_task`` (rule execution and creation).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.platform.models import TenantSettings

KEY = "ai_automation"
SWITCHES: tuple[str, ...] = (
    "rent_increase_check",
    "batch_mail_classification",
    "realtime_mail_classification",
    "master_data_change_proposals",
    "automation_ai_task",
)
DEFAULTS: dict[str, bool] = {
    "realtime_mail_classification": True,
    "master_data_change_proposals": True,
    "automation_ai_task": True,
}


def read_switches(settings: TenantSettings | None) -> dict[str, bool]:
    raw = ((settings.objektakte_classification if settings else {}) or {}).get(KEY) or {}
    return {name: bool(raw.get(name, DEFAULTS.get(name, False))) for name in SWITCHES}


async def is_enabled(session: AsyncSession, name: str) -> bool:
    document = await session.scalar(select(TenantSettings.objektakte_classification))
    raw = (document or {}).get(KEY) or {}
    return bool(raw.get(name, DEFAULTS.get(name, False)))


def write_switches(settings: TenantSettings, values: dict[str, bool | None]) -> dict[str, bool]:
    """Merges the given switches (``None`` keeps the stored value) and returns all of them."""
    document: dict[str, Any] = dict(settings.objektakte_classification or {})
    current = read_switches(settings)
    for name, value in values.items():
        if name in SWITCHES and value is not None:
            current[name] = bool(value)
    document[KEY] = current
    settings.objektakte_classification = document  # reassigned, so the JSONB change is tracked
    return current
