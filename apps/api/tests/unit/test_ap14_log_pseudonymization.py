"""GAM-409: personal keys in log records are pseudonymised."""

import json

import structlog

from mhvp.core.logging import _SHARED_PROCESSORS
from mhvp.core.redaction import PSEUDONYM_PREFIX, pseudonym, pseudonymize_event


def test_personal_keys_are_pseudonymised() -> None:
    out = pseudonymize_event(
        None,
        "info",
        {
            "event": "gmail_push_received",
            "address": "max.mustermann@example.org",
            "iban": "DE89370400440532013000",
            "to": ["a@example.org", "b@example.org"],
            "count": 3,
            "extra": {"phone": "+49 30 123", "status": "ok"},
        },
    )
    assert out["event"] == "gmail_push_received"
    assert out["address"].startswith(PSEUDONYM_PREFIX)
    assert "mustermann" not in json.dumps(out)
    assert "DE89" not in json.dumps(out)
    assert all(v.startswith(PSEUDONYM_PREFIX) for v in out["to"])
    assert out["extra"]["phone"].startswith(PSEUDONYM_PREFIX)
    assert out["extra"]["status"] == "ok"
    assert out["count"] == 3


def test_pseudonym_is_stable_and_case_insensitive() -> None:
    assert pseudonym("A@Example.org") == pseudonym("a@example.org")
    assert pseudonym("a@example.org") != pseudonym("b@example.org")


def test_processor_is_in_shared_chain() -> None:
    assert pseudonymize_event in _SHARED_PROCESSORS
    record = structlog.processors.JSONRenderer()(
        None, "info", pseudonymize_event(None, "info", {"event": "x", "email": "p@x.de"})
    )
    assert "p@x.de" not in record
