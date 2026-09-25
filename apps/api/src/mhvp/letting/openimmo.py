"""OpenImmo 1.2.7 XML export for listings (M26-02, read only, no portal upload).

Rule 0.1.3: no invented interface. This module only builds an OpenImmo XML document from
the fields the `Listing`, `Property` and `Unit` models actually hold; it never calls
FLOWFACT or any portal (that stays the placeholder described in docs/rules/M28-01.md). No
official OpenImmo 1.2.7 XSD is bundled with the repository (licence, see
docs/OPEN_QUESTIONS.md M26-02); the mapping below follows the public element names of the
OpenImmo 1.2.7 standard but is not validated against the schema itself. Amounts are written
as plain decimal strings (`1234.56`), matching the model's `NUMERIC(14,2)`.
"""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from mhvp.letting.models import Listing
from mhvp.properties.models import Property, Unit

OPENIMMO_VERSION = "1.2.7"

# Objektart mapping (M28-01 object_type -> OpenImmo objektart child element).
_OBJEKTART_TAG = {
    "wohnung": "wohnung",
    "haus": "haus",
    "gewerbe": "buero_praxen",
    "stellplatz": "parkhaus_tiefgarage",
    "grundstueck": "grundstueck",
}

# Known boolean features (M28-01 positive list) mapped to plausible OpenImmo ausstattung
# elements. This is a Fachliche Umsetzung mapping, not a normative OpenImmo requirement;
# unmapped or unknown feature keys are never emitted.
_FEATURE_TAGS = {
    "balkon": "balkon",
    "terrasse": "terrasse",
    "garten": "gaerten",
    "keller": "keller",
    "aufzug": "personenaufzug",
    "einbaukueche": "einbaukueche",
    "gaeste_wc": "gaeste_wc",
    "barrierefrei": "rollstuhlgerecht",
    "moebliert": "moebliert",
    "wg_geeignet": "wg_geeignet",
    "haustiere_erlaubt": "haustiere",
}

_ENERGY_EPART = {"verbrauch": "energieverbrauchkennwert", "bedarf": "endenergiebedarf"}


def _money(value: Any) -> str | None:
    return None if value is None else format(value, "f")


def _text(parent: Element, tag: str, value: Any) -> Element | None:
    if value is None or value == "":
        return None
    el = SubElement(parent, tag)
    el.text = str(value)
    return el


