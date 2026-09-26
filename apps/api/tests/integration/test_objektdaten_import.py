"""Objektdaten CLI against PostgreSQL: test run leaves nothing behind, apply creates properties
and units once, a second apply reports them unchanged, tenant separation holds."""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.imports.objektdaten import import_prepared, parse_objektdaten, prepare
from mhvp.platform import services
from mhvp.properties.models import Property, PropertyStatus, Unit, UnitType
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration

CSV = "\n".join(
    [
        "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
        '"aktueller Eigentümer";"vereinbarter Zahlbetrag";"aktueller Mieter";"vereinbarter Zahlbetrag"',
        '336;"Gladbacher Straße 95";WEG-Verwaltung;"WEG Gladbacher Straße 95";10001;01;"EG links";'
        '"Steiger, Rolf";269,12;;',
        '336;"Gladbacher Straße 95";WEG-Verwaltung;"WEG Gladbacher Straße 95";10002;02;"EG rechts";'
        '"Koch, Maria";227,22;;',
        '81;"Z-ABGEBEN Roskaul 70-72";WEG-Verwaltung;"Roskaul 70-72";1;"WE 1";"WE 1";"Hoos, Marcel";'
        "130,00;;",
        '216;"Haagstraße 32";Mietverwaltung;"Haagstraße 32";14;"WE 14";DG;;;"Roggen, Anna";620,00',
        '216;"Haagstraße 32";Mietverwaltung;"Haagstraße 32";15;"Stellplatz 1";;;;"Roggen, Anna";40,00',
        '10012;"Am Bildchen 9";Mietverwaltung;Haus;1;WE1;EG;;;"Meier";400,00',
    ]
)


async def _counts(factory: Any, tenant_id: uuid.UUID) -> tuple[int, int]:
    async with tenant_transaction(factory, tenant_id) as session:
        props = await session.scalar(select(func.count()).select_from(Property))
        units = await session.scalar(select(func.count()).select_from(Unit))
        return int(props or 0), int(units or 0)


async def _scenario(settings: Any) -> None:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant_a, _ = await services.provision_tenant(
            factory, slug=f"od-a-{RUN}", name=f"Objektdaten A {RUN}"
        )
        tenant_b, _ = await services.provision_tenant(
            factory, slug=f"od-b-{RUN}", name=f"Objektdaten B {RUN}"
        )
        prepared = prepare(parse_objektdaten(CSV), {})

        dry = await import_prepared(factory, tenant_a, None, prepared, apply=False)
        assert dry["apply"] is False
        assert dry["counts"]["property_created"] == 3
        assert dry["counts"]["property_skipped"] == 1  # 10012 has no three digit number
        assert await _counts(factory, tenant_a) == (0, 0)

        applied = await import_prepared(factory, tenant_a, None, prepared, apply=True)
        assert applied["counts"] == {
            "property_created": 3,
            "property_skipped": 1,
            "unit_created": 5,
        }
        assert await _counts(factory, tenant_a) == (3, 5)
        async with tenant_transaction(factory, tenant_a) as session:
            roskaul = await session.scalar(select(Property).where(Property.number == "081"))
            assert roskaul is not None
            assert roskaul.name == "Roskaul 70-72"
            assert roskaul.status is PropertyStatus.TERMINATED
            assert roskaul.source_id == "81"
            weg = await session.scalar(select(Property).where(Property.number == "336"))
            assert weg is not None
            assert weg.status is PropertyStatus.ONBOARDING
            assert weg.management_type.value == "hoa"
            unit = await session.scalar(
                select(Unit).where(Unit.property_id == weg.id, Unit.number == "10001")
            )
            assert unit is not None
            assert unit.unit_type is UnitType.APARTMENT
            assert unit.custom_fields["altsystem"]["eigentuemer"] == "Steiger, Rolf"
            assert unit.custom_fields["altsystem"]["hausgeld_vereinbart"] == "269,12"
            parking = await session.scalar(select(Unit).where(Unit.number == "15"))
            assert parking is not None
            assert parking.unit_type is UnitType.PARKING
            assert parking.custom_fields["altsystem"]["mieter"] == "Roggen, Anna"

        again = await import_prepared(factory, tenant_a, None, prepared, apply=True)
        assert again["counts"] == {
            "property_unchanged": 3,
            "property_skipped": 1,
            "unit_unchanged": 5,
        }
        assert await _counts(factory, tenant_a) == (3, 5)
        # Tenant separation: nothing of it is visible in another tenant.
        assert await _counts(factory, tenant_b) == (0, 0)
    finally:
        await engine.dispose()


def test_objektdaten_import(database: Database, redis_url: str) -> None:
    asyncio.run(_scenario(base_settings(database, redis_url)))
