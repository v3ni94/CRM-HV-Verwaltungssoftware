"""AK02 (GAI-307): one helper for domain events with old and new values on money routes.

Rows are snapshotted into JSON safe dicts (Decimal, date and UUID as strings) so that the event
payload and the audit row (``core.events.emit`` with ``changes``) stay readable without the ORM.
"""

import uuid
from collections.abc import Iterable
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import diff, emit


def snap(row: Any, fields: Iterable[str]) -> dict[str, Any]:
    """JSON safe snapshot of the given attributes; ``None`` row gives an empty dict."""
    if row is None:
        return {}
    data: dict[str, Any] = to_jsonable_python({name: getattr(row, name) for name in fields})
    return data


async def record_change(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    before: dict[str, Any],
    after: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit ``type`` with the new state as payload and the changed keys as audit row.

    Deletions pass ``after={}``: the payload then carries the removed state so the event alone
    shows what was deleted.
    """
    body = dict(payload or (after if after else {"deleted": before}))
    await emit(
        session,
        tenant_id=tenant_id,
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        payload=body,
        changes=diff(before, after),
    )
