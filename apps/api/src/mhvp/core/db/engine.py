"""Engine factories. psycopg 3 serves both the async API and sync callers (ADR 0001)."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mhvp.core.config import Settings


def create_app_engine(settings: Settings) -> AsyncEngine:
    """Async engine for the runtime role (mhvp_app)."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def create_sync_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
