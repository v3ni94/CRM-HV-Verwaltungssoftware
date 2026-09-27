"""Adapter interface of the Messdienstleister module (master prompt sections 8 and 9).

One shared business service (``mhvp.metering.services``) and separate provider adapters. Stage 1
ships the interface, the ``manual`` adapter (no remote calls at all) and a ``fake`` adapter for
tests. Real ista and KALO adapters are stage 2 and must be written from the official technical
specification (Q1, Q3, Q8 to Q11); no endpoint, payload or authentication scheme is invented
here. Internal method names are not external URL conventions.

Stage 2 adds the real ista and KALO adapters (``adapters_ista``, ``adapters_kalo``) written from
the bved OpenAPI files linked by Q6/Q7 and the provider pages Q1, Q3, Q8, Q9; they are registered
at the end of this module. Every adapter declares the functions it implements and the
specification version it was verified against. A connection test is read only: it may
authenticate and nothing else (no billing order, no user change, no document receipt).

Outbound HTTPS targets of real adapters must pass ``mhvp.core.webhooks.pin_target`` (SSRF
guard, TLS verification stays on); secrets are never sent to a host other than the pinned
one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from mhvp.metering.providers import Function


class TestOutcome:
    OK = "ok"
    AUTH_FAILED = "auth_failed"
    NOT_RELEASED = "not_released"
    CREDENTIALS_MISSING = "credentials_missing"
    NOT_IMPLEMENTED = "not_implemented"
    ERROR = "error"


@dataclass(frozen=True)
class ConnectionTestResult:
    """Outcome of a read only authentication check. ``ok`` never claims access to any
    property (section 4); ``functions_released`` lists what the account answered for, if the
    adapter can tell, otherwise it stays empty."""

    outcome: str
    detail: str
    functions_released: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalUnitData:
    external_unit_number: str
    label: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExternalBillingUnitData:
    external_number: str
    name: str | None = None
    address: str | None = None
    units: tuple[ExternalUnitData, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsumptionRecord:
    external_billing_unit: str
    external_unit_number: str | None
    period_from: date
    period_to: date
    kind: str
    unit_of_measure: str
    reading_type: str
    value: Decimal | None
    value_kind: str
    external_ref: str | None = None


@dataclass(frozen=True)
class BillingResultRecord:
    external_billing_unit: str
    external_unit_number: str | None
    period_from: date
    period_to: date
    amount: Decimal
    currency: str
    external_document_ref: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentRecord:
    """Metadata of a provider document (bved documents 1.3 ``documents[]``); the content is
    downloaded separately after the assignment is known. ``version`` distinguishes a changed
    billing under the same external id (hash value or document type version)."""

    external_id: str
    filename: str
    doctype: str
    mime_type: str | None
    version: str | None
    file_date: datetime | None
    external_billing_unit: str | None
    external_unit_number: str | None
    period_from: date | None
    period_to: date | None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchResult:
    """Result of a read only fetch. ``unclear`` marks a call whose outcome could not be
    determined (timeout after the request left the process); the job is then reported as
    ``unclear`` and never retried blindly."""

    consumption: tuple[ConsumptionRecord, ...] = ()
    billing_results: tuple[BillingResultRecord, ...] = ()
    billing_units: tuple[ExternalBillingUnitData, ...] = ()
    documents: tuple[DocumentRecord, ...] = ()
    errors: tuple[str, ...] = ()
    unclear: bool = False
    waiting_provider: bool = False


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a controlled write (section 12). ``outcome`` is ``accepted`` (provider
    transaction id present), ``validated`` (validate only, nothing stored at the provider),
    ``rejected`` (provider validation errors), ``unclear`` (timeout after the request left the
    process; never retried blindly, case 11) or ``failed`` (technical error before or without
    a provider decision). ``messages`` carry the provider's validation messages as
    ``{"type": "error" | "warning", "message": ..., "shortmessage": ...}``."""

    outcome: str
    transaction_id: str | None = None
    messages: tuple[dict[str, Any], ...] = ()
    detail: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> tuple[dict[str, Any], ...]:
        return tuple(m for m in self.messages if str(m.get("type", "")).lower() != "warning")

    @property
    def warnings(self) -> tuple[dict[str, Any], ...]:
        return tuple(m for m in self.messages if str(m.get("type", "")).lower() == "warning")


class WriteOutcome:
    ACCEPTED = "accepted"
    VALIDATED = "validated"
    REJECTED = "rejected"
    UNCLEAR = "unclear"
    FAILED = "failed"


