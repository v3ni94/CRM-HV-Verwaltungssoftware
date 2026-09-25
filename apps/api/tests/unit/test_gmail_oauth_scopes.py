"""Unit-Test: OAuth-Consent-URL je Zweck (mail vs. drive, M20-01 / Google-Drive-OAuth 1.9.1)."""

from mhvp.communication.gmail import SCOPES, authorization_url
from tests.conftest import make_settings


def test_authorization_url_default_purpose_uses_mail_scopes() -> None:
    settings = make_settings(api_public_url="https://immoware.example.test")
    url = authorization_url("client-id", settings, "state123")
    assert "scope=" in url
    assert "gmail.readonly" in url
    assert "drive.file" not in url


def test_authorization_url_drive_purpose_uses_drive_file_scope() -> None:
    settings = make_settings(api_public_url="https://immoware.example.test")
    url = authorization_url("client-id", settings, "state123", purpose="drive")
    assert "drive.file" in url
    assert "gmail.readonly" not in url
    # Redirect-URI bleibt für beide Zwecke identisch (ein einziger Rückruf bei Google hinterlegt).
    assert "oauth%2Fgoogle%2Fcallback" in url or "oauth/google/callback" in url


def test_mail_scopes_unchanged() -> None:
    assert "gmail.readonly" in SCOPES
    assert "gmail.send" in SCOPES


def test_mail_scopes_include_modify_for_archive_on_done() -> None:
    # M20-03 "Erledigt archiviert Mail" (operator 25.09.2026): gmail.readonly allein kann keine
    # Labels ändern, daher muss gmail.modify im Consent enthalten sein.
    assert "gmail.modify" in SCOPES
