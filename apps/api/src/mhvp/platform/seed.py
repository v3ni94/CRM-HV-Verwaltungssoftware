"""``python -m mhvp.platform.seed``: tenants from seeds (5.2), optional initial administrator.

The initial administrator comes from ``MHVP_SEED_ADMIN_EMAIL`` / ``MHVP_SEED_ADMIN_PASSWORD``
(never from the repository); the account becomes tenant administrator of both tenants and
must set up TOTP at first login. No release gate is opened.
"""

import asyncio
import os
import sys

import mhvp.models  # noqa: F401  (registers every mapped table so cross-module FKs resolve)
from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.logging import configure_logging, get_logger
from mhvp.platform.services import add_member, create_user, seed_tenants


async def run() -> int:
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.seed")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenants = await seed_tenants(factory)
        log.info("tenants_seeded", tenants=sorted(tenants))
        email = os.environ.get("MHVP_SEED_ADMIN_EMAIL")
        password = os.environ.get("MHVP_SEED_ADMIN_PASSWORD")
        if email and password:
            from mhvp.core.problems import ProblemError

            try:
                user_id = await create_user(
                    factory,
                    email=email,
                    display_name=os.environ.get("MHVP_SEED_ADMIN_NAME", email),
                    password=password,
                    is_platform_admin=True,
                )
                for tenant_id in tenants.values():
                    await add_member(
                        factory,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        role_codes=["tenant_admin"],
                        actor_user_id=None,
                    )
                log.info("seed_admin_created")
            except ProblemError as exc:
                log.warning("seed_admin_skipped", code=exc.error.code)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