class MeteringAdapter(Protocol):
    code: str
    spec_source: str
    spec_version: str
    implemented: frozenset[Function]
    required_secrets: frozenset[str]

    def test_connection(
        self, *, config: Mapping[str, Any], secrets: Mapping[str, str], environment: str
    ) -> ConnectionTestResult: ...

    def fetch(
        self,
        *,
        function: Function,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_units: Sequence[str],
        period_from: date | None,
        period_to: date | None,
        cursor: str | None = None,
    ) -> FetchResult: ...

    def download_document(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        document: DocumentRecord,
    ) -> bytes: ...

    def acknowledge_document(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        document: DocumentRecord,
    ) -> None:
        """Provider receipt (bved documents ``PUT /documents/out/{id}/status``). Called by the
        service only after the document is durably stored and committed (section 11)."""
        ...

    def submit_billing_unit_setup(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        residential_units: Sequence[Mapping[str, Any]],
        customer_number: str,
    ) -> str:
        """Writing step of the Ordnungsbegriffsabgleich (bved billing unit data ``sendSetup``).
        Returns the provider transaction id. Never retried after a timeout (case 11). Not
        offered by any endpoint while ``write_sync_enabled`` is off (M40-03)."""
        ...

    def fetch_billing_template(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        period_to: date,
    ) -> dict[str, Any]:
        """Read only: the provider's billing template of a period (bved billing-input
        ``GET .../billingperiods/{to}``). Raises ``NotImplementedError`` when the provider
        has no documented and implemented billing input API."""
        ...

    def send_billing_input(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        period_to: date,
        payload: Mapping[str, Any],
        action: str,
    ) -> WriteResult:
        """bved billing-input ``POST .../billingperiods/{to}?action=``. ``VALIDATE`` stores
        nothing at the provider; ``SEND`` and ``SEND_AND_IGNORE_WARNINGS`` are binding orders
        (an accepted send may trigger the billing, Q11). Sent exactly once (case 11)."""
        ...

    def send_roles(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        external_unit_number: str,
        payload: Mapping[str, Any],
    ) -> WriteResult:
        """bved on-site-roles 2.0 ``POST .../residentialunits/{unit}/on-site-roles``: the full
        data set of one residential unit (omitted roles may be ended by the provider, hence
        the service always sends the complete set, section 12). Sent exactly once."""
        ...


