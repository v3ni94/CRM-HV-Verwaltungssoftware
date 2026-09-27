"""Draft chart of accounts from annex A.1 (HVM convention excerpt).

``A1_ACCOUNTS`` holds only accounts named in annex A.1; numbers are not invented. Category
and type follow the ranges of section 7.2 (assumption A-023). Allocation category and
statement kind are left at "none" unless A.1 states them, because allocability and treatment
depend on the case (7.2, Ergänzende Einordnung). The template is created unreleased;
releasing it is the operator decision V8.

``PROPOSED_ACCOUNTS`` (operator decision M10-01 of 26.09.2026): the revenue accounts of the
rental management that annex A.1 names only by payment kind (7.2, range 060000 to 069999)
are proposed following the A.1 numbering pattern (060100 Hausgeld, 060200 Erhaltungsrücklage,
then one hundred step per payment kind). Each proposal carries ``review_status = "entwurf"``
and the note "Freigabe durch Steuerberatung offen"; allocation, statement kind and VAT option
stay unset (M10-02 open). Deposits (Kaution) and rent receivables get no proposed number:
7.2 defines no range for deposit liabilities and receivables are the debtor accounts
(090000 to 099999, one per contract); see OPEN_QUESTIONS M10-01.

Cost account presets (operator decision M10-02 of 26.09.2026): the cost accounts of annex A.1
are pre-set as a DRAFT following the Betriebskostenverordnung (BetrKV, source register R07).
Accounts that belong to one of the operating cost types of the BetrKV catalogue become
allocable with the customary key (living area for most, consumption for heating, hot water
and water where meters exist); the remaining cost accounts (repairs) are not allocable. The
VAT option stays unset. Every preset carries ``review_status = "entwurf"`` and the note
"Freigabe durch Steuerberatung offen"; the BetrKV reference is kept on the template row as
``betrkv_reference`` for the review only. ``fill_unset`` applies the presets to template rows
that still carry ``"none"`` and never overwrites operator edits. The preset is a proposal, not
a legal classification: the billing lock (M17-01, A02) still requires the classification per
account and property, and the mixed cases (e.g. smoke detectors) stay ``"none"``.
"""

from typing import Any

HOA = ["hoa"]
ALL = ["hoa", "rental_owner", "sev_owner", "manager"]
RENTAL = ["rental_owner", "sev_owner"]

REVIEW_NONE = "none"
REVIEW_DRAFT = "entwurf"
DRAFT_NOTE = "Freigabe durch Steuerberatung offen"


def _a(
    number: str,
    name: str,
    category: str,
    type_: str,
    applies_to: list[str],
    statement_kind: str = "none",
    cash: bool = False,
    review_status: str = REVIEW_NONE,
    note: str | None = None,
    allocation: str = "none",
    key: str | None = None,
    betrkv: str | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "name": name,
        "category": category,
        "type": type_,
        "statement_kind": statement_kind,
        "allocation_category": allocation,
        "vat_option": "none",
        "relevant_for_cash_report": cash,
        "applies_to": applies_to,
        "review_status": review_status,
        "review_note": note,
        # M10-02: proposed allocation key (code of the annex A.2 standard list) and the BetrKV
        # cost type the proposal refers to; both are review information, not applied to ledgers.
        "allocation_key_code": key,
        "betrkv_reference": betrkv,
    }


# Operating cost types of the BetrKV catalogue (§ 2 BetrKV) as commonly listed; the official
# wording of number 15 changed with the telecommunications reform and is to be checked with the
# tax adviser ("zu prüfen"). Numbers are the catalogue numbers, used only as review reference.
BETRKV_TYPES: dict[int, str] = {
    1: "Laufende öffentliche Lasten des Grundstücks (Grundsteuer)",
    2: "Wasserversorgung",
    3: "Entwässerung",
    4: "Heizung (zentrale Heizungsanlage)",
    5: "Warmwasserversorgung (zentrale Warmwasserversorgungsanlage)",
    6: "Verbundene Heizungs- und Warmwasserversorgungsanlagen",
    7: "Aufzug",
    8: "Straßenreinigung und Müllbeseitigung",
    9: "Gebäudereinigung und Ungezieferbekämpfung",
    10: "Gartenpflege",
    11: "Beleuchtung",
    12: "Schornsteinreinigung",
    13: "Sach- und Haftpflichtversicherung",
    14: "Hauswart",
    15: "Gemeinschaftsantenne, Breitbandnetz (Wortlaut zu prüfen)",
    16: "Einrichtungen für die Wäschepflege",
    17: "Sonstige Betriebskosten",
}

