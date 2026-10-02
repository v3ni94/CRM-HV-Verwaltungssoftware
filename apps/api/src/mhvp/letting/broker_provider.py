"""BrokerProvider (M28-01 stage 3): a small adapter interface for a portal/CRM broker
backend (FLOWFACT, Propstack, onOffice) so the router and the CRM never depend on a concrete
vendor. Every implementation maps exactly one documented operation to one call; an operation
with no verified, concrete endpoint contract raises `DocumentationRequiredError` instead of
guessing a URL, method or payload (rule 0.1.3, docs/plans/M28-makler.md).

FLOWFACT status, corrected 29.09.2026 (see docs/rules/M28-02.md): the 27.09.2026 note above
concluded "not implemented" from public pages alone (developer.flowfact.com was unreachable
that session). That conclusion was wrong: `v3ni94/FLOWFACTxHVM`, the operator's production
Laravel application against FLOWFACT, has a working, account-verified connector
(`docs/flowfact-api.md`, `docs/connector.md` in that repo, endpoints read from the private npm
SDK `@flowfact/api-services` and confirmed against a real account 21.09.2026). This module's
`FlowfactBrokerProvider` now implements `create_or_update_listing` from that verified contract
(Cognito token exchange, `entity-service`, `search-service`). `set_status` and
`fetch_prospects` stay undocumented for FLOWFACT too: the `BrokerProvider` interface does not
carry the schema name an existing entity lives in, which both operations need (see
docs/rules/M28-02.md, open point).

- onOffice (`api.onoffice.de`): unreachable (HTTP 503) in the 27.09.2026 session. No concrete
  endpoint read. Not implemented.
- Propstack (`docs.propstack.de`): reachable, but only names operations in prose ("Erstellen
  und Aktualisieren von Objekten", "Anlegen und Aktualisieren von Kontakten", lead feedback
  "indem ein Kontakt angelegt und eine Notiz mit der Kontaktquellen-ID erstellt wird"); no
  concrete REST path, HTTP method or request body is given on the pages that session could
  read. Not implemented.

onOffice and Propstack still raise `DocumentationRequiredError` for every operation
(rule 0.1.3: uncertainty is no basis for a fabricated call); a provider is switched on
operation by operation only once an operator supplies the concrete, citable documentation
(endpoint, method, payload) for that operation, following the `mhvp.integrations.lexoffice`
pattern (one docstring per method naming the exact endpoint).

`FakeBrokerProvider` is a deterministic test double (no network) used by CRM and API tests to
exercise the router and CRM without a real account, per the shared test rule (fake provider).
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from mhvp.core.money import json_number

FLOWFACT_BASE_URL = "https://api.production.cloudios.flowfact-prod.cloud"
_FLOWFACT_TOKEN_PATH = "/admin-token-service/public/adminUser/authenticate"  # noqa: S105 (path, not a secret)


class DocumentationRequiredError(RuntimeError):
    """Raised instead of guessing an endpoint. `operation` and `provider` identify what is
    missing so the router can turn this into a clear 501 problem response."""

    def __init__(self, provider: str, operation: str) -> None:
        self.provider = provider
        self.operation = operation
        super().__init__(
            f"{provider}: keine belegte Dokumentation für '{operation}' (Regel 0.1.3). "
            "Der Betreiber muss die konkrete Schnittstelle (Endpunkt, Methode, Datenformat) "
            "vorlegen, bevor diese Operation umgesetzt wird."
        )


class BrokerUpstreamError(RuntimeError):
    """A configured provider rejected or failed a call. The message is safe to store: never
    an access key or a session token (see FlowfactBrokerProvider._scrub)."""


class BrokerAmbiguousMatchError(RuntimeError):
    """Search before create found more than one match at the provider; manual review is
    required instead of guessing which one to update (mirrors FLOW Pruefbericht 2026-09-11
    Befund 3)."""


@dataclass(frozen=True)
class BrokerListingPayload:
    """Fields passed to a provider for create/update; the mapping to the provider's own
    schema belongs in that provider's implementation once documented, never here."""

    external_ref: str
    title: str
    kind: str
    object_type: str
    price: str | None
    living_area_sqm: str | None
    rooms: str | None
    status: str
    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str = "DE"


