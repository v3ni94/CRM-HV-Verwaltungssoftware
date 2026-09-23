"""FastAPI application factory.

``uvicorn mhvp.main:app`` resolves ``app`` lazily (module ``__getattr__``), so importing this
module has no side effects and tests build their own app with :func:`create_app`.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from mhvp.contacts.routers import router as contacts_router
from mhvp.contracts.routers import router as contracts_router
from mhvp.core import crypto, health
from mhvp.core.auth import oidc
from mhvp.core.auth.routers import router as auth_router
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.health import ReadinessCheck
from mhvp.core.logging import configure_logging
from mhvp.core.middleware import CorrelationIdMiddleware
from mhvp.core.problems import install_problem_handlers
from mhvp.core.release_gates import ClosedReleaseGateResolver, ReleaseGateResolver
from mhvp.core.storage import create_s3_client
from mhvp.documents.routers import router as documents_router
from mhvp.platform.gates import DbReleaseGateResolver
from mhvp.platform.routers import platform_router, tenant_router
from mhvp.properties.routers import router as properties_router

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

API_PREFIX = "/api/v1"


@dataclass(slots=True)
class Resources:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    s3: "S3Client | None"


ReadinessChecksFactory = Callable[[Settings, Resources], dict[str, ReadinessCheck]]


def default_readiness_checks(settings: Settings, resources: Resources) -> dict[str, ReadinessCheck]:
    return {
        "database": health.database_check(resources.engine),
        "database_role": health.database_role_check(resources.engine),
        "migrations": health.migrations_check(resources.engine, settings.alembic_config),
        "redis": health.redis_check(resources.redis),
        "object_storage": health.object_storage_check(settings, resources.s3),
    }


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks_factory: ReadinessChecksFactory | None = None,
    release_gate_resolver: ReleaseGateResolver | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    checks_factory = readiness_checks_factory or default_readiness_checks

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        timeout = settings.health_check_timeout_seconds
        if settings.master_key is not None:
            crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
        engine = create_app_engine(settings)
        resources = Resources(
            engine=engine,
            session_factory=create_session_factory(engine),
            redis=Redis.from_url(
                settings.redis_url.get_secret_value(),
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
            ),
            s3=create_s3_client(settings) if settings.s3_configured else None,
        )
        app.state.resources = resources
        app.state.readiness_checks = checks_factory(settings, resources)
        if release_gate_resolver is None:
            app.state.release_gate_resolver = DbReleaseGateResolver(resources.session_factory)
        try:
            yield
        finally:
            await resources.redis.aclose()
            await resources.engine.dispose()

    app = FastAPI(
        title="MH Verwaltungsplattform API",
        version=settings.app_version,
        description=(
            "Offene REST-API der MH Verwaltungsplattform. Fachbegriffe deutsch, Feldnamen "
            "englisch. Fehler als RFC 9457 Problem Details (application/problem+json)."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.release_gate_resolver = release_gate_resolver or ClosedReleaseGateResolver()
    install_problem_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(oidc.router, prefix=API_PREFIX)
    app.include_router(oidc.well_known)
    app.include_router(platform_router, prefix=API_PREFIX)
    app.include_router(tenant_router, prefix=API_PREFIX)
    app.include_router(contacts_router, prefix=API_PREFIX)
    app.include_router(properties_router, prefix=API_PREFIX)
    app.include_router(contracts_router, prefix=API_PREFIX)
    app.include_router(documents_router, prefix=API_PREFIX)
    app.add_middleware(CorrelationIdMiddleware)
    return app


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return create_app()
    raise AttributeError(name)
