"""Korpus deutscher Mailtexte für die deterministische Erkennung in ``mhvp.tickets.proposals``
(M19-05): Namensänderungen, Umzüge, neue E-Mail und Telefonnummer, Kombinationen sowie
Negativbeispiele. Alle Namen, Anschriften und Kennungen sind erfunden. Die Trefferquote wird
als Zusicherung festgehalten (mindestens 90 % der Positivfälle mit exakt den erwarteten
Feldern, kein Negativfall mit einer Feldänderung)."""

from datetime import date
from typing import Any

import pytest

from mhvp.tickets import proposals

Case = dict[str, Any]

POSITIVE: list[Case] = [
    {
        "id": "heirat_von_in",
        "subject": "Namensänderung",
        "body": "Guten Tag,\n\nmein Name hat sich aufgrund der Hochzeit von Jacqueline Kampmeier "
        "in Jacqueline Müller geändert. Bitte passen Sie Ihre Unterlagen an.\n\nViele Grüße\n"
        "Jacqueline Müller",
        "expect": {"last_name": "Müller"},
        "name_old": "Jacqueline Kampmeier",
    },
    {
        "id": "heisse_jetzt",
        "subject": "Neuer Name",
        "body": "Hallo,\n\nich habe geheiratet und heiße jetzt Sabine Weber. Bitte ändern Sie das "
        "in Ihren Unterlagen.\n\nViele Grüße\nSabine Weber",
        "expect": {"last_name": "Weber"},
    },
    {
        "id": "neuer_name_lautet_doppelname",
        "subject": "Änderung meiner Daten",
        "body": "Sehr geehrte Damen und Herren,\n\nmein neuer Name lautet Katrin Hoffmann-Berger "
        "(Doppelname nach der Hochzeit).\n\nMit freundlichen Grüßen\nKatrin Hoffmann-Berger",
        "expect": {"last_name": "Hoffmann-Berger"},
    },
    {
        "id": "nach_hochzeit_trage_namen",
        "subject": "Wohnung 12, Namensänderung",
        "body": "Guten Tag Frau Schulz,\n\nnach meiner Hochzeit im August trage ich jetzt den "
        "Namen Lena Bachmann. Meine Wohnung und alles andere bleibt unverändert.\n\n"
        "Viele Grüße\nLena Bachmann",
        "expect": {"last_name": "Bachmann"},
        "salutation": None,
    },
    {
        "id": "scheidung_geburtsname_von_in",
        "subject": "Nachname",
        "body": "Hallo,\n\nnach meiner Scheidung trage ich wieder meinen Geburtsnamen Fischer. "
        "Bitte ändern Sie meinen Nachnamen von Petra Hartmann in Petra Fischer.\n\n"
        "Danke und Grüße\nPetra Fischer",
        "expect": {"last_name": "Fischer"},
        "name_old": "Petra Hartmann",
    },
    {
        "id": "scheidung_heisse_nun_wieder",
        "subject": "Namensänderung nach Scheidung",
        "body": "Guten Tag,\n\nich bin geschieden und heiße nun wieder Monika Schreiber.\n\n"
        "Mit freundlichen Grüßen\nMonika Schreiber",
        "expect": {"last_name": "Schreiber"},
    },
    {
        "id": "doppelname_von_in",
        "subject": "Doppelname",
        "body": "Sehr geehrte Damen und Herren,\n\nmein Nachname hat sich von Krüger in "
        "Krüger-Lindemann geändert.\n\nFreundliche Grüße\nAnja Krüger-Lindemann",
        "expect": {"last_name": "Krüger-Lindemann"},
    },
    {
        "id": "firma_umfirmiert_von_in",
        "subject": "Umfirmierung",
        "body": "Sehr geehrte Damen und Herren,\n\nwir haben umfirmiert: von Hausmeisterservice "
        "Krause GmbH in Krause Gebäudeservice GmbH. Bitte passen Sie die Rechnungsanschrift "
        "an.\n\nMit freundlichen Grüßen\nJens Krause",
        "expect": {"company_name": "Krause Gebäudeservice GmbH"},
    },
    {
        "id": "firma_heisst_jetzt",
        "subject": "Neuer Firmenname",
        "body": "Guten Tag,\n\nunsere Firma heißt jetzt Malerbetrieb Sonnenschein GmbH & Co. KG. "
        "Alles andere bleibt gleich.\n\nViele Grüße\nBirgit Sonnenschein",
        "expect": {"company_name": "Malerbetrieb Sonnenschein GmbH & Co. KG"},
    },
    {
        "id": "firmiert_unter",
        "subject": "Firmierung",
        "body": "Sehr geehrte Damen und Herren,\n\nunser Unternehmen firmiert ab sofort unter "
        "Nordlicht Immobilien AG.\n\nMit freundlichen Grüßen\nOle Petersen",
        "expect": {"company_name": "Nordlicht Immobilien AG"},
    },
    {
        "id": "umzug_ab_dem_zusatz",
        "subject": "Neue Adresse ab 01.10.2026",
        "body": "Hallo,\n\nich ziehe um. Ab dem 01.10.2026 lautet meine neue Anschrift "
        "Lindenallee 7a, 50667 Köln.\n\nViele Grüße\nTobias Brandt",
        "expect": {
            "street": "Lindenallee",
            "house_number": "7a",
            "postal_code": "50667",
            "city": "Köln",
        },
        "valid_from": "2026-10-01",
    },
    {
        "id": "umzug_ohne_datum",
        "subject": "Umzug",
        "body": "Guten Tag,\n\nich bin umgezogen. Meine neue Adresse: Hauptstraße 12, "
        "40789 Monheim am Rhein.\n\nMit freundlichen Grüßen\nPeter Beispiel",
        "expect": {
            "street": "Hauptstraße",
            "house_number": "12",
            "postal_code": "40789",
            "city": "Monheim am Rhein",
        },
        "valid_from": None,
    },
    {
        "id": "strasse_zwei_woerter_zusatz",
        "subject": "Adressänderung",
        "body": "Sehr geehrte Damen und Herren,\n\nmeine Anschrift hat sich geändert: "
        "Berliner Straße 45 b, 10115 Berlin, Hinterhaus 2. OG.\n\nMit freundlichen Grüßen\n"
        "Nadine Roth",
        "expect": {
            "street": "Berliner Straße",
            "house_number": "45b",
            "postal_code": "10115",
            "city": "Berlin",
        },
    },
    {
        "id": "ort_vor_plz",
        "subject": "Neue Anschrift",
        "body": "Hallo,\n\nwir sind umgezogen und wohnen jetzt in Düsseldorf, 40213, "
        "Königsallee 30.\n\nViele Grüße\nFamilie Yilmaz",
        "expect": {
            "street": "Königsallee",
            "house_number": "30",
            "postal_code": "40213",
            "city": "Düsseldorf",
        },
    },
    {
        "id": "am_alten_bahnhof_zum_datum",
        "subject": "Umzug zum 15.11.2026",
        "body": "Guten Tag,\n\nzum 15.11.2026 ziehe ich um. Neue Adresse: Am Alten Bahnhof 3, "
        "21614 Buxtehude.\n\nGrüße\nHeiko Lorenz",
        "expect": {
            "street": "Am Alten Bahnhof",
            "house_number": "3",
            "postal_code": "21614",
            "city": "Buxtehude",
        },
        "valid_from": "2026-11-15",
    },
    {
        "id": "wohne_seit_monatsname",
        "subject": "Adresse",
        "body": "Hallo,\n\nich wohne seit dem 1. September 2026 in der Rosengasse 5, "
        "79098 Freiburg im Breisgau.\n\nBeste Grüße\nClara Vogt",
        "expect": {
            "street": "Rosengasse",
            "house_number": "5",
            "postal_code": "79098",
            "city": "Freiburg im Breisgau",
        },
        "valid_from": "2026-09-01",
    },
    {
        "id": "umzug_nr_ab_datum",
        "subject": "Umzug",
        "body": "Hallo,\n\nwir ziehen um! Unsere neue Anschrift ab 1.12.2026: Schlossplatz Nr. 4, "
        "70173 Stuttgart.\n\nViele Grüße\nFamilie Öztürk",
        "expect": {
            "street": "Schlossplatz",
            "house_number": "4",
            "postal_code": "70173",
            "city": "Stuttgart",
        },
        "valid_from": "2026-12-01",
    },
    {
        "id": "neue_wohnung_zeilen",
        "subject": "Neue Wohnung",
        "body": "Guten Tag,\n\nich habe eine neue Wohnung:\nMarktplatz 1\n01067 Dresden\n\n"
        "Bitte senden Sie die Post künftig dorthin.\n\nGrüße\nFrank Seidel",
        "expect": {
            "street": "Marktplatz",
            "house_number": "1",
            "postal_code": "01067",
            "city": "Dresden",
        },
    },
    {
        "id": "neue_email_lautet",
        "subject": "Neue E-Mail-Adresse",
        "body": "Guten Tag,\n\nmeine neue E-Mail-Adresse lautet lena.k@example.org. Die alte "
        "Adresse wird abgeschaltet.\n\nViele Grüße\nLena Kaiser",
        "sender": "lena.alt@example.org",
        "expect": {"email": "lena.k@example.org"},
    },
    {
        "id": "email_kuenftig_an",
        "subject": "Kontaktdaten",
        "body": "Hallo,\n\nbitte schicken Sie E-Mails künftig an buero@beispiel-firma.example "
        "statt an die alte Adresse.\n\nMit freundlichen Grüßen\nMartin Ebert",
        "sender": "m.ebert@example.org",
        "expect": {"email": "buero@beispiel-firma.example"},
    },
    {
        "id": "email_hat_sich_ab_sofort",
        "subject": "Änderung",
        "body": "Sehr geehrte Damen und Herren,\n\nmeine E-Mail-Adresse hat sich geändert. Sie "
        "erreichen mich ab sofort unter neu.mustermann@example.net.\n\nMit freundlichen "
        "Grüßen\nErik Mustermann",
        "sender": "erik.alt@example.net",
        "expect": {"email": "neu.mustermann@example.net"},
    },
    {
        "id": "neue_telefonnummer",
        "subject": "Neue Telefonnummer",
        "body": "Guten Tag,\n\nich habe eine neue Telefonnummer: 0171 2345678. Die alte Nummer "
        "ist nicht mehr gültig.\n\nGrüße\nRita Ruf",
        "expect": {"phone": "0171 2345678"},
    },
    {
        "id": "handynummer_hat_sich",
        "subject": "Handynummer",
        "body": "Hallo,\n\nmeine Handynummer hat sich geändert, ich bin jetzt unter "
        "+49 160 9876543 erreichbar.\n\nViele Grüße\nSven Ott",
        "expect": {"phone": "+49 160 9876543"},
    },
    {
        "id": "festnetz_mit_alter_signatur",
        "subject": "Neue Festnetznummer",
        "body": "Sehr geehrte Damen und Herren,\n\nunsere neue Festnetznummer lautet "
        "0211/5551234.\n\nMit freundlichen Grüßen\nDorothea Lange\nTel. 0211/5550000 (alt)",
        "expect": {"phone": "0211/5551234"},
    },
    {
        "id": "telefonisch_nur_noch",
        "subject": "Erreichbarkeit",
        "body": "Guten Tag,\n\nich bin telefonisch nur noch unter 0157 11223344 zu erreichen, "
        "die Festnetznummer wurde gekündigt.\n\nMit freundlichen Grüßen\nUte Winkler",
        "expect": {"phone": "0157 11223344"},
    },
    {
        "id": "kombination_name_adresse",
        "subject": "Heirat und Umzug",
        "body": "Hallo,\n\nich habe geheiratet und bin umgezogen. Mein Name hat sich von "
        "Julia Stein in Julia Winter geändert, meine neue Anschrift ist Mühlenweg 2, "
        "48143 Münster.\n\nLiebe Grüße\nJulia Winter",
        "expect": {
            "last_name": "Winter",
            "street": "Mühlenweg",
            "house_number": "2",
            "postal_code": "48143",
            "city": "Münster",
        },
    },
    {
        "id": "kombination_adresse_telefon_email",
        "subject": "Meine neuen Kontaktdaten",
        "body": "Guten Tag,\n\nab dem 15.10.2026 wohne ich in der Feldstraße 9, 22765 Hamburg. "
        "Neue Telefonnummer: 040 1234567, neue E-Mail: hans.neu@example.org.\n\n"
        "Mit freundlichen Grüßen\nHans Neumann",
        "sender": "hans.alt@example.org",
        "expect": {
            "street": "Feldstraße",
            "house_number": "9",
            "postal_code": "22765",
            "city": "Hamburg",
            "phone": "040 1234567",
            "email": "hans.neu@example.org",
        },
        "valid_from": "2026-10-15",
    },
    {
        "id": "name_mit_frau_in_signatur",
        "subject": "Namensänderung",
        "body": "Sehr geehrte Damen und Herren,\n\nseit meiner Hochzeit heiße ich Isabel Roth. "
        "Bitte aktualisieren Sie Ihre Unterlagen.\n\nMit freundlichen Grüßen\nFrau Isabel Roth",
        "expect": {"last_name": "Roth"},
        "salutation": "Frau",
    },
    {
        "id": "neuer_nachname_ihr_signatur",
        "subject": "Neuer Nachname",
        "body": "Hallo,\n\nmein neuer Nachname ist Brandt (vorher Kowalski).\n\nIhr Michael Brandt",
        "expect": {"last_name": "Brandt"},
        "salutation": "Herr",
    },
]

