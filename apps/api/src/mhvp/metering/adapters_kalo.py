"""KALO / Kalorimeta adapter (stage 2, read paths).

Sources checked 26.09.2026: Q3 (developer portal: Nutzer-Management-API, Verbrauchsdaten-API,
Dokumenten-API for uVI, Dokumenten-API for DTA), its sub pages "Verbrauchsdaten-API" and
"Dokumenten-API": production base ``https://api.kalo.de/arge`` with ``/consumptions/v1/`` and
``/documents/v1/``; token endpoint ``https://meine.kalo.de/auth/realms/arge-api/protocol/
openid-connect/token`` (client credentials) or Basic Auth; header ``Accept: application/json``;
``GET /billingunits/{mscnumber}/consumptions/periods[/{period}]`` (9 digit mscnumber with
leading zeros); ``GET /documents/out?offset&limit``, ``/documents/out/count``,
``/documents/out/{documentid}/data``, ``PUT /documents/out/{documentid}/status``. Payloads follow
the bved files consumption-data 1.2.1 and documents 1.3 (Q7).

Not documented (blockers, see docs/integrations/messdienstleister.md): a test system URL (a
test connection therefore needs ``base_url`` and ``token_url`` from KALO and they must differ
from production), the body of ``PUT .../status`` on the KALO page (the bved 1.3 body is used),
billing unit data / billing result APIs (not implemented), and how ``resident`` references map
to a billing unit (documents without a ``billingunit`` reference go to clearing).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import urlsplit

from mhvp.metering.adapters_base import AdapterConfigError, BvedAdapterBase, Family
from mhvp.metering.providers import Function

PRODUCTION_BASE_URL = "https://api.kalo.de/arge"
PRODUCTION_OIDC_ENDPOINT = (  # public OpenID Connect endpoint (Q3), no credential
    "https://meine.kalo.de/auth/realms/arge-api/protocol/openid-connect/" + "token"
)
_PRODUCTION_HOSTS = frozenset({"api.kalo.de", "meine.kalo.de"})


class KaloAdapter(BvedAdapterBase):
    code = "kalo"
    spec_source = (
        "KALO Entwicklerportal Q3 (Verbrauchsdaten-API, Dokumenten-API, 26.09.2026) und bved "
        "OpenAPI consumption-data 1.2.1, documents 1.3 (Q7)"
    )
    spec_version = (
        "KALO ARGE v1 (consumptions/v1, documents/v1), bved 1.2.1 / 1.3, geprüft 26.09.2026"
    )
    implemented = frozenset({Function.CONSUMPTION, Function.DOCUMENTS})
    families: ClassVar[dict[Function, Family]] = {
        Function.CONSUMPTION: Family(
            Function.CONSUMPTION, ("oauth2", "basic"), "consumptions/v1", "KALO Verbrauchsdaten-API"
        ),
        Function.DOCUMENTS: Family(
            Function.DOCUMENTS, ("oauth2", "basic"), "documents/v1", "KALO Dokumenten-API"
        ),
    }

    def _root(self, config: Mapping[str, Any], environment: str) -> str:
        if environment == "production":
            return PRODUCTION_BASE_URL  # documented, never overridden by configuration
        url = config.get("base_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise AdapterConfigError(
                "Test-Basis-URL fehlt: KALO dokumentiert kein Testsystem; base_url muss von KALO "
                "genannt werden (nur https)."
            )
        if urlsplit(url).hostname in _PRODUCTION_HOSTS:
            raise AdapterConfigError("Testverbindung darf nicht auf das Produktionssystem zeigen.")
        return url

    def base_url(self, config: Mapping[str, Any], environment: str, family: Family) -> str:
        return self._root(config, environment).rstrip("/") + "/" + family.config_key

    def token_url(self, config: Mapping[str, Any], environment: str) -> str:
        if environment == "production":
            return PRODUCTION_OIDC_ENDPOINT
        url = config.get("token_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise AdapterConfigError("Test token_url fehlt (von KALO zu nennen, nur https).")
        if urlsplit(url).hostname in _PRODUCTION_HOSTS:
            raise AdapterConfigError("Testverbindung darf nicht das Produktions-Token nutzen.")
        return url
