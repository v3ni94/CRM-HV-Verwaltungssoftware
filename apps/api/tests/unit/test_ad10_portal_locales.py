"""AD10 (GB14-01): the API list of portal languages matches the portal message files.

Expected by hand: apps/web-portal/messages holds de.json and en.json, so the default setting
``de,en`` must equal that set; a setting with a further code is accepted by the validator."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from mhvp.portal.routers import portal_locales

MESSAGES = Path(__file__).resolve().parents[4] / "apps" / "web-portal" / "messages"


def _settings(raw: str) -> Any:
    return cast(Any, SimpleNamespace(portal_locales=raw))


def test_default_equals_message_files() -> None:
    files = sorted(p.stem for p in MESSAGES.glob("*.json"))
    assert files, "message files not found"
    assert sorted(portal_locales(_settings("de,en"))) == files


def test_setting_extends_and_blank_falls_back() -> None:
    assert portal_locales(_settings(" de, en ,xx ")) == ("de", "en", "xx")
    assert portal_locales(_settings(" , ")) == ("de", "en")
