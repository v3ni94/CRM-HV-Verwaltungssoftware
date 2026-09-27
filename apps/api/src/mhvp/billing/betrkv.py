"""System catalogue of operating cost types after the Betriebskostenverordnung (M17-01).

Draft with source status: the 17 positions of § 2 BetrKV (source register R07) with the
allocability marker per position, plus the two exclusions of § 1 Abs. 2 BetrKV
(administration ``V`` and maintenance ``I``) as explicitly non allocable entries. The
catalogue is a system catalogue: no tenant edits, no amounts, no legal classification of a
single case. It only carries the review hints of the statement preview (A02, D22):

* ``yes``: operating cost type of § 2 BetrKV; allocable to residential tenants when the lease
  passes the operating costs on (§ 556 Abs. 1 BGB, the position basis names the clause);
* ``agreement_only``: § 2 Nr. 17 (sonstige Betriebskosten) needs the cost type named in the
  lease; a general reference to the BetrKV is not enough (assessment, to be released, M17-01);
* ``no``: administration and maintenance are no operating costs (§ 1 Abs. 2 BetrKV).

The wording of number 15 changed with the telecommunications reform (see M10-02); the
labels are kept close to the law but are a draft until the legal review releases them.
Every hint is a proposal for a person; the calculation does not change because of it.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SOURCE = "R07 (§ 1 und § 2 BetrKV), Entwurf, Freigabe Rechtsberatung offen (M17-01)"
ADMINISTRATION = "V"
MAINTENANCE = "I"
OTHER = "17"


class Allocability(StrEnum):
    YES = "yes"
    NO = "no"
    AGREEMENT_ONLY = "agreement_only"


@dataclass(frozen=True)
class OperatingCostType:
    code: str
    label: str
    allocability: Allocability
    reference: str
    note: str = ""

    def out(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "allocability": self.allocability.value,
            "reference": self.reference,
            "note": self.note,
            "source": SOURCE,
        }


def _t(code: str, label: str, allocability: Allocability, note: str = "") -> OperatingCostType:
    reference = (
        f"§ 2 Nr. {code} BetrKV"
        if code.isdigit()
        else ("§ 1 Abs. 2 Nr. 1 BetrKV" if code == ADMINISTRATION else "§ 1 Abs. 2 Nr. 2 BetrKV")
    )
    return OperatingCostType(code, label, allocability, reference, note)


CATALOGUE: tuple[OperatingCostType, ...] = (
    _t("1", "Laufende öffentliche Lasten des Grundstücks (Grundsteuer)", Allocability.YES),
    _t("2", "Kosten der Wasserversorgung", Allocability.YES),
    _t("3", "Kosten der Entwässerung", Allocability.YES),
    _t(
        "4",
        "Kosten des Betriebs der zentralen Heizungsanlage einschließlich der Abgasanlage",
        Allocability.YES,
        "Verteilung nach Heizkostenverordnung (H01 bis H05, M17-02).",
    ),
    _t(
        "5",
        "Kosten des Betriebs der zentralen Warmwasserversorgungsanlage",
        Allocability.YES,
        "Verteilung nach Heizkostenverordnung (H01 bis H05, M17-02).",
    ),
    _t("6", "Kosten verbundener Heizungs- und Warmwasserversorgungsanlagen", Allocability.YES),
    _t("7", "Kosten des Betriebs des Personen- oder Lastenaufzugs", Allocability.YES),
    _t("8", "Kosten der Straßenreinigung und Müllbeseitigung", Allocability.YES),
    _t("9", "Kosten der Gebäudereinigung und Ungezieferbekämpfung", Allocability.YES),
    _t("10", "Kosten der Gartenpflege", Allocability.YES),
    _t("11", "Kosten der Beleuchtung", Allocability.YES),
    _t("12", "Kosten der Schornsteinreinigung", Allocability.YES),
    _t("13", "Kosten der Sach- und Haftpflichtversicherung", Allocability.YES),
    _t("14", "Kosten für den Hauswart", Allocability.YES, "Ohne Instandhaltung und Verwaltung."),
    _t(
        "15",
        "Kosten des Betriebs der Gemeinschaftsantennenanlage oder der mit einem Breitbandnetz "
        "verbundenen Verteilanlage",
        Allocability.YES,
        "Wortlaut nach der Telekommunikationsreform zu prüfen (M10-02).",
    ),
    _t("16", "Kosten des Betriebs der Einrichtungen für die Wäschepflege", Allocability.YES),
    _t(
        OTHER,
        "Sonstige Betriebskosten",
        Allocability.AGREEMENT_ONLY,
        "Nur mit ausdrücklicher Nennung der Kostenart im Mietvertrag.",
    ),
    _t(
        ADMINISTRATION,
        "Verwaltungskosten (keine Betriebskosten)",
        Allocability.NO,
        "Ausschluss nach § 1 Abs. 2 Nr. 1 BetrKV.",
    ),
    _t(
        MAINTENANCE,
        "Instandhaltungs- und Instandsetzungskosten (keine Betriebskosten)",
        Allocability.NO,
        "Ausschluss nach § 1 Abs. 2 Nr. 2 BetrKV.",
    ),
)
BY_CODE: dict[str, OperatingCostType] = {t.code: t for t in CATALOGUE}
LAW_POSITIONS = 17


def catalogue() -> list[dict[str, Any]]:
    return [t.out() for t in CATALOGUE]


def get(code: str | None) -> OperatingCostType | None:
    return BY_CODE.get(code) if code else None


def suggest_from_reference(reference: str | None) -> str | None:
    """Catalogue code suggested by a template's ``betrkv_reference`` (M10-02), for review only.

    ``"§ 2 Nr. 14 Hauswart"`` gives ``"14"``; ``"Instandsetzung, keine Betriebskosten"`` gives
    ``"I"``; an ambiguous reference ("... sonst Nr. 12 (zu prüfen)") or an unknown text gives
    ``None`` so that a person decides.
    """
    if not reference:
        return None
    text = reference.strip()
    if "zu prüfen" in text or "sonst" in text:
        return None
    lowered = text.lower()
    if "instandsetzung" in lowered or "instandhaltung" in lowered:
        return MAINTENANCE
    if "verwaltung" in lowered:
        return ADMINISTRATION
    marker = "nr. "
    idx = lowered.find(marker)
    if idx < 0:
        return None
    digits = ""
    for ch in lowered[idx + len(marker) :]:
        if ch.isdigit():
            digits += ch
        else:
            break
    return digits if digits in BY_CODE else None


def position_hints(
    *, label: str, type_code: str | None, allocation_category: str | None
) -> list[dict[str, str]]:
    """Review hints for one cost position (never a lock; the locks live in ``check_item``).

    ``allocation_category`` is the account classification of the ledger (M10-02). A mapping to
    a non allocable catalogue entry on an account classified as allocable, an ``agreement_only``
    entry and a missing mapping each give one hint. A position without an account gets the
    hint that the cost type is unassigned.
    """
    hints: list[dict[str, str]] = []
    cost_type = get(type_code)
    if cost_type is None:
        hints.append(
            {
                "code": "BETRKV-UNASSIGNED",
                "level": "info",
                "position": label,
                "message": (
                    f"{label}: keine Betriebskostenart des Katalogs zugeordnet; Zuordnung und "
                    "Umlagevereinbarung prüfen (M17-01)."
                ),
            }
        )
        return hints
    if cost_type.allocability is Allocability.NO:
        hints.append(
            {
                "code": "BETRKV-NOT-ALLOCABLE",
                "level": "warning",
                "position": label,
                "message": (
                    f"{label}: {cost_type.label}, {cost_type.reference}; nicht umlagefähig, "
                    "Position aus der Wohnraumabrechnung nehmen oder Grundlage belegen."
                ),
            }
        )
        if allocation_category and allocation_category.startswith("allocable"):
            hints.append(
                {
                    "code": "BETRKV-CATEGORY-CONFLICT",
                    "level": "warning",
                    "position": label,
                    "message": (
                        f"{label}: Konto ist als umlagefähig eingeordnet, die Katalogposition "
                        f"{cost_type.code} aber nicht; Einordnung des Kontos prüfen (M10-02)."
                    ),
                }
            )
    elif cost_type.allocability is Allocability.AGREEMENT_ONLY:
        hints.append(
            {
                "code": "BETRKV-AGREEMENT-ONLY",
                "level": "warning",
                "position": label,
                "message": (
                    f"{label}: {cost_type.label} ({cost_type.reference}) nur mit ausdrücklicher "
                    "Vereinbarung der Kostenart im Mietvertrag; Grundlage der Position prüfen."
                ),
            }
        )
    return hints
