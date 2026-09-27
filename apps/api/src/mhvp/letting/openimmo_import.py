"""OpenImmo import (M26-02 supplement, docs/rules/M26-02.md): read an uploaded OpenImmo 1.2.7
file (single XML or a ZIP of NAB/ZIP transfers) and produce a review preview only. Nothing is
written to `listing` before an operator approves a row (rule 0.1.3, 0.1.6).

Only the elements documented in `mhvp.letting.openimmo_schema` (structural check, itself
derived from the publicly documented element list, no licensed XSD in the repository, see
docs/OPEN_QUESTIONS.md M26-02) are read. Contacts (`anbieter`) are shown as a proposal text
only; they are never written to `contact` here, because that table requires a purpose,
retention date and consent decision (`mhvp.contacts.models.Contact`) that an OpenImmo transfer
does not carry and that must not be invented (rule 0.1.3, see docs/rules/M26-02.md "Offen").

Dedup: the OpenImmo object id (`verwaltung_techn/objektnr_extern`, falling back to
`objektnr_intern` of the sending system) is stored as `Listing.external_ref` with
`Listing.source = "openimmo_import"`; a second import of the same id is flagged as a duplicate
in the preview and is not created again on apply (idempotent, like the FLOW import,
`mhvp.letting.flow_import`).

Image attachments: only inline, base64 encoded attachments (`anhaenge/anhang` with
`location="INLINE"` and `daten/pfad` as base64 content, or a `<base64>` child, per the
documented element list) are read into memory and offered for `document_link`; an external
`location="EXTERN"` reference is listed as a hint only (no automatic fetch of a third party
URL, rule 0.1.13 no unaudited external transfer).
"""

from __future__ import annotations

import base64
import binascii
import uuid
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as safe_fromstring  # type: ignore[import-untyped]

from mhvp.letting.openimmo_schema import check_structure

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 200

_VERMARKTUNG_TO_KIND = {"MIETE_PACHT": "rental", "KAUF": "sale", "ERBPACHT": "sale"}
_OBJEKTART_TAGS = (
    "wohnung",
    "haus",
    "buero_praxen",
    "einzelhandel",
    "gastronomie",
    "hallen_lager_prod",
    "grundstueck",
    "parking",
    "sonstige",
)
_OBJEKTART_TO_TYPE = {
    "wohnung": "wohnung",
    "haus": "haus",
    "buero_praxen": "gewerbe",
    "einzelhandel": "gewerbe",
    "gastronomie": "gewerbe",
    "hallen_lager_prod": "gewerbe",
    "grundstueck": "grundstueck",
    "parking": "stellplatz",
}


class OpenImmoImportError(ValueError):
    """The upload could not be read at all (not a per-row report)."""


@dataclass
class ImportedImage:
    filename: str
    content: bytes
    content_type: str


@dataclass
class ProposedListing:
    """One `immobilie` element as a review row; never persisted by this module."""

    external_ref: str | None
    title: str
    kind: str | None
    object_type: str | None
    price: Decimal | None
    living_area_sqm: Decimal | None
    rooms: Decimal | None
    plz: str | None
    ort: str | None
    strasse: str | None
    contact_proposal: dict[str, Any]
    images: list[ImportedImage] = field(default_factory=list)
    external_image_hints: list[str] = field(default_factory=list)
    structure_errors: list[str] = field(default_factory=list)
    is_duplicate: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