class ManualAdapter:
    """Provider without API or without implemented adapter: nothing is called. Used for
    ``other`` and for every catalogue provider until its real adapter exists (stage 2)."""

    code = "manual"
    spec_source = "keine (manuelle Verwaltung)"
    spec_version = "n/a"
    implemented: frozenset[Function] = frozenset()
    required_secrets: frozenset[str] = frozenset()

    def test_connection(
        self, *, config: Mapping[str, Any], secrets: Mapping[str, str], environment: str
    ) -> ConnectionTestResult:
        return ConnectionTestResult(
            TestOutcome.NOT_IMPLEMENTED,
            "Für diesen Anbieter ist kein Adapter implementiert; es wurde keine Verbindung "
            "aufgebaut. Zuordnungen und Daten werden manuell oder per Import gepflegt.",
        )

    def fetch(self, **kwargs: Any) -> FetchResult:
        return FetchResult(
            errors=("Für diesen Anbieter ist kein Abruf implementiert (kein Adapter).",)
        )

    def download_document(self, **kwargs: Any) -> bytes:
        raise NotImplementedError("kein Adapter")

    def acknowledge_document(self, **kwargs: Any) -> None:
        raise NotImplementedError("kein Adapter")

    def submit_billing_unit_setup(self, **kwargs: Any) -> str:
        raise NotImplementedError("kein Adapter")

    def fetch_billing_template(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("kein Adapter")

    def send_billing_input(self, **kwargs: Any) -> WriteResult:
        raise NotImplementedError("kein Adapter")

    def send_roles(self, **kwargs: Any) -> WriteResult:
        raise NotImplementedError("kein Adapter")


class FakeAdapter:
    """Test double (artificial data only, never a sandbox or production system). Behaviour is
    scripted through ``config``: ``fake_outcome`` for the test, ``fake_records`` for fetches."""

    code = "fake"
    spec_source = "Testdouble, keine Anbieterspezifikation"
    spec_version = "test"
    implemented: frozenset[Function] = frozenset(
        {
            Function.CONSUMPTION,
            Function.BILLING_RESULT,
            Function.BILLING_UNIT_DATA,
            Function.DOCUMENTS,
            Function.ROLES,
            Function.BILLING_INPUT,
        }
    )
    required_secrets: frozenset[str] = frozenset({"api_key"})

    def __init__(self) -> None:
        # Test observation only: acknowledged external document ids in call order.
        self.acknowledged: list[str] = []
        self.downloads: list[str] = []
        # Test observation only: every write call as (kind, action, external unit, payload).
        self.writes: list[tuple[str, str, str, dict[str, Any]]] = []

    def test_connection(
        self, *, config: Mapping[str, Any], secrets: Mapping[str, str], environment: str
    ) -> ConnectionTestResult:
        if not secrets.get("api_key"):
            return ConnectionTestResult(
                TestOutcome.CREDENTIALS_MISSING, "Zugangsdaten (api_key) sind nicht hinterlegt."
            )
        outcome = str(config.get("fake_outcome", TestOutcome.OK))
        if outcome == TestOutcome.AUTH_FAILED:
            return ConnectionTestResult(outcome, "Authentifizierung fehlgeschlagen (Test).")
        if outcome == TestOutcome.NOT_RELEASED:
            return ConnectionTestResult(outcome, "Kundenkonto nicht freigeschaltet (Test).")
        return ConnectionTestResult(
            TestOutcome.OK,
            "Anmeldung erfolgreich (Testdouble). Kein Nachweis für Objektzugriff.",
            tuple(str(f) for f in config.get("fake_released", [])),
        )

    def fetch(
        self,
        *,
        function: Function,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_units: Sequence[str],
        period_from: date | None,
        period_to: date | None,
        cursor: str | None = None,
    ) -> FetchResult:
        if not secrets.get("api_key"):
            return FetchResult(errors=("Zugangsdaten (api_key) sind nicht hinterlegt.",))
        if config.get("fake_unclear"):
            return FetchResult(unclear=True, errors=("Zeitüberschreitung, Ergebnis unklar.",))
        records = list(config.get("fake_records", []))
        consumption = tuple(
            ConsumptionRecord(
                external_billing_unit=str(r["external_billing_unit"]),
                external_unit_number=r.get("external_unit_number"),
                period_from=date.fromisoformat(r["period_from"]),
                period_to=date.fromisoformat(r["period_to"]),
                kind=str(r.get("kind", "heating")),
                unit_of_measure=str(r.get("unit_of_measure", "kWh")),
                reading_type=str(r.get("reading_type", "period_consumption")),
                value=None if r.get("value") is None else Decimal(str(r["value"])),
                value_kind=str(r.get("value_kind", "actual")),
                external_ref=r.get("external_ref"),
            )
            for r in records
            if r.get("type", "consumption") == "consumption" and function == Function.CONSUMPTION
        )
        billing = tuple(
            BillingResultRecord(
                external_billing_unit=str(r["external_billing_unit"]),
                external_unit_number=r.get("external_unit_number"),
                period_from=date.fromisoformat(r["period_from"]),
                period_to=date.fromisoformat(r["period_to"]),
                amount=Decimal(str(r["amount"])),
                currency=str(r.get("currency", "EUR")),
                external_document_ref=str(r["external_document_ref"]),
            )
            for r in records
            if r.get("type") == "billing_result" and function == Function.BILLING_RESULT
        )
        documents = tuple(
            DocumentRecord(
                external_id=str(r["external_id"]),
                filename=str(r.get("filename", "dokument.pdf")),
                doctype=str(r.get("doctype", "OTHER")),
                mime_type=r.get("mime_type", "application/pdf"),
                version=r.get("version"),
                file_date=None,
                external_billing_unit=r.get("external_billing_unit"),
                external_unit_number=r.get("external_unit_number"),
                period_from=date.fromisoformat(r["period_from"]) if r.get("period_from") else None,
                period_to=date.fromisoformat(r["period_to"]) if r.get("period_to") else None,
                payload={"content_b64": r.get("content_b64", "")},
            )
            for r in records
            if r.get("type") == "document" and function == Function.DOCUMENTS
        )
        errors = tuple(str(e) for e in config.get("fake_errors", []))
        return FetchResult(
            consumption=consumption, billing_results=billing, documents=documents, errors=errors
        )

    def download_document(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        document: DocumentRecord,
    ) -> bytes:
        import base64

        self.downloads.append(document.external_id)
        return base64.b64decode(document.payload.get("content_b64", ""))

    def acknowledge_document(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        document: DocumentRecord,
    ) -> None:
        self.acknowledged.append(document.external_id)

    def submit_billing_unit_setup(self, **kwargs: Any) -> str:
        raise NotImplementedError("Testdouble: schreibende Vorgänge sind gesperrt.")

    def fetch_billing_template(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        period_to: date,
    ) -> dict[str, Any]:
        template = config.get("fake_billing_template")
        if isinstance(template, dict):
            return dict(template)
        return {"currency": "EUR", "expectedvat": "GROSS", "billingrecipients": []}

    def _write(
        self,
        kind: str,
        action: str,
        unit: str,
        payload: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> WriteResult:
        """Scripted through ``config``: ``fake_write_unclear`` (timeout after the request left,
        exactly one attempt is recorded), ``fake_write_messages`` (provider validation
        messages; an error rejects), ``fake_write_transaction`` (transaction id)."""
        self.writes.append((kind, action, unit, dict(payload)))
        if config.get("fake_write_unclear"):
            return WriteResult(
                WriteOutcome.UNCLEAR,
                detail="Zeitüberschreitung bei schreibendem Aufruf; Ergebnis unklar, keine "
                "automatische Wiederholung.",
            )
        messages = tuple(dict(m) for m in config.get("fake_write_messages", []))
        errors = [m for m in messages if str(m.get("type", "")).lower() != "warning"]
        if errors:
            return WriteResult(WriteOutcome.REJECTED, messages=messages, detail="Abgewiesen.")
        if action == "VALIDATE":
            return WriteResult(WriteOutcome.VALIDATED, messages=messages, detail="Geprüft.")
        if messages and action == "SEND":
            return WriteResult(
                WriteOutcome.REJECTED,
                messages=messages,
                detail="Warnungen vorhanden; SEND abgebrochen (Testdouble).",
            )
        return WriteResult(
            WriteOutcome.ACCEPTED,
            transaction_id=str(config.get("fake_write_transaction", "FAKE-TX-1")),
            messages=messages,
            detail="Angenommen (Testdouble).",
        )

    def send_billing_input(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        period_to: date,
        payload: Mapping[str, Any],
        action: str,
    ) -> WriteResult:
        if not secrets.get("api_key"):
            return WriteResult(WriteOutcome.FAILED, detail="Zugangsdaten (api_key) fehlen.")
        return self._write("billing_input", action, external_billing_unit, payload, config)

    def send_roles(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        external_billing_unit: str,
        external_unit_number: str,
        payload: Mapping[str, Any],
    ) -> WriteResult:
        if not secrets.get("api_key"):
            return WriteResult(WriteOutcome.FAILED, detail="Zugangsdaten (api_key) fehlen.")
        return self._write("roles", "SEND", external_unit_number, payload, config)


_ADAPTERS: dict[str, MeteringAdapter] = {"manual": ManualAdapter(), "fake": FakeAdapter()}

# Provider code to adapter code. ista and KALO are replaced by ``_register_real_adapters``
# (stage 2); the others stay ``manual`` until their technical documentation exists (M40-02).
PROVIDER_ADAPTERS: dict[str, str] = {
    "ista": "manual",
    "techem": "manual",
    "kalo": "manual",
    "brunata_minol": "manual",
    "brunata_metrona": "manual",
    "other": "manual",
}


def adapter_for(provider_code: str, config: Mapping[str, Any]) -> MeteringAdapter:
    """Adapter of a connection. ``config["adapter"] == "fake"`` selects the test double; it is
    only honoured for the ``test`` environment so a production connection can never run
    against artificial data."""
    if config.get("adapter") == "fake" and config.get("_environment") == "test":
        return _ADAPTERS["fake"]
    return _ADAPTERS[PROVIDER_ADAPTERS.get(provider_code, "manual")]


def register_adapter(adapter: MeteringAdapter, *, provider_code: str) -> None:
    _ADAPTERS[adapter.code] = adapter
    PROVIDER_ADAPTERS[provider_code] = adapter.code


def _register_real_adapters() -> None:
    # Imported here: the real adapters depend on the record types above.
    from mhvp.metering.adapters_ista import IstaAdapter
    from mhvp.metering.adapters_kalo import KaloAdapter

    register_adapter(IstaAdapter(), provider_code="ista")
    register_adapter(KaloAdapter(), provider_code="kalo")


_register_real_adapters()