ALLOC_HEATING = "allocable_heating"
ALLOC_WATER = "allocable_water"
ALLOC_OTHER = "allocable_other"
NON_HEATING = "non_allocable_heating"
NON_OTHER = "non_allocable_other"
KEY_AREA = "WFL"  # Wohnfläche (annex A.2)
KEY_HEATING = "V_HEIZ"  # Verbrauch Heizung
KEY_HOT_WATER = "V_WW"  # Verbrauch Warmwasser
KEY_COLD_WATER = "V_KW"  # Verbrauch Kaltwasser

# (number, name, allocation_category, proposed key, BetrKV reference). Draft M10-02.
# Keys: area for most; consumption for heating, hot water and water (where meters exist,
# otherwise persons or area per property; the per property key stays a property decision).
COSTS: list[tuple[str, str, str, str | None, str | None]] = [
    ("040100", "Hausmeisterkosten", ALLOC_OTHER, KEY_AREA, "§ 2 Nr. 14 Hauswart"),
    ("040200", "Hausmeistergehalt", ALLOC_OTHER, KEY_AREA, "§ 2 Nr. 14 Hauswart"),
    ("040300", "Reinigungskosten", ALLOC_OTHER, KEY_AREA, "§ 2 Nr. 9 Gebäudereinigung"),
    (
        "040400",
        "Gartenarbeiten und Pflege Außenanlagen",
        ALLOC_OTHER,
        KEY_AREA,
        "§ 2 Nr. 10 Gartenpflege",
    ),
    ("040500", "Winterdienst", ALLOC_OTHER, KEY_AREA, "§ 2 Nr. 8 Straßenreinigung"),
    ("041000", "Brennstoffkosten", ALLOC_HEATING, KEY_HEATING, "§ 2 Nr. 4 Heizung"),
    (
        "041100",
        "Schornsteinfeger",
        ALLOC_HEATING,
        KEY_HEATING,
        "§ 2 Nr. 4 Heizung bei Zentralheizung, sonst Nr. 12 (zu prüfen)",
    ),
    ("041200", "Emissionsmessung", ALLOC_HEATING, KEY_HEATING, "§ 2 Nr. 4 Heizung"),
    ("041300", "Wartung Heizung", ALLOC_HEATING, KEY_HEATING, "§ 2 Nr. 4 Heizung"),
    ("041400", "Heizungsreparaturen", NON_HEATING, None, "Instandsetzung, keine Betriebskosten"),
    ("041500", "Miete Heizungszähler", ALLOC_HEATING, KEY_HEATING, "§ 2 Nr. 4 Heizung"),
    ("041600", "Miete Kaltwasserzähler", ALLOC_WATER, KEY_COLD_WATER, "§ 2 Nr. 2 Wasser"),
    ("041700", "Miete Warmwasserzähler", ALLOC_HEATING, KEY_HOT_WATER, "§ 2 Nr. 5 Warmwasser"),
    (
        "041800",
        "Servicekosten Heizkostenabrechnung",
        ALLOC_HEATING,
        KEY_HEATING,
        "§ 2 Nr. 4 Heizung",
    ),
    (
        "041801",
        "Servicekosten Wasserabrechnung",
        ALLOC_WATER,
        KEY_COLD_WATER,
        "§ 2 Nr. 2 Wasser",
    ),
    # Mixed account (rent and maintenance of smoke detectors): no preset, classification per
    # property and contract with the tax adviser (billing lock stays active).
    ("041805", "Rauchwarnmelder", "none", None, "Einordnung zu prüfen (Miete/Wartung)"),
    ("042000", "Wasser allgemein", ALLOC_WATER, KEY_COLD_WATER, "§ 2 Nr. 2 Wasser"),
    ("042100", "Trinkwasser", ALLOC_WATER, KEY_COLD_WATER, "§ 2 Nr. 2 Wasser"),
    ("042200", "Abwasser", ALLOC_WATER, KEY_COLD_WATER, "§ 2 Nr. 3 Entwässerung"),
    ("042300", "Niederschlagswasser", ALLOC_WATER, KEY_AREA, "§ 2 Nr. 3 Entwässerung"),
    ("043000", "Allgemeinstrom", ALLOC_OTHER, KEY_AREA, "§ 2 Nr. 11 Beleuchtung"),
]

