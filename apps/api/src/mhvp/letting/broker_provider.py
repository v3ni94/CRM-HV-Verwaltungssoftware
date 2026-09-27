"""BrokerProvider (M28-01 stage 3): a small adapter interface for a portal/CRM broker
backend (FLOWFACT, Propstack, onOffice) so the router and the CRM never depend on a concrete
vendor. Every implementation maps exactly one documented operation to one call; an operation
with no verified, concrete endpoint contract raises `DocumentationRequiredError` instead of
guessing a URL, method or payload (rule 0.1.3, docs/plans/M28-makler.md).

Evidence checked 27.09.2026 (WebFetch, public pages only, no account, no SDK download):

- FLOWFACT (`developer.flowfact.com`): unreachable (HTTP 503). Prior finding (25.09.2026,
  docs/plans/M28-makler.md): the only documented contract is the private npm SDK
  `@flowfact/api-services` (token exchange via `admin-token-service`, then
  `entity-service`/`schema-service`/`search-service`/`multimedia-service`/
  `portal-management-service`); no public REST path or JSON body is documented anywhere this
  session could read. Not implemented.
- onOffice (`api.onoffice.de`): unreachable (HTTP 503) in this session. No concrete endpoint
  read. Not implemented.
- Propstack (`docs.propstack.de`): reachable, but only names operations in prose ("Erstellen
  und Aktualisieren von Objekten", "Anlegen und Aktualisieren von Kontakten", lead feedback
  "indem ein Kontakt angelegt und eine Notiz mit der Kontaktquellen-ID erstellt wird"); no
  concrete REST path, HTTP method or request body is given on the pages this session could
  read. Not implemented.

Every provider therefore currently raises `DocumentationRequiredError` for every operation.
This is intentional (rule 0.1.3: uncertainty is no basis for a fabricated call) and is not a
bug; a provider is switched on operation by operation only once an operator supplies the
concrete, citable documentation (endpoint, method, payload) for that operation, following the
`mhvp.integrations.lexoffice` pattern (one docstring per method naming the exact endpoint).

`FakeBrokerProvider` is a deterministic test double (no network) used by CRM and API tests to
exercise the router and CRM without a real account, per the shared test rule (fake provider).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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


class FlowfactBrokerProvider(_UndocumentedProvider):
    name = "flowfact"


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


def get_provider(name: str) -> BrokerProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise DocumentationRequiredError(name, "provider unbekannt")
    return cls()
