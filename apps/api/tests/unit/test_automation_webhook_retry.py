"""Unit tests of the rule webhook outbox (A82): state transitions after an attempt follow the
schedule of ``mhvp.core.webhooks``."""

from datetime import UTC, datetime, timedelta

from mhvp.automation.models import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_SUCCEEDED,
    AutomationWebhookDelivery,
)
from mhvp.automation.services import redeliver_webhook, schedule_after_attempt
from mhvp.core.webhooks import RETRY_SCHEDULE_SECONDS

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _delivery() -> AutomationWebhookDelivery:
    return AutomationWebhookDelivery(status=DELIVERY_PENDING, attempts=0)


def test_failures_walk_the_staged_schedule_then_fail() -> None:
    delivery = _delivery()
    for index, delay in enumerate(RETRY_SCHEDULE_SECONDS):
        delivery.attempts += 1
        schedule_after_attempt(delivery, ok=False, now=NOW)
        assert delivery.status == DELIVERY_PENDING, index
        assert delivery.next_attempt_at == NOW + timedelta(seconds=delay)
    delivery.attempts += 1
    schedule_after_attempt(delivery, ok=False, now=NOW)
    assert delivery.status == DELIVERY_FAILED
    assert delivery.next_attempt_at is None
    assert delivery.attempts == len(RETRY_SCHEDULE_SECONDS) + 1


def test_success_and_redelivery() -> None:
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