# BetrKV types without an account in annex A.1 (no numbers invented, see OPEN_QUESTIONS M10-02).
BETRKV_TYPES_WITHOUT_ACCOUNT: tuple[int, ...] = (1, 6, 7, 13, 15, 16, 17)


def _cost(
    number: str, name: str, allocation: str, key: str | None, betrkv: str | None
) -> dict[str, Any]:
    preset = allocation != "none"
    return _a(
        number,
        name,
        "cost",
        "expense",
        ALL,
        statement_kind="operating_costs" if allocation.startswith("allocable") else "none",
        review_status=REVIEW_DRAFT if preset else REVIEW_NONE,
        note=DRAFT_NOTE if preset else None,
        allocation=allocation,
        key=key,
        betrkv=betrkv,
    )


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
    *[_cost(*row) for row in COSTS],
    _a("060100", "Hausgeld", "revenue", "income", HOA, "hoa_fee"),
    _a("060200", "Erhaltungsrücklage (Sollstellung)", "revenue", "income", HOA, "reserve"),
]

# Proposal M10-01 (26.09.2026): rental revenue accounts, draft until the tax adviser releases.
PROPOSED_ACCOUNTS: list[dict[str, Any]] = [
    _a(n, name, "revenue", "income", RENTAL, review_status=REVIEW_DRAFT, note=DRAFT_NOTE)
    for n, name in [
        ("060300", "Miete"),
        ("060400", "Betriebskostenvorauszahlung"),
        ("060500", "Heizkostenvorauszahlung"),
        ("060600", "Garagenmiete"),
        ("060700", "Stellplatzmiete"),
        ("060800", "Sonstige Erlöse"),
    ]
]

TEMPLATE_ACCOUNTS: list[dict[str, Any]] = [*A1_ACCOUNTS, *PROPOSED_ACCOUNTS]


def merge_missing(
    existing: list[dict[str, Any]], wanted: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return ``existing`` plus the rows of ``wanted`` whose number is not yet present.

    Existing rows are never changed (idempotent seed, no overwrite of tenant edits).
    """
    known = {row["number"] for row in existing}
    return [*existing, *[row for row in wanted if row["number"] not in known]]


# Fields the M10-02 preset may fill on an existing template row while they are still unset.
PRESET_FIELDS = ("allocation_category", "statement_kind", "allocation_key_code")
# Review information only: filled when unset, but does not make the row a draft by itself.
INFO_FIELDS = ("betrkv_reference",)


def _unset(value: Any) -> bool:
    return value is None or value == "none"


def fill_unset(
    existing: list[dict[str, Any]], wanted: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    """Fill the M10-02 preset fields of ``existing`` rows that are still unset.

    A field is filled only if the existing row has ``None`` or ``"none"`` and the template
    proposes a value; operator edits (any other value) are kept. A row that received a preset
    is marked ``review_status = "entwurf"`` with the draft note unless it already carries a
    review status. Returns the new list and whether anything changed. Rows are copied, so the
    JSONB column notices the change.
    """
    by_number = {row["number"]: row for row in wanted}
    result: list[dict[str, Any]] = []
    changed = False
    for row in existing:
        spec = by_number.get(row["number"])
        if spec is None:
            result.append(row)
            continue
        new = dict(row)
        filled = False
        for field in PRESET_FIELDS:
            if _unset(new.get(field)) and not _unset(spec.get(field)):
                new[field] = spec[field]
                filled = True
        if filled and _unset(new.get("review_status")):
            new["review_status"] = REVIEW_DRAFT
            new["review_note"] = new.get("review_note") or DRAFT_NOTE
        for field in INFO_FIELDS:
            if _unset(new.get(field)) and not _unset(spec.get(field)):
                new[field] = spec[field]
                changed = True
        result.append(new)
        changed = changed or filled
    return result, changed


DEFAULT_CODE = "a1"
DEFAULT_NAME = "Kontenrahmen nach Anhang A.1 (Entwurf, Freigabe V8 offen)"
