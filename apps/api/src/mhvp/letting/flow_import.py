"""FLOW import (M28 stage 4): parser for MySQL/MariaDB SQL dumps of the FLOW database
(phpMyAdmin or mysqldump style) and the mapping from FLOW rows to CRM listing fields.

Only the six tables of the FLOW data contract (docs/datenvertrag.md, sections 2.2 to 2.9) are
read: ``listings``, ``listing_prices``, ``listing_energies``, ``listing_internals``,
``listing_flowfact_links``, ``listing_portal_publications``. Everything else in the dump is
ignored. This module never calls FLOWFACT and never writes to the database; it only produces a
preview structure that the router persists (rule 0.1.6, docs/rules/M28-01.md).
"""

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

CENT = Decimal("0.01")

TABLES = (
    "listings",
    "listing_prices",
    "listing_energies",
    "listing_internals",
    "listing_flowfact_links",
    "listing_portal_publications",
)

# FLOW listings.status -> CRM listing.status (docs/rules/M28-01.md, section 4.1 of the
# data contract).
STATUS_MAP = {
    "entwurf": "draft",
    "bereit": "draft",
    "veroeffentlicht": "active",
    "zurueckgezogen": "inactive",
    "archiviert": "inactive",
}

# FLOW listing_flowfact_links.sync_status -> CRM listing.publication_status placeholder.
PUBLICATION_MAP = {
    "uebertragen": "handed_over",
    "geaendert_seit_uebertragung": "handed_over",
    "fehlgeschlagen": "error",
}

OBJECT_TYPE_MAP = {
    "wohnung": "wohnung",
    "haus": "haus",
    "gewerbe": "gewerbe",
    "stellplatz": "stellplatz",
    "grundstueck": "grundstueck",
}

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+`?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)`?\s*"
    r"(?:\((?P<columns>[^)]*)\)\s*)?VALUES\s*(?P<values>.+?);",
    re.IGNORECASE | re.DOTALL,
)


class FlowDumpError(ValueError):
    """Raised when the dump cannot be parsed at all (not a syntax report per row)."""


def _split_columns(raw: str) -> list[str]:
    return [c.strip().strip("`\"'") for c in raw.split(",") if c.strip()]


def _tokenize_rows(values_blob: str) -> list[str]:
    """Split ``(a, b, 'c,d'), (e, f)`` into one string per parenthesised row, honouring
    quoted strings with backslash and doubled quote escaping."""
    rows: list[str] = []
    depth = 0
    current: list[str] = []
    in_string: str | None = None
    i = 0
    n = len(values_blob)
    while i < n:
        ch = values_blob[i]
        if in_string is not None:
            current.append(ch)
            if ch == "\\" and i + 1 < n:
                current.append(values_blob[i + 1])
                i += 2
                continue
            if ch == in_string:
                # doubled-quote escape: '' or ""
                if i + 1 < n and values_blob[i + 1] == in_string:
                    current.append(values_blob[i + 1])
                    i += 2
                    continue
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            current.append(ch)
            i += 1
            continue
        if ch == "(":
            if depth == 0:
                current = []
            else:
                current.append(ch)
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                rows.append("".join(current))
            else:
                current.append(ch)
            i += 1
            continue
        if depth > 0:
            current.append(ch)
        i += 1
    return rows


