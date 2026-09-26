"""Derived contact roles and object relations of a contact (Betreiberauftrag 26.09.2026)."""

import asyncio
import uuid
from datetime import date
from typing import Any

from mhvp.contacts import services
from mhvp.contacts.models import Contact, ContactKind
from mhvp.contracts.models import Contract, ContractKind
from mhvp.properties.models import Property, PropertyContact, PropertyOwner, Unit

TODAY = date(2026, 9, 26)
TENANT = uuid.uuid4()


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    """Returns queued results for scalars/scalar/execute in call order."""

    def __init__(self, *results: Any) -> None:
        self.results = list(results)

    async def scalars(self, _stmt: Any) -> _Result:
        return _Result(self.results.pop(0))

    async def scalar(self, _stmt: Any) -> Any:
        return self.results.pop(0)

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(self.results.pop(0))


def _contact(roles: list[str]) -> Contact:
    return Contact(
        id=uuid.uuid4(), tenant_id=TENANT, kind=ContactKind.PERSON, display_name="X", roles=roles
    )


def test_derive_roles_mapping() -> None:
    assert services.derive_roles({"tenancy"}, False) == {"mieter"}
    assert services.derive_roles({"ownership"}, False) == {"eigentuemer"}
    assert services.derive_roles(set(), True) == {"eigentuemer"}
    assert services.derive_roles(set(), False) == set()


def test_merge_roles_never_removes_manual_roles() -> None:
    assert services.merge_roles(["bank", "mieter"], set()) == ["bank", "mieter"]
    assert services.merge_roles(["dienstleister"], {"mieter"}) == ["dienstleister", "mieter"]


def test_recompute_adds_contract_and_owner_roles() -> None:
    contact = _contact(["sonstiges"])
    session = _Session([ContractKind.TENANCY], uuid.uuid4(), [])
    changed = asyncio.run(services.recompute_derived_roles(session, contact, TODAY))  # type: ignore[arg-type]
    assert changed is True
    assert contact.roles == ["eigentuemer", "mieter", "sonstiges"]


def test_recompute_without_links_keeps_roles() -> None:
    contact = _contact(["verwalter"])
    session = _Session([], None, [])
    changed = asyncio.run(services.recompute_derived_roles(session, contact, TODAY))  # type: ignore[arg-type]
    assert changed is False
    assert contact.roles == ["verwalter"]


def test_object_relations_sources_and_order() -> None:
    contact = _contact([])
    prop = Property(id=uuid.uuid4(), tenant_id=TENANT, name="Hauptstr. 1", city="Hilden")
    unit = Unit(id=uuid.uuid4(), tenant_id=TENANT, property_id=prop.id, number="W01", label=None)
    ended = Contract(
        id=uuid.uuid4(),
        kind=ContractKind.TENANCY,
        property_id=prop.id,
        unit_id=unit.id,
        start_date=date(2018, 1, 1),
        end_date=date(2020, 12, 31),
    )
    running = Contract(
        id=uuid.uuid4(),
        kind=ContractKind.OWNERSHIP,
        property_id=prop.id,
        unit_id=unit.id,
        start_date=date(2021, 1, 1),
        end_date=None,
    )
    owner = PropertyOwner(property_id=prop.id, valid_from=date(2015, 3, 1), valid_to=None)
    link = PropertyContact(
        property_id=prop.id, category_code="hausmeister", valid_from=date(2024, 1, 1)
    )
    session = _Session(
        [(ended, prop, unit), (running, prop, unit)], [(owner, prop)], [(link, prop)]
    )
    rows = asyncio.run(services.object_relations(session, contact, TODAY))  # type: ignore[arg-type]
    assert [(r.source, r.kind, r.active) for r in rows] == [
        ("property_contact", "kontakt", True),
        ("contract", "eigentuemer", True),
        ("property_owner", "eigentuemer", True),
        ("contract", "mieter", False),
    ]
    assert rows[1].unit_label == "W01"
    assert rows[1].contract_id == running.id
    assert rows[0].category_code == "hausmeister"
    assert rows[3].valid_to == date(2020, 12, 31)
