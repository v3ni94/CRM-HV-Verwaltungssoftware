"""OpenImmo 1.2.7 XML export for listings (M26-02, read only, no portal upload).

Rule 0.1.3: no invented interface. This module only builds an OpenImmo XML document from
the fields the `Listing`, `Property` and `Unit` models actually hold; it never calls
FLOWFACT or any portal (that stays the placeholder described in docs/rules/M28-01.md). No
official OpenImmo 1.2.7 XSD is bundled with the repository (licence, see
docs/OPEN_QUESTIONS.md M26-02); the mapping below follows the public element names of the
OpenImmo 1.2.7 standard but is not validated against the schema itself. Amounts are written
as plain decimal strings (`1234.56`), matching the model's `NUMERIC(14,2)`.

Completeness check (M26, Produktschutz)
---------------------------------------
`REQUIRED_FIELDS` documents which values must be present before a listing is exported. The
list is a product standard derived from the OpenImmo element structure and from what a
listing needs to be usable in a portal (address, object type, price, area, energy pass,
contact). It is not a statement about legal Pflichtangaben in Immobilienanzeigen (GEG etc.,
open point M26-03); nothing here is claimed as a legal duty. An export of an incomplete
listing is blocked by the API unless the caller explicitly sets `force=true`
("trotzdem exportieren"); the check result is returned either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

# Image formats written into anhaenge/anhang/format (upper case file extension).
_IMAGE_FORMATS = {
    "image/jpeg": "JPG",
    "image/jpg": "JPG",
    "image/png": "PNG",
    "image/gif": "GIF",
    "image/webp": "WEBP",
}

# Pflichtfeldliste (Produktschutz). Tuple of (field key, German label, OpenImmo path).
# Field keys are stable identifiers for the API and the CRM UI. The energy pass entries
# apply only while `energy_status == "liegt_vor"`; `nicht_erforderlich` needs no data,
# `in_erstellung` is reported as missing because no energiepass element can be written.
REQUIRED_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("address.postal_code", "PLZ des Objekts", "geo/plz"),
    ("address.city", "Ort des Objekts", "geo/ort"),
    ("address.street", "Straße des Objekts", "geo/strasse"),
    ("address.house_number", "Hausnummer des Objekts", "geo/hausnummer"),
    ("object_type", "Objektart", "objektkategorie/objektart"),
    ("price", "Kaltmiete bzw. Kaufpreis", "preise/kaltmiete bzw. preise/kaufpreis"),
    ("living_area_sqm", "Wohnfläche", "flaechen/wohnflaeche"),
    ("rooms", "Zimmerzahl", "flaechen/anzahl_zimmer"),
    ("title", "Objekttitel", "freitexte/objekttitel"),
    ("description", "Objektbeschreibung", "freitexte/objektbeschreibung"),
    ("energy.status", "Energieausweis liegt vor", "zustand_angaben/energiepass"),
    ("energy.type", "Energieausweisart (Verbrauch oder Bedarf)", "energiepass/@epart"),
    (
        "energy.value",
        "Energiekennwert",
        "energiepass/energieverbrauchkennwert bzw. energiepass/endenergiebedarf",
    ),
    ("energy.class", "Energieeffizienzklasse", "energiepass/@wertklasse"),
    ("energy.valid_until", "Gültigkeit des Energieausweises", "energiepass/@gueltig_bis"),
    ("contact.company", "Anbieter (Firma)", "anbieter/firma"),
    ("contact.name", "Kontaktperson", "kontaktperson/name"),
    ("contact.email", "E-Mail der Kontaktperson", "kontaktperson/email_zentrale"),
)

_LABELS = {key: label for key, label, _path in REQUIRED_FIELDS}
_PATHS = {key: path for key, _label, path in REQUIRED_FIELDS}


@dataclass(frozen=True)
class ExportContact:
    """Provider and contact person of the listing. Derived by the router from the tenant
    (Firma) and the exporting user (Kontaktperson); no listing level contact field exists
    (docs/rules/M26-02.md). Missing values are reported, never invented."""

    company: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass(frozen=True)
class ExportImage:
    """One image attachment written into the ZIP and referenced from anhaenge/anhang."""

    filename: str
    mime_type: str
    data: bytes
    title: str | None = None


@dataclass(frozen=True)
class MissingField:
    field: str
    label: str
    path: str
    message: str


@dataclass
class CompletenessResult:
    missing: list[MissingField] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def messages(self) -> list[str]:
        return [m.message for m in self.missing]

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "missing": [
                {"field": m.field, "label": m.label, "path": m.path, "message": m.message}
                for m in self.missing
            ],
            "warnings": self.messages,
            "hints": list(self.hints),
        }


def _money(value: Any) -> str | None:
    return None if value is None else format(value, "f")


def _text(parent: Element, tag: str, value: Any) -> Element | None:
    if value is None or value == "":
        return None
    el = SubElement(parent, tag)
    el.text = str(value)
    return el


def build_openimmo_xml(
    listing: Listing,
    prop: Property,
    unit: Unit,
    *,
    contact: ExportContact | None = None,
    images: list[ExportImage] | None = None,
) -> bytes:
    """Build the OpenImmo 1.2.7 XML document for one listing. Fields the models do not
    have, or that are not set, are omitted rather than invented (rule 0.1.3). `images`
    are referenced as `anhaenge/anhang` with relative paths (`images/<filename>`), the
    binary data goes into the ZIP next to `listing.xml`."""

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
    if contact is not None:
        _text(anbieter, "firma", contact.company)
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

    # kontaktperson ----------------------------------------------------------------------
    if contact is not None:
        kontakt = SubElement(immobilie, "kontaktperson")
        _text(kontakt, "email_zentrale", contact.email)
        _text(kontakt, "tel_zentrale", contact.phone)
        _text(kontakt, "name", contact.name)
        _text(kontakt, "firma", contact.company)
        if len(kontakt) == 0:
            immobilie.remove(kontakt)

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
        attrs["mitwarmwasser"] = "true" if listing.energy_includes_hot_water else "false"
        energiepass = SubElement(zustand, "energiepass", attrs)
        if epart is not None and listing.energy_value is not None:
            _text(energiepass, epart, listing.energy_value)
        _text(energiepass, "primaerenergietraeger", listing.energy_source)
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

    # anhaenge (images, relative paths inside the ZIP) -------------------------------------
    if images:
        anhaenge = SubElement(immobilie, "anhaenge")
        for image in images:
            anhang = SubElement(anhaenge, "anhang", {"location": "EXTERN", "gruppe": "BILD"})
            _text(anhang, "anhangtitel", image.title or image.filename)
            _text(anhang, "format", _IMAGE_FORMATS.get(image.mime_type.lower()))
            daten = SubElement(anhang, "daten")
            _text(daten, "pfad", f"images/{image.filename}")

    # verwaltung_techn ----------------------------------------------------------------------
    verwaltung = SubElement(immobilie, "verwaltung_techn")
    _text(verwaltung, "objektnr_intern", str(listing.id))
    SubElement(verwaltung, "aktion", {"aktionart": "CHANGE"})
    _text(verwaltung, "stand", listing.updated_at.isoformat() if listing.updated_at else None)

    body: bytes = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body


def _missing(key: str, message: str) -> MissingField:
    return MissingField(field=key, label=_LABELS[key], path=_PATHS[key], message=message)


def check_completeness(
    listing: Listing, prop: Property, contact: ExportContact | None = None
) -> CompletenessResult:
    """Completeness check against `REQUIRED_FIELDS` (Produktschutz, docs/rules/M26-02.md).
    Returns the structured list of missing fields plus non blocking hints. It is not a
    legal completeness check of Pflichtangaben in Immobilienanzeigen (open point M26-03)."""

    result = CompletenessResult()
    add = result.missing.append

    # Adresse
    if not prop.postal_code:
        add(_missing("address.postal_code", "PLZ des Objekts fehlt (geo/plz)."))
    if not prop.city:
        add(_missing("address.city", "Ort des Objekts fehlt (geo/ort)."))
    if listing.address_release == "vollstaendig":
        if not prop.street:
            add(
                _missing(
                    "address.street",
                    "Straße fehlt, obwohl die Adresse vollständig freigegeben ist (geo/strasse).",
                )
            )
        if not prop.house_number:
            add(
                _missing(
                    "address.house_number",
                    "Hausnummer fehlt, obwohl die Adresse vollständig freigegeben ist "
                    "(geo/hausnummer).",
                )
            )

    # Objektart
    if listing.object_type not in _OBJEKTART_TAG:
        add(
            _missing("object_type", "Objektart ist keiner bekannten OpenImmo-Objektart zugeordnet.")
        )

    # Preis oder Miete
    if listing.price is None:
        add(
            _missing(
                "price",
                "Preis fehlt (Kaltmiete bzw. Kaufpreis, preise)."
                if listing.kind == "rental"
                else "Kaufpreis fehlt (preise/kaufpreis).",
            )
        )

    # Flächen
    if listing.living_area_sqm is None:
        add(_missing("living_area_sqm", "Wohnfläche fehlt (flaechen/wohnflaeche)."))
    if listing.rooms is None:
        add(_missing("rooms", "Zimmerzahl fehlt (flaechen/anzahl_zimmer)."))

    # Texte
    if not listing.title:
        add(_missing("title", "Objekttitel fehlt (freitexte/objekttitel)."))
    if not listing.description:
        add(_missing("description", "Objektbeschreibung fehlt (freitexte/objektbeschreibung)."))

    # Energieausweis
    if listing.energy_status == "in_erstellung":
        add(
            _missing(
                "energy.status",
                "Energieausweis liegt noch nicht vor; zustand_angaben/energiepass wird nicht "
                "ausgegeben.",
            )
        )
    elif listing.energy_status == "liegt_vor":
        if listing.energy_type is None or listing.energy_type not in _ENERGY_EPART:
            add(
                _missing(
                    "energy.type",
                    "Energieausweisangaben unvollständig: Energieausweisart fehlt (Verbrauch "
                    "oder Bedarf, energiepass/@epart).",
                )
            )
        if listing.energy_value is None:
            add(
                _missing(
                    "energy.value",
                    "Energieausweisangaben unvollständig: Energiekennwert fehlt.",
                )
            )
        if listing.energy_class is None:
            add(
                _missing(
                    "energy.class",
                    "Energieausweisangaben unvollständig: Energieeffizienzklasse fehlt "
                    "(energiepass/@wertklasse).",
                )
            )
        if listing.energy_valid_until is None:
            add(
                _missing(
                    "energy.valid_until",
                    "Energieausweisangaben unvollständig: Gültigkeit des Energieausweises fehlt "
                    "(energiepass/@gueltig_bis).",
                )
            )
        if not listing.energy_source:
            result.hints.append(
                "Energieträger ist nicht angegeben (energiepass/primaerenergietraeger)."
            )
    # energy_status == "nicht_erforderlich": zulässig, kein Hinweis nötig

    # Kontakt
    if contact is None or not contact.company:
        add(_missing("contact.company", "Anbieter fehlt (Firma des Mandanten, anbieter/firma)."))
    if contact is None or not contact.name:
        add(_missing("contact.name", "Kontaktperson fehlt (kontaktperson/name)."))
    if contact is None or not contact.email:
        add(
            _missing(
                "contact.email",
                "E-Mail der Kontaktperson fehlt (kontaktperson/email_zentrale).",
            )
        )

    return result


def check_openimmo(
    listing: Listing, prop: Property, contact: ExportContact | None = None
) -> list[str]:
    """German list of blocking messages for a complete OpenImmo export (compatibility
    wrapper around `check_completeness`)."""

    return check_completeness(listing, prop, contact).messages
