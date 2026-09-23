"""Draft chart of accounts from annex A.1 (HVM convention excerpt).

Only accounts named in annex A.1 are included; numbers are not invented. Category and type
follow the ranges of section 7.2 (assumption A-023). Allocation category and statement kind
are left at "none" unless A.1 states them, because allocability and treatment depend on the
case (7.2, Ergänzende Einordnung). The template is created unreleased; releasing it is the
operator decision V8.
"""

from typing import Any

HOA = ["hoa"]
ALL = ["hoa", "rental_owner", "sev_owner", "manager"]


def _a(
    number: str,
    name: str,
    category: str,
    type_: str,
    applies_to: list[str],
    statement_kind: str = "none",
    cash: bool = False,
) -> dict[str, Any]:
    return {
        "number": number,
        "name": name,
        "category": category,
        "type": type_,
        "statement_kind": statement_kind,
        "allocation_category": "none",
        "vat_option": "none",
        "relevant_for_cash_report": cash,
        "applies_to": applies_to,
    }


COSTS = [
    ("040100", "Hausmeisterkosten"),
    ("040200", "Hausmeistergehalt"),
    ("040300", "Reinigungskosten"),
    ("040400", "Gartenarbeiten und Pflege Außenanlagen"),
    ("040500", "Winterdienst"),
    ("041000", "Brennstoffkosten"),
    ("041100", "Schornsteinfeger"),
    ("041200", "Emissionsmessung"),
    ("041300", "Wartung Heizung"),
    ("041400", "Heizungsreparaturen"),
    ("041500", "Miete Heizungszähler"),
    ("041600", "Miete Kaltwasserzähler"),
    ("041700", "Miete Warmwasserzähler"),
    ("041800", "Servicekosten Heizkostenabrechnung"),
    ("041801", "Servicekosten Wasserabrechnung"),
    ("041805", "Rauchwarnmelder"),
    ("042000", "Wasser allgemein"),
    ("042100", "Trinkwasser"),
    ("042200", "Abwasser"),
    ("042300", "Niederschlagswasser"),
    ("043000", "Allgemeinstrom"),
]

A1_ACCOUNTS: list[dict[str, Any]] = [
    _a("001200", "WEG-Konto", "bank", "asset", HOA, cash=True),
    _a("001201", "Rücklagenkonto", "bank", "asset", HOA, cash=True),
    _a("001300", "Kasse", "cash", "asset", ALL, cash=True),
    _a("001400", "Überzahlungen aus Vorjahren", "technical", "liability", ALL),
    _a("008000", "Erhaltungsrücklage", "reserve", "liability", HOA, "reserve"),
    _a("008500", "Darlehen", "loan", "liability", ALL),
    _a("008600", "Hypotheken", "loan", "liability", ALL),
    _a("009000", "Anfangsbestandskonto", "opening_balance", "liability", ALL),
    _a("009999", "Durchlaufposten WEG", "transit", "asset", HOA),
    _a("026000", "Vorsteuerrückerstattungen", "tax", "income", ALL),
    _a("027000", "Durchlaufposten Skonti", "transit", "asset", ALL),
    _a("028100", "Zinseinnahmen WEG-Konto", "revenue", "income", HOA),
    _a("028101", "Zinseinnahmen Erhaltungsrücklage", "revenue", "income", HOA, "reserve"),
    _a("029100", "Entnahme Erhaltungsrücklage", "technical", "income", HOA, "reserve"),
    _a("030000", "Zuführung Erhaltungsrücklage", "technical", "expense", HOA, "reserve"),
    *[_a(n, name, "cost", "expense", ALL) for n, name in COSTS],
    _a("060100", "Hausgeld", "revenue", "income", HOA, "hoa_fee"),
    _a("060200", "Erhaltungsrücklage (Sollstellung)", "revenue", "income", HOA, "reserve"),
]

DEFAULT_CODE = "a1"
DEFAULT_NAME = "Kontenrahmen nach Anhang A.1 (Entwurf, Freigabe V8 offen)"
