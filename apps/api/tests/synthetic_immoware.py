"""Synthetic Immoware24 exports for the full import tests (M8-01, M8-02): 67 objects with
869 units, the matching contact lists, an address list, a balance list, a bank export and the
contract lists (Mietverträge, Eigentümerverträge) that fit the units and contacts.
Structure follows the sample rows of tests/unit/test_objektdaten_import.py and
test_kontakte_import.py; every value is invented and no statement about real exports."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal

OBJEKTDATEN_HEADER = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    '"aktueller Eigentümer";"vereinbarter Zahlbetrag";"aktueller Mieter";"vereinbarter Zahlbetrag"'
)
KONTAKTE_HEADER = (
    "id;Name;Briefanrede;Benutzername;Adresse;Stadt;PLZ;Staat;Land;Landesvorwahl;Vorwahl;"
    "Telefonnummer;E-Mail"
)
ADRESSEN_HEADER = "Objektnummer;Straße;Hausnummer;PLZ;Ort"
SALDEN_HEADER = "Objekt-Nummer;VE-Nummer;Vertragsart;Name;Saldo"
BANK_HEADER = "Objekt;IBAN;Datum;Betrag;Saldo"
MIETVERTRAEGE_HEADER = (
    "Vertragsnummer;Objektnummer;Einheitennummer;Kontakt-ID Mieter;Mietbeginn;Mietende;Miete"
)
EIGENTUEMERVERTRAEGE_HEADER = (
    "Vertragsnummer;Objektnummer;Einheitennummer;Kontakt-ID Eigentümer;Beginn;"
    "Eigentumsübergang (Grundbuch);Nutzen-/Lastenwechsel;Ende;Hausgeld;SEV"
)
OWNER_START = "01.01.2020"
TENANT_START = "01.01.2025"
STREETS = (
    "Gladbacher Straße",
    "Haagstraße",
    "Roskaul",
    "Fontanestr.",
    "Brunnenstraße",
    "Am Bildchen",
    "Wehrstraße",
    "Dürener Straße",
    "Gewerbestraße Süd",
    "Binzstraße",
    "Marktplatz",
    "Venner Straße",
)
CITIES = (
    ("41569", "Rommerskirchen"),
    ("52399", "Merzenich"),
    ("41812", "Erkelenz"),
    ("41068", "Mönchengladbach"),
)
FAMILY = (
    "Sakwa",
    "Schmitz",
    "Roggen",
    "Hoos",
    "Meier",
    "Steiger",
    "Koch",
    "Hamacher",
    "Joachims",
    "Ecker",
    "Klauenberg",
    "Franken",
    "Pawlinski",
    "Weber",
    "Fischer",
    "Wagner",
    "Becker",
    "Schulz",
    "Hoffmann",
)
GIVEN = (
    "Agata",
    "Anna",
    "Marcel",
    "Rolf",
    "Maria",
    "Sven",
    "Christina",
    "Anne",
    "Jana",
    "Jens",
    "Andreas",
)
MANAGEMENT = ("WEG-Verwaltung", "Mietverwaltung", "WEG mit SE-Verwaltung")


def _csv(value: str | None) -> str:
    if not value:
        return ""
    if any(ch in value for ch in ';",\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


@dataclass
class Dataset:
    objektdaten: str
    eigentuemer: str
    mieter: str
    adressen: str
    salden: str
    bankumsaetze: str
    mietvertraege: str = ""
    eigentuemervertraege: str = ""
    object_numbers: list[str] = field(default_factory=list)
    unit_count: int = 0
    owner_ids: list[str] = field(default_factory=list)
    tenant_ids: list[str] = field(default_factory=list)
    # Expected results of the contract lists (rule 0.1.8): rows per kind, rows that become a
    # landlord entry instead of a contract, and the target rent / Hausgeld sum per object.
    tenancy_rows: int = 0
    ownership_rows: int = 0
    landlord_rows: int = 0
    rent_sums: dict[str, Decimal] = field(default_factory=dict)
    fee_sums: dict[str, Decimal] = field(default_factory=dict)
    balance_rows: int = 0


def _contact_row(cid: int, name: str, rng: random.Random) -> str:
    plz, city = rng.choice(CITIES)
    street = f"{rng.choice(STREETS)} {rng.randint(1, 120)}"
    last = name.split(",")[0]
    return ";".join(
        [
            str(cid),
            _csv(name),
            _csv(f"Sehr geehrte Damen und Herren {last}"),
            "",
            _csv(street),
            city,
            plz,
            "Nordrhein-Westfalen",
            "Deutschland",
            "0049",
            str(rng.randint(200, 9999)),
            str(rng.randint(100000, 999999)),
            f"kontakt{cid}@example.org",
        ]
    )


def generate(objects: int = 67, units: int = 869, seed: int = 4501) -> Dataset:
    """Deterministic dataset: ``objects`` properties with ``units`` units in total, unique three
    digit object numbers, one owner per WEG unit and one tenant per let unit.

    Contract lists follow the platform rules (``mhvp.contracts.services.creditor_entity``): no
    tenancy in a pure WEG object (its tenants stay contacts only), SEV on the ownership of a
    let unit in "WEG mit SE-Verwaltung", one landlord (owner row on unit 01) per
    Mietverwaltung object."""
    rng = random.Random(seed)  # noqa: S311 - test data, not security
    numbers = [f"{100 + i}" for i in range(objects)]
    # Distribute the units: at least one per object, the rest spread deterministically.
    per_object = [1] * objects
    for i in range(units - objects):
        per_object[i % objects] += 1
    owners: dict[int, str] = {}
    tenants: dict[int, str] = {}
    obj_lines = [OBJEKTDATEN_HEADER]
    adr_lines = [ADRESSEN_HEADER]
    salden_lines = [SALDEN_HEADER]
    bank_lines = [BANK_HEADER]
    miet_lines = [MIETVERTRAEGE_HEADER]
    eig_lines_v = [EIGENTUEMERVERTRAEGE_HEADER]
    rent_sums: dict[str, Decimal] = {}
    fee_sums: dict[str, Decimal] = {}
    landlord_rows = 0
    next_id = 1000
    for i, number in enumerate(numbers):
        street = STREETS[i % len(STREETS)]
        house = 3 + i
        name = f"{street} {house}"
        management = MANAGEMENT[i % len(MANAGEMENT)]
        plz, city = CITIES[i % len(CITIES)]
        adr_lines.append(";".join([number, _csv(street), str(house), plz, city]))
        bank_lines.append(
            ";".join([number, f"DE02{i:018d}"[:22], "15.06.2026", "1.234,56", "10.000,00"])
        )
        if management == "Mietverwaltung":
            # Landlord of the rental object: an owner contact with an ownership row on unit 01.
            next_id += 1
            landlord = f"{FAMILY[next_id % len(FAMILY)]}, {GIVEN[next_id % len(GIVEN)]} {next_id}"
            owners[next_id] = landlord
            eig_lines_v.append(
                ";".join(
                    [
                        f"EV-{next_id}",
                        number,
                        "01",
                        str(next_id),
                        OWNER_START,
                        OWNER_START,
                        "",
                        "",
                        "",
                        "",
                    ]
                )
            )
            landlord_rows += 1
        for k in range(per_object[i]):
            unit_number = f"{k + 1:02d}"
            label = f"WE {k + 1}" if k % 5 else f"Stellplatz {k + 1}"
            location = ("EG", "1.OG", "2.OG", "DG")[k % 4]
            owner = owner_amount = tenant = tenant_amount = ""
            if management != "Mietverwaltung":
                next_id += 1
                owner = f"{FAMILY[next_id % len(FAMILY)]}, {GIVEN[next_id % len(GIVEN)]} {next_id}"
                owners[next_id] = owner
                owner_amount = f"{rng.randint(80, 450)},00"
            if management != "WEG-Verwaltung" or k % 3 == 0:
                next_id += 1
                family = FAMILY[(next_id * 7) % len(FAMILY)]
                tenant = f"{family}, {GIVEN[(next_id * 3) % len(GIVEN)]} {next_id}"
                tenants[next_id] = tenant
                tenant_amount = f"{rng.randint(300, 1200)},00"
            obj_lines.append(
                ";".join(
                    [
                        number,
                        _csv(name),
                        _csv(management),
                        _csv(f"Haus {name}"),
                        unit_number,
                        _csv(label),
                        location,
                        _csv(owner),
                        owner_amount,
                        _csv(tenant),
                        tenant_amount,
                    ]
                )
            )
            if owner:
                fee_sums[number] = fee_sums.get(number, Decimal(0)) + Decimal(
                    owner_amount.replace(",", ".")
                )
                sev = management == "WEG mit SE-Verwaltung" and bool(tenant)
                owner_id = [k for k, v in owners.items() if v == owner][-1]
                eig_lines_v.append(
                    ";".join(
                        [
                            f"EV-{owner_id}",
                            number,
                            unit_number,
                            str(owner_id),
                            OWNER_START,
                            OWNER_START,
                            OWNER_START,
                            "",
                            owner_amount,
                            "ja" if sev else "nein",
                        ]
                    )
                )
            if tenant and management != "WEG-Verwaltung":
                tenant_id = [k for k, v in tenants.items() if v == tenant][-1]
                rent_sums[number] = rent_sums.get(number, Decimal(0)) + Decimal(
                    tenant_amount.replace(",", ".")
                )
                miet_lines.append(
                    ";".join(
                        [
                            f"MV-{tenant_id}",
                            number,
                            unit_number,
                            str(tenant_id),
                            TENANT_START,
                            "",
                            tenant_amount,
                        ]
                    )
                )
                salden_lines.append(
                    ";".join(
                        [
                            number,
                            unit_number,
                            "Mieter",
                            _csv(tenant),
                            f"{rng.randint(-300, 300)},{rng.randint(0, 99):02d}",
                        ]
                    )
                )
            if owner:
                salden_lines.append(
                    ";".join(
                        [
                            number,
                            unit_number,
                            "Eigentümer",
                            _csv(owner),
                            f"{rng.randint(-300, 300)},{rng.randint(0, 99):02d}",
                        ]
                    )
                )
    eig_lines = [KONTAKTE_HEADER] + [_contact_row(cid, name, rng) for cid, name in owners.items()]
    mie_lines = [KONTAKTE_HEADER] + [_contact_row(cid, name, rng) for cid, name in tenants.items()]
    return Dataset(
        objektdaten="\n".join(obj_lines) + "\n",
        eigentuemer="\n".join(eig_lines) + "\n",
        mieter="\n".join(mie_lines) + "\n",
        adressen="\n".join(adr_lines) + "\n",
        salden="\n".join(salden_lines) + "\n",
        bankumsaetze="\n".join(bank_lines) + "\n",
        mietvertraege="\n".join(miet_lines) + "\n",
        eigentuemervertraege="\n".join(eig_lines_v) + "\n",
        object_numbers=numbers,
        unit_count=units,
        owner_ids=[str(i) for i in owners],
        tenant_ids=[str(i) for i in tenants],
        tenancy_rows=len(miet_lines) - 1,
        ownership_rows=len(eig_lines_v) - 1,
        landlord_rows=landlord_rows,
        rent_sums=rent_sums,
        fee_sums=fee_sums,
        balance_rows=len(salden_lines) - 1,
    )
