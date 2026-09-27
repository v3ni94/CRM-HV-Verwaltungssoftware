"""System catalogues of annex B (Ergänzung 27.09.2026, section 4.11 and annex B).

Every list of annex B that is a select list becomes a catalogue with system entries per
tenant (``catalog_entry.is_system``). Tenants extend catalogues with own entries and may
deactivate system entries, but never delete them (AP4, operator decision 27.09.2026:
catalogues serve new fields, code enums that mirror a list stay and are only documented).

The lists here are frozen reference data: migration 0152 and ``ensure_tenant_defaults``
seed from them idempotently (key: tenant, catalogue, code). Codes are stable identifiers
(``[a-z0-9_]``), labels the German display texts of annex B. B.16 (number ranges), B.27
(system roles) and B.29 (reports) are no select lists and are not seeded; roles live in
``platform``, reports in ``reports``.
"""

Entries = tuple[tuple[str, str], ...]


def _entries(*labels: str) -> Entries:
    """Builds ``(code, label)`` pairs from labels with deterministic slug codes."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label in labels:
        code = _slug(label)
        if code in seen:
            raise ValueError(f"duplicate catalogue code {code!r}")
        seen.add(code)
        out.append((code, label))
    return tuple(out)


_TRANS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e"})


def _slug(label: str) -> str:
    text = label.lower().translate(_TRANS)
    text = text.replace("§", "par").replace("%", "prozent")
    chars = [c if c.isalnum() else "_" for c in text]
    slug = "".join(chars)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")[:63]


# Annex B lists that are select lists. Key: catalogue name; value: (code, label) tuples.
ANNEX_B_CATALOGS: dict[str, Entries] = {
    # B.1
    "contact_group": _entries(
        "Mieter",
        "Mietinteressent",
        "Dienstleister und Handwerker",
        "Makler",
        "Verwalter",
        "Eigentümer",
        "Bank",
        "sonstiger Kontakt",
        "Neukunden-Akquise",
    ),
    # B.2
    "trade": _entries(
        "Abrechnungsunternehmen",
        "Dachdecker",
        "Elektriker",
        "Energieversorger",
        "Fensterbauer",
        "Gärtner",
        "Haftpflichtversicherer",
        "Hausmeister",
        "Heizung und Sanitär",
        "Kabel- und Telefonanbieter",
        "Klempner",
        "Kommunen",
        "Müllentsorger",
        "Rauchmelder und Brandschutz",
        "Reinigungsfirmen",
        "Sachversicherer",
        "Schlüsseldienste",
        "Schornsteinfeger",
        "sonstige Dienstleister",
        "Tischler",
        "Verwalter",
        "Wasserversorger",
        "Winterdienst",
    ),
    # B.3
    "address_label": _entries("Postanschrift", "Privat", "Arbeit", "öffentlich"),
    "phone_label": _entries(
        "Arbeit",
        "Fax Arbeit",
        "Mobil",
        "Privat",
        "Fax privat",
        "Pager",
        "andere",
        "öffentliches Telefon",
        "öffentlich Mobil",
        "öffentliches Fax",
    ),
    "email_label": _entries("Arbeit", "Privat", "öffentlich"),
    # B.4
    "bank_account_type": _entries(
        "Mietkonto",
        "Bankkonto 1",
        "Bankkonto 2",
        "WEG-Konto",
        "Rücklagenkonto",
        "Kautionskonto",
        "Hausgeldkonto",
        "Altkonto",
    ),
    # B.5
    "privacy_purpose": _entries(
        "Reparaturen und Beseitigung",
        "Ablesung und Austausch von Zählern",
        "Prüfung und Wartung von Anlagen",
        "Begutachtung durch Hausmeister",
        "themenbezogene Kontaktaufnahme",
        "Erstellung von Kaufangeboten",
    ),
    # B.6
    "note_category": _entries(
        "Schriftverkehr",
        "E-Mail",
        "Fax",
        "Anruf",
        "Vertrag",
        "Sollstellung",
        "Abrechnung",
        "Mieterhöhung",
        "Mietminderung",
        "Schaden",
        "Mahnung",
        "Kaution",
        "Beschwerde",
        "Schlüsselübergabe",
        "Wohnungsabnahme",
    ),
    # B.7 (property_type is the catalogue already checked by POST /properties)
    "property_type": _entries(
        "Altbau",
        "Bauernhaus",
        "Bungalow",
        "Burg",
        "Einfamilienhaus",
        "Herrenhaus",
        "Mehrfamilienhaus",
        "Neubau",
        "Stadthaus",
        "Straße",
        "Wohnblock",
    ),
    "management_type": (
        ("rental", "Mietverwaltung"),
        ("hoa", "WEG-Verwaltung"),
        ("hoa_with_sev", "WEG mit SE-Verwaltung"),
    ),
    "management_kind": _entries("Eigenverwaltung", "Fremdverwaltung"),
    # B.8
    "energy_source_property": _entries(
        "Biogas",
        "Steinkohle",
        "Koks",
        "Kokereigas",
        "Fernwärme",
        "Strom",
        "Strom für Wärmepumpe",
        "Erdwärme",
        "schweres Heizöl",
        "leichtes Heizöl",
        "Braunkohle",
        "Flüssiggas",
        "Nahwärme",
        "Erdgas H",
        "Erdgas L",
        "Solarenergie",
        "Holz",
        "Holz lufttrocken",
        "Holzhackschnitzel",
        "Holzpellets",
    ),
    "energy_source_building": _entries(
        "Gas", "Fernwärme", "Öl", "Solar", "Geothermie", "Pellet", "Elektro", "Kohle"
    ),
    "heating_type": (
        ("etage", "Etagenheizung"),
        ("ofen", "Ofenheizung"),
        ("zentral", "Zentralheizung"),
    ),
    # B.9 (payment_type: codes of the existing catalogue, extended by the WEG list)
    "payment_type": (
        ("rent", "Miete"),
        ("operating_cost_advance", "Betriebskosten-Vorauszahlung"),
        ("heating_cost_advance", "Heizkosten-Vorauszahlung"),
        ("garage", "Garagenmiete"),
        ("parking", "Stellplatzmiete"),
        ("rent_reduction", "Mietminderung"),
        ("hoa_fee", "Hausgeld"),
        ("reserve", "Erhaltungsrücklage"),
        ("special_levy", "Sonderumlage"),
        ("other", "Sonstige"),
    ),
    "payment_interval": (
        ("monthly", "monatlich"),
        ("quarterly", "quartalsweise"),
        ("half_yearly", "halbjährlich"),
        ("yearly", "jährlich"),
    ),
    "due_rule": (
        ("day", "Tag"),
        ("business_day", "Werktag"),
        ("last_day", "letzter Tag"),
        ("day_next_month", "Tag im Folgemonat"),
    ),
    "mandate_income_type": _entries(
        "Miete",
        "Betriebskosten-VZ",
        "Heizkosten-VZ",
        "Garage",
        "Stellplatz",
        "Hausgeld",
        "Erhaltungsrücklage",
        "Guthaben und Nachzahlung",
        "Zinsen",
        "Entnahme Rücklage",
        "vereinnahmte Mahngebühren",
        "Verzugszinsen",
        "Rücklastschriftgebühren",
        "Mietminderung",
    ),
    # B.10
    "unit_type": _entries(
        "Wohneinheit", "Gewerbeeinheit", "Optionsfläche", "Garage", "Stellplatz", "Garten"
    ),
    "unit_commercial_type": _entries(
        "Praxis", "Laden", "Büro", "Gastronomie", "Lagerhalle", "Industriehalle", "Werkstatt"
    ),
    # B.11
    "equipment_kitchen": _entries("Einbauküche", "Elektroherd", "Gasherd", "Küche mit Fenster"),
    "equipment_sanitary": _entries("Bad mit Fenster", "Badewanne", "Dusche", "Gäste-WC"),
    "equipment_misc": _entries("Aufzug", "Balkon", "Kabel-TV", "Rauchmelder", "Terrasse"),
    "equipment_hot_water": _entries(
        "Elektro-Boiler",
        "Elektro-Durchlauferhitzer",
        "Gas-Durchlauferhitzer",
        "Gas-Kombitherme",
        "zentrale Versorgung",
    ),
    "equipment_heating": _entries("Kamin"),
    "equipment_additional": _entries(
        "Abstellraum", "Bodenkammer", "Carport", "Garage", "Keller", "Stellplatz"
    ),
    # B.12
    "vat_option": _entries(
        "kein Gewerbe",
        "gewerblich ohne Umsatzsteuer",
        "gewerblich mit voller Umsatzsteuer",
        "gewerblich mit ermäßigter Umsatzsteuer",
    ),
    "vat_rate": (
        ("vat_0", "0 Prozent"),
        ("vat_5", "5 Prozent"),
        ("vat_7", "7 Prozent"),
        ("vat_16", "16 Prozent"),
        ("vat_19", "19 Prozent"),
    ),
    "vat_account_mode": (("none", "ohne"), ("full", "voll"), ("reduced", "ermäßigt")),
    # B.13
    "deposit_kind": _entries(
        "Kautionsversicherung",
        "Sparbuch",
        "Barkaution",
        "Bürgschaft",
        "Festgeld",
        "Patronatserklärung",
    ),
    # B.14
    "delivery_channel": _entries(
        "bevorzugter Zustellweg des Kontakts",
        "E-Post-Brief",
        "E-Mail mit Anhang",
        "E-Mail mit Freigabelink",
        "Druck",
        "Portal-Freigabe",
    ),
    "delivery_status": _entries("vorbereitet", "im Versand", "versendet", "fehlgeschlagen"),
    # B.15
    "notice_category": _entries(
        "Allgemein", "Hausordnung", "Reinigungsplan", "Wartung und Service"
    ),
    "notice_type": _entries("neutral", "Info", "Warnung", "Gefahrenhinweis"),
    # B.17
    "booking_type": _entries(
        "Sollstellung",
        "Rechnung",
        "benutzerdefinierte Buchung",
        "Bankumbuchung",
        "Kostenumbuchung",
        "Anfangsbestandsbuchung",
        "Zahlung Debitor",
    ),
    "bank_rule_action": _entries(
        "Zahlung Debitor",
        "Zahlung Kreditor",
        "Rechnung mit Zahlung",
        "Zuführung Rücklage",
        "Entnahme Rücklage",
        "SE-Rechnung mit Zahlung",
        "Auszahlung Einnahmeüberschuss",
        "Umbuchung Mieterträge",
    ),
    # B.18
    "invoice_plan_interval": _entries(
        "täglich",
        "alle 14 Tage",
        "monatlich",
        "alle 2 Monate",
        "quartalsweise",
        "halbjährlich",
        "jährlich",
    ),
    # B.19
    "bank_rule_criterion": _entries(
        "Kontoinhaber",
        "IBAN",
        "BIC",
        "Kontonummer",
        "Bankleitzahl",
        "End-to-End-Referenz",
        "Verwendungszweck",
        "Mandatsreferenz",
        "Betrag",
        "Ein- oder Auszahlung",
        "Geschäftsvorfall-Code",
        "eigenes Konto",
    ),
    "bank_rule_operator": _entries(
        "beinhaltet", "beinhaltet nicht", "beginnt mit", "endet mit", "ist", "ist nicht"
    ),
    # B.20
    "meeting_type": _entries(
        "ordentliche Eigentümerversammlung",
        "außerordentliche Eigentümerversammlung",
        "Wiederholungsversammlung",
        "Fortsetzungsversammlung",
        "Umlaufbeschluss",
        "Teilversammlung",
        "Gerichtsbeschluss",
    ),
    "meeting_presence": _entries("vor Ort", "online", "hybrid"),
    # B.21
    "majority_rule": _entries(
        "einfache Mehrheit",
        "relative Mehrheit",
        "Dreiviertelmehrheit",
        "allstimmig",
        "einstimmig",
        "nach §21 Abs. 2 WEG",
    ),
    "voting_principle": _entries(
        "Wertprinzip (MEA)", "Kopfprinzip", "Objektprinzip", "freies Beschlussprinzip"
    ),
    "proxy_kind": _entries("Generalvollmacht", "weisungsgebundene Vollmacht"),
    "proxy_status": _entries("offen", "bestätigt", "abgelehnt"),
    "attendance_wish": _entries("keine Angabe", "online", "vor Ort", "abgelehnt"),
    # B.22
    "resolution_status": _entries(
        "positiv",
        "negativ",
        "bestandskräftig",
        "angefochten",
        "aufgehoben",
        "gelöscht",
        "rechtskräftig",
        "bedeutungslos",
    ),
    # B.23
    "ticket_tracker": _entries(
        "Akquise",
        "Buchhaltung",
        "Makleraufträge",
        "Objektbetreuung",
        "Objektübernahme",
        "Sonstiges",
    ),
    "ticket_template": _entries(
        "Angebot",
        "Aufnahme",
        "Beratung",
        "Betriebskostenabrechnung",
        "Hausgeldabrechnung",
        "Heizkostenabrechnung",
        "Überweisung",
        "Widerspruch",
        "Verkauf",
        "Vermietung",
        "Baumangel",
        "Mieterhöhung",
        "Mieterhöhungsklage",
        "Reparaturanfrage",
        "Versicherungsfall",
        "Objektübernahme WEG",
        "Verwaltungsunterlagen",
        "Ticket",
    ),
    "portal_form_kind": _entries(
        "Änderungsmitteilung Mieterdaten", "Baumangel", "Schadensmeldung", "Störungsmeldung"
    ),
    # B.24
    "ticket_status": _entries(
        "neu", "in Bearbeitung", "wartend", "ausgeführt", "abgeschlossen", "abgewiesen"
    ),
    "ticket_priority": _entries("niedrig", "normal", "hoch", "dringend", "sofort"),
    # B.25
    "dms_category": _entries(
        "Angebote",
        "Auswertungen",
        "Bilder",
        "Dokumente",
        "Kontakte",
        "Mieterhöhungen",
        "Objektdaten",
        "Posteingang",
        "Rechnungswesen",
        "Ticketsystem",
        "Verträge",
        "Benutzerordner",
        "Unkategorisiert",
    ),
    # B.26
    "template_category": _entries(
        "Abrechnungen",
        "Archiv",
        "Auftragswesen",
        "Briefe",
        "Eigentümerversammlung",
        "Formulare",
        "Genehmigungen und Bescheinigungen",
        "Mahnwesen",
        "Mieterhöhung und Mietminderung",
        "Mitteilungen",
        "Protokolle",
        "Rechnungswesen",
        "Sonstiges",
        "Vertragswesen",
    ),
    # B.28 (codes are the values of custom_field_definition.field_type)
    "custom_field_type": (
        ("integer", "Ganzzahl"),
        ("number", "Nummer"),
        ("amount", "Betrag"),
        ("bool", "Ja/Nein"),
        ("date", "Datum"),
        ("datetime", "Datum und Uhrzeit"),
        ("string", "Zeichenkette"),
        ("text", "Text"),
        ("rich_text", "formatierter Text"),
        ("contact_ref", "Kontaktverknüpfung"),
        ("document_ref", "Dokumentverknüpfung"),
        ("property_ref", "Objektverknüpfung"),
        ("choice", "Einzelauswahl"),
        ("url", "URL"),
    ),
    # B.30
    "calendar_recurrence": (
        ("none", "keine"),
        ("daily", "täglich"),
        ("weekly", "wöchentlich"),
        ("monthly", "monatlich"),
        ("yearly", "jährlich"),
    ),
    "calendar_reminder": (
        ("at_start", "zu Beginn"),
        ("5m", "5 Minuten vorher"),
        ("10m", "10 Minuten vorher"),
        ("15m", "15 Minuten vorher"),
        ("30m", "30 Minuten vorher"),
        ("1h", "1 Stunde vorher"),
        ("2h", "2 Stunden vorher"),
        ("4h", "4 Stunden vorher"),
        ("1d", "1 Tag vorher"),
    ),
    "maintenance_reminder": (
        ("14d", "14 Tage vor Ablauf"),
        ("1m", "1 Monat vor Ablauf"),
        ("3m", "3 Monate vor Ablauf"),
        ("6m", "6 Monate vor Ablauf"),
    ),
    "portal_access_end": (
        ("setting", "laut Einstellung"),
        ("1m", "1 Monat"),
        ("3m", "3 Monate"),
        ("6m", "6 Monate"),
        ("9m", "9 Monate"),
        ("12m", "12 Monate"),
        ("18m", "18 Monate"),
        ("24m", "24 Monate"),
        ("30m", "30 Monate"),
        ("36m", "36 Monate"),
    ),
}

# B.28 field types accepted by custom_field_definition.field_type.
CUSTOM_FIELD_TYPES: frozenset[str] = frozenset(
    code for code, _ in ANNEX_B_CATALOGS["custom_field_type"]
)
# 4.11: entities that carry custom fields.
CUSTOM_FIELD_ENTITIES: tuple[str, ...] = (
    "property",
    "building",
    "unit",
    "contract",
    "contact",
    "service_provider",
    "service_provider_relation",
)
CUSTOM_FIELD_UNIQUENESS: tuple[str, ...] = ("none", "contract", "all_contracts")
