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
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.platform.models import TenantSettings

KEY = "ai_automation"
SWITCHES: tuple[str, ...] = ("rent_increase_check", "batch_mail_classification")


def read_switches(settings: TenantSettings | None) -> dict[str, bool]:
    raw = ((settings.objektakte_classification if settings else {}) or {}).get(KEY) or {}
    return {name: bool(raw.get(name, False)) for name in SWITCHES}


async def is_enabled(session: AsyncSession, name: str) -> bool:
    document = await session.scalar(select(TenantSettings.objektakte_classification))
    raw = (document or {}).get(KEY) or {}
    return bool(raw.get(name, False))


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