def _split_fields(row: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    in_string: str | None = None
    i = 0
    n = len(row)
    while i < n:
        ch = row[i]
        if in_string is not None:
            if ch == "\\" and i + 1 < n:
                current.append(ch)
                current.append(row[i + 1])
                i += 2
                continue
            if ch == in_string:
                if i + 1 < n and row[i + 1] == in_string:
                    current.append(ch)
                    current.append(row[i + 1])
                    i += 2
                    continue
                current.append(ch)
                in_string = None
                i += 1
                continue
            current.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            current.append(ch)
            i += 1
            continue
        if ch == ",":
            fields.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    fields.append("".join(current).strip())
    return fields


def _unescape(literal: str) -> str:
    quote = literal[0]
    body = literal[1:-1]
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "\\" and i + 1 < n:
            nxt = body[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", "'": "'", '"': '"'}
            out.append(mapping.get(nxt, nxt))
            i += 2
            continue
        if ch == quote and i + 1 < n and body[i + 1] == quote:
            out.append(quote)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw.upper() == "NULL":
        return None
    if raw and raw[0] in ("'", '"') and raw[-1] == raw[0] and len(raw) >= 2:
        return _unescape(raw)
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        return Decimal(raw)
    except Exception:
        return raw.strip("`")


def parse_dump(text: str) -> dict[str, list[dict[str, Any]]]:
    """Parse a mysqldump/phpMyAdmin SQL dump and return rows per known table.

    Statements may span several lines; only ``INSERT INTO`` statements for the six known
    tables are read. Anything else (CREATE TABLE, comments, other tables) is ignored.
    """
    tables: dict[str, list[dict[str, Any]]] = {t: [] for t in TABLES}
    found_any = False
    for match in _INSERT_RE.finditer(text):
        table = match.group("table")
        if table not in tables:
            continue
        found_any = True
        columns_raw = match.group("columns")
        columns = _split_columns(columns_raw) if columns_raw else None
        for row_text in _tokenize_rows(match.group("values")):
            values = [_parse_value(v) for v in _split_fields(row_text)]
            if columns is None:
                # Positional dump without an explicit column list is not supported: the
                # FLOW export always emits explicit column names (mysqldump default).
                raise FlowDumpError(
                    f"INSERT INTO `{table}` ohne Spaltenliste wird nicht unterstützt."
                )
            if len(values) != len(columns):
                continue
            tables[table].append(dict(zip(columns, values, strict=False)))
    if not found_any:
        raise FlowDumpError("Kein INSERT der FLOW-Tabellen im Dump gefunden.")
    return tables


def _cents_to_eur(value: Any) -> Decimal | None:
    if value is None:
        return None
    return (Decimal(value) / Decimal(100)).quantize(CENT)


@dataclass
class RowPreview:
    index: int
    external_uuid: str | None
    external_ref: str | None
    title: str | None
    kind: str
    object_type: str
    status: str
    listing_fields: dict[str, Any]
    match: dict[str, Any]
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "external_uuid": self.external_uuid,
            "external_ref": self.external_ref,
            "title": self.title,
            "kind": self.kind,
            "object_type": self.object_type,
            "status": self.status,
            "listing_fields": _jsonable(self.listing_fields),
            "match": self.match,
            "problems": self.problems,
        }


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Decimal | uuid.UUID):
            out[key] = str(value)
        else:
            out[key] = value
    return out