def _text(el: Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def _contact_proposal(anbieter: Element | None) -> dict[str, Any]:
    if anbieter is None:
        return {}
    firma = _text(anbieter, "firma")
    ansprechpartner = anbieter.find("ansprechpartner")
    name = None
    email = None
    if ansprechpartner is not None:
        vorname = _text(ansprechpartner, "vorname") or ""
        nachname = _text(ansprechpartner, "nachname") or ""
        name = f"{vorname} {nachname}".strip() or None
        email = _text(ansprechpartner, "email_zentrale") or _text(ansprechpartner, "email_direkt")
    email = email or _text(anbieter, "email_zentrale")
    return {"company": firma, "name": name, "email": email}


def _images(immobilie: Element) -> tuple[list[ImportedImage], list[str]]:
    images: list[ImportedImage] = []
    hints: list[str] = []
    anhaenge = immobilie.find("anhaenge")
    if anhaenge is None:
        return images, hints
    for anhang in anhaenge.findall("anhang"):
        gruppe = anhang.get("gruppe", "")
        if gruppe and gruppe != "BILD":
            continue
        location = anhang.get("location", "EXTERN")
        daten = anhang.find("daten")
        pfad = _text(daten, "pfad") if daten is not None else None
        if location == "INLINE" or (daten is not None and daten.find("base64") is not None):
            b64_el = daten.find("base64") if daten is not None else None
            raw_b64 = (b64_el.text or "") if b64_el is not None else (pfad or "")
            try:
                content = base64.b64decode(raw_b64, validate=False)
            except (binascii.Error, ValueError):
                hints.append(f"Bildanhang nicht lesbar (base64 ungültig): {pfad or '(ohne Pfad)'}")
                continue
            if not content or len(content) > MAX_IMAGE_BYTES:
                hints.append(f"Bildanhang übersprungen (leer oder zu groß): {pfad or ''}")
                continue
            name = pfad or f"openimmo-{len(images) + 1}.jpg"
            images.append(ImportedImage(filename=name, content=content, content_type="image/jpeg"))
        else:
            hints.append(
                "Externer Bildverweis (kein automatischer Abruf, Regel 0.1.13): "
                f"{pfad or '(ohne Pfad)'}"
            )
    return images, hints


def _immobilie_to_proposal(immobilie: Element, anbieter: Element | None) -> ProposedListing:
    verw = immobilie.find("verwaltung_techn")
    external_ref = _text(verw, "objektnr_extern") or _text(verw, "objektnr_intern")
    kat = immobilie.find("objektkategorie")
    kind = None
    object_type = None
    if kat is not None:
        vermarktung = kat.find("vermarktungsart")
        if vermarktung is not None:
            if vermarktung.get("MIETE_PACHT") == "true":
                kind = "rental"
            elif vermarktung.get("KAUF") == "true":
                kind = "sale"
        objektart = kat.find("objektart")
        if objektart is not None:
            for tag in _OBJEKTART_TAGS:
                if objektart.find(tag) is not None:
                    object_type = _OBJEKTART_TO_TYPE.get(tag)
                    break
    geo = immobilie.find("geo")
    flaechen = immobilie.find("flaechen")
    preise = immobilie.find("preise")
    freitexte = immobilie.find("freitexte")
    title = _text(freitexte, "objekttitel") or external_ref or "OpenImmo-Import"
    images, hints = _images(immobilie)
    return ProposedListing(
        external_ref=external_ref,
        title=title,
        kind=kind,
        object_type=object_type,
        price=_decimal(_text(preise, "kaltmiete/preis") or _text(preise, "kaufpreis/preis")),
        living_area_sqm=_decimal(_text(flaechen, "wohnflaeche")),
        rooms=_decimal(_text(flaechen, "anzahl_zimmer")),
        plz=_text(geo, "plz"),
        ort=_text(geo, "ort"),
        strasse=_text(geo, "strasse"),
        contact_proposal=_contact_proposal(anbieter),
        images=images,
        external_image_hints=hints,
    )


def _xml_files(upload: bytes, filename: str) -> list[bytes]:
    if filename.lower().endswith(".zip") or upload[:2] == b"PK":
        out: list[bytes] = []
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(upload)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".xml"):
                        out.append(zf.read(name))
        except zipfile.BadZipFile as exc:
            raise OpenImmoImportError("Die Datei ist kein gültiges ZIP-Archiv.") from exc
        if not out:
            raise OpenImmoImportError("Kein XML im ZIP-Archiv gefunden.")
        return out
    return [upload]


def parse_openimmo_upload(
    upload: bytes, filename: str, *, existing_external_refs: set[str]
) -> list[ProposedListing]:
    """Parse an uploaded OpenImmo file (XML or ZIP) into review rows. Raises
    `OpenImmoImportError` only when nothing at all could be read; a malformed single
    `immobilie` is instead reported via `structure_errors` on its row."""

    files = _xml_files(upload, filename)
    proposals: list[ProposedListing] = []
    for xml in files:
        try:
            root = safe_fromstring(xml)
        except Exception as exc:  # malformed document
            raise OpenImmoImportError(f"XML nicht wohlgeformt: {exc}") from exc
        structure_errors = check_structure(xml)
        anbieter = root.find("anbieter")
        immobilien = root.findall("anbieter/immobilie") or root.findall(".//immobilie")
        for immobilie in immobilien[:MAX_ENTRIES]:
            proposal = _immobilie_to_proposal(immobilie, anbieter)
            proposal.structure_errors = list(structure_errors)
            if proposal.external_ref and proposal.external_ref in existing_external_refs:
                proposal.is_duplicate = True
            proposals.append(proposal)
    if not proposals:
        raise OpenImmoImportError("Keine <immobilie>-Elemente gefunden.")
    return proposals


def proposal_to_row(p: ProposedListing) -> dict[str, Any]:
    """JSON row for `OpenImmoImportRun.rows` (preview and, after apply, outcome)."""

    return {
        "external_ref": p.external_ref,
        "title": p.title,
        "kind": p.kind,
        "object_type": p.object_type,
        "price": str(p.price) if p.price is not None else None,
        "living_area_sqm": str(p.living_area_sqm) if p.living_area_sqm is not None else None,
        "rooms": str(p.rooms) if p.rooms is not None else None,
        "plz": p.plz,
        "ort": p.ort,
        "strasse": p.strasse,
        "contact_proposal": p.contact_proposal,
        "image_count": len(p.images),
        "external_image_hints": p.external_image_hints,
        "structure_errors": p.structure_errors,
        "is_duplicate": p.is_duplicate,
        "status": "duplicate" if p.is_duplicate else "previewed",
        "listing_id": None,
        "row_id": str(uuid.uuid4()),
    }
