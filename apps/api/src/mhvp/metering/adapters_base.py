"""Shared behaviour of the real bved based adapters (ista, KALO): configuration and secret
resolution per API family, strict test/production separation, optional mTLS material, and
the read paths (consumption, billing result, billing unit data, documents) over
``mhvp.metering.bved``. Provider specific parts (families, hosts, authentication scheme per
family) live in the subclasses and cite their source."""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

import httpx

from mhvp.core.webhooks import PinnedTarget
from mhvp.metering import bved
from mhvp.metering.adapters import (
    ConnectionTestResult,
    DocumentRecord,
    ExternalBillingUnitData,
    FetchResult,
    TestOutcome,
)
from mhvp.metering.http import (
    AuthFailedError,
    BasicCredentials,
    ClientCertificate,
    OAuth2ClientCredentials,
    ProviderHttp,
    ProviderHttpError,
)
from mhvp.metering.providers import Function


class AdapterConfigError(Exception):
    """Configuration or credentials incomplete; reported, never guessed."""


@dataclass(frozen=True)
class Family:
    """One API family of a provider: the function it serves, the documented authentication
    scheme(s) and how the base URL is found in the connection configuration."""

    function: Function
    auth_schemes: tuple[str, ...]  # documented options, first one is the default
    config_key: str  # key under ``config["base_urls"]`` (ista) or a fixed path (KALO)
    spec: str


