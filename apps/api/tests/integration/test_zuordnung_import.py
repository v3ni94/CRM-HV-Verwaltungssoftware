"""Zuordnung CLI against PostgreSQL: after objektdaten and kontakte, a test run leaves nothing,
apply creates ownership and tenancy contracts with monthly payments once, a second apply finds
them, a different owner is a conflict, ambiguous and unknown names are reported."""

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.contacts.models import Contact, ContactRoleCode
from mhvp.contracts.models import (
    Contract,
    ContractKind,
    ContractPayment,
    PaymentInterval,
    PaymentSchedule,
)
from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.imports import kontakte, objektdaten
from mhvp.imports.zuordnung import import_rows
from mhvp.platform import services
from mhvp.properties.models import Unit
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration

HEAD = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    '"aktueller Eigentümer";"vereinbarter Zahlbetrag";"aktueller Mieter";"vereinbarter Zahlbetrag"'
)
OBJEKTE = "\n".join(
    [
        HEAD,
        '336;"Gladbacher Straße 95";WEG-Verwaltung;Haus;10001;01;EG;"Steiger, Rolf";269,12;;',
        '336;"Gladbacher Straße 95";WEG-Verwaltung;Haus;10002;02;OG;"koch,  Maria u. Peter";'
        "1.019,71;;",
        '336;"Gladbacher Straße 95";WEG-Verwaltung;Haus;10003;03;DG;"Meier, Hans";200,00;;',
        '336;"Gladbacher Straße 95";WEG-Verwaltung;Haus;10004;04;DG;"Unbekannt, Udo";200,00;;',
        '391;"Weidenbruch 1";WEG mit SE-Verwaltung;Haus;1;"WE 1";EG;"Bunte, Eva";290,00;'
        '"Stark, Tim";745,00',
        '391;"Weidenbruch 1";WEG mit SE-Verwaltung;Haus;2;"WE 2";OG;"Bunte, Eva";300,00;;',
        '216;"Haagstraße 32";Mietverwaltung;Haus;14;"WE 14";DG;;;"Roggen, Anna";620,00',
        '216;"Haagstraße 32";Mietverwaltung;Haus;15;"WE 15";DG;;;Leerstand;',
    ]
)
KHEAD = (
    "id;Name;Briefanrede;Benutzername;Adresse;Stadt;PLZ;Staat;Land;Landesvorwahl;Vorwahl;"
    "Telefonnummer;E-Mail"
)
EIGENTUEMER = "\n".join(
    [
        KHEAD,
        '10;"Steiger, Rolf";"Sehr geehrter Herr Steiger";;;;;Nordrhein-Westfalen;;;;;',
        '11;"Koch, Maria & Peter";"Sehr geehrte Eheleute Koch";;;;;;;;;;',
        '12;"Meier, Hans";;;;;;;;;;;',
        '13;"Meier, Hans";;;;;;;;;;;',
        '14;"Bunte, Eva";;;;;;;;;;;',
    ]
)
MIETER = "\n".join([KHEAD, '20;"Stark, Tim";;;;;;;;;;;', '21;"Roggen, Anna";;;;;;;;;;;'])
START = date(2026, 1, 1)


async def _contracts(factory: Any, tenant_id: uuid.UUID) -> tuple[int, int, int]:
    async with tenant_transaction(factory, tenant_id) as session:
        contracts = await session.scalar(select(func.count()).select_from(Contract))
        payments = await session.scalar(select(func.count()).select_from(ContractPayment))
        schedules = await session.scalar(select(func.count()).select_from(PaymentSchedule))
        return int(contracts or 0), int(payments or 0), int(schedules or 0)


async def _run(factory: Any, tenant_id: uuid.UUID, text: str, *, apply: bool) -> dict[str, Any]:
    return await import_rows(
        factory,
        tenant_id,
        None,
        objektdaten.parse_objektdaten(text).rows,
        apply=apply,
        start=START,
        start_assumed=False,
    )


