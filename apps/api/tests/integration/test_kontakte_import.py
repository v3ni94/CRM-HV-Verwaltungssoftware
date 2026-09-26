"""Kontakte CLI against PostgreSQL: test run leaves nothing, apply creates contacts with party,
the same id in a second list only adds a role, tenant separation holds."""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.contacts.models import Contact, ContactRoleCode, Party
from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.imports.kontakte import import_prepared, parse_kontakte, prepare
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration

HEADER = (
    "id;Name;Briefanrede;Benutzername;Adresse;Stadt;PLZ;Staat;Land;Landesvorwahl;Vorwahl;"
    "Telefonnummer;E-Mail"
)
OWNERS = "\n".join(
    [
        HEADER,
        '1;"Hausverwaltung Müller GmbH";"Sehr geehrte Damen und Herren";admin;"Rheinpromenade 13";'
        '"Monheim am Rhein";40789;Nordrhein-Westfalen;Deutschland;0049;1522;9233185;'
        "info@muellerhv.de",
        '9;"Goritzka, Janina & Jacek";"Sehr geehrte Eheleute Goritzka";;"Wehrstraße 23";'
        "Rommerskirchen;41569;Nordrhein-Westfalen;Deutschland;;;;goritzka@web.de",
    ]
)
OTHERS = "\n".join(
    [
        HEADER,
        '1;"Hausverwaltung Müller GmbH";"Sehr geehrte Damen und Herren";admin;"Rheinpromenade 13";'
        '"Monheim am Rhein";40789;Nordrhein-Westfalen;Deutschland;0049;1522;9233185;'
        "info@muellerhv.de",
        '1376;"Anne Ecker";"Sehr geehrte Frau Ecker";;;;;;;;;;',
    ]
)


async def _counts(factory: Any, tenant_id: uuid.UUID) -> tuple[int, int]:
    async with tenant_transaction(factory, tenant_id) as session:
        contacts = await session.scalar(
            select(func.count()).select_from(Contact).where(Contact.deleted_at.is_(None))
        )
        parties = await session.scalar(select(func.count()).select_from(Party))
        return int(contacts or 0), int(parties or 0)


async def _scenario(settings: Any) -> None:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant_a, _ = await services.provision_tenant(
            factory, slug=f"kt-a-{RUN}", name=f"Kontakte A {RUN}"
        )
        tenant_b, _ = await services.provision_tenant(
            factory, slug=f"kt-b-{RUN}", name=f"Kontakte B {RUN}"
        )
        rows = list(parse_kontakte(OWNERS, ContactRoleCode.EIGENTUEMER, "eigentuemer.csv").rows)
        rows += list(parse_kontakte(OTHERS, ContactRoleCode.SONSTIGES, "sonstige.csv").rows)
        prepared = prepare(rows)

        dry = await import_prepared(factory, tenant_a, None, prepared, apply=False)
        assert dry["counts"] == {"created": 3, "role_added": 1}
        assert await _counts(factory, tenant_a) == (0, 0)

        applied = await import_prepared(factory, tenant_a, None, prepared, apply=True)
        assert applied["counts"] == {"created": 3, "role_added": 1}
        assert await _counts(factory, tenant_a) == (3, 3)
        async with tenant_transaction(factory, tenant_a) as session:
            hvm = await session.scalar(
                select(Contact).where(Contact.external_ids["immoware24"].astext == "1")
            )
            assert hvm is not None
            assert hvm.kind.value == "company"
            assert sorted(hvm.roles) == ["eigentuemer", "sonstiges"]
            assert hvm.external_ids["immoware24_user"] == "admin"
            goritzka = await session.scalar(
                select(Contact).where(Contact.external_ids["immoware24"].astext == "9")
            )
            assert goritzka is not None
            assert (goritzka.first_name, goritzka.last_name) == ("Janina & Jacek", "Goritzka")
            assert goritzka.display_name == "Goritzka, Janina & Jacek"
            ecker = await session.scalar(
                select(Contact).where(Contact.external_ids["immoware24"].astext == "1376")
            )
            assert ecker is not None
            assert ecker.completeness.value == "incomplete"
            assert ecker.roles == ["sonstiges"]

        again = await import_prepared(factory, tenant_a, None, prepared, apply=True)
        assert again["counts"] == {"unchanged": 4}
        assert await _counts(factory, tenant_a) == (3, 3)
        assert await _counts(factory, tenant_b) == (0, 0)
    finally:
        await engine.dispose()


def test_kontakte_import(database: Database, redis_url: str) -> None:
    asyncio.run(_scenario(base_settings(database, redis_url)))
