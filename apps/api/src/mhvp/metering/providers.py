"""Provider catalogue (master prompt Messdienstleister section 3), as code constants.

Research state 26.09.2026 from the official sources Q1 to Q11 named in the master prompt. Every
entry must be re-checked against those sources before an adapter is implemented ("vor
Implementierung erneut prüfen"). The catalogue records only what the sources state; a missing
technical documentation is never presented as a missing API (``UNCLEAR`` instead of ``NO``).

Four dimensions are kept apart per function (section 3): documented support at the provider
(this catalogue), adapter implemented in the CRM (``mhvp.metering.adapters``), release of the
customer account (per connection, maintained by the tenant) and the actual connection test
(per connection, result stored with a timestamp and a stale marker).
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Function(StrEnum):
    """Functions of the module that a provider may or may not support."""

    BILLING_UNIT_DATA = "billing_unit_data"  # Stammdaten / Ordnungsbegriffsabgleich
    ROLES = "roles"  # user / role submission (On-Site Roles, Nutzerwechsel)
    BILLING_INPUT = "billing_input"  # Abrechnungsdaten senden (may trigger a billing!)
    BILLING_RESULT = "billing_result"  # Abrechnungsergebnis abrufen
    DOCUMENTS = "documents"
    CONSUMPTION = "consumption"  # monatliche Verbrauchsdaten / uVI


class DocumentedSupport(StrEnum):
    """Documented API availability at the provider. ``NO`` only for confirmed absence."""

    YES = "yes"  # "Ja, API vorhanden"
    DOCUMENTATION_REQUIRED = "documentation_required"  # offer page only, no technical spec
    UNCLEAR = "unclear"  # not stated in the checked sources
    NO = "no"  # confirmed absence (none today)


DOCUMENTED_SUPPORT_LABELS: dict[str, str] = {
    DocumentedSupport.YES: "Ja, API vorhanden",
    DocumentedSupport.DOCUMENTATION_REQUIRED: "Dokumentation erforderlich",
    DocumentedSupport.UNCLEAR: "Ungeklärt",
    DocumentedSupport.NO: "Nein, keine API vorhanden",
}


@dataclass(frozen=True)
class FunctionSupport:
    documented: DocumentedSupport
    source: str  # Q reference(s) of the master prompt
    note: str = ""


@dataclass(frozen=True)
class Provider:
    code: str
    name: str
    manual_only: bool
    functions: dict[Function, FunctionSupport] = field(default_factory=dict)
    sources: tuple[str, ...] = ()
    research_note: str = ""
    # Authentication note per API family (section 9); never a global assumption.
    auth_note: str = ""

    def support(self, function: Function) -> FunctionSupport:
        return self.functions.get(
            function,
            FunctionSupport(DocumentedSupport.UNCLEAR, "", "Nicht in den geprüften Quellen."),
        )


RECHECK = "Recherchestand 26.09.2026, vor Implementierung anhand der Quelle erneut prüfen."

SOURCES: dict[str, str] = {
    "Q1": "https://www.ista.com/developer-portal/api-dokumentation/",
    "Q2": "https://www.techem.com/re/de/digitale-Immobilienverwaltung/Data-Exchange-Services",
    "Q3": "https://developers.kalo.de/docs",
    "Q4": "https://www.minol.de/heizkostenabrechnung/cloud-to-cloud/",
    "Q5": (
        "https://www.brunata-metrona.de/haeufige-fragen/ueber-welche-schnittstellen-koennen-die-"
        "unterjaehrigen-verbrauchsinformationen-in-das-kundeneigene-system-integriert-werden/"
    ),
    "Q6": "https://bved.info/datenaustauschneu/releasekandidaten/",
    "Q7": "https://bved.info/datenaustauschneu/spezifikationen/",
    "Q8": "https://www.ista.com/developer-portal/artikel/billing-unit-data/",
    "Q9": "https://www.ista.com/developer-portal/haeufig-gestellte-fragen/",
    "Q10": "https://www.ista.com/developer-portal/artikel/on-site-roles-20-fuer-hka/",
    "Q11": "https://www.ista.com/developer-portal/artikel/billing-input/",
}

_YES = DocumentedSupport.YES
_DOC = DocumentedSupport.DOCUMENTATION_REQUIRED
_UNC = DocumentedSupport.UNCLEAR

PROVIDERS: tuple[Provider, ...] = (
    Provider(
        code="ista",
        name="ista",
        manual_only=False,
        functions={
            Function.BILLING_UNIT_DATA: FunctionSupport(
                _YES, "Q1, Q8", "Ordnungsbegriffsabgleich ist asynchron (Q8)."
            ),
            Function.ROLES: FunctionSupport(
                _YES, "Q1, Q10", "On-Site Roles 2.0: Vollabgleich, ausgelassene Rollen (Q10)."
            ),
            Function.BILLING_INPUT: FunctionSupport(
                _YES, "Q1, Q11", "Finale Übertragung kann eine Abrechnung auslösen (Q11)."
            ),
            Function.BILLING_RESULT: FunctionSupport(_YES, "Q1"),
            Function.DOCUMENTS: FunctionSupport(_YES, "Q1"),
            Function.CONSUMPTION: FunctionSupport(_YES, "Q1", "Monatliche Verbrauchsdaten."),
        },
        sources=("Q1", "Q8", "Q9", "Q10", "Q11"),
        research_note=RECHECK,
        auth_note=(
            "Unterschiedliche Verfahren für neuere bved-APIs und ältere Dokumentendienste; "
            "Test- und Produktionszugang unterscheiden sich hinsichtlich mTLS (Q9)."
        ),
    ),
    Provider(
        code="techem",
        name="Techem",
        manual_only=False,
        functions={
            function: FunctionSupport(
                _DOC,
                "Q2",
                "DXS und DXS Dynamic API werden angeboten; die Angebotsseite ersetzt keine "
                "technische Endpunktdokumentation.",
            )
            for function in Function
        },
        sources=("Q2",),
        research_note=RECHECK,
        auth_note="Nicht dokumentiert in den geprüften Quellen.",
    ),
    Provider(
        code="kalo",
        name="KALO / Kalorimeta",
        manual_only=False,
        functions={
            Function.ROLES: FunctionSupport(_YES, "Q3", "Nutzerwechsel zur uVI."),
            Function.CONSUMPTION: FunctionSupport(_YES, "Q3"),
            Function.DOCUMENTS: FunctionSupport(_YES, "Q3", "uVI-Dokumente."),
            Function.BILLING_UNIT_DATA: FunctionSupport(
                _UNC, "Q3", "DTA-Datenaustausch dokumentiert; Abgleich nicht pauschal ableiten."
            ),
            Function.BILLING_INPUT: FunctionSupport(_UNC, "Q3"),
            Function.BILLING_RESULT: FunctionSupport(_UNC, "Q3"),
        },
        sources=("Q3",),
        research_note=RECHECK,
    ),
    Provider(
        code="brunata_minol",
        name="Brunata Minol",
        manual_only=False,
        functions={
            Function.CONSUMPTION: FunctionSupport(
                _YES,
                "Q4, Q6, Q7",
                "Cloud-to-Cloud über den bved-/ARGE-Webservice; Bereitstellung und "
                "Voraussetzungen müssen vereinbart sein.",
            ),
            Function.DOCUMENTS: FunctionSupport(_UNC, "Q4"),
            Function.ROLES: FunctionSupport(_UNC, "Q4"),
            Function.BILLING_UNIT_DATA: FunctionSupport(_UNC, "Q4"),
            Function.BILLING_INPUT: FunctionSupport(_UNC, "Q4"),
            Function.BILLING_RESULT: FunctionSupport(_UNC, "Q4"),
        },
        sources=("Q4", "Q6", "Q7"),
        research_note=RECHECK,
    ),
    Provider(
        code="brunata_metrona",
        name="BRUNATA-METRONA",
        manual_only=False,
        functions={
            Function.DOCUMENTS: FunctionSupport(_YES, "Q5", "Dokumenten-Webservice für uVI."),
            Function.CONSUMPTION: FunctionSupport(_YES, "Q5", "Verbrauchsdaten-Webservice."),
            Function.ROLES: FunctionSupport(_UNC, "Q5", "Nur nach dokumentiertem Nachweis."),
            Function.BILLING_UNIT_DATA: FunctionSupport(_UNC, "Q5"),
            Function.BILLING_INPUT: FunctionSupport(_UNC, "Q5"),
            Function.BILLING_RESULT: FunctionSupport(_UNC, "Q5"),
        },
        sources=("Q5",),
        research_note=RECHECK,
    ),
    Provider(
        code="other",
        name="Sonstiger Messdienstleister / manuelle Verwaltung",
        manual_only=True,
        functions={},
        sources=(),
        research_note="Keine API; Zuordnungen und Daten werden manuell oder per Import gepflegt.",
    ),
)

PROVIDERS_BY_CODE: dict[str, Provider] = {p.code: p for p in PROVIDERS}


def get_provider(code: str) -> Provider | None:
    return PROVIDERS_BY_CODE.get(code)
