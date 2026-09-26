"""Kontakte CLI: role from file name, name splitting, phone composition, address parsing."""

import pytest

from mhvp.contacts.models import ContactKind, ContactRoleCode
from mhvp.imports.kontakte import (
    compose_phone,
    is_company,
    parse_kontakte,
    prepare,
    role_from_filename,
    salutation,
    split_person_name,
    split_street,
)

HEADER = (
    "id;Name;Briefanrede;Benutzername;Adresse;Stadt;PLZ;Staat;Land;Landesvorwahl;Vorwahl;"
    "Telefonnummer;E-Mail"
)
SAMPLE = "\n".join(
    [
        HEADER,
        '8;"Pawlinski, Andreas & Radoslaw";"Sehr geehrter Herr Pawlinski,";;"Wehrstraße 23";'
        "Rommerskirchen;41569;Nordrhein-Westfalen;Deutschland;;;;andipwlnsk@googlemail.com",
        '111;"Sven Hamacher";"Sehr geehrter Herr Sven Hamacher";;"Dürener Straße 37";Merzenich;'
        "52399;Nordrhein-Westfalen;Deutschland;0049;0157;54296195;svenhamacher1@web.de",
        '2320;"Joachims Christina Maria";"Sehr geehrte Frau Joachims";chrjoa;'
        '"Gewerbestraße Süd 30";Erkelenz;41812;Nordrhein-Westfalen;Deutschland;;;;'
        "joachims.christina@gmail.com",
        '3;"Commerzbank Halle";;;Marktplatz;Halle;06108;Sachsen-Anhalt;Deutschland;0049;345;51050;',
        '1376;"Anne Ecker";"Sehr geehrte Frau Ecker";;;;;;;;;;',
        '803;"Jana Klauenberg & Jens Franken";"Sehr geehrte Damen und Herren";;'
        '"Venner Straße 16 / Annakirchenstraße 24";Mönchengladbach;41068;NRW;Deutschland;;;;',
        '47;Hausverwalter-Vermittlung;"Sehr geehrte Damen und Herren";;"Binzstraße 8";Berlin;'
        "13189;Berlin;Deutschland;030;4391;7008;info@hausverwalter-vermittlung.de",
    ]
)


def test_role_from_filename() -> None:
    assert role_from_filename("/import/de48809d-eigentuemerutf8.csv") is ContactRoleCode.EIGENTUEMER
    assert role_from_filename("mieterutf8.csv") is ContactRoleCode.MIETER
    assert role_from_filename("BankUTF8.csv") is ContactRoleCode.BANK
    assert role_from_filename("SonstigeUTF8.csv") is ContactRoleCode.SONSTIGES
    assert role_from_filename("export.csv") is None


def test_split_person_name() -> None:
    assert split_person_name("Pawlinski, Andreas & Radoslaw") == (
        "Andreas & Radoslaw",
        "Pawlinski",
        None,
    )
    assert split_person_name("Sven Hamacher", "Sehr geehrter Herr Sven Hamacher") == (
        "Sven",
        "Hamacher",
        None,
    )
    assert split_person_name("Joachims Christina Maria", "Sehr geehrte Frau Joachims") == (
        "Christina Maria",
        "Joachims",
        None,
    )
    first, last, note = split_person_name("Elke & Peter Lenders", "Sehr geehrte Eheleute")
    assert (first, last) == ("Elke & Peter", "Lenders")
    assert note is not None
    assert split_person_name("Liam") == (None, "Liam", None)


def test_company_and_salutation() -> None:
    assert is_company("Commerzbank Halle", ContactRoleCode.BANK)
    assert is_company("Lotta Center GmbH", ContactRoleCode.EIGENTUEMER)
    assert is_company("WEG Kohlenweg 14", ContactRoleCode.EIGENTUEMER)
    assert is_company("TEDI", ContactRoleCode.SONSTIGES)
    assert not is_company("Sven Hamacher", ContactRoleCode.MIETER)
    assert salutation("Sehr geehrter Herr Pawlinski,") == "Herr"
    assert salutation("Sehr geehrte Frau") == "Frau"
    assert salutation("Sehr geehrte Damen und Herren") is None
    assert salutation("Sehr geehrte Eheleute Goritzka") is None


def test_phone_and_street() -> None:
    assert compose_phone("0049", "0157", "54296195") == "+4915754296195"
    assert compose_phone("0049", "345", "51050") == "+4934551050"
    assert compose_phone("030", "4391", "7008") == "03043917008"
    assert compose_phone(None, "02431", "9550300") == "024319550300"
    assert compose_phone(None, None, None) is None
    assert split_street("Wehrstraße 23") == ("Wehrstraße", "23")
    assert split_street("Große Steinstraße 20") == ("Große Steinstraße", "20")
    assert split_street("Wilhelm-Külz-Straße 2-3") == ("Wilhelm-Külz-Straße", "2-3")
    assert split_street("Marktplatz") == ("Marktplatz", None)
    assert split_street("Venner Straße 16 / Annakirchenstraße 24") == (
        "Venner Straße 16 / Annakirchenstraße 24",
        None,
    )
    assert split_street(None) == (None, None)


def test_role_from_filename_dienstleister() -> None:
    assert role_from_filename("/import/5e23c88c-Dienstleisterutf8.csv") is (
        ContactRoleCode.DIENSTLEISTER
    )


def test_parse_and_prepare() -> None:
    rows = parse_kontakte(SAMPLE, ContactRoleCode.MIETER, "mieter.csv")
    assert len(rows) == 7
    prepared = {p.row.external_id: p for p in prepare(rows)}
    assert all(p.data is not None for p in prepared.values())
    hamacher = prepared["111"].data
    assert hamacher is not None
    assert hamacher.kind is ContactKind.PERSON
    assert (hamacher.first_name, hamacher.last_name, hamacher.salutation) == (
        "Sven",
        "Hamacher",
        "Herr",
    )
    assert hamacher.roles == [ContactRoleCode.MIETER]
    assert hamacher.external_ids == {"immoware24": "111", "immoware24_name": "Sven Hamacher"}
    assert hamacher.notes == (
        "Briefanrede laut Altsystem: Sehr geehrter Herr Sven Hamacher\n"
        "Bundesland laut Altsystem: Nordrhein-Westfalen"
    )
    assert hamacher.addresses[0].street == "Dürener Straße"
    assert hamacher.addresses[0].house_number == "37"
    assert hamacher.addresses[0].postal_code == "52399"
    assert hamacher.phones[0].number == "+4915754296195"
    assert hamacher.emails[0].email == "svenhamacher1@web.de"
    bank = prepared["3"].data
    assert bank is not None
    assert bank.kind is ContactKind.COMPANY
    assert bank.company_name == "Commerzbank Halle"
    joachims = prepared["2320"].data
    assert joachims is not None
    assert joachims.external_ids["immoware24_user"] == "chrjoa"
    ecker = prepared["1376"].data
    assert ecker is not None
    assert ecker.completeness.value == "incomplete"
    assert ecker.addresses == []
    vermittlung = prepared["47"].data
    assert vermittlung is not None
    assert vermittlung.kind is ContactKind.COMPANY
    assert vermittlung.phones[0].number == "+493043917008"
    with pytest.raises(ValueError, match="Spalten fehlen"):
        parse_kontakte("Nr;Wert\n1;x\n", ContactRoleCode.MIETER, "x.csv")
