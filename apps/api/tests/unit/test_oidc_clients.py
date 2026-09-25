import pytest

from mhvp.core.auth import oidc_clients
from mhvp.core.auth.oidc_clients import OidcClientError, validate_client_id, validate_redirect_uri


@pytest.mark.parametrize(
    "uri",
    [
        "https://status.example.org/oauth2/callback",
        "http://localhost:4180/oauth2/callback",
        "http://127.0.0.1/cb",
    ],
)
def test_redirect_uri_accepts_https_and_local_http(uri: str) -> None:
    assert validate_redirect_uri(uri) == uri


@pytest.mark.parametrize(
    "uri",
    [
        "http://status.example.org/oauth2/callback",
        "https://status.example.org/cb#fragment",
        "/oauth2/callback",
        "status.example.org/cb",
        "javascript:alert(1)",
    ],
)
def test_redirect_uri_rejects_insecure_or_relative(uri: str) -> None:
    with pytest.raises(OidcClientError):
        validate_redirect_uri(uri)


@pytest.mark.parametrize("client_id", ["status", "status-page.v2", "a1"])
def test_client_id_accepts_slugs(client_id: str) -> None:
    assert validate_client_id(client_id) == client_id


@pytest.mark.parametrize("client_id", ["", "S", "Status", "-status", "st atus", "a" * 101])
def test_client_id_rejects_other_forms(client_id: str) -> None:
    with pytest.raises(OidcClientError):
        validate_client_id(client_id)


def test_parser_collects_repeated_redirect_uris() -> None:
    args = oidc_clients.build_parser().parse_args(
        [
            "create",
            "--client-id",
            "status",
            "--name",
            "Statusseite",
            "--redirect-uri",
            "https://a.example.org/cb",
            "--redirect-uri",
            "https://b.example.org/cb",
        ]
    )
    assert args.command == "create"
    assert args.redirect_uris == ["https://a.example.org/cb", "https://b.example.org/cb"]
    assert args.public is False


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        oidc_clients.build_parser().parse_args([])
