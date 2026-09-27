"""Unit tests of the rule webhook outbox (A82, M9-08): state transitions after an attempt
follow the retry plan 1, 5, 15, 60 minutes, at most 5 attempts, then ``dead``."""

from datetime import UTC, datetime, timedelta

from mhvp.automation.models import (
    DELIVERY_DEAD,
    DELIVERY_PENDING,
    DELIVERY_SUCCEEDED,
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_RETRY_SCHEDULE_SECONDS,
    AutomationWebhookDelivery,
)
from mhvp.automation.services import redeliver_webhook, schedule_after_attempt

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _delivery() -> AutomationWebhookDelivery:
    return AutomationWebhookDelivery(status=DELIVERY_PENDING, attempts=0)


def test_retry_plan_is_1_5_15_60_minutes() -> None:
    assert WEBHOOK_RETRY_SCHEDULE_SECONDS == (60, 300, 900, 3600)


def test_failures_walk_the_staged_schedule_then_go_dead() -> None:
    delivery = _delivery()
    assert WEBHOOK_MAX_ATTEMPTS == 5
    for index, delay in enumerate(WEBHOOK_RETRY_SCHEDULE_SECONDS):
        delivery.attempts += 1
        schedule_after_attempt(delivery, ok=False, now=NOW)
        assert delivery.status == DELIVERY_PENDING, index
        assert delivery.next_attempt_at == NOW + timedelta(seconds=delay)
    # 5th attempt: the plan is exhausted, the row is dead, no further attempt is scheduled.
    delivery.attempts += 1
    schedule_after_attempt(delivery, ok=False, now=NOW)
    assert delivery.status == DELIVERY_DEAD
    assert delivery.next_attempt_at is None
    assert delivery.attempts == WEBHOOK_MAX_ATTEMPTS == len(WEBHOOK_RETRY_SCHEDULE_SECONDS) + 1


def test_success_and_redelivery_keeps_attempt_count() -> None:
    delivery = _delivery()
    delivery.attempts = 3
    schedule_after_attempt(delivery, ok=True, now=NOW)
    assert delivery.status == DELIVERY_SUCCEEDED
    assert delivery.delivered_at == NOW
    assert delivery.next_attempt_at is None
    redeliver_webhook(delivery, now=NOW + timedelta(hours=1))
    assert delivery.status == DELIVERY_PENDING
    assert delivery.next_attempt_at == NOW + timedelta(hours=1)
    assert delivery.attempts == 3


def test_redelivery_of_a_dead_row_resets_the_attempt_budget() -> None:
    """M9-08: once the operator has looked at a dead delivery and asks for a resend, it gets
    a fresh budget of 5 attempts instead of being immediately dead again on the next failure."""
    delivery = _delivery()
    delivery.attempts = WEBHOOK_MAX_ATTEMPTS
    delivery.status = DELIVERY_DEAD
    delivery.owner_notified = True
    redeliver_webhook(delivery, now=NOW)
    assert delivery.status == DELIVERY_PENDING
    assert delivery.attempts == 0
    assert delivery.owner_notified is False
