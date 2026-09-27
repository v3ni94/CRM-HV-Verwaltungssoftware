"""Adapter interface of the Messdienstleister module (master prompt sections 8 and 9).

One shared business service (``mhvp.metering.services``) and separate provider adapters. Stage 1
ships the interface, the ``manual`` adapter (no remote calls at all) and a ``fake`` adapter for
tests. Real ista and KALO adapters are stage 2 and must be written from the official technical
specification (Q1, Q3, Q8 to Q11); no endpoint, payload or authentication scheme is invented
here. Internal method names are not external URL conventions.

Every adapter declares the functions it implements and the specification version it was
verified against. A connection test is read only: it may authenticate and nothing else (no
billing order, no user change, no document receipt).

Outbound HTTPS targets of real adapters must pass ``mhvp.core.webhooks.pin_target`` (SSRF
guard, TLS verification stays on); secrets are never sent to a host other than the pinned
one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
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
class FetchResult:
    """Result of a read only fetch. ``unclear`` marks a call whose outcome could not be
    determined (timeout after the request left the process); the job is then reported as
    ``unclear`` and never retried blindly."""

    consumption: tuple[ConsumptionRecord, ...] = ()
    billing_results: tuple[BillingResultRecord, ...] = ()
    billing_units: tuple[ExternalBillingUnitData, ...] = ()
    errors: tuple[str, ...] = ()
    unclear: bool = False
    waiting_provider: bool = False


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
    ) -> FetchResult: ...


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


class FakeAdapter:
    """Test double (artificial data only, never a sandbox or production system). Behaviour is
    scripted through ``config``: ``fake_outcome`` for the test, ``fake_records`` for fetches."""

    code = "fake"
    spec_source = "Testdouble, keine Anbieterspezifikation"
    spec_version = "test"
    implemented: frozenset[Function] = frozenset(
        {Function.CONSUMPTION, Function.BILLING_RESULT, Function.BILLING_UNIT_DATA}
    )
    required_secrets: frozenset[str] = frozenset({"api_key"})

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
        errors = tuple(str(e) for e in config.get("fake_errors", []))
        return FetchResult(consumption=consumption, billing_results=billing, errors=errors)


_ADAPTERS: dict[str, MeteringAdapter] = {"manual": ManualAdapter(), "fake": FakeAdapter()}

# Provider code to adapter code. Stage 1: every real provider maps to ``manual`` (no adapter
# implemented); stage 2 replaces the entries for ista and KALO once written from Q1/Q3.
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
