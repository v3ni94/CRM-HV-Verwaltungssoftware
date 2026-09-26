"""Hallo-Heidi-Anrufe (mhvp.tickets.call_assistant): Erkennung, Regex-Extraktion,
Nummernnormalisierung und Namensabgleich ohne Datenbank."""

from mhvp.contacts.models import Contact, ContactKind
from mhvp.tickets import call_assistant as ca

PROTOCOL = """Neue Gesprächsnotiz von Hallo Heidi

Anrufer: Frau Petra Schneider
Rückrufnummer: 0171 / 234 56 78
Objekt: Lindenstr. 12, 40210 Düsseldorf
Einheit: Whg. 3, 2. OG links
Anliegen: Die Heizung in der Wohnung bleibt seit gestern kalt.
Bitte um Rückruf.

Datum: 26.09.2026 09:14
"""


def test_detection_by_sender_subject_and_body() -> None:
    cfg = ca.config_from({})
    assert ca.is_call_mail(cfg, "notiz@hallo-heidi.de", "Neuer Anruf", "")
    assert ca.is_call_mail(cfg, "x@example.org", "Hallo Heidi: Anruf", "")
    assert ca.is_call_mail(cfg, "x@example.org", "Anruf", "Hallo Heidi\nTelefon: 0171 2345678")
    # Anrede an eine Mitarbeiterin ohne Protokollmerkmale ist kein Anruf.
    assert not ca.is_call_mail(cfg, "mieter@example.org", "Frage", "Hallo Heidi, wie geht es?")
    custom = ca.config_from({"sender_patterns": ["@telefonbot.example"], "keywords": []})
    assert ca.is_call_mail(custom, "bot@telefonbot.example", "Anruf", "")
    assert not ca.is_call_mail(custom, "notiz@hallo-heidi.de", "Anruf", "")
    assert not ca.is_call_mail(ca.config_from({"enabled": False}), "a@hallo-heidi.de", "", "")


def test_extraction_from_protocol() -> None:
    data = ca.extract("Hallo Heidi: Anruf", PROTOCOL)
    assert data.caller_phone == "+491712345678"
    assert data.caller_phone_label == "mobile"
    assert data.caller_name == "Petra Schneider"
    assert data.salutation == "Frau"
    assert data.street == "Lindenstr."
    assert data.house_number == "12"
    assert data.unit_number == "3"
    assert data.floor == "2. OG links"
    assert data.concern == "Die Heizung in der Wohnung bleibt seit gestern kalt. Bitte um Rückruf."
    assert data.callback_requested


def test_extraction_variants() -> None:
    data = ca.extract(
        "Anruf", "Herr Max Weber hat angerufen.\nObjekt Nr. 104, WE 12\nTelefon: +49 211 9876543"
    )
    assert data.caller_name == "Max Weber"
    assert data.salutation == "Herr"
    assert data.property_number == "104"
    assert data.unit_number == "12"
    assert data.caller_phone == "+492119876543"
    assert data.caller_phone_label == "other"
    assert ca.extract("Anruf", "ohne Angaben").caller_phone is None


def test_phone_normalisation_and_label() -> None:
    assert ca.normalise_e164("0171-2345678") == "+491712345678"
    assert ca.normalise_e164("+49 (0)171 2345678") in ("+491712345678", None)
    assert ca.normalise_e164("0049 1512 3456789") == "+4915123456789"
    assert ca.normalise_e164("123") is None
    assert ca.phone_label("+4916012345678") == "mobile"
    assert ca.phone_label("+4921112345") == "other"


def test_ai_fills_gaps_only() -> None:
    data = ca.extract("Anruf", "Telefon: 0171 2345678")
    merged = ca.merge_ai(
        data,
        {
            "caller_name": "Petra Schneider",
            "property_hint": "Objekt 104",
            "unit_hint": "Whg. 7",
            "concern": "Heizung kalt.",
            "callback_requested": True,
            "confidence": 0.8,
        },
    )
    assert merged.caller_name == "Petra Schneider"
    assert merged.sources["caller_name"] == "ai"
    assert merged.property_number == "104"
    assert merged.unit_number == "7"
    assert merged.caller_phone == "+491712345678"
    low = ca.merge_ai(ca.extract("Anruf", ""), {"caller_name": "X Y", "confidence": 0.2})
    assert low.caller_name is None


def test_name_and_street_matching() -> None:
    contact = Contact(kind=ContactKind.PERSON, first_name="Petra", last_name="Schneider")
    assert ca.name_matches(contact, "Petra Schneider")
    assert ca.name_matches(contact, "schneider")
    assert not ca.name_matches(contact, "Anna Schneider")
    assert ca.street_key("Lindenstr.") == ca.street_key("Lindenstraße")
    assert ca.street_key("Linden Strasse") == ca.street_key("Lindenstr")
