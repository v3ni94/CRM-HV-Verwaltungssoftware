"""Kompetenzkatalog der Mitglieder und Themen der Tickets (operator 25.09.2026).

Der Katalog ist im Code hinterlegt (Codes und deutsche Bezeichnungen) und um mandantenspezifische
Einträge erweiterbar (``TenantSettings.competence_catalogue_extra``), ohne dass dafür eine
Migration nötig ist. Jede Kompetenz trägt zusätzlich Schlüsselwörter für die deterministische
Themen-Erkennung eingehender Mails (``mhvp.communication.assignment``); diese Zuordnung ist ein
interner Produktschutz-Vorschlag, keine Rechtsvorschrift.
"""

from __future__ import annotations

from typing import Any, TypedDict


class Competence(TypedDict):
    code: str
    label: str
    keywords: list[str]


def _c(code: str, label: str, keywords: list[str]) -> Competence:
    return {"code": code, "label": label, "keywords": keywords}


# Reihenfolge wie vom Betreiber vorgegeben (25.09.2026).
COMPETENCE_CATALOGUE: list[Competence] = [
    _c(
        "vermietung",
        "Vermietung",
        ["vermietung", "mietinteressent", "besichtigung", "wohnungsangebot"],
    ),
    _c("verkauf", "Verkauf", ["verkauf", "makler", "kaufinteressent", "exposé", "expose"]),
    _c("vertrag", "Vertrag", ["vertrag", "kündigung", "kuendigung", "nachtrag", "mietvertrag"]),
    _c(
        "buchhaltung",
        "Buchhaltung",
        ["rechnung", "buchung", "zahlung", "überweisung", "ueberweisung", "beleg"],
    ),
    _c(
        "abrechnung",
        "Abrechnung",
        ["abrechnung", "nebenkostenabrechnung", "betriebskosten", "nachzahlung", "guthaben"],
    ),
    _c(
        "heizkosten",
        "Heizkosten",
        ["heizkosten", "heizung", "ablesung", "verbrauch", "warmwasser"],
    ),
    _c(
        "stammdaten",
        "Stammdaten",
        [
            "adressänderung",
            "adressaenderung",
            "bankverbindung",
            "stammdaten",
            "kontaktdaten",
            "umzug",
        ],
    ),
    _c(
        "reparatur",
        "Reparatur",
        ["reparatur", "schaden", "defekt", "handwerker", "störung", "stoerung"],
    ),
    _c(
        "versicherungsfall",
        "Versicherungsfall",
        ["versicherung", "schadensfall", "gutachten schaden", "wasserschaden", "brandschaden"],
    ),
    _c(
        "maklergeschaeft",
        "Maklergeschäft",
        ["maklerauftrag", "provision", "alleinauftrag", "maklervertrag"],
    ),
    _c(
        "gutachten",
        "Gutachten",
        ["gutachten", "wertermittlung", "sachverständiger", "sachverstaendiger"],
    ),
    _c(
        "mieterhoehung",
        "Mieterhöhung",
        ["mieterhöhung", "mieterhoehung", "mietspiegel", "indexmiete", "staffelmiete"],
    ),
    _c(
        "weg_verwaltung",
        "WEG-Verwaltung",
        [
            "eigentümerversammlung",
            "eigentuemerversammlung",
            "beirat",
            "beschluss",
            "weg",
            "hausgeld",
        ],
    ),
    _c(
        "mahnwesen",
        "Mahnwesen",
        [
            "mahnung",
            "zahlungsrückstand",
            "zahlungsrueckstand",
            "rückstand",
            "rueckstand",
            "inkasso",
        ],
    ),
    _c("bank", "Bank", ["bankkonto", "kontoauszug", "sepa", "lastschrift", "iban"]),
    _c("dokumente", "Dokumente", ["dokument", "unterlage", "anhang", "urkunde"]),
    _c("sonstiges", "Sonstiges", []),
]

CODES = {c["code"] for c in COMPETENCE_CATALOGUE}
LABELS = {c["code"]: c["label"] for c in COMPETENCE_CATALOGUE}


def full_catalogue(tenant_extra: list[dict[str, Any]] | None = None) -> list[Competence]:
    """Katalog inklusive der mandantenspezifischen Erweiterung (``TenantSettings``); ein
    Erweiterungscode, der bereits im Basiskatalog steht, wird ignoriert."""
    extra: list[Competence] = []
    for entry in tenant_extra or []:
        code = str(entry.get("code", "")).strip()
        label = str(entry.get("label", "")).strip()
        if not code or not label or code in CODES:
            continue
        extra.append(_c(code, label, [str(k) for k in entry.get("keywords", [])]))
    return [*COMPETENCE_CATALOGUE, *extra]


def label_for(code: str, tenant_extra: list[dict[str, Any]] | None = None) -> str:
    for c in full_catalogue(tenant_extra):
        if c["code"] == code:
            return c["label"]
    return code


def is_known_code(code: str, tenant_extra: list[dict[str, Any]] | None = None) -> bool:
    return any(c["code"] == code for c in full_catalogue(tenant_extra))


def classify_topic(text: str, tenant_extra: list[dict[str, Any]] | None = None) -> str | None:
    """Deterministische Themenerkennung per Schlagwort-Treffer, kein KI-Aufruf. Bei
    Gleichstand gewinnt der Katalogeintrag mit den meisten Treffern; ohne Treffer ``None``."""
    haystack = (text or "").lower()
    best_code: str | None = None
    best_hits = 0
    for c in full_catalogue(tenant_extra):
        hits = sum(1 for kw in c["keywords"] if kw and kw.lower() in haystack)
        if hits > best_hits:
            best_hits, best_code = hits, c["code"]
    return best_code
