"""BPD failure of the dialog initialisation maps to MHVP-BANK-0014 with an explanation."""

from mhvp.banking import fints


class FinTSClientError(Exception):
    pass


def test_bpd_failure_explains_registration_delay() -> None:
    exc = FinTSClientError(
        "Error during dialog initialization, could not fetch BPD. Please check that you "
        "passed the correct bank identifier to the HBCI URL of the correct bank."
    )
    problem = fints.problem_for_exception(exc)
    assert problem.error.code == "MHVP-BANK-0014"
    assert "Produktregistrierung" in str(problem.detail)
    assert "Bankleitzahl" in str(problem.detail)
