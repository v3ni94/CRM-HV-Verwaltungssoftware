"""Coverage: workspace service helpers (M9) without database: operator calendar day of UTC
timestamps and the idempotent ``notify`` helper with a fake session."""

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

from mhvp.workspace import services
from mhvp.workspace.models import Notification


class _FakeSession:
    def __init__(self, existing: Any = None) -> None:
        self.added: list[Any] = []
        self.queries = 0
        self._existing = existing

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def scalar(self, query: Any) -> Any:
        self.queries += 1
        return self._existing


def test_local_date_uses_operator_time_zone() -> None:
    # 23:30 UTC in summer is already the next day in Europe/Berlin (UTC+2).
    assert services.local_date(datetime(2026, 7, 1, 23, 30, tzinfo=UTC)) == date(2026, 7, 2)
    # 23:30 UTC in winter is 00:30 of the next day (UTC+1).
    assert services.local_date(datetime(2026, 1, 1, 23, 30, tzinfo=UTC)) == date(2026, 1, 2)
    assert services.local_date(datetime(2026, 1, 1, 22, 30, tzinfo=UTC)) == date(2026, 1, 1)
    assert isinstance(services.local_today(), date)


def test_remind_days_table() -> None:
    assert services.REMIND_DAYS == {"14d": 14, "1m": 30, "3m": 91, "6m": 182}
    assert services.DEFAULT_REMIND_DAYS == 14


def test_notify_without_entity_never_deduplicates() -> None:
    session = _FakeSession(existing=uuid.uuid4())
    tenant, user = uuid.uuid4(), uuid.uuid4()
    row = asyncio.run(
        services.notify(
            session,  # type: ignore[arg-type]
            tenant_id=tenant,
            user_id=user,
            kind="info",
            title="Hallo",
        )
    )
    assert isinstance(row, Notification)
    assert session.queries == 0  # no lookup without entity id
    assert session.added == [row]
    assert row.tenant_id == tenant
    assert row.user_id == user
    assert row.body is None
    assert row.entity_type is None
    assert row.entity_id is None


def test_notify_with_entity_skips_existing_unread() -> None:
    session = _FakeSession(existing=uuid.uuid4())
    row = asyncio.run(
        services.notify(
            session,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            kind="maintenance_due",
            title="Fällig",
            body="x",
            entity_type="maintenance_item",
            entity_id=uuid.uuid4(),
        )
    )
    assert row is None
    assert session.queries == 1
    assert session.added == []


def test_notify_with_entity_creates_when_none_unread() -> None:
    session = _FakeSession(existing=None)
    entity = uuid.uuid4()
    row = asyncio.run(
        services.notify(
            session,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            kind="maintenance_due",
            title="Fällig",
            body="x",
            entity_type="maintenance_item",
            entity_id=entity,
        )
    )
    assert row is not None
    assert row.entity_id == entity
    assert row.entity_type == "maintenance_item"
    assert session.added == [row]
