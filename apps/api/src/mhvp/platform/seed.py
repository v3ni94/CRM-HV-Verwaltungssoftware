"""``python -m mhvp.platform.seed``: tenants from seeds (5.2), optional initial administrator.

The initial administrator comes from ``MHVP_SEED_ADMIN_EMAIL`` / ``MHVP_SEED_ADMIN_PASSWORD``
(never from the repository); the account becomes tenant administrator of both tenants and
must set up TOTP at first login. With ``MHVP_SEED_ADMIN_SUPERADMIN=true`` that account (also
when it already exists) receives the single superadmin marker (ADR 0011); the address itself
is never part of the code. No release gate is opened and no platform flag is switched on.
"""

import asyncio
import os
import sys

import mhvp.models  # noqa: F401  (registers every mapped table so cross-module FKs resolve)
from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.logging import configure_logging, get_logger
from mhvp.platform.services import (
    add_member,
    create_user,
    seed_tenants,
    set_superadmin,
    user_id_by_email,
)

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


async def run() -> int:
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.seed")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenants = await seed_tenants(factory)
        log.info("tenants_seeded", tenants=sorted(tenants))
        # Prozesskatalog der Vorgangsarten als Ticketvorlagen je Mandant (Regel M19-11),
        # idempotent; vom Mandanten bearbeitete Vorlagen bleiben unverändert.
        from mhvp.core.db.tenancy import tenant_transaction
        from mhvp.tickets.flows import seed_process_templates

        for slug, tenant_id in tenants.items():
            async with tenant_transaction(factory, tenant_id) as session:
                counts = await seed_process_templates(session, tenant_id)
            log.info("process_catalogue_seeded", tenant=slug, **counts)
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
            if os.environ.get("MHVP_SEED_ADMIN_SUPERADMIN", "").strip().lower() in TRUE_VALUES:
                admin_id = await user_id_by_email(factory, email)
                if admin_id is None:
                    log.warning("seed_superadmin_skipped", reason="admin_missing")
                else:
                    try:
                        await set_superadmin(
                            factory, user_id=admin_id, granted=True, actor_user_id=None
                        )
                        log.info("seed_superadmin_set")
                    except ProblemError as exc:
                        log.warning("seed_superadmin_skipped", code=exc.error.code)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