NEGATIVE: list[Case] = [
    {
        "id": "schadensmeldung",
        "subject": "Wasserschaden",
        "body": "Hallo,\n\nin meiner Wohnung Hauptstraße 5, 2. OG tropft es seit gestern aus der "
        "Decke. Bitte schicken Sie jemanden vorbei.\n\nMit freundlichen Grüßen\nMax Muster",
    },
    {
        "id": "rechnung_mit_iban",
        "subject": "Rechnung Nr. 2026-118",
        "body": "Sehr geehrte Damen und Herren,\n\nanbei unsere Rechnung über 1.234,56 EUR für "
        "die Dachrinnenreinigung. Bitte überweisen Sie den Betrag auf unser bekanntes Konto, "
        "IBAN DE89 3704 0044 0532 0130 00.\n\nMit freundlichen Grüßen\nDachdeckerei Hansen GmbH",
    },
    {
        "id": "terminanfrage_mit_telefon",
        "subject": "Terminanfrage Besichtigung",
        "body": "Guten Tag,\n\nkönnen wir die Besichtigung am Dienstag um 10 Uhr machen? Sie "
        "erreichen mich unter 0171 2345678.\n\nViele Grüße\nAnna Berg",
    },
    {
        "id": "name_nur_in_grussformel",
        "subject": "Heizung defekt",
        "body": "Hallo,\n\nseit gestern ist die Heizung kalt. Bitte um Reparatur.\n\n"
        "Mit freundlichen Grüßen\nJacqueline Müller",
    },
    {
        "id": "nachbar_mit_namen",
        "subject": "Lärmbelästigung",
        "body": "Sehr geehrte Damen und Herren,\n\nder neue Mieter im 3. OG, Herr Weber, macht "
        "jede Nacht Lärm. Bitte sprechen Sie ihn an.\n\nMit freundlichen Grüßen\nKarin Lang",
    },
    {
        "id": "hochzeit_ohne_namensaenderung",
        "subject": "Nutzung Gemeinschaftsraum",
        "body": "Hallo,\n\nwir möchten den Gemeinschaftsraum am 12.12.2026 für die Hochzeit "
        "meiner Tochter nutzen. Ist das möglich?\n\nViele Grüße\nBernd Schuster",
    },
    {
        "id": "kuendigung_stellplatz_nachmieter",
        "subject": "Kündigung Stellplatz",
        "body": "Guten Tag,\n\nich kündige den Stellplatz Nr. 7 zum 31.12.2026. Der Nachmieter, "
        "Herr Klein, übernimmt ihn nicht.\n\nMit freundlichen Grüßen\nSilke Bauer",
    },
    {
        "id": "signatur_mit_kontaktdaten",
        "subject": "Frage zur Abrechnung",
        "body": "Sehr geehrte Damen und Herren,\n\nich habe eine Frage zur Position Hausreinigung "
        "in der Abrechnung 2025. Können Sie mir die Rechnung zusenden?\n\nMit freundlichen "
        "Grüßen\nOliver Kern\nGartenweg 12, 40789 Monheim am Rhein\nTel. 02173 123456\n"
        "E-Mail: oliver.kern@example.org",
        "sender": "oliver.kern@example.org",
    },
]

