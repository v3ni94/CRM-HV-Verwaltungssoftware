"""Ratings of completed work orders (GAF-35, 14 Dienstleister, AE30-02).

One rating per work order and party (management or affected resident), stars 1 to 5 and an
optional free text. Ratings are internal: the provider never sees them. Display follows the
tenant switch ``provider_rating_display`` (off, staff, all); the free text is never part of an
aggregate. Ratings never change money, a posting or a release gate."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import OrderStatus, WorkOrder, WorkOrderRating

RATABLE = (OrderStatus.DONE, OrderStatus.INVOICED, OrderStatus.ACCEPTED)


class WorkOrderRatingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


def rating_out(row: WorkOrderRating, *, with_comment: bool) -> dict[str, Any]:
    return {
        "id": row.id,
        "party": row.party,
        "stars": row.stars,
        "comment": row.comment if with_comment else None,
        "created_at": row.created_at,
    }


async def add_rating(
    session: AsyncSession,
    order: WorkOrder,
    party: str,
    body: WorkOrderRatingIn,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
) -> WorkOrderRating:
    """Store the rating of one party. 409 when the order is not completed or the party has
    rated already (a rating is never overwritten)."""
    if order.status not in RATABLE:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Bewertung erst nach Abschluss des Auftrags möglich."
        )
    existing = await session.scalar(
        select(WorkOrderRating.id).where(
            WorkOrderRating.work_order_id == order.id, WorkOrderRating.party == party
        )
    )
    if existing is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Dieser Auftrag wurde bereits bewertet.")
    row = WorkOrderRating(
        tenant_id=tenant_id,
        work_order_id=order.id,
        party=party,
        stars=body.stars,
        comment=(body.comment or "").strip() or None,
        rated_by_user_id=user_id,
        rated_by_contact_id=contact_id,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Dieser Auftrag wurde bereits bewertet."
        ) from None
    return row


async def provider_counts(session: AsyncSession, provider_contact_id: uuid.UUID) -> dict[int, int]:
    """Star counts of a provider over both parties (no free text)."""
    rows = await session.execute(
        select(WorkOrderRating.stars, func.count())
        .join(WorkOrder, WorkOrder.id == WorkOrderRating.work_order_id)
        .where(WorkOrder.provider_contact_id == provider_contact_id)
        .group_by(WorkOrderRating.stars)
    )
    return {int(stars): int(n) for stars, n in rows.all()}