def build_previews(dump: dict[str, list[dict[str, Any]]]) -> list[RowPreview]:
    prices_by_listing = {row["listing_id"]: row for row in dump["listing_prices"]}
    energy_by_listing = {row["listing_id"]: row for row in dump["listing_energies"]}
    internals_by_listing = {row["listing_id"]: row for row in dump["listing_internals"]}
    links_by_listing = {row["listing_id"]: row for row in dump["listing_flowfact_links"]}

    previews: list[RowPreview] = []
    for index, listing in enumerate(dump["listings"]):
        problems: list[str] = []
        listing_id = listing.get("id")
        price = prices_by_listing.get(listing_id, {})
        energy = energy_by_listing.get(listing_id, {})
        internal = internals_by_listing.get(listing_id)
        link = links_by_listing.get(listing_id, {})

        vermarktungsart = listing.get("vermarktungsart")
        if vermarktungsart == "miete":
            kind: str | None = "rental"
        elif vermarktungsart == "kauf":
            kind = "sale"
        else:
            kind = None
        if kind is None:
            problems.append(f"Unbekannte Vermarktungsart: {vermarktungsart!r}")
            kind = "rental"

        object_type = OBJECT_TYPE_MAP.get(str(listing.get("objektart")))
        if object_type is None:
            problems.append(f"Unbekannte Objektart: {listing.get('objektart')!r}")
            object_type = "wohnung"

        flow_status = listing.get("status")
        status = STATUS_MAP.get(str(flow_status))
        if status is None:
            problems.append(f"Unbekannter Bearbeitungsstatus: {flow_status!r}")
            status = "draft"

        publication_status = "not_published"
        flowfact_entity_id = link.get("flowfact_entity_id")
        sync_status = link.get("sync_status")
        if sync_status in PUBLICATION_MAP:
            publication_status = PUBLICATION_MAP[sync_status]
            if publication_status == "handed_over" and not flowfact_entity_id:
                problems.append(
                    "sync_status uebertragen ohne flowfact_entity_id; publication_status "
                    "bleibt handed_over, FLOWFACT-Kennung fehlt."
                )

        additional_costs = _cents_to_eur(price.get("nebenkosten_cent"))
        heating_costs = _cents_to_eur(price.get("heizkosten_cent"))
        heating_in_additional = bool(price.get("heizkosten_in_nebenkosten_enthalten") or False)
        if kind == "rental":
            listing_price = _cents_to_eur(price.get("kaltmiete_cent"))
            if listing_price is None:
                problems.append("Kaltmiete fehlt (kaltmiete_cent).")
        else:
            listing_price = _cents_to_eur(price.get("kaufpreis_cent"))
            additional_costs = None
            heating_costs = None
            if listing_price is None:
                problems.append("Kaufpreis fehlt (kaufpreis_cent).")

        deposit = _cents_to_eur(price.get("kaution_cent")) if kind == "rental" else None
        hoa_fee = _cents_to_eur(price.get("hausgeld_cent"))
        parking_price = _cents_to_eur(
            price.get("stellplatz_miete_cent")
            if kind == "rental"
            else price.get("stellplatz_kaufpreis_cent")
        )
        commission_type_map = {
            "provisionsfrei": "provisionsfrei",
            "provisionspflichtig": "provisionspflichtig",
        }
        commission_type = commission_type_map.get(str(price.get("provision_typ")))

        energy_status_map = {
            "liegt_vor": "liegt_vor",
            "nicht_erforderlich": "nicht_erforderlich",
            "in_erstellung": "in_erstellung",
        }
        energy_status = energy_status_map.get(str(energy.get("status")), "in_erstellung")
        energy_type_map = {"bedarf": "bedarf", "verbrauch": "verbrauch"}
        energy_type = energy_type_map.get(str(energy.get("ausweistyp")))
        if energy_status == "liegt_vor" and (
            energy_type is None
            or energy.get("kennwert_kwh") is None
            or energy.get("effizienzklasse") is None
        ):
            problems.append(
                "Energieausweis liegt_vor ohne vollständige Angaben (Ausweistyp, Kennwert, "
                "Effizienzklasse); vor Aktivierung nachzutragen."
            )

        ausstattung_raw = listing.get("ausstattung")
        features: dict[str, Any] = {}
        allowed_features = {
            "balkon",
            "terrasse",
            "garten",
            "keller",
            "aufzug",
            "einbaukueche",
            "gaeste_wc",
            "barrierefrei",
            "moebliert",
            "wg_geeignet",
            "haustiere_erlaubt",
        }
        if isinstance(ausstattung_raw, str) and ausstattung_raw.strip():
            import json

            try:
                parsed = json.loads(ausstattung_raw)
            except Exception:
                parsed = {}
                problems.append("Ausstattung (JSON) konnte nicht gelesen werden.")
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    if key in allowed_features and isinstance(value, bool):
                        features[key] = value

        external_uuid = listing.get("uuid")
        external_ref = listing.get("objektnummer")
        street = listing.get("strasse")
        house_number = listing.get("hausnummer")
        postal_code = listing.get("plz")
        city = listing.get("ort")

        listing_fields: dict[str, Any] = {
            "kind": kind,
            "status": status,
            "object_type": object_type,
            "title": listing.get("titel"),
            "description": listing.get("beschreibung_objekt"),
            "price": listing_price,
            "additional_costs": additional_costs,
            "heating_costs": heating_costs,
            "heating_in_additional_costs": heating_in_additional,
            "deposit": deposit,
            "hoa_fee": hoa_fee,
            "parking_price": parking_price,
            "commission_type": commission_type,
            "commission_note": price.get("provision_text"),
            "living_area_sqm": listing.get("wohnflaeche_qm"),
            "rooms": listing.get("zimmer"),
            "floor": str(listing.get("etage")) if listing.get("etage") is not None else None,
            "address_release": (
                "vollstaendig"
                if listing.get("adresse_im_inserat_anzeigen", True)
                else "nur_plz_ort"
            ),
            "heating_type": listing.get("heizungsart"),
            "energy_source": listing.get("energietraeger"),
            "energy_status": energy_status,
            "energy_type": energy_type,
            "energy_value": energy.get("kennwert_kwh"),
            "energy_class": energy.get("effizienzklasse"),
            "energy_year_of_installation": energy.get("baujahr_anlage"),
            "energy_valid_until": energy.get("gueltig_bis"),
            "energy_includes_hot_water": bool(energy.get("enthaelt_warmwasser") or False),
            "features": features,
            "publication_status": publication_status,
            "flowfact_entity_id": flowfact_entity_id,
            "street": street,
            "house_number": house_number,
            "postal_code": postal_code,
            "city": city,
        }
        if internal is not None and internal.get("interne_notizen"):
            listing_fields["notes"] = internal["interne_notizen"]

        match: dict[str, Any] = {
            "unit_id": None,
            "property_id": None,
            "unit_number": None,
            "property_number": None,
            "basis": None,
        }
        object_number = None
        if internal is not None:
            object_number = internal.get("verwaltungsobjekt_referenz")
        if object_number:
            match["basis"] = "object_number"
            match["object_number"] = object_number
        elif street or postal_code:
            match["basis"] = "address"
        else:
            match["basis"] = None
            problems.append("Keine Zuordnungsgrundlage (weder Objektnummer noch Adresse).")

        previews.append(
            RowPreview(
                index=index,
                external_uuid=str(external_uuid) if external_uuid else None,
                external_ref=str(external_ref) if external_ref else None,
                title=listing.get("titel"),
                kind=kind,
                object_type=object_type,
                status=status,
                listing_fields=listing_fields,
                match=match,
                problems=problems,
            )
        )
    return previews