@dataclass(frozen=True)
class BrokerListingResult:
    provider_entity_id: str
    status: str


@dataclass(frozen=True)
class BrokerProspect:
    """One interested-party feedback row read back from the provider."""

    provider_lead_id: str
    listing_provider_entity_id: str
    name: str | None
    email: str | None
    phone: str | None
    message: str | None
    received_at: str | None


class BrokerProvider(ABC):
    """Adapter interface (M28-01 stage 3). Every method maps to exactly one operation named
    in docs/plans/M28-makler.md: create/update a listing, read/set its status, and read back
    prospect feedback. No method here ever posts money or approves anything on its own
    (rule 0.1.6); it only exchanges listing and lead data."""

    name: str

    @abstractmethod
    def create_or_update_listing(self, payload: BrokerListingPayload) -> BrokerListingResult:
        """Idempotent create-or-update of one listing at the provider, keyed by
        `payload.external_ref`."""

    @abstractmethod
    def set_status(self, provider_entity_id: str, status: str) -> BrokerListingResult:
        """Change the listing's status at the provider (e.g. published/withdrawn)."""

    @abstractmethod
    def fetch_prospects(self, provider_entity_id: str) -> list[BrokerProspect]:
        """Read back interested-party feedback for one listing (never written by the CRM;
        the provider is the source, the CRM only stores what comes back as a `Prospect`)."""


class _UndocumentedProvider(BrokerProvider):
    """Base for a named provider with no verified endpoint contract yet (see module
    docstring). Every operation raises `DocumentationRequiredError`."""

    def create_or_update_listing(self, payload: BrokerListingPayload) -> BrokerListingResult:
        raise DocumentationRequiredError(self.name, "create_or_update_listing")

    def set_status(self, provider_entity_id: str, status: str) -> BrokerListingResult:
        raise DocumentationRequiredError(self.name, "set_status")

    def fetch_prospects(self, provider_entity_id: str) -> list[BrokerProspect]:
        raise DocumentationRequiredError(self.name, "fetch_prospects")


def _scrub(message: str, *secrets: str | None) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    return message


