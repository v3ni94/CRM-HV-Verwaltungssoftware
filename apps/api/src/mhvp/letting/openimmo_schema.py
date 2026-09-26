"""Schema check of the OpenImmo export (M26-02, docs/rules/M26-02.md).

The official OpenImmo 1.2.7 XSD is copyrighted by the OpenImmo e.V. and is not bundled with
the repository (docs/OPEN_QUESTIONS.md M26-02). Two modes therefore exist:

* ``xsd``: the operator has stored a schema file and set ``MHVP_OPENIMMO_XSD_PATH``. The
  export is validated against that file with a schema library that is already installed
  (``xmlschema`` preferred, ``lxml`` as fallback). Nothing is downloaded from the network
  and no library is installed on demand.
* ``structure``: no XSD is configured (or no schema library is available). A structural
  check of the elements documented in docs/rules/M26-02.md is run with ``defusedxml``.
  This is Produktschutz derived from our own mapping, not a statement about the official
  schema, and the result carries the operator notice "XSD nicht hinterlegt".

Both modes return a ``SchemaResult`` with a German error list. The router treats an invalid
result like an incomplete listing: the export is locked unless the caller sets
``force=true`` (bestehende Sperrlogik, rule 0.1.3 without an invented schema).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as safe_fromstring  # type: ignore[import-untyped]

from mhvp.letting.openimmo import OPENIMMO_VERSION

NOTICE_NO_XSD = (
    "OpenImmo-XSD nicht hinterlegt. Die Datei wird nur strukturell gegen die dokumentierten "
    "Elemente geprüft (docs/rules/M26-02.md), nicht gegen das amtliche Schema. Der Betreiber "
    "hinterlegt die XSD 1.2.7 (Bezug über den OpenImmo e.V., Mitgliedschaft oder Lizenz) "
    "und setzt MHVP_OPENIMMO_XSD_PATH."
)
NOTICE_NO_LIBRARY = (
    "OpenImmo-XSD ist hinterlegt, aber keine Schemabibliothek (xmlschema oder lxml) ist "
    "installiert. Die Datei wird nur strukturell geprüft."
)
NOTICE_XSD_MISSING = (
    "OpenImmo-XSD ist unter dem konfigurierten Pfad nicht lesbar (MHVP_OPENIMMO_XSD_PATH). "
    "Die Datei wird nur strukturell geprüft."
)
NOTICE_XSD_INVALID = (
    "Die hinterlegte OpenImmo-XSD konnte nicht geladen werden. Die Datei wird nur "
    "strukturell geprüft."
)

# Validator callable: takes the XML bytes, returns German error messages (empty = valid).
Validator = Callable[[bytes], list[str]]


@dataclass
class SchemaResult:
    """Outcome of the schema check. ``mode`` is ``xsd`` (validated against the configured
    file) or ``structure`` (documented elements only). ``notice`` is the operator hint that
    explains why no XSD validation ran; it is informational and never blocks on its own."""

    mode: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    notice: str | None = None
    xsd_configured: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "valid": self.valid,
            "errors": list(self.errors),
            "notice": self.notice,
            "xsd_configured": self.xsd_configured,
        }


def _parse(xml: bytes) -> Element | None:
    try:
        parsed: Element = safe_fromstring(xml)
    except Exception:  # malformed document is reported, not raised
        return None
    return parsed


# Structural check (mode "structure") ----------------------------------------------------

# Elements the export always writes (docs/rules/M26-02.md, `build_openimmo_xml`). Tuple of
# (path relative to immobilie, German message). Optional blocks such as preise, flaechen or
# energiepass are covered by the completeness check, not here.
_IMMOBILIE_REQUIRED: tuple[tuple[str, str], ...] = (
    ("objektkategorie", "immobilie/objektkategorie fehlt."),
    ("objektkategorie/nutzungsart", "objektkategorie/nutzungsart fehlt."),
    ("objektkategorie/vermarktungsart", "objektkategorie/vermarktungsart fehlt."),
    ("objektkategorie/objektart", "objektkategorie/objektart fehlt."),
    ("geo", "immobilie/geo fehlt."),
    ("verwaltung_techn", "immobilie/verwaltung_techn fehlt."),
    ("verwaltung_techn/objektnr_intern", "verwaltung_techn/objektnr_intern fehlt."),
    ("verwaltung_techn/aktion", "verwaltung_techn/aktion fehlt."),
)


def check_structure(xml: bytes) -> list[str]:
    """German error list of the structural check (empty when the documented elements are
    present). Parsed with defusedxml; a malformed document yields one error."""

    root = _parse(xml)
    if root is None:
        return ["Die XML-Datei ist nicht wohlgeformt."]
    errors: list[str] = []
    if root.tag != "openimmo":
        errors.append(f"Wurzelelement ist '{root.tag}', erwartet 'openimmo'.")
        return errors

    uebertragung = root.find("uebertragung")
    if uebertragung is None:
        errors.append("uebertragung fehlt.")
    else:
        for attr in ("art", "umfang", "version"):
            if not uebertragung.get(attr):
                errors.append(f"uebertragung/@{attr} fehlt.")
        version = uebertragung.get("version")
        if version and version != OPENIMMO_VERSION:
            errors.append(f"uebertragung/@version ist '{version}', erwartet '{OPENIMMO_VERSION}'.")

    anbieter = root.findall("anbieter")
    if not anbieter:
        errors.append("anbieter fehlt.")
    for a_index, provider in enumerate(anbieter, start=1):
        immobilien = provider.findall("immobilie")
        if not immobilien:
            errors.append(f"anbieter {a_index}: immobilie fehlt.")
        for i_index, immobilie in enumerate(immobilien, start=1):
            prefix = f"immobilie {i_index}: " if len(immobilien) > 1 else ""
            for path, message in _IMMOBILIE_REQUIRED:
                if immobilie.find(path) is None:
                    errors.append(prefix + message)
            objektart = immobilie.find("objektkategorie/objektart")
            if objektart is not None and len(objektart) == 0:
                errors.append(prefix + "objektkategorie/objektart enthält keine Objektart.")
            aktion = immobilie.find("verwaltung_techn/aktion")
            if aktion is not None and not aktion.get("aktionart"):
                errors.append(prefix + "verwaltung_techn/aktion/@aktionart fehlt.")
            for anhang in immobilie.findall("anhaenge/anhang"):
                if anhang.find("daten/pfad") is None:
                    errors.append(prefix + "anhaenge/anhang ohne daten/pfad.")
    return errors


# XSD validation (mode "xsd") ------------------------------------------------------------


def _xmlschema_validator(path: Path) -> Validator | None:
    try:
        import xmlschema  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except ImportError:
        return None
    schema = xmlschema.XMLSchema(str(path))

    def validate(xml: bytes) -> list[str]:
        return [str(err.reason or err) for err in schema.iter_errors(xml)]

    return validate


def _lxml_validator(path: Path) -> Validator | None:
    try:
        from lxml import etree  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except ImportError:
        return None
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    schema = etree.XMLSchema(etree.parse(str(path), parser))

    def validate(xml: bytes) -> list[str]:
        document = etree.fromstring(xml, parser)
        schema.validate(document)
        return [f"Zeile {err.line}: {err.message}" for err in schema.error_log]

    return validate


def load_validator(xsd_path: str | None) -> tuple[Validator | None, str | None]:
    """Resolve the operator's XSD to a validator callable. Returns (validator, notice); the
    notice explains why no XSD validation is possible (no path, unreadable file, no
    library, unloadable schema) and is shown to the operator."""

    if not xsd_path:
        return None, NOTICE_NO_XSD
    path = Path(xsd_path)
    if not path.is_file():
        return None, NOTICE_XSD_MISSING
    try:
        validator = _xmlschema_validator(path) or _lxml_validator(path)
    except Exception:  # schema file present but not loadable
        return None, NOTICE_XSD_INVALID
    if validator is None:
        return None, NOTICE_NO_LIBRARY
    return validator, None


def validate_openimmo(xml: bytes, xsd_path: str | None) -> SchemaResult:
    """Validate the export document. With a usable XSD the result is ``mode == "xsd"``;
    otherwise the structural check runs and the notice says why."""

    validator, notice = load_validator(xsd_path)
    if validator is None:
        errors = check_structure(xml)
        return SchemaResult(
            mode="structure",
            valid=not errors,
            errors=errors,
            notice=notice,
            xsd_configured=bool(xsd_path),
        )
    if _parse(xml) is None:
        return SchemaResult(
            mode="xsd",
            valid=False,
            errors=["Die XML-Datei ist nicht wohlgeformt."],
            xsd_configured=True,
        )
    try:
        errors = validator(xml)
    except Exception as exc:  # library error is reported as validation error
        errors = [f"Schemaprüfung fehlgeschlagen: {exc}"]
    return SchemaResult(mode="xsd", valid=not errors, errors=errors, xsd_configured=True)
