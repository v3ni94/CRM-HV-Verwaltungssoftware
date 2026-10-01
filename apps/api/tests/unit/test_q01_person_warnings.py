"""S69-03: person check of two approvers beyond user id (warning, no block)."""

import uuid
from datetime import date

from mhvp.accounting.approval_decisions import PersonFeatures, compare


def _p(**kw: object) -> PersonFeatures:
    return PersonFeatures(user_id=uuid.uuid4(), **kw)  # type: ignore[arg-type]


def test_same_name_and_birth_date_warns() -> None:
    a = _p(name="erika muster", birth_date=date(1980, 5, 1))
    b = _p(name="erika muster", birth_date=date(1980, 5, 1))
    assert compare(a, b) == [
        "Möglicherweise dieselbe Person: gleicher Name und gleiches Geburtsdatum."
    ]


def test_same_name_other_birth_date_is_silent() -> None:
    a = _p(name="erika muster", birth_date=date(1980, 5, 1))
    b = _p(name="erika muster", birth_date=date(1981, 5, 1))
    assert compare(a, b) == []


def test_same_name_without_birth_date_warns() -> None:
    assert compare(_p(name="erika muster"), _p(name="erika muster", birth_date=date(1980, 1, 1)))


def test_shared_contact_email_warns() -> None:
    a = _p(emails={"e@example.org", "x@example.org"})
    b = _p(emails={"x@example.org"})
    assert "gleiche E-Mail-Adresse" in compare(a, b)[0]


def test_different_persons_are_silent() -> None:
    assert compare(_p(name="a b", emails={"a@x.de"}), _p(name="c d", emails={"c@x.de"})) == []
