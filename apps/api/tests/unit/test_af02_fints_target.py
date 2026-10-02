"""AF02 GAE-25: the FinTS target address is checked after name resolution (no network: the
resolver is injected)."""

import socket
from typing import Any

import pytest

from mhvp.banking import fints
from mhvp.banking.tasks import is_transient_ebics_error, retry_countdown
from mhvp.core.problems import ProblemError


def _resolver(*addresses: str) -> Any:
    def resolve(host: str, port: int, type: int = 0) -> list[Any]:
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET6 if ":" in a else socket.AF_INET, type, 6, "", (a, port))
            for a in addresses
        ]

    return resolve


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.0.10",
        "172.16.5.5",
        "169.254.169.254",
        "100.64.0.1",
        "::1",
        "fd00::1",
        "fe80::1%eth0",
        "::ffff:10.0.0.1",
        "0.0.0.0",  # noqa: S104
        "224.0.0.1",
    ],
)
def test_internal_addresses_are_refused(address: str) -> None:
    with pytest.raises(ProblemError) as err:
        fints.check_fints_target("https://fints.bank.example/fints", _resolver(address))
    assert err.value.error.code == "MHVP-BANK-0062"


def test_public_address_passes_and_mixed_answer_is_refused() -> None:
    fints.check_fints_target("https://fints.bank.example:8443/x", _resolver("93.184.216.34"))
    with pytest.raises(ProblemError):
        fints.check_fints_target(
            "https://fints.bank.example/x", _resolver("93.184.216.34", "10.0.0.1")
        )


def test_missing_host_and_unresolvable_name() -> None:
    with pytest.raises(ProblemError):
        fints.check_fints_target(None, _resolver("93.184.216.34"))

    def fail(*_a: Any, **_k: Any) -> Any:
        raise socket.gaierror("no such host")

    fints.check_fints_target("https://unbekannt.bank.example/x", fail)


def test_guard_runs_in_front_of_the_real_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fints, "RESOLVER", _resolver("127.0.0.1"))
    monkeypatch.setattr(fints, "CLIENT_FACTORY", fints._client_class)
    creds = fints.Credentials(
        blz="12345678",
        fints_url="https://fints.bank.example/x",
        login="u",
        pin="p",
        product_id="X",
    )
    with pytest.raises(ProblemError) as err:
        fints._build_client(creds, None)
    assert err.value.error.code == "MHVP-BANK-0062"


def test_ebics_retry_policy() -> None:
    assert is_transient_ebics_error("MHVP-BANK-0056")
    assert not is_transient_ebics_error("MHVP-BANK-0050")
    assert not is_transient_ebics_error(None)
    assert [retry_countdown(i) for i in range(3)] == [60, 120, 240]