class BvedAdapterBase:
    code = ""
    spec_source = ""
    spec_version = ""
    implemented: frozenset[Function] = frozenset()
    required_secrets: frozenset[str] = frozenset()  # checked per family instead
    families: ClassVar[dict[Function, Family]] = {}
    # Test injection: transport (httpx.MockTransport), pin (no DNS) and sleep (no backoff wait).
    transport: httpx.BaseTransport | None = None
    pin: Callable[[str], PinnedTarget] | None = None
    sleep: Callable[[float], None] | None = None

    # Provider specific ---------------------------------------------------------------

    def base_url(self, config: Mapping[str, Any], environment: str, family: Family) -> str:
        raise NotImplementedError

    def token_url(self, config: Mapping[str, Any], environment: str) -> str:
        raise NotImplementedError

    def certificate_required(self, environment: str) -> bool:
        return False

    # Shared ------------------------------------------------------------------------------

    def check_environment(self, config: Mapping[str, Any], environment: str) -> None:
        """A configuration written for one environment never runs in the other: the
        configuration must name its environment explicitly (section 4, case 9)."""
        declared = config.get("config_environment")
        if declared != environment:
            raise AdapterConfigError(
                "Konfiguration ist nicht für diese Umgebung freigegeben (config_environment "
                f"= {declared!r}, Verbindung = {environment!r})."
            )

    def auth_for(
        self,
        family: Family,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
    ) -> OAuth2ClientCredentials | BasicCredentials:
        scheme = str(config.get(f"{family.function.value}_auth") or family.auth_schemes[0])
        if scheme not in family.auth_schemes:
            raise AdapterConfigError(
                f"Authentifizierung {scheme!r} ist für {family.function.value} nicht dokumentiert "
                f"(zulässig: {', '.join(family.auth_schemes)})."
            )
        if scheme == "oauth2":
            missing = [k for k in ("client_id", "client_secret") if not secrets.get(k)]
            if missing:
                raise AdapterConfigError("Zugangsdaten fehlen: " + ", ".join(missing) + ".")
            return OAuth2ClientCredentials(
                token_url=self.token_url(config, environment),
                client_id=secrets["client_id"],
                client_secret=secrets["client_secret"],
                scope=config.get("oauth_scope") or None,
            )
        missing = [k for k in ("basic_username", "basic_password") if not secrets.get(k)]
        if missing:
            raise AdapterConfigError("Zugangsdaten fehlen: " + ", ".join(missing) + ".")
        return BasicCredentials(secrets["basic_username"], secrets["basic_password"])

    def _http(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], environment: str
    ) -> ProviderHttp:
        certificate: ClientCertificate | None = None
        cert_pem, key_pem = secrets.get("client_cert_pem"), secrets.get("client_key_pem")
        if cert_pem and key_pem:
            certificate = _write_certificate(cert_pem, key_pem)
        elif self.certificate_required(environment):
            raise AdapterConfigError(
                "Zugangsdaten fehlen: client_cert_pem, client_key_pem (mTLS im Testzugang, Q9)."
            )
        http = _CleaningHttp(
            timeout=float(config.get("timeout_seconds", 30.0)),
            retries=int(config.get("retries", 2)),
            backoff_seconds=float(config.get("backoff_seconds", 0.5)),
            transport=self.transport,
            pin=self.pin,
            sleep=self.sleep or time.sleep,
            certificate=certificate,
        )
        return http

    def _family(self, function: Function) -> Family:
        family = self.families.get(function)
        if family is None:
            raise AdapterConfigError(
                f"Funktion {function.value} ist für {self.code} nicht dokumentiert."
            )
        return family

    # Interface -----------------------------------------------------------------------------

    def test_connection(
        self, *, config: Mapping[str, Any], secrets: Mapping[str, str], environment: str
    ) -> ConnectionTestResult:
        """Read only: one authenticated, side effect free GET per configured family
        (``.../count`` or a one element list). Nothing is ordered, changed or acknowledged."""
        try:
            self.check_environment(config, environment)
            http = self._http(config, secrets, environment)
        except AdapterConfigError as exc:
            return ConnectionTestResult(TestOutcome.CREDENTIALS_MISSING, str(exc))
        released: list[str] = []
        details: list[str] = []
        auth_failed = False
        with http:
            for function, family in self.families.items():
                try:
                    base = self.base_url(config, environment, family)
                    auth = self.auth_for(family, config, secrets, environment)
                except AdapterConfigError as exc:
                    details.append(f"{function.value}: nicht konfiguriert ({exc})")
                    continue
                try:
                    self._probe(http, base, auth, family)
                except AuthFailedError as exc:
                    auth_failed = True
                    details.append(f"{function.value}: {exc.message}")
                except ProviderHttpError as exc:
                    details.append(f"{function.value}: {exc.message}")
                else:
                    released.append(function.value)
        if not released and auth_failed:
            return ConnectionTestResult(TestOutcome.AUTH_FAILED, "; ".join(details))
        if not released:
            return ConnectionTestResult(
                TestOutcome.ERROR, "; ".join(details) or "Keine API-Familie konfiguriert."
            )
        return ConnectionTestResult(
            TestOutcome.OK,
            "Anmeldung erfolgreich für: "
            + ", ".join(released)
            + ". Kein Nachweis für Objektzugriff."
            + ("; " + "; ".join(details) if details else ""),
            tuple(released),
        )

    def _probe(self, http: ProviderHttp, base: str, auth: Any, family: Family) -> None:
        if family.function == Function.DOCUMENTS:
            http.get_json(bved.join(base, "/documents/out/count"), auth=auth)
        elif family.function == Function.BILLING_UNIT_DATA:
            http.get_json(
                bved.join(base, "/billingunitdata/v1/billingunits"),
                auth=auth,
                params={"limit": 1, "offset": 0},
            )
        elif family.function == Function.CONSUMPTION:
            http.get_json(bved.join(base, "/eedbillingunits/count"), auth=auth)
        elif family.function == Function.BILLING_RESULT:
            # No list without a billing unit in 1.0.3: obtaining the token is the check.
            if isinstance(auth, OAuth2ClientCredentials):
                http._bearer(auth)
            else:  # pragma: no cover - billing result is OAuth 2 only
                raise ProviderHttpError("Billing Result ist nur mit OAuth 2 dokumentiert.")

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
        try:
            self.check_environment(config, environment)
            family = self._family(function)
            base = self.base_url(config, environment, family)
            auth = self.auth_for(family, config, secrets, environment)
            http = self._http(config, secrets, environment)
        except AdapterConfigError as exc:
            return FetchResult(errors=(str(exc),))
        parallel = int(config.get("max_parallel", 2))
        currency = str(config.get("currency", "EUR"))
        with http:
            try:
                if function == Function.CONSUMPTION:
                    return self._fetch_consumption(
                        http, base, auth, external_billing_units, period_from, period_to, parallel
                    )
                if function == Function.BILLING_RESULT:
                    return self._fetch_billing_results(
                        http,
                        base,
                        auth,
                        external_billing_units,
                        period_from,
                        period_to,
                        parallel,
                        currency,
                    )
                if function == Function.BILLING_UNIT_DATA:
                    return self._fetch_billing_units(
                        http, base, auth, external_billing_units, cursor
                    )
                if function == Function.DOCUMENTS:
                    return FetchResult(documents=tuple(bved.list_documents(http, base, auth=auth)))
            except AuthFailedError as exc:
                return FetchResult(errors=(exc.message,))
            except ProviderHttpError as exc:
                return FetchResult(errors=(exc.message,), unclear=exc.unclear)
            except bved.BvedPayloadError as exc:
                return FetchResult(errors=(f"Antwort entspricht nicht der Spezifikation: {exc}",))
        return FetchResult(errors=(f"Funktion {function.value} nicht implementiert.",))

    def _fetch_consumption(
        self,
        http: ProviderHttp,
        base: str,
        auth: Any,
        units: Sequence[str],
        period_from: date | None,
        period_to: date | None,
        parallel: int,
    ) -> FetchResult:
        records: list[Any] = []
        errors: list[str] = []

        def one(unit: str) -> Callable[[], list[Any]]:
            def run() -> list[Any]:
                years = {period_from.year} if period_from else set()
                if period_to:
                    years.add(period_to.year)
                periods: list[str] = []
                for year in sorted(years) or [None]:  # type: ignore[list-item]
                    periods.extend(
                        bved.consumption_periods(
                            http, base, auth=auth, billing_unit=unit, year=year
                        )
                    )
                out: list[Any] = []
                for period in sorted(set(periods)):
                    start, end = bved.month_period(period)
                    if (period_from and end < period_from) or (period_to and start > period_to):
                        continue
                    body = bved.consumption_data(
                        http, base, auth=auth, billing_unit=unit, period=period
                    )
                    if body is not None:
                        out.extend(bved.parse_consumption(body))
                return out

            return run

        for unit, (value, error) in zip(
            units, bved.run_bounded([one(u) for u in units], max_parallel=parallel), strict=True
        ):
            if error:
                errors.append(f"Abrechnungseinheit {unit}: {error}")
            else:
                records.extend(value or [])
        return FetchResult(consumption=tuple(records), errors=tuple(errors))

    def _fetch_billing_results(
        self,
        http: ProviderHttp,
        base: str,
        auth: Any,
        units: Sequence[str],
        period_from: date | None,
        period_to: date | None,
        parallel: int,
        currency: str,
    ) -> FetchResult:
        records: list[Any] = []
        errors: list[str] = []

        def one(unit: str) -> Callable[[], list[Any]]:
            def run() -> list[Any]:
                out: list[Any] = []
                for period in bved.billing_periods(http, base, auth=auth, billing_unit=unit):
                    to = str(period.get("to") or "")
                    if not to:
                        continue
                    to_date = date.fromisoformat(to[:10])
                    if (period_from and to_date < period_from) or (
                        period_to and to_date > period_to
                    ):
                        continue
                    body = bved.billing_result(
                        http, base, auth=auth, billing_unit=unit, period_to=to
                    )
                    if body is not None:
                        out.extend(bved.parse_billing_result(body, currency=currency))
                return out

            return run

        for unit, (value, error) in zip(
            units, bved.run_bounded([one(u) for u in units], max_parallel=parallel), strict=True
        ):
            if error:
                errors.append(f"Abrechnungseinheit {unit}: {error}")
            else:
                records.extend(value or [])
        return FetchResult(billing_results=tuple(records), errors=tuple(errors))

    def _fetch_billing_units(
        self, http: ProviderHttp, base: str, auth: Any, units: Sequence[str], cursor: str | None
    ) -> FetchResult:
        """Asynchronous Ordnungsbegriffsabgleich (Q8): the list carries the setup status per
        billing unit; results are fetched for completed units, running ones leave the job in
        ``waiting_provider``. ``cursor`` is the ``from`` filter (last durable run)."""
        entries = bved.list_billing_units(http, base, auth=auth, since=cursor)
        wanted = set(units)
        results: list[ExternalBillingUnitData] = []
        errors: list[str] = []
        waiting = False
        for entry in entries:
            number = str(entry.get("billingunitMscnumber") or "")
            if wanted and number not in wanted:
                continue
            status = str(entry.get("setupstatus") or "")
            detail = None
            if status == "COMPLETED":
                try:
                    detail = bved.setup_result(http, base, auth=auth, billing_unit=number)
                except ProviderHttpError as exc:
                    errors.append(f"Abrechnungseinheit {number}: {exc.message}")
            elif status == "IN_PROGRESS":
                waiting = True
            try:
                results.append(bved.parse_billing_unit(entry, detail))
            except bved.BvedPayloadError as exc:
                errors.append(f"Abrechnungseinheit {number or '?'}: {exc}")
        return FetchResult(
            billing_units=tuple(results), errors=tuple(errors), waiting_provider=waiting
        )

    def download_document(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        document: DocumentRecord,
    ) -> bytes:
        self.check_environment(config, environment)
        family = self._family(Function.DOCUMENTS)
        base = self.base_url(config, environment, family)
        auth = self.auth_for(family, config, secrets, environment)
        with self._http(config, secrets, environment) as http:
            return bved.download_document(http, base, auth=auth, external_id=document.external_id)

    def acknowledge_document(
        self,
        *,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        environment: str,
        document: DocumentRecord,
    ) -> None:
        self.check_environment(config, environment)
        family = self._family(Function.DOCUMENTS)
        base = self.base_url(config, environment, family)
        auth = self.auth_for(family, config, secrets, environment)
        with self._http(config, secrets, environment) as http:
            bved.acknowledge_document(http, base, auth=auth, external_id=document.external_id)

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
        self.check_environment(config, environment)
        family = self._family(Function.BILLING_UNIT_DATA)
        base = self.base_url(config, environment, family)
        auth = self.auth_for(family, config, secrets, environment)
        with self._http(config, secrets, environment) as http:
            return bved.submit_setup(
                http,
                base,
                auth=auth,
                billing_unit=external_billing_unit,
                customer_number=customer_number,
                residential_units=residential_units,
                pm_number=None,
            )


def _write_certificate(cert_pem: str, key_pem: str) -> ClientCertificate:
    """PEM material from the encrypted secrets into private temporary files (httpx needs
    paths); removed again when the client closes."""
    directory = tempfile.mkdtemp(prefix="mhvp-mtls-")
    cert_path = os.path.join(directory, "client.crt")
    key_path = os.path.join(directory, "client.key")
    for path, content in ((cert_path, cert_pem), (key_path, key_pem)):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
    return ClientCertificate(cert_path=cert_path, key_path=key_path)


class _CleaningHttp(ProviderHttp):
    def __init__(self, *, certificate: ClientCertificate | None = None, **kwargs: Any) -> None:
        super().__init__(certificate=certificate, **kwargs)
        self._certificate = certificate

    def close(self) -> None:
        super().close()
        if self._certificate is not None:
            for path in (self._certificate.cert_path, self._certificate.key_path):
                with contextlib.suppress(OSError):
                    os.remove(path)
            with contextlib.suppress(OSError):
                os.rmdir(os.path.dirname(self._certificate.cert_path))
            self._certificate = None
