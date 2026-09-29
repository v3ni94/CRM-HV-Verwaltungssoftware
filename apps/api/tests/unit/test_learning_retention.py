"""Retention of the learning store (operator decision M12-06, OPEN_QUESTIONS M12-09):
anonymisation instead of deletion, pure functions with fixed expectations, beat entry."""

from __future__ import annotations

from mhvp.banking import learning
from mhvp.worker import create_celery


def test_anonymise_features_nulls_the_fingerprint_only() -> None:
    features = {
        "amount": "250.00",
        "direction": "credit",
        "counterpart_iban_fingerprint": "a" * 64,
        "has_mandate_reference": True,
        "open_item_ids": ["oi-1"],
    }
    out = learning.anonymise_features(features)
    assert out == {
        "amount": "250.00",
        "direction": "credit",
        "counterpart_iban_fingerprint": None,
        "has_mandate_reference": True,
        "open_item_ids": ["oi-1"],
    }
    assert features["counterpart_iban_fingerprint"] == "a" * 64  # input untouched


def test_anonymise_proposals_keeps_outcome_drops_text() -> None:
    proposals = [
        {
            "source": "match",
            "kind": "full",
            "unambiguous": True,
            "confidence": 0.85,
            "splits": [{"open_item_id": "oi-1", "amount": "250.00"}],
            "reasoning": ["Vertragsnummer 4711 im Verwendungszweck", "Zahler Max Muster"],
            "evidence": {"lines": [{"account_number": "040100"}]},
            "label": "Hausgeld Muster",
        }
    ]
    assert learning.anonymise_proposals(proposals) == [
        {
            "source": "match",
            "kind": "full",
            "unambiguous": True,
            "confidence": 0.85,
            "splits": [{"open_item_id": "oi-1", "amount": "250.00"}],
        }
    ]


def test_retention_months_and_beat_entry(settings: object) -> None:
    assert learning.LEARNING_RETENTION_MONTHS == 24
    entry = create_celery(settings).conf.beat_schedule["banking-learning-retention"]  # type: ignore[arg-type]
    assert entry["task"] == "mhvp.banking.learning_retention"
