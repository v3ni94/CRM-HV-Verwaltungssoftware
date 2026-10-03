"""Shared completion event of a work order (GAK-302, section 12).

The catalogue name ``work_order.completed`` is emitted next to ``work_order.done`` on every
path that moves an order to DONE: CRM, provider portal and automation action. A repeated
call cannot double the event because ORDER_FLOW allows the transition DONE only once.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit


async def emit_completed_if_done(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    new_status: Any,
    actor_user_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Emit ``work_order.completed`` when ``new_status`` is DONE; returns whether it did."""
    if getattr(new_status, "value", new_status) != "done":
        return False
    await emit(
        session,
        tenant_id=tenant_id,
        type="work_order.completed",
        entity_type="work_order",
        entity_id=order_id,
        actor_user_id=actor_user_id,
        payload=payload or {},
    )
    return True