def _cognito_expiry_seconds(token: str) -> int:
    """TTL from the JWT `exp` claim minus a safety margin, else a conservative fallback
    (mirrors FLOW `CognitoTokenCache::gueltigkeitSekunden`)."""
    try:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode((payload_segment + padding).encode()))
        exp = int(payload["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        return 1500
    remaining = exp - int(time.time())
    return 1 if remaining <= 0 else max(60, remaining - 60)


class FlowfactBrokerProvider(BrokerProvider):
    """FLOWFACT via the verified contract from `v3ni94/FLOWFACTxHVM` (module docstring above).
    `access_key` is the FLOWFACT platform token (itself not a call token: it is exchanged for
    a short lived Cognito token first). `settings` carries FLOWFACT specific configuration the
    generic `BrokerTenantConfig` has no column for: `schema_rental` and `schema_sale`, the
    FLOWFACT schema name to use for each listing kind (never guessed, set by the operator
    after loading the account's schemas)."""

    name = "flowfact"

    def __init__(
        self,
        *,
        access_key: str | None = None,
        settings: dict[str, Any] | None = None,
        http: httpx.Client | None = None,
        base_url: str = FLOWFACT_BASE_URL,
    ) -> None:
        self._access_key = access_key
        self._settings = settings or {}
        self._http = http or httpx.Client(timeout=30.0)
        self._owns_http = http is None
        self._base = base_url.rstrip("/")

    def __del__(self) -> None:
        if getattr(self, "_owns_http", False):
            self._http.close()

    def _schema_for(self, kind: str) -> str | None:
        key = "schema_rental" if kind == "rental" else "schema_sale"
        value = self._settings.get(key)
        return value if isinstance(value, str) and value.strip() else None

    def _cognito_token(self) -> str:
        if not self._access_key:
            raise DocumentationRequiredError(self.name, "create_or_update_listing")
        response = self._http.get(
            self._base + _FLOWFACT_TOKEN_PATH, headers={"token": self._access_key}
        )
        if response.status_code != 200:
            raise BrokerUpstreamError(
                _scrub(
                    f"Zugangsschluessel-Tausch fehlgeschlagen: HTTP {response.status_code}",
                    self._access_key,
                )
            )
        token = response.text.strip().strip('"')
        if not token:
            raise BrokerUpstreamError("Zugangsschluessel-Tausch lieferte kein Cognito-Token.")
        return token

    def _headers(self) -> dict[str, str]:
        return {"cognitoToken": self._cognito_token()}

    def _raise_for(self, response: httpx.Response, what: str) -> None:
        if response.status_code >= 400:
            raise BrokerUpstreamError(
                _scrub(f"{what}: HTTP {response.status_code}", self._access_key)
            )

    def create_or_update_listing(self, payload: BrokerListingPayload) -> BrokerListingResult:
        schema = self._schema_for(payload.kind)
        if schema is None:
            raise DocumentationRequiredError(self.name, "create_or_update_listing")
        entity_id = self._find_existing(schema, payload.external_ref)
        if entity_id is None:
            entity_id = self._create(schema, payload)
        return BrokerListingResult(provider_entity_id=entity_id, status="synced")

    def _find_existing(self, schema: str, external_ref: str) -> str | None:
        """Search before create for idempotency (FLOW Pruefbericht 2026-09-11 Befund 3): a
        single exact match on `identifier` is reused, more than one match is an error."""
        body = {
            "target": "ENTITY",
            "fetch": [],
            "aggregations": [],
            "conditions": [
                {
                    "type": "HASFIELDWITHVALUE",
                    "field": "identifier",
                    "value": external_ref,
                    "operator": "EQUALS",
                }
            ],
            "distinct": False,
            "joins": [],
            "sorts": [],
            "schemaIds": [],
        }
        response = self._http.post(
            f"{self._base}/search-service/schemas/{schema}",
            json=body,
            params={"page": 1, "size": 2, "withCount": "true"},
            headers=self._headers(),
        )
        self._raise_for(response, "Suche vor dem Anlegen")
        data = response.json() if response.content else {}
        entries = [
            e
            for e in (data.get("entries") if isinstance(data, dict) else None) or []
            if isinstance(e, dict)
        ]
        matches = [
            e for e in entries if (e.get("identifier") or {}).get("values") == [external_ref]
        ]
        if len(matches) > 1:
            raise BrokerAmbiguousMatchError(
                "Mehrere Objekte mit dieser Kennung in FLOWFACT, bitte manuell klären."
            )
        if not matches:
            return None
        entity_id = matches[0].get("id") or (matches[0].get("_metadata") or {}).get("id")
        return str(entity_id) if entity_id else None

    def _create(self, schema: str, payload: BrokerListingPayload) -> str:
        """`entity-service` create, `x-ff-version: 2` (confirmed contract). Only field names
        confirmed in `docs/connector.md` of the FLOW repo are sent: `headline`, `identifier`,
        `rent`/`purchaseprice`, `livingarea`, `rooms`, `addresses`. Fields without a confirmed
        name (description, deposit, additional costs, estatetype, ...) stay out (rule 0.1.3)."""
        fields: dict[str, list[Any]] = {
            "identifier": [payload.external_ref],
            "headline": [payload.title],
        }
        if payload.price is not None:
            price_field = "rent" if payload.kind == "rental" else "purchaseprice"
            fields[price_field] = [json_number(Decimal(payload.price))]
        if payload.living_area_sqm is not None:
            fields["livingarea"] = [json_number(Decimal(payload.living_area_sqm))]
        if payload.rooms is not None:
            fields["rooms"] = [json_number(Decimal(payload.rooms))]
        if payload.street or payload.postal_code or payload.city:
            fields["addresses"] = [
                {
                    "type": "private",
                    "street": " ".join(p for p in (payload.street, payload.house_number) if p)
                    or None,
                    "zipcode": payload.postal_code,
                    "city": payload.city,
                    "country": "Deutschland" if payload.country == "DE" else payload.country,
                }
            ]
        body = {name: {"values": values} for name, values in fields.items()}
        headers = self._headers()
        headers["x-ff-version"] = "2"
        response = self._http.post(
            f"{self._base}/entity-service/schemas/{schema}", json=body, headers=headers
        )
        self._raise_for(response, "Anlegen")
        entity_id = self._extract_id(response)
        if entity_id is None:
            raise BrokerUpstreamError(
                "FLOWFACT hat die Entitaet angelegt, aber keine ID zurueckgegeben."
            )
        return entity_id

    @staticmethod
    def _extract_id(response: httpx.Response) -> str | None:
        if not response.content:
            return None
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip().strip('"')
            return text or None
        if isinstance(data, str):
            return data.strip() or None
        if isinstance(data, dict):
            for key in ("id", "entityId"):
                value = data.get(key)
                if isinstance(value, str | int) and str(value):
                    return str(value)
            metadata = data.get("_metadata")
            if isinstance(metadata, dict) and metadata.get("id"):
                return str(metadata["id"])
        return None

    def set_status(self, provider_entity_id: str, status: str) -> BrokerListingResult:
        # The BrokerProvider interface does not carry the schema an existing entity lives in
        # (docs/rules/M28-02.md open point); without it entity-service/schemas/{schema}/... is
        # not addressable, so this stays undocumented rather than guessing a schema.
        raise DocumentationRequiredError(self.name, "set_status")

    def fetch_prospects(self, provider_entity_id: str) -> list[BrokerProspect]:
        # portal-management-service / inquiry feedback is out of scope for stage 3 (push
        # only, docs/plans/M28-makler.md).
        raise DocumentationRequiredError(self.name, "fetch_prospects")


class PropstackBrokerProvider(_UndocumentedProvider):
    name = "propstack"


class OnOfficeBrokerProvider(_UndocumentedProvider):
    name = "onoffice"


@dataclass
class FakeBrokerProvider(BrokerProvider):
    """Deterministic in-memory test double, no network (shared test rule "Tests mit
    Fake-Provider"). Used only by tests and by a tenant's explicit "Testmodus" choice, never
    a substitute for a real provider in production."""

    name: str = "fake"
    _listings: dict[str, BrokerListingResult] = field(default_factory=dict)
    _prospects: dict[str, list[BrokerProspect]] = field(default_factory=dict)

    def create_or_update_listing(self, payload: BrokerListingPayload) -> BrokerListingResult:
        entity_id = self._listings.get(payload.external_ref)
        result = BrokerListingResult(
            provider_entity_id=entity_id.provider_entity_id if entity_id else str(uuid.uuid4()),
            status="synced",
        )
        self._listings[payload.external_ref] = result
        return result

    def set_status(self, provider_entity_id: str, status: str) -> BrokerListingResult:
        return BrokerListingResult(provider_entity_id=provider_entity_id, status=status)

    def fetch_prospects(self, provider_entity_id: str) -> list[BrokerProspect]:
        return list(self._prospects.get(provider_entity_id, []))

    def seed_prospect(self, provider_entity_id: str, prospect: BrokerProspect) -> None:
        self._prospects.setdefault(provider_entity_id, []).append(prospect)


PROVIDERS: dict[str, type[BrokerProvider]] = {
    "flowfact": FlowfactBrokerProvider,
    "propstack": PropstackBrokerProvider,
    "onoffice": OnOfficeBrokerProvider,
}


def get_provider(
    name: str, *, api_key: str | None = None, settings: dict[str, Any] | None = None
) -> BrokerProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise DocumentationRequiredError(name, "provider unbekannt")
    if cls is FlowfactBrokerProvider:
        return FlowfactBrokerProvider(access_key=api_key, settings=settings)
    return cls()