MIN_HIT_RATE = 0.9


def _fields(found: proposals.Detection) -> dict[str, str | None]:
    return {c["field"]: c["new"] for c in found.changes}


def _run(case: Case) -> proposals.Detection:
    return proposals.detect(case["subject"], case["body"], case.get("sender"))


def _matches(case: Case, found: proposals.Detection) -> bool:
    if _fields(found) != case["expect"]:
        return False
    if "valid_from" in case and found.address_valid_from != case["valid_from"]:
        return False
    if "salutation" in case and found.salutation != case["salutation"]:
        return False
    return "name_old" not in case or found.name_old == case["name_old"]


def test_corpus_size() -> None:
    assert len(POSITIVE) >= 25
    assert len(NEGATIVE) >= 8
    assert len({c["id"] for c in POSITIVE + NEGATIVE}) == len(POSITIVE) + len(NEGATIVE)


def test_positive_hit_rate_at_least_90_percent() -> None:
    """Zusicherung der Trefferquote (M19-05): Anteil der Positivfälle, bei denen die
    deterministische Stufe exakt die erwarteten Felder mit den erwarteten Werten liefert."""
    failed = [c["id"] for c in POSITIVE if not _matches(c, _run(c))]
    rate = 1 - len(failed) / len(POSITIVE)
    assert rate >= MIN_HIT_RATE, f"Trefferquote {rate:.0%}, Fehlschläge: {failed}"