async def _scenario(settings: Any) -> None:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant, _ = await services.provision_tenant(
            factory, slug=f"zo-a-{RUN}", name=f"Zuordnung A {RUN}"
        )
        other, _ = await services.provision_tenant(
            factory, slug=f"zo-b-{RUN}", name=f"Zuordnung B {RUN}"
        )
        prepared = objektdaten.prepare(objektdaten.parse_objektdaten(OBJEKTE), {})
        await objektdaten.import_prepared(factory, tenant, None, prepared, apply=True)
        rows = kontakte.parse_kontakte(EIGENTUEMER, ContactRoleCode.EIGENTUEMER, "eigentuemer.csv")
        rows.extend(kontakte.parse_kontakte(MIETER, ContactRoleCode.MIETER, "mieter.csv"))
        await kontakte.import_prepared(factory, tenant, None, kontakte.prepare(rows), apply=True)

        dry = await _run(factory, tenant, OBJEKTE, apply=False)
        assert dry["apply"] is False
        assert dry["counts"]["vertraege_angelegt"] == 5
        assert await _contracts(factory, tenant) == (0, 0, 0)

        applied = await _run(factory, tenant, OBJEKTE, apply=True)
        assert applied["einheiten_gesamt"] == 8
        assert applied["eigentuemer_zugeordnet"] == 4
        assert applied["mieter_zugeordnet"] == 1
        assert applied["leerstand"] == 1
        assert [x["name"] for x in applied["nicht_gefunden"]] == ["Unbekannt, Udo"]
        assert [x["name"] for x in applied["mehrdeutig"]] == ["Meier, Hans"]
        assert len(applied["mehrdeutig"][0]["kandidaten"]) == 2
        # Mietverwaltung without recorded owner of the property: no landlord, reported.
        assert [x["name"] for x in applied["konflikte"]] == ["Roggen, Anna"]
        assert applied["counts"]["vertraege_angelegt"] == 5
        assert applied["counts"]["zahlungen_angelegt"] == 5
        assert applied["counts"].get("parties_angelegt", 0) == 0  # parties from kontakte
        assert await _contracts(factory, tenant) == (5, 5, 5)

        async with tenant_transaction(factory, tenant) as session:
            unit = await session.scalar(select(Unit).where(Unit.source_id == "336/10002"))
            assert unit is not None
            koch = await session.scalar(select(Contract).where(Contract.unit_id == unit.id))
            assert koch is not None
            assert koch.kind is ContractKind.OWNERSHIP
            assert koch.start_date == START
            assert koch.title_transfer_date == START
            payment = await session.scalar(
                select(ContractPayment).where(ContractPayment.contract_id == koch.id)
            )
            assert payment is not None
            assert payment.payment_type_code == "hoa_fee"
            assert payment.gross == Decimal("1019.71")
            schedule = await session.scalar(
                select(PaymentSchedule).where(PaymentSchedule.contract_id == koch.id)
            )
            assert schedule is not None
            assert schedule.interval is PaymentInterval.MONTHLY
            sev_unit = await session.scalar(select(Unit).where(Unit.source_id == "391/1"))
            assert sev_unit is not None
            kinds = {
                c.kind: c
                for c in (
                    await session.scalars(select(Contract).where(Contract.unit_id == sev_unit.id))
                ).all()
            }
            assert kinds[ContractKind.OWNERSHIP].sev_enabled is True
            assert kinds[ContractKind.TENANCY].legal_entity_id != (
                kinds[ContractKind.OWNERSHIP].legal_entity_id
            )
            rent = await session.scalar(
                select(ContractPayment).where(
                    ContractPayment.contract_id == kinds[ContractKind.TENANCY].id
                )
            )
            assert rent is not None
            assert (rent.payment_type_code, rent.gross) == ("rent", Decimal("745.00"))
            stark = await session.scalar(
                select(Contact).where(Contact.external_ids["immoware24"].astext == "20")
            )
            assert stark is not None
            assert "mieter" in stark.roles
            bunte = await session.scalar(
                select(Contact).where(Contact.external_ids["immoware24"].astext == "14")
            )
            assert bunte is not None
            assert "eigentuemer" in bunte.roles

        again = await _run(factory, tenant, OBJEKTE, apply=True)
        assert again["counts"].get("vertraege_angelegt", 0) == 0
        assert again["counts"]["vertraege_vorhanden"] == 5
        assert again["eigentuemer_zugeordnet"] == 4
        assert await _contracts(factory, tenant) == (5, 5, 5)

        changed = OBJEKTE.replace('"Steiger, Rolf";269,12', '"Bunte, Eva";269,12')
        conflict = await _run(factory, tenant, changed, apply=True)
        names = [(x["ve"], x["name"]) for x in conflict["konflikte"]]
        assert ("10001", "Bunte, Eva") in names
        assert await _contracts(factory, tenant) == (5, 5, 5)

        assert await _contracts(factory, other) == (0, 0, 0)
    finally:
        await engine.dispose()


def test_zuordnung_import(database: Database, redis_url: str) -> None:
    asyncio.run(_scenario(base_settings(database, redis_url)))
