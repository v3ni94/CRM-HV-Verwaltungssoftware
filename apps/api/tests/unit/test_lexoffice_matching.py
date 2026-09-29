"""Contact matching (rule INT-LEXO-01, spec 3.2): score precedence, ambiguity on equal top
scores, one remote per CRM contact, name normalisation."""

from __future__ import annotations

import uuid

from mhvp.integrations.lexoffice_ext import matching as m


def test_normalisation() -> None:
    assert m.normalise_name("Müller & Partner GbR") == m.normalise_name("Mueller und Partner")
    assert m.normalise_name("Harter GmbH & Co. KG") == "harter"
    assert m.normalise_street("Hauptstr. 5") == m.normalise_street("Hauptstraße 5")


def _crm(
    name: str, zip_: str | None = None, emails: set[str] | None = None, number: int | None = None
) -> m.CrmContact:
    return m.CrmContact(
        id=uuid.uuid4(),
        name=m.normalise_name(name),
        zip=zip_,
        emails=emails or set(),
        customer_number=number,
    )


def _remote(
    rid: str,
    name: str,
    zip_: str | None = None,
    emails: set[str] | None = None,
    number: int | None = None,
) -> m.RemoteContact:
    return m.RemoteContact(
        id=rid,
        display={"name": name},
        name=m.normalise_name(name),
        zip=zip_,
        emails=emails or set(),
        customer_number=number,
        vendor_number=None,
        archived=False,
    )


def test_score_precedence() -> None:
    crm = _crm("Hardy Harter", "40721", {"h@x.de"}, 10001)
    assert m.score(_remote("r", "Anders", number=10001), crm) == m.Candidate(
        crm.id, "customer_number", 1.0
    )
    assert m.score(_remote("r", "Anders", emails={"H@x.de".lower()}), crm) == m.Candidate(
        crm.id, "email_exact", 0.9
    )
    assert m.score(_remote("r", "Hardy Harter", "40721"), crm) == m.Candidate(
        crm.id, "name_zip", 0.7
    )
    assert m.score(_remote("r", "Hardy Harter"), crm) == m.Candidate(crm.id, "name_only", 0.4)
    assert m.score(_remote("r", "Someone Else"), crm) is None


def test_assignment_ambiguous_and_one_remote_per_contact() -> None:
    a = _crm("Hardy Harter", "40721")
    b = _crm("Hardy Harter", "40721")
    c = _crm("Erika Muster", "10115", {"erika@x.de"})
    remotes = [
        _remote("r1", "Hardy Harter", "40721"),
        _remote("r2", "Erika Muster", emails={"erika@x.de"}),
        _remote("r3", "Erika Muster", "10115"),
        _remote("r4", "Nur Name"),
    ]
    result = m.assign(remotes, [a, b, c])
    assert result["r1"][0] == "ambiguous"
    assert {x.contact_id for x in result["r1"][1]} == {
        a.id,
        b.id,
    }
    assert result["r2"] == ("proposed", [m.Candidate(c.id, "email_exact", 0.9)])
    # c is taken by r2 (higher score), r3 has no other candidate above the threshold.
    assert result["r3"][0] == "remote_only"
    assert result["r4"][0] == "remote_only"


def test_remote_from_json_collects_emails_and_display() -> None:
    remote = m.remote_from_json(
        {
            "id": "c-1",
            "roles": {"customer": {"number": 5}},
            "company": {"name": "Firma AG", "contactPersons": [{"emailAddress": "CP@x.de"}]},
            "emailAddresses": {"business": ["Info@x.de"]},
            "addresses": {"billing": [{"zip": "40721", "city": "Hilden"}]},
            "archived": False,
        }
    )
    assert remote.emails == {"cp@x.de", "info@x.de"}
    assert remote.display["name"] == "Firma AG"
    assert remote.display["zip"] == "40721"
    assert remote.customer_number == 5
    assert remote.name == "firma"
