from fastapi.testclient import TestClient

from mhvp.core.auth.oidc import authorization_endpoint
from tests.conftest import make_settings
from tests.unit.helpers import app_with_checks

ISSUER = "https://api.example.org"


def test_discovery_points_browsers_to_the_crm_bridge() -> None:
    settings = make_settings(jwt_issuer=ISSUER, web_crm_url="https://crm.example.org/")
    with TestClient(app_with_checks(settings)) as client:
        body = client.get("/.well-known/openid-configuration").json()
    assert body["issuer"] == ISSUER
    assert body["authorization_endpoint"] == "https://crm.example.org/oidc/authorize"
    assert body["token_endpoint"] == f"{ISSUER}/api/v1/oidc/token"
    assert body["jwks_uri"] == f"{ISSUER}/api/v1/oidc/jwks"
    assert body["code_challenge_methods_supported"] == ["S256"]


def test_discovery_without_crm_url_keeps_the_api_endpoint() -> None:
    settings = make_settings(jwt_issuer=ISSUER, web_crm_url=None)
    assert authorization_endpoint(settings) == f"{ISSUER}/api/v1/oidc/authorize"
    with TestClient(app_with_checks(settings)) as client:
        body = client.get("/.well-known/openid-configuration").json()
    assert body["authorization_endpoint"] == f"{ISSUER}/api/v1/oidc/authorize"