@pytest.mark.parametrize("case", POSITIVE, ids=lambda c: str(c["id"]))
def test_positive_case_fields(case: Case) -> None:
    found = _run(case)
    assert _fields(found) == case["expect"]
    if "valid_from" in case:
        assert found.address_valid_from == case["valid_from"]
    if "salutation" in case:
        assert found.salutation == case["salutation"]
    if "name_old" in case:
        assert found.name_old == case["name_old"]
    assert found.bank_change_mentioned is False


@pytest.mark.parametrize("case", NEGATIVE, ids=lambda c: str(c["id"]))
def test_negative_case_yields_no_field_change(case: Case) -> None:
    """Kein Negativfall liefert eine Feldänderung; ohne Feldänderung entsteht ohne KI-Anbieter
    kein Vorschlag (``propose_contact_change``). Der Bankhinweis bleibt ein reiner Hinweis."""
    found = _run(case)
    assert found.changes == []
    assert found.name_new is None
    assert found.company_new is None


def test_reply_sentences_per_change_kind() -> None:
    today = date(2026, 9, 26)
    assert proposals.reply_sentences([{"field": "last_name", "new": "Müller"}]) == (
        "Wir haben unsere Stammdaten soeben korrigiert."
    )
    address = [
        {"field": "street", "new": "Lindenallee"},
        {"field": "house_number", "new": "7a"},
        {"field": "postal_code", "new": "50667"},
        {"field": "city", "new": "Köln"},
    ]
    assert proposals.reply_sentences(address, "2026-10-01", today) == (
        "Ihre neue Anschrift Lindenallee 7a, 50667 Köln haben wir ab dem 01.10.2026 in "
        "unseren Stammdaten hinterlegt."
    )
    assert proposals.reply_sentences(address, None, today) == (
        "Ihre neue Anschrift Lindenallee 7a, 50667 Köln haben wir zum 26.09.2026 in "
        "unseren Stammdaten hinterlegt."
    )
    both = proposals.reply_sentences(
        [{"field": "email", "new": "neu@example.org"}, {"field": "phone", "new": "0171 1"}]
    )
    assert both == (
        "Ihre neue E-Mail-Adresse neu@example.org haben wir hinterlegt und schreiben Sie "
        "künftig unter dieser Adresse an. Ihre neue Telefonnummer 0171 1 haben wir hinterlegt."
    )
    assert proposals.reply_sentences([]) == "Wir haben unsere Stammdaten soeben korrigiert."
    for text in (both, proposals.reply_sentences(address, None, today)):
        assert chr(0x2013) not in text
        assert chr(0x2014) not in text


def test_greeting_uses_gender_only_when_known() -> None:
    assert proposals.greeting_for("Frau", "Müller", "Jacqueline Müller") == "Hallo Frau Müller"
    assert proposals.greeting_for(None, "Beispiel", "Peter Beispiel") == "Guten Tag Peter Beispiel"
    assert proposals.greeting_for("Firma", "Beispiel", "Peter Beispiel") == (
        "Guten Tag Peter Beispiel"
    )
    assert proposals.greeting_for(None, None, None) == "Guten Tag"


def test_reply_for_takes_salutation_from_signature_when_contact_has_none() -> None:
    case = next(c for c in POSITIVE if c["id"] == "name_mit_frau_in_signatur")
    found = _run(case)
    draft = proposals._reply_for(None, found.changes, case["subject"], found.salutation, None)
    assert draft["body"].startswith("Hallo Frau Roth,\n\nvielen Dank. Wir haben unsere Stammdaten")
    neutral = proposals._reply_for(
        None, [{"field": "last_name", "old": None, "new": "Roth"}], "x", None, None
    )
    assert neutral["body"].startswith("Guten Tag,\n\nvielen Dank.")
