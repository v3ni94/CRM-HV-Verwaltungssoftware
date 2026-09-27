"""File exchange adapters for Techem, Brunata Minol and BRUNATA-METRONA (M40-02).

What is publicly documented (checked 27.09.2026, see docs/integrations/messdienstleister.md
section 7.7):

* Techem (Q2, Q13): "Techem Data Exchange Services entsprechen dem offenen Standard des bved";
  the services carry "Abrechnungsdokumente (E898), Datentauschdateien (LM- und BK-Sätze),
  EED-Verbrauchsinformation"; transport via the client application "DXS Connector" and the
  "Techem DXS Filetransfer Service" or the "DXS Dynamic API". No host, protocol, port,
  authentication or API reference is published.
* Brunata Minol (Q12): "bved 3.10" and "ARGE 3.10" with L/M, B/K, D and E898 records;
  transport through software integrations and the customer portal "Minol direct"; no
  technical transport documentation.
* BRUNATA-METRONA (Q5): only the ARGE web services "documents" and "consumption" for uVI are
  named; file exchange is not mentioned on the checked page.

Consequently these adapters open no network connection at all: they parse the bved 3.10
exchange files (``mhvp.metering.heiwako``, Q14) that the operator downloads from the
provider's portal or receives through the provider's transfer client. Every online operation
answers "Dokumentation erforderlich" (``ManualAdapter`` behaviour, ``setup_submission`` is
``None``). An SFTP configuration is deliberately not offered: no provider documents host, port
or key procedure, so the CRM would only invent one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar

from mhvp.metering import heiwako
from mhvp.metering.adapters import (
    BillingResultRecord,
    ConnectionTestResult,
    ManualAdapter,
    TestOutcome,
)
from mhvp.metering.providers import Function

__all__ = [
    "BrunataMetronaFileAdapter",
    "BrunataMinolFileAdapter",
    "FileImportResult",
    "HeiwakoFileAdapter",
    "TechemFileAdapter",
]

MAX_FILE_BYTES = 20_000_000


@dataclass
class FileImportResult:
    """Outcome of parsing uploaded exchange files. Nothing is stored by the adapter."""

    files: list[dict[str, Any]] = field(default_factory=list)
    billing_results: list[BillingResultRecord] = field(default_factory=list)
    users: list[heiwako.MRecord] = field(default_factory=list)
    properties: list[heiwako.LRecord] = field(default_factory=list)
    references: list[heiwako.ARecord] = field(default_factory=list)
    images: list[heiwako.E898Record] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class HeiwakoFileAdapter(ManualAdapter):
    """Base of the file exchange adapters: no remote calls, bved 3.10 file parsing only."""

    code = "heiwako_file"
    spec_source = (
        "bved Standard-Datenaustausch 3.10 dritte Erweiterung, September 2025 (Q14, PDF vom "
        "27.09.2026 ausgewertet)"
    )
    spec_version = "bved 3.10 (Dateien DTA310, DTM310, DTD310, DTE898), geprüft 27.09.2026"
    # No online function is implemented; the capability matrix therefore keeps every function
    # at "Adapter nicht implementiert". File import is a separate, documented path.
    implemented: frozenset[Function] = frozenset()
    setup_submission: str | None = None
    required_secrets: frozenset[str] = frozenset()
    file_kinds: ClassVar[tuple[str, ...]] = ("DTA310", "DTM310", "DTD310", "DTE898")
    # Documented transport of the provider (operator document), no technical parameters.
    transport_note: ClassVar[str] = ""
    # Record types the provider names publicly for its file exchange; others are parsed the
    # same way but reported as "nicht belegt" for this provider.
    documented_record_types: ClassVar[frozenset[str]] = frozenset()

    def test_connection(
        self, *, config: Mapping[str, Any], secrets: Mapping[str, str], environment: str
    ) -> ConnectionTestResult:
        return ConnectionTestResult(
            TestOutcome.NOT_IMPLEMENTED,
            "Dateiaustausch nach bved 3.10: es wurde keine Verbindung aufgebaut. "
            + self.transport_note
            + " Dateien werden über den Import geprüft; Online-Zugang: Dokumentation "
            "erforderlich (M40-02).",
        )

    def import_files(
        self,
        files: Mapping[str, bytes],
        *,
        period_from: date | None = None,
        default_currency: str = "EUR",
    ) -> FileImportResult:
        """Parse a set of exchange files (name to content). A DTM310 file in the same set
        provides the billing period of every property for the D records; otherwise
        ``period_from`` is required for billing results."""
        result = FileImportResult()
        parsed: list[tuple[str, heiwako.HeiwakoFile]] = []
        for name, raw in files.items():
            if len(raw) > MAX_FILE_BYTES:
                result.errors.append(f"{name}: Datei größer als {MAX_FILE_BYTES // 1_000_000} MB.")
                continue
            try:
                parsed_file = heiwako.parse_file(raw, filename=name)
            except UnicodeDecodeError:
                result.errors.append(f"{name}: nicht als ISO 8859-15 lesbar.")
                continue
            parsed.append((name, parsed_file))
            counts: dict[str, int] = {}
            for line in parsed_file.records:
                counts[line.record_type] = counts.get(line.record_type, 0) + 1
            documented = self.documented_record_types
            undocumented = sorted(t for t in counts if documented and t not in documented)
            result.files.append(
                {
                    "name": name,
                    "kind": parsed_file.kind,
                    "record_counts": counts,
                    "errors": list(parsed_file.errors),
                    "undocumented_record_types": undocumented,
                }
            )
            result.errors.extend(f"{name}: {e}" for e in parsed_file.errors)
            if parsed_file.kind is None:
                result.errors.append(
                    f"{name}: Dateiname entspricht nicht dem Standard (DTA310_, DTM310_, "
                    "DTD310_, DTE898_ mit Zeitstempel .DAT)."
                )
        periods: dict[str, tuple[date, date]] = {}
        for _, parsed_file in parsed:
            for l_rec in parsed_file.of_type("L"):
                result.properties.append(l_rec)
                prop = l_rec.header.provider_property_number
                if prop and l_rec.period_from and l_rec.period_to:
                    periods[prop] = (l_rec.period_from, l_rec.period_to)
            result.users.extend(parsed_file.of_type("M"))
            result.references.extend(parsed_file.of_type("A"))
            result.images.extend(parsed_file.of_type("E898"))
        d_records: list[heiwako.DRecord] = []
        for _, parsed_file in parsed:
            d_records.extend(parsed_file.of_type("D"))
        billing, problems = heiwako.billing_results_from_d(
            d_records,
            periods=periods,
            period_from=period_from,
            default_currency=default_currency,
        )
        result.billing_results.extend(billing)
        result.errors.extend(problems)
        return result


class TechemFileAdapter(HeiwakoFileAdapter):
    code = "techem_file"
    transport_note = (
        "Techem nennt öffentlich den DXS Connector und den DXS Filetransfer Service (Q2, Q13) "
        "ohne Host, Protokoll oder Anmeldeverfahren."
    )
    # Q2/Q13 name E898, LM and BK records; D records are not named on the Techem page.
    documented_record_types = frozenset({"L", "M", "E898"})


class BrunataMinolFileAdapter(HeiwakoFileAdapter):
    code = "brunata_minol_file"
    transport_note = (
        "Brunata Minol nennt öffentlich bved 3.10 mit L/M-, B/K-, D- und E898-Sätzen sowie das "
        "Kundenportal Minol direct (Q12) ohne technische Übertragungsparameter."
    )
    documented_record_types = frozenset({"L", "M", "D", "E898"})


class BrunataMetronaFileAdapter(HeiwakoFileAdapter):
    code = "brunata_metrona_file"
    transport_note = (
        "BRUNATA-METRONA nennt öffentlich nur die ARGE-Webservices für uVI (Q5); ein "
        "Dateiaustausch nach bved 3.10 ist dort nicht belegt."
    )
    documented_record_types = frozenset()