def build_openimmo_xml(listing: Listing, prop: Property, unit: Unit) -> bytes:
    """Build the OpenImmo 1.2.7 XML document for one listing. Fields the models do not
    have, or that are not set, are omitted rather than invented (rule 0.1.3)."""

    root = Element("openimmo")
    SubElement(
        root,
        "uebertragung",
        {
            "art": "CHANGE",
            "umfang": "TEIL",
            "online_relevant": "false",
            "version": OPENIMMO_VERSION,
        },
    )
    anbieter = SubElement(root, "anbieter")
    immobilie = SubElement(anbieter, "immobilie")

    # objektkategorie ------------------------------------------------------------------
    kategorie = SubElement(immobilie, "objektkategorie")
    nutzungsart = SubElement(kategorie, "nutzungsart")
    nutzungsart.set("WOHNEN", "true" if listing.object_type != "gewerbe" else "false")
    nutzungsart.set("GEWERBE", "true" if listing.object_type == "gewerbe" else "false")
    vermarktungsart = SubElement(kategorie, "vermarktungsart")
    vermarktungsart.set("KAUF", "true" if listing.kind == "sale" else "false")
    vermarktungsart.set("MIETE_PACHT", "true" if listing.kind == "rental" else "false")
    objektart = SubElement(kategorie, "objektart")
    tag = _OBJEKTART_TAG.get(listing.object_type)
    if tag is not None:
        SubElement(objektart, tag)

    # geo --------------------------------------------------------------------------------
    geo = SubElement(immobilie, "geo")
    _text(geo, "plz", prop.postal_code)
    _text(geo, "ort", prop.city)
    if listing.address_release == "vollstaendig":
        _text(geo, "strasse", prop.street)
        _text(geo, "hausnummer", prop.house_number)

    # preise (amounts as decimal strings, cf. rule 10) ------------------------------------
    preise = SubElement(immobilie, "preise")
    if listing.kind == "rental":
        _text(preise, "kaltmiete", _money(listing.price))
        _text(preise, "nebenkosten", _money(listing.additional_costs))
        _text(preise, "warmmiete", _money(listing.warm_rent))
        _text(preise, "kaution", _money(listing.deposit))
    else:
        _text(preise, "kaufpreis", _money(listing.price))
    if len(preise) == 0:
        immobilie.remove(preise)

    # flaechen -----------------------------------------------------------------------------
    flaechen = SubElement(immobilie, "flaechen")
    _text(flaechen, "wohnflaeche", listing.living_area_sqm)
    _text(flaechen, "anzahl_zimmer", listing.rooms)
    if len(flaechen) == 0:
        immobilie.remove(flaechen)

    # ausstattung ----------------------------------------------------------------------
    ausstattung = SubElement(immobilie, "ausstattung")
    for key, value in (listing.features or {}).items():
        tag_name = _FEATURE_TAGS.get(key)
        if tag_name is not None and value:
            SubElement(ausstattung, tag_name)
    if len(ausstattung) == 0:
        immobilie.remove(ausstattung)

    # zustand_angaben (energy pass) ------------------------------------------------------
    zustand = SubElement(immobilie, "zustand_angaben")
    if listing.energy_status == "liegt_vor" and listing.energy_type:
        epart = _ENERGY_EPART.get(listing.energy_type)
        attrs: dict[str, str] = {}
        if epart is not None:
            attrs["epart"] = epart
        if listing.energy_valid_until is not None:
            attrs["gueltig_bis"] = listing.energy_valid_until.isoformat()
        if listing.energy_class is not None:
            attrs["wertklasse"] = listing.energy_class
        energiepass = SubElement(zustand, "energiepass", attrs)
        if epart is not None and listing.energy_value is not None:
            _text(energiepass, epart, listing.energy_value)
    if len(zustand) == 0:
        immobilie.remove(zustand)

    # freitexte ---------------------------------------------------------------------------
    freitexte = SubElement(immobilie, "freitexte")
    _text(freitexte, "objekttitel", listing.title)
    _text(freitexte, "objektbeschreibung", listing.description)
    _text(freitexte, "ausstatt_beschr", listing.energy_note)
    _text(freitexte, "lage", listing.commission_note)
    if len(freitexte) == 0:
        immobilie.remove(freitexte)

    # verwaltung_techn ----------------------------------------------------------------------
    verwaltung = SubElement(immobilie, "verwaltung_techn")
    _text(verwaltung, "objektnr_intern", str(listing.id))
    SubElement(verwaltung, "aktion", {"aktionart": "CHANGE"})
    _text(verwaltung, "stand", listing.updated_at.isoformat() if listing.updated_at else None)

    body: bytes = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body


def check_openimmo(listing: Listing, prop: Property) -> list[str]:
    """German list of fields missing or invalid for a complete OpenImmo export. This is a
    Produktschutz check (docs/rules/M28-01.md), not a legal completeness check of
    Pflichtangaben in Immobilienanzeigen (open point M26-03)."""

    missing: list[str] = []
    if not prop.postal_code or not prop.city:
        missing.append("PLZ und Ort des Objekts fehlen (geo).")
    if listing.address_release == "vollstaendig" and (not prop.street or not prop.house_number):
        missing.append("Straße und Hausnummer fehlen, obwohl die Adresse freigegeben ist.")
    if not listing.title:
        missing.append("Objekttitel fehlt (freitexte/objekttitel).")
    if not listing.description:
        missing.append("Objektbeschreibung fehlt (freitexte/objektbeschreibung).")
    if listing.price is None:
        missing.append(
            "Preis fehlt (Kaltmiete bzw. Kaufpreis, preise)."
            if listing.kind == "rental"
            else "Kaufpreis fehlt (preise/kaufpreis)."
        )
    if listing.living_area_sqm is None:
        missing.append("Wohnfläche fehlt (flaechen/wohnflaeche).")
    if listing.rooms is None:
        missing.append("Zimmerzahl fehlt (flaechen/anzahl_zimmer).")
    if listing.object_type not in _OBJEKTART_TAG:
        missing.append("Objektart ist keiner bekannten OpenImmo-Objektart zugeordnet.")
    if listing.energy_status == "in_erstellung":
        missing.append(
            "Energieausweis liegt noch nicht vor; zustand_angaben/energiepass wird nicht "
            "ausgegeben."
        )
    elif listing.energy_status == "liegt_vor" and (
        listing.energy_type is None or listing.energy_value is None or listing.energy_class is None
    ):
        missing.append(
            "Energieausweisangaben unvollständig (Energieart, Kennwert oder Klasse fehlen)."
        )
    if listing.energy_status == "nicht_erforderlich":
        pass  # zulässig, kein Hinweis nötig
    return missing
