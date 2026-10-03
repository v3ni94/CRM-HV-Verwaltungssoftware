"""AK11 (GAI-304): ratchet on routes without a typed response model.

A route counts as untyped when it has no ``response_model``, or the model is ``Any``,
``dict[...]`` or ``list[dict[...]]``. Status 204 routes are exempt (no body). The allowlist in
``data/untyped_routes_allowlist.txt`` holds the current untyped routes ("METHODS path"); a new
untyped route fails this test. Adding a model to a listed route is welcome: remove its line
(stale lines only produce a hint so that parallel work does not break the test). Money
responses stay in the list until the JSON format of Decimal amounts is decided (number versus
string, see AJ22 open points)."""

from __future__ import annotations

import typing
import warnings
from pathlib import Path
from typing import Any

ALLOWLIST = Path(__file__).parent / "data" / "untyped_routes_allowlist.txt"


def _is_untyped(model: Any) -> bool:
    if model is None or model is typing.Any:
        return True
    origin = typing.get_origin(model) or model
    if origin is dict:
        return True
    if origin is list:
        args = typing.get_args(model)
        return bool(args) and (typing.get_origin(args[0]) or args[0]) in (dict, typing.Any)
    return False


def untyped_routes() -> set[str]:
    from mhvp.core.listparams import _walk_routes
    from mhvp.main import app

    found: set[str] = set()
    for path, route in _walk_routes(app.routes):
        if route.status_code == 204 or not _is_untyped(route.response_model):
            continue
        methods = ",".join(sorted(route.methods - {"HEAD"}))
        found.add(f"{methods} {path}")
    return found


def _allowlist() -> set[str]:
    return {
        line.strip()
        for line in ALLOWLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def test_untyped_routes_never_grow() -> None:
    current = untyped_routes()
    allowed = _allowlist()
    new = sorted(current - allowed)
    assert not new, (
        "New routes without a typed response model (add a Pydantic model with a unique, "
        f"domain prefixed name): {new}"
    )
    assert len(current) <= len(allowed)
    stale = sorted(allowed - current)
    if stale:
        warnings.warn(
            f"{len(stale)} allowlisted routes are typed now, remove them: {stale[:10]}",
            stacklevel=1,
        )


def test_ak11_typed_routes_stay_typed() -> None:
    """The routes typed in AK11 must not fall back to dict responses."""
    current = untyped_routes()
    typed = {
        "POST /api/v1/accounting/ledgers/{ledger_id}/sync-debtors",
        "POST /api/v1/accounting/ledgers/{ledger_id}/lock",
        "POST /api/v1/accounting/open-items/{open_item_id}/dunning-blocks",
        "POST /api/v1/accounting/dunning-blocks/{block_id}/release",
        "PATCH /api/v1/accounting/open-items/{open_item_id}/notice-received",
        "PUT /api/v1/hoa/correction-report-settings",
        "PUT /api/v1/hoa/circular-lower-majority",
        "PUT /api/v1/hoa/portal-circular-settings",
        "PUT /api/v1/hoa/plan-change-settings",
        "PUT /api/v1/hoa/online-meeting-settings",
        "POST /api/v1/portal/notices/{notice_id}/read",
    }
    assert not typed & current, sorted(typed & current)


def test_extra_fields_survive_typed_model() -> None:
    """``extra="allow"`` keeps fields the model does not declare (no silent field loss)."""
    from mhvp.hoa.online_meeting import HoaOnlineSettingOut, setting_out

    payload = setting_out(False, "flag")
    dumped = HoaOnlineSettingOut.model_validate(payload).model_dump()
    assert dumped["conflict_note"] == payload["conflict_note"]
    assert dumped["proxy_conflict_modes"] == payload["proxy_conflict_modes"]
