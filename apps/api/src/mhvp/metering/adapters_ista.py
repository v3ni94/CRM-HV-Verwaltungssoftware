"""ista adapter (stage 2, read paths).

Sources checked 26.09.2026: Q1 (API families: Billing Unit Data, Billing Input, Billing Results,
On-Site Roles 2.0, ARGE EED Consumption Data, ARGE Document Webservices), Q8 (Billing Unit Data:
asynchronous, OAuth 2, filters ``from``, ``status``, ``limit``, ``offset``, at most 100 entries),
Q9 (FAQ: "Alle neueren Schnittstellen (bved 2026) sind mit OAuth2 Verfahren gesichert. Ältere
Schnittstellen (bved/ARGE 3.10) und document webservices ... werden mit Basic Auth gesichert";
test systems need an mTLS client certificate, production of the new bved APIs does not; "Die
Endpunkte sind Schnittstellenabhängig und werden bei der Einrichtung ihres Zugangs
übermittelt"), bved OpenAPI files 1.0.2 / 1.0.3 / 1.2.1 / 1.3 (Q6, Q7).

Consequences: no base URL and no token URL is hard coded; both come from the connection
configuration (``base_urls`` per family, ``token_url``) that ista transmits at onboarding.
Authentication per family: OAuth 2 client credentials for billing unit data and billing
result, Basic for the ARGE document web service and the EED consumption data (older ARGE
family per Q9; OAuth 2 selectable per family if ista confirms it for the account).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from mhvp.metering.adapters_base import AdapterConfigError, BvedAdapterBase, Family
from mhvp.metering.providers import Function


class IstaAdapter(BvedAdapterBase):
    code = "ista"
    spec_source = (
        "ista Developer Portal Q1/Q8/Q9 (26.09.2026) und bved OpenAPI: billing-unit-data 1.0.2, "
        "billing-result 1.0.3, consumption-data 1.2.1, documents 1.3 (Q6, Q7)"
    )
    spec_version = (
        "bved 1.0.2 / 1.0.3 / 1.2.1 / 1.3, geprüft 26.09.2026; on-site-roles 2.0.2 und "
        "billing-input 1.0.3, geprüft 27.09.2026"
    )
    implemented = frozenset(
        {
            Function.BILLING_UNIT_DATA,
            Function.BILLING_RESULT,
            Function.CONSUMPTION,
            Function.DOCUMENTS,
            Function.ROLES,
            Function.BILLING_INPUT,
        }
    )
    families: ClassVar[dict[Function, Family]] = {
        Function.BILLING_UNIT_DATA: Family(
            Function.BILLING_UNIT_DATA,
            ("oauth2",),
            "billing_unit_data",
            "bved billing-unit-data 1.0.2",
        ),
        Function.BILLING_RESULT: Family(
            Function.BILLING_RESULT, ("oauth2",), "billing_result", "bved billing-result 1.0.3"
        ),
        Function.CONSUMPTION: Family(
            Function.CONSUMPTION, ("basic", "oauth2"), "consumption", "ARGE consumption-data 1.2.1"
        ),
        Function.DOCUMENTS: Family(
            Function.DOCUMENTS, ("basic", "oauth2"), "documents", "bved/ARGE documents 1.3 (3.10)"
        ),
        # Write families (section 12; Q10, Q11 and the bved zip files checked 27.09.2026).
        # Offered only through the controlled transmission workflow of the service layer.
        Function.ROLES: Family(Function.ROLES, ("oauth2",), "roles", "bved on-site-roles 2.0.2"),
        Function.BILLING_INPUT: Family(
            Function.BILLING_INPUT, ("oauth2",), "billing_input", "bved billing-input 1.0.3"
        ),
    }

    def base_url(self, config: Mapping[str, Any], environment: str, family: Family) -> str:
        urls = config.get("base_urls")
        url = urls.get(family.config_key) if isinstance(urls, dict) else None
        if not isinstance(url, str) or not url.startswith("https://"):
            raise AdapterConfigError(
                f"Basis-URL für {family.config_key} fehlt (wird von ista bei der Einrichtung "
                "übermittelt, Q9); nur https."
            )
        return url

    def token_url(self, config: Mapping[str, Any], environment: str) -> str:
        url = config.get("token_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise AdapterConfigError(
                "OAuth2 token_url fehlt (von ista übermittelt, Q9); nur https."
            )
        return url

    def certificate_required(self, environment: str) -> bool:
        # Q9: client certificate (mTLS) in the test access, not in production of the new APIs.
        return environment == "test"
