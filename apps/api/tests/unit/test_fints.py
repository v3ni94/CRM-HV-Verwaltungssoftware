"""FinTS/HBCI PIN/TAN (M11-01 addendum 27.09.2026): institute search, IBAN to BLZ, the
pause/resume TAN state machine (init TAN, wrong TAN, decoupled polling, TAN in the middle of
the work), PIN/lock mapping to registered problem codes and the MT940 object mapping with a
stable dedup key. Fake client only (`tests.fints_fake`), never a live bank."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from mhvp.banking import fints as fints_mod
from mhvp.core.problems import ErrorCodes, ProblemError
from tests import fints_fake as fake

CREDS = fints_mod.Credentials(
    blz="38250110",
    fints_url="https://banking-rl5.s-fints-pt-rl.de/fints30",
    login="user",
    pin=fake.GOOD_PIN,
    product_id="ABCDEF0123456789ABCDEF0123",
)


@pytest.fixture(autouse=True)
def _fake(monkeypatch: pytest.MonkeyPatch) -> None:
    fake.install(monkeypatch)


# --- institutes ---------------------------------------------------------------------------


def test_institute_list_loads_and_marks_connectable() -> None:
    rows = fints_mod.load_institutes()
    assert len(rows) > 4000
    connectable = [r for r in rows if r.connectable]
    assert len(connectable) > 2500
    inst = fints_mod.find_institute("38250110")
    assert inst is not None
    assert inst.name == "Kreissparkasse Euskirchen"
    assert inst.fints_url == "https://banking-rl5.s-fints-pt-rl.de/fints30"
    assert inst.bic == "WELADED1EUS"
    not_connectable = fints_mod.find_institute("25440047")
    assert not_connectable is not None
    assert not not_connectable.connectable


@pytest.mark.parametrize(
    ("iban", "blz"),
    [
        ("DE89 3704 0044 0532 0130 00", "37040044"),
        ("de89370400440532013000", "37040044"),
        ("FR7630006000011234567890189", None),
        ("DE8937040044", None),
        ("", None),
    ],
)
def test_blz_from_iban(iban: str, blz: str | None) -> None:
    assert fints_mod.blz_from_iban(iban) == blz


def test_search_by_blz_bic_iban_and_name() -> None:
    by_blz = fints_mod.search_institutes("38250110")
    assert [i.blz for i in by_blz] == ["38250110"]
    by_iban = fints_mod.search_institutes("DE12 3825 0110 0000 0000 01")
    assert [i.blz for i in by_iban] == ["38250110"]
    by_bic = fints_mod.search_institutes("WELADED1EUS")
    assert by_bic
    assert by_bic[0].blz == "38250110"
    by_name = fints_mod.search_institutes("Euskirchen")
    assert any(i.blz == "38250110" for i in by_name)
    assert by_name[0].connectable  # connectable institutes first
    many = fints_mod.search_institutes("Sparkasse")
    assert len(many) == fints_mod.SEARCH_LIMIT
    assert fints_mod.search_institutes("   ") == []


# --- state machine ------------------------------------------------------------------------


def _start(progress: fints_mod.Progress | None = None) -> fints_mod.StepResult:
    return fints_mod.start_session(
        CREDS,
        client_data=None,
        tan_mechanism=None,
        tan_medium=None,
        progress=progress or fints_mod.Progress(with_transactions=False),
    )


def _continue(
    step: fints_mod.StepResult, tan: str | None, progress: fints_mod.Progress | None = None
) -> fints_mod.StepResult:
    assert step.challenge is not None
    return fints_mod.continue_session(
        CREDS,
        challenge=step.challenge,
        tan=tan,
        tan_mechanism=step.tan_mechanism,
        tan_medium=step.tan_medium,
        progress=progress or step.progress or fints_mod.Progress(with_transactions=False),
    )


def test_init_tan_then_accounts_and_balances() -> None:
    step = _start()
    assert step.status == "awaiting_tan"
    assert step.challenge is not None
    assert step.challenge.text == "TAN für init eingeben"
    assert step.challenge.hhduc == "0248A0123456789"
    assert step.challenge.decoupled is False
    assert step.tan_mechanism == "912"
    assert {m.code for m in step.tan_mechanisms} == {"912", "922"}
    assert step.tan_medium == "Handy 1"
    assert step.client_data  # opaque, stored encrypted by the caller
    done = _continue(step, fake.GOOD_TAN)
    assert done.status == "done"
    assert done.progress is not None
    assert done.progress.accounts is not None
    ibans = [a["iban"] for a in done.progress.accounts]
    assert ibans == [fake.IBAN_1, fake.IBAN_2]
    assert done.progress.accounts[0]["balance"] == "1234.56"
    assert done.progress.accounts[1]["balance"] == "-10.00"
    assert done.progress.accounts[0]["balance_date"] == "2026-09-27"
    # the second client was built from the stored client state, not from scratch
    assert fake.Scenario.constructed[-1]["from_data"] is not None


def test_wrong_tan_maps_to_tan_rejected() -> None:
    step = _start()
    with pytest.raises(ProblemError) as exc:
        _continue(step, "000000")
    assert exc.value.error is ErrorCodes.FINTS_TAN_REJECTED


def test_decoupled_polls_until_confirmed() -> None:
    fake.Scenario.decoupled = True
    fake.Scenario.decoupled_polls_until_confirmed = 3
    step = _start()
    assert step.status == "awaiting_decoupled"
    assert step.challenge is not None
    assert step.challenge.decoupled
    second = _continue(step, None)
    assert second.status == "awaiting_decoupled"
    third = _continue(second, None)
    assert third.status == "awaiting_decoupled"
    done = _continue(third, None)
    assert done.status == "done"
    assert fake.Scenario.polls == 3


def test_matrix_challenge_is_passed_as_image() -> None:
    fake.Scenario.matrix = True
    step = _start()
    assert step.challenge is not None
    assert step.challenge.image_mime == "image/png"
    assert step.challenge.image == b"\x89PNG-fake"


def test_tan_in_the_middle_of_transactions_resumes_at_the_same_account() -> None:
    fake.Scenario.init_tan = False
    fake.Scenario.tan_for_transactions = True
    progress = fints_mod.Progress(with_transactions=True, since="2026-09-01", until=None)
    step = _start(progress)
    assert step.status == "awaiting_tan"
    assert step.progress is not None
    assert step.progress.stage == "transactions"
    assert step.progress.next_index == 0
    assert step.progress.accounts is not None
    assert step.progress.accounts[0]["balance"] == "1234.56"
    done = _continue(step, fake.GOOD_TAN)
    assert done.status == "done"
    assert done.progress is not None
    rows = done.progress.transactions[fake.IBAN_1]
    assert len(rows) == 2
    assert done.progress.transactions[fake.IBAN_2] == []
    raw = fints_mod.raw_from_json(rows[0])
    assert raw.amount == Decimal("700.00")
    assert raw.bank_reference == "fints:REF-1"
    assert raw.counterpart_iban == "DE89370400440532013000"
    assert raw.end_to_end_id == "E2E-1"


def test_no_tan_at_all_completes_in_one_step() -> None:
    fake.Scenario.init_tan = False
    step = _start()
    assert step.status == "done"
    assert step.challenge is None


def test_pin_rejected_and_locked_map_to_registered_codes() -> None:
    fake.Scenario.reject_pin = True
    with pytest.raises(ProblemError) as exc:
        _start()
    assert exc.value.error is ErrorCodes.FINTS_PIN_REJECTED
    fake.Scenario.reject_pin = False
    fake.Scenario.lock_account = True
    with pytest.raises(ProblemError) as exc2:
        _start()
    assert exc2.value.error is ErrorCodes.FINTS_ACCOUNT_LOCKED


def test_unknown_tan_mechanism_is_refused() -> None:
    with pytest.raises(ProblemError) as exc:
        fints_mod.start_session(
            CREDS,
            client_data=None,
            tan_mechanism="999",
            tan_medium=None,
            progress=fints_mod.Progress(with_transactions=False),
        )
    assert exc.value.error is ErrorCodes.FINTS_STATE


def test_credentials_repr_hides_pin() -> None:
    assert fake.GOOD_PIN not in repr(CREDS)
    assert "user" not in repr(CREDS)


# --- error mapping ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "error"),
    [
        ("9942", ErrorCodes.FINTS_PIN_REJECTED),
        ("3938", ErrorCodes.FINTS_ACCOUNT_LOCKED),
        ("9941", ErrorCodes.FINTS_TAN_REJECTED),
        ("9075", ErrorCodes.FINTS_SCA_REQUIRED),
        ("9050", ErrorCodes.FINTS_BANK_REJECTED),
    ],
)
def test_problem_for_code(code: str, error: object) -> None:
    assert fints_mod.problem_for_code(code, "text").error is error


def test_problem_for_exception_uses_class_name_and_return_code() -> None:
    assert (
        fints_mod.problem_for_exception(fake.FinTSDialogError("code 9941 TAN falsch")).error
        is ErrorCodes.FINTS_TAN_REJECTED
    )
    assert (
        fints_mod.problem_for_exception(ConnectionError("down")).error
        is ErrorCodes.FINTS_UNAVAILABLE
    )
    assert (
        fints_mod.problem_for_exception(RuntimeError("x")).error is ErrorCodes.FINTS_BANK_REJECTED
    )


# --- MT940 mapping and dedup key ----------------------------------------------------------


def test_mt940_mapping_signs_and_stable_reference() -> None:
    debit = fake.mt940_tx("2026-09-21", "50.00", "D", "Miete", "B-1")
    raw = fints_mod.mt940_transaction_to_raw(debit, "stmt")
    assert raw.amount == Decimal("-50.00")
    assert raw.booking_date == date(2026, 9, 21)
    assert raw.bank_reference == "fints:B-1"
    assert raw.transaction_code == "166"
    assert raw.raw["reference_source"] == "61//bank_reference"
    reversal = fake.mt940_tx("2026-09-21", "50.00", "RC", "Miete", "B-2")
    assert fints_mod.mt940_transaction_to_raw(reversal, "stmt").amount == Decimal("-50.00")
    # without a bank reference the key is derived from content and stays stable on re-fetch
    a = fints_mod.mt940_transaction_to_raw(
        fake.mt940_tx("2026-09-21", "50.00", "C", "X", None), "s"
    )
    b = fints_mod.mt940_transaction_to_raw(
        fake.mt940_tx("2026-09-21", "50.00", "C", "X", None), "s"
    )
    c = fints_mod.mt940_transaction_to_raw(
        fake.mt940_tx("2026-09-21", "50.00", "C", "Y", None), "s"
    )
    assert a.bank_reference == b.bank_reference
    assert a.bank_reference != c.bank_reference
    assert a.raw["reference_source"].startswith("derived:")
    back = fints_mod.raw_from_json(fints_mod.raw_to_json(raw))
    assert back == raw


def test_sca_due_after_90_days() -> None:
    today = date(2026, 9, 27)
    assert fints_mod.sca_due(None, today)
    assert not fints_mod.sca_due(date(2026, 9, 1), today)
    assert fints_mod.sca_due(date(2026, 6, 29), today)
    assert fints_mod.initial_since(None, today) == date(2026, 6, 30)
    assert fints_mod.initial_since(date(2026, 9, 20), today) == date(2026, 9, 17)
