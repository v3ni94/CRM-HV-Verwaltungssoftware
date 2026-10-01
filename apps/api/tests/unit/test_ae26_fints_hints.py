"""AE26 / M11-01: German check steps for MHVP-BANK-0010 (locked) and MHVP-BANK-0013 (bank not
reachable), network failures of the requests library, the manual FinTS address (validation,
resolution against the institute list). Operator finding of 01.10.2026: python-fints reported
"Account is temporarily locked." in English without a next step."""

from __future__ import annotations

import pytest
import requests

from mhvp.banking import fints as fints_mod
from mhvp.core.problems import ErrorCodes
from tests import fints_fake as fake

NO_DASH = (chr(0x2013), chr(0x2014), " - ")


def _assert_plain_german(text: str) -> None:
    for dash in NO_DASH:
        assert dash not in text


def test_temporary_auth_error_becomes_german_check_steps_without_the_english_text() -> None:
    problem = fints_mod.problem_for_exception(
        fake.FinTSClientTemporaryAuthError("Account is temporarily locked.")
    )
    assert problem.error is ErrorCodes.FINTS_ACCOUNT_LOCKED
    assert problem.error.code == "MHVP-BANK-0010"
    detail = str(problem.detail)
    assert "temporarily" not in detail
    assert "Rückmeldecode 3938" in detail
    for step in ("Online-Banking", "FinTS", "Anmeldename", "entsperren", "PIN"):
        assert step in detail
    # five numbered steps, one per line
    lines = detail.splitlines()
    assert [line[:2] for line in lines[1:]] == ["1.", "2.", "3.", "4.", "5."]
    _assert_plain_german(detail)


@pytest.mark.parametrize("code", ["3938", "9931"])
def test_locked_return_codes_quote_the_bank_text_and_give_the_same_steps(code: str) -> None:
    problem = fints_mod.problem_for_code(code, "Zugang gesperrt")
    assert problem.error is ErrorCodes.FINTS_ACCOUNT_LOCKED
    detail = str(problem.detail)
    assert f"Rückmeldecode {code}" in detail
    assert "Meldung der Bank: Zugang gesperrt" in detail
    assert "Online-Banking" in detail
    assert "Anmeldename" in detail
    _assert_plain_german(detail)


def test_pin_and_other_codes_keep_their_short_detail() -> None:
    assert str(fints_mod.problem_for_code("9942", "PIN falsch").detail) == (
        "Rückmeldecode 9942: PIN falsch"
    )
    assert fints_mod.problem_for_code("9050").error is ErrorCodes.FINTS_BANK_REJECTED


URL = "https://hbci-pintan.gad.de/cgi-bin/hbciservlet"


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectionError("HTTPSConnectionPool(host='x', port=443): refused"),
        requests.exceptions.SSLError("certificate verify failed"),
        requests.exceptions.ConnectTimeout("timed out"),
        requests.exceptions.ReadTimeout("read timed out"),
        TimeoutError("timed out"),
        ConnectionRefusedError("refused"),
    ],
)
def test_network_failures_name_the_host_and_give_check_steps(exc: BaseException) -> None:
    problem = fints_mod.problem_for_exception(exc, fints_url=URL)
    assert problem.error is ErrorCodes.FINTS_UNAVAILABLE
    assert problem.error.code == "MHVP-BANK-0013"
    detail = str(problem.detail)
    assert "unter hbci-pintan.gad.de" in detail
    for step in ("Bankfusion", "FinTS-Adresse", "Firewall", "Technische Meldung"):
        assert step in detail
    _assert_plain_german(detail)


def test_connection_error_wrapped_by_python_fints_in_a_dialog_error_is_unreachable() -> None:
    """python-fints turns every non FinTS exception of the dialog init into a dialog init
    error; the network cause must still lead to MHVP-BANK-0013."""

    class FinTSDialogInitError(Exception):
        pass

    try:
        try:
            raise requests.exceptions.ConnectionError("Name or service not known")
        except requests.exceptions.ConnectionError as cause:
            raise FinTSDialogInitError("Couldn't establish dialog with bank") from cause
    except FinTSDialogInitError as wrapped:
        problem = fints_mod.problem_for_exception(wrapped, fints_url="https://fints1.atruvia.de/x")
    assert problem.error is ErrorCodes.FINTS_UNAVAILABLE
    assert "unter fints1.atruvia.de" in str(problem.detail)


def test_unavailable_without_url_and_long_technical_text_is_trimmed() -> None:
    problem = fints_mod.problem_for_exception(ConnectionError("x" * 900))
    detail = str(problem.detail)
    assert "unter der hinterlegten FinTS-Adresse" in detail
    assert len(detail) < 1500


