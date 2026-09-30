"""Token based subscription address for the calendar feed (M23-06, 13.5 Kalender ICS).

External calendar clients cannot log in. A user creates a personal feed token; only its hash is
stored, the address is shown once. The feed carries the same entries as the logged in feed
(own and shared entries, derived dates when the creator may read contracts and properties at
creation time). The token can be revoked; a new one replaces the old one."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import Boolean, DateTime, Index, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(tags=["Kommunikation"])
FEED = require_permission("tenant_settings:read")


class CalendarFeedToken(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "calendar_feed_token"
    __table_args__ = (
        Index("ux_calendar_feed_token_hash", "token_hash", unique=True),
        Index("ix_calendar_feed_token_user", "tenant_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    include_contracts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.text("false")
    )
    include_properties: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.text("false")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/workspace/calendar-feed/token", status_code=201, summary="Kalender-Abo erzeugen")
async def create_feed_token(
    request: Request, principal: TenantPrincipal = Depends(FEED)
) -> dict[str, Any]:
    """Replaces an existing token of the user. The token is part of the response only once."""
    token = f"{principal.tenant_id.hex}.{secrets.token_urlsafe(32)}"
    async with tenant_tx(request, principal) as session:
        now = datetime.now(UTC)
        for old in (
            await session.scalars(
                select(CalendarFeedToken).where(
                    CalendarFeedToken.user_id == principal.user_id,
                    CalendarFeedToken.revoked_at.is_(None),
                )
            )
        ).all():
            old.revoked_at = now
        session.add(
            CalendarFeedToken(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                user_id=principal.user_id,
                token_hash=_hash(token),
                include_contracts=principal.has("contracts:read"),
                include_properties=principal.has("properties:read"),
            )
        )
        await session.flush()
    return {
        "token": token,
        "path": f"/api/v1/workspace/calendar-feed/{token}.ics",
        "note": "Die Adresse wird nur einmal angezeigt und gilt wie ein Passwort.",
    }


@router.get("/workspace/calendar-feed/token", summary="Status des Kalender-Abos")
async def feed_token_status(
    request: Request, principal: TenantPrincipal = Depends(FEED)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(CalendarFeedToken).where(
                CalendarFeedToken.user_id == principal.user_id,
                CalendarFeedToken.revoked_at.is_(None),
            )
        )
        return {
            "active": row is not None,
            "created_at": row.created_at if row else None,
            "last_used_at": row.last_used_at if row else None,
        }


@router.delete("/workspace/calendar-feed/token", status_code=204, summary="Kalender-Abo widerrufen")
async def revoke_feed_token(request: Request, principal: TenantPrincipal = Depends(FEED)) -> None:
    async with tenant_tx(request, principal) as session:
        for row in (
            await session.scalars(
                select(CalendarFeedToken).where(
                    CalendarFeedToken.user_id == principal.user_id,
                    CalendarFeedToken.revoked_at.is_(None),
                )
            )
        ).all():
            row.revoked_at = datetime.now(UTC)


@router.get(
    "/workspace/calendar-feed/{token}.ics",
    summary="Kalender-Abo für externe Kalender (Token, ohne Anmeldung)",
)
async def feed(token: str, request: Request) -> PlainTextResponse:
    from mhvp.communication.dispatch import build_ics

    try:
        tenant_id = uuid.UUID(hex=token.split(".", 1)[0])
    except ValueError as exc:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND) from exc
    async with tenant_transaction(sessions(request), tenant_id) as session:
        row = await session.scalar(
            select(CalendarFeedToken).where(CalendarFeedToken.token_hash == _hash(token))
        )
        if row is None or row.revoked_at is not None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.last_used_at = datetime.now(UTC)
        body = await build_ics(
            session,
            row.user_id,
            contracts=row.include_contracts,
            properties=row.include_properties,
        )
    return PlainTextResponse(body, media_type="text/calendar")
