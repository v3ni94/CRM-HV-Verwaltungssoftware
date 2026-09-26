"""Four eyes release of contact IBANs (M5-01): state transitions, self release, payment filter."""

import asyncio
import uuid
from datetime import date
from typing import Any

import pytest

from mhvp.accounting import direct_debit as dd
from mhvp.contacts import services
from mhvp.contacts.models import (
    BankAccountApproval,
    ContactBankAccount,
    ContactMandateStatus,
    MandateGrantedVia,
    MandateScheme,
)
from mhvp.core.events import DomainEvent
from mhvp.core.problems import ProblemError

TENANT = uuid.uuid4()
CLERK = uuid.uuid4()
APPROVER = uuid.uuid4()


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    def events(self) -> list[str]:
        return [e.type for e in self.added if isinstance(e, DomainEvent)]


def _account(**overrides: object) -> ContactBankAccount:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "contact_id": uuid.uuid4(),
        "iban": "DE89370400440532013000",
        "iban_suffix": "3000",
        "iban_fingerprint": "fp",
        "valid_from": date(2020, 1, 1),
        "sepa_enabled": True,
        "mandate_reference": "MREF-1",
        "mandate_signed_on": date(2024, 1, 10),
        "mandate_granted_via": MandateGrantedVia.BRIEF,
        "mandate_scheme": MandateScheme.CORE,
        "mandate_status": ContactMandateStatus.ACTIVE,
        "approval_status": BankAccountApproval.PENDING,
        "requested_by": CLERK,
    }
    values.update(overrides)
    return ContactBankAccount(**values)


def _decide(account: ContactBankAccount, actor: uuid.UUID | None, **kw: Any) -> _Session:
    session = _Session()
    asyncio.run(
        services.decide_bank_account(
            session,  # type: ignore[arg-type]
            account,
            tenant_id=TENANT,
            actor_user_id=actor,
            approve=kw.pop("approve", True),
            **kw,
        )
    )
    return session


def test_second_person_approves_pending_account() -> None:
    account = _account()
    session = _decide(account, APPROVER)
    assert account.approval_status is BankAccountApproval.APPROVED
    assert account.decided_by == APPROVER
    assert account.decided_at is not None
    assert session.events() == ["bank_account.approved"]


def test_second_person_rejects_pending_account() -> None:
    account = _account()
    session = _decide(account, APPROVER, approve=False, reason="Beleg fehlt")
    assert account.approval_status is BankAccountApproval.REJECTED
    assert session.events() == ["bank_account.rejected"]
    event = next(e for e in session.added if isinstance(e, DomainEvent))
    assert event.payload["reason"] == "Beleg fehlt"


@pytest.mark.parametrize("approve", [True, False])
def test_requester_cannot_decide_own_account(approve: bool) -> None:
    account = _account()
    with pytest.raises(ProblemError):
        _decide(account, CLERK, approve=approve)
    assert account.approval_status is BankAccountApproval.PENDING


def test_platform_admin_and_anonymous_cannot_decide() -> None:
    with pytest.raises(ProblemError):
        _decide(_account(), APPROVER, is_platform_admin=True)
    with pytest.raises(ProblemError):
        _decide(_account(), None)


@pytest.mark.parametrize("status", [BankAccountApproval.APPROVED, BankAccountApproval.REJECTED])
def test_only_pending_accounts_can_be_decided(status: BankAccountApproval) -> None:
    account = _account(approval_status=status, requested_by=CLERK)
    with pytest.raises(ProblemError):
        _decide(account, APPROVER)
    assert account.approval_status is status


def test_direct_debit_skips_unreleased_accounts() -> None:
    day = date(2026, 10, 15)
    assert "nicht freigegeben" in str(dd.mandate_block_reason(_account(), day))
    rejected = _account(approval_status=BankAccountApproval.REJECTED)
    assert "abgelehnt" in str(dd.mandate_block_reason(rejected, day))
    released = _account(approval_status=BankAccountApproval.APPROVED)
    assert dd.mandate_block_reason(released, day) is None


def test_missing_status_counts_as_not_released() -> None:
    assert services.approval_block_reason(object()) is not None