def test_a_dialog_error_without_network_cause_is_not_called_unreachable() -> None:
    problem = fints_mod.problem_for_exception(RuntimeError("boom"))
    assert problem.error is ErrorCodes.FINTS_BANK_REJECTED


def test_pin_error_stays_a_pin_error_even_with_a_network_context() -> None:
    def fail() -> None:
        try:
            raise ConnectionError("earlier")
        except ConnectionError:
            raise fake.FinTSClientPINError("PIN wrong?")  # noqa: B904

    with pytest.raises(fake.FinTSClientPINError) as caught:
        fail()
    assert fints_mod.problem_for_exception(caught.value).error is ErrorCodes.FINTS_PIN_REJECTED


# --- manual address ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://fints1.atruvia.de/cgi-bin/hbciservlet",
            "https://fints1.atruvia.de/cgi-bin/hbciservlet",
        ),
        (
            "  HTTPS://FinTS.Example-Bank.DE:443/Fints30  ",
            "https://fints.example-bank.de:443/Fints30",
        ),
        ("https://banking.example.de", "https://banking.example.de"),
        ("https://xn--bnk-7qa.example.de/hbci", "https://xn--bnk-7qa.example.de/hbci"),
    ],
)
def test_manual_url_accepted_and_normalised(raw: str, expected: str) -> None:
    assert fints_mod.validate_manual_fints_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "http://fints.example.de/hbci",
        "ftp://fints.example.de/hbci",
        "fints.example.de/hbci",
        "https://",
        "https://user:pw@fints.example.de/hbci",
        "https://fints.example.de@evil.example/hbci",
        "https://127.0.0.1/hbci",
        "https://10.0.0.5:8443/hbci",
        "https://[::1]/hbci",
        "https://localhost/hbci",
        "https://bank/hbci",
        "https://bank.local/hbci",
        "https://db.internal/hbci",
        "https://nas.fritz.box.home.arpa/hbci",
        "https://999.999.999.999/hbci",
        "https://fints.example.de:99999/hbci",
        "https://fints.example.de/hbci#frag",
        "https://fints.example.de/a b",
        "https://-bad-.example.de/hbci",
        "https://fints..example.de/hbci",
        "https://fints.example.de/" + "a" * 300,
    ],
)
def test_manual_url_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match=r"FinTS-Adresse|Port"):
        fints_mod.validate_manual_fints_url(raw)


def test_manual_url_messages_are_german_without_dashes() -> None:
    for raw in ("http://x.example.de", "https://127.0.0.1", "https://a.local"):
        with pytest.raises(ValueError, match=r"FinTS-Adresse") as caught:
            fints_mod.validate_manual_fints_url(raw)
        _assert_plain_german(str(caught.value))


def test_resolution_prefers_manual_then_current_list_then_stored() -> None:
    stored_legacy = "https://hbci-pintan.gad.de/cgi-bin/hbciservlet"
    manual = "https://fints.volksbank-im-westen.example.de/hbci"
    # manual entry always wins
    assert fints_mod.resolve_fints_url("39061981", stored_legacy, manual) == manual
    # a connection created with the shut down legacy address is repaired by the current list
    assert fints_mod.resolve_fints_url("39061981", stored_legacy) == (
        "https://fints1.atruvia.de/cgi-bin/hbciservlet"
    )
    assert fints_mod.list_fints_url("39061981") == "https://fints1.atruvia.de/cgi-bin/hbciservlet"
    # unknown BLZ: the address stored at creation stays
    assert fints_mod.resolve_fints_url("00000000", "https://x.example.de/f") == (
        "https://x.example.de/f"
    )
    assert fints_mod.list_fints_url("00000000") is None


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://FinTS1.Atruvia.de/cgi-bin/hbciservlet", "fints1.atruvia.de"),
        ("https://fints.example.de:8443/x", "fints.example.de"),
        ("https://u:p@fints.example.de/x", "fints.example.de"),
        ("", None),
        (None, None),
    ],
)
def test_fints_host(url: str | None, host: str | None) -> None:
    assert fints_mod.fints_host(url) == host


def test_pin_and_sca_errors_of_the_library_are_shown_in_german() -> None:
    pin = fints_mod.problem_for_exception(
        fake.FinTSClientPINError("Error during dialog initialization, PIN wrong?")
    )
    assert pin.error is ErrorCodes.FINTS_PIN_REJECTED
    assert "PIN wrong" not in str(pin.detail)
    assert "Online-Banking" in str(pin.detail)

    class FinTSSCARequiredError(Exception):
        pass

    sca = fints_mod.problem_for_exception(
        FinTSSCARequiredError("This operation requires strong customer authentication.")
    )
    assert sca.error is ErrorCodes.FINTS_SCA_REQUIRED
    assert "strong customer" not in str(sca.detail)
    assert "Erneut freigeben" in str(sca.detail)
    _assert_plain_german(str(pin.detail) + str(sca.detail))
