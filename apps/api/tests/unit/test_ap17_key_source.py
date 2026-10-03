"""AP17 / GAM-108: source check of allocation keys for rented condominium units (SEV owner).

Expected (predefined): a template derived key without confirmation is refused (behaviour before
AP17); a confirmed key whose source applies from the period start passes; a confirmation that
starts after the period start does not lift the block; a key not taken from the template passes
unless the tenant switch ``allocation_key_confirmation_required`` is on.
"""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.billing import services
from mhvp.core.problems import ProblemError

PERIOD = date(2025, 1, 1)


class _Session:
    def __init__(self, required: bool | None) -> None:
        self.required = required

    async def scalar(self, _stmt: Any) -> bool | None:
        return self.required


def _key(template: bool, confirmed: bool, valid_from: date | None) -> Any:
    return SimpleNamespace(
        code="WFL",
        is_template_derived=template,
        confirmed_at=datetime(2025, 1, 2, tzinfo=UTC) if confirmed else None,
        source_valid_from=valid_from,
    )


def _check(key: Any, required: bool | None = False) -> None:
    asyncio.run(services._check_sev_key_source(_Session(required), "Pos", key, PERIOD))  # type: ignore[arg-type]


def test_template_key_without_confirmation_is_refused() -> None:
    with pytest.raises(ProblemError) as exc:
        _check(_key(True, False, None))
    assert "aus dem Muster übernommenen Schlüssel WFL" in str(exc.value.detail)


def test_confirmed_template_key_with_valid_source_passes() -> None:
    _check(_key(True, True, date(2020, 1, 1)))
    assert services.key_source_confirmed(_key(True, True, PERIOD), PERIOD)


def test_confirmation_starting_after_period_start_keeps_the_block() -> None:
    assert not services.key_source_confirmed(_key(True, True, date(2025, 2, 1)), PERIOD)
    with pytest.raises(ProblemError):
        _check(_key(True, True, date(2025, 2, 1)))


def test_own_key_passes_by_default_and_needs_confirmation_with_switch() -> None:
    _check(_key(False, False, None), required=False)
    _check(_key(False, False, None), required=None)
    with pytest.raises(ProblemError) as exc:
        _check(_key(False, False, None), required=True)
    assert "Muster" not in str(exc.value.detail)
    _check(_key(False, True, date(2024, 1, 1)), required=True)
