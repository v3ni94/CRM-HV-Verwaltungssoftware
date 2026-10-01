"""AE34: legal basis register of the consent rules (pure logic, no database)."""

import pytest

from mhvp.contacts import consent_rules
from mhvp.contacts.consent_rules import BasisEntry, ConsentPolicy, policy_from


def test_default_is_the_restrictive_variant() -> None:
    policy = policy_from(None)
    assert all(policy.basis_for(p) == "consent" for p in consent_rules.PURPOSES)
    assert all(policy.basis_origin(p) == "default" for p in consent_rules.PURPOSES)
    assert policy.as_dict() == {
        "email_delivery": "consent_only",
        "data_sharing": "consent_only",
        "portal_terms_version": None,
    }


def test_legacy_switch_counts_as_contract_and_register_wins() -> None:
    legacy = policy_from(
        {
            "consent_policy": {
                "email_delivery": "consent_or_contract",
                "data_sharing": "consent_only",
            }
        }
    )
    assert legacy.basis_for("email_delivery") == "contract"
    assert legacy.basis_origin("email_delivery") == "policy"
    assert legacy.basis_for("data_sharing") == "consent"
    register = {"email_delivery": {"basis": "consent", "note": None}}
    both = policy_from(
        {
            "consent_policy": {"email_delivery": "consent_or_contract"},
            "consent_legal_basis": register,
        }
    )
    assert both.basis_for("email_delivery") == "consent"
    assert both.basis_origin("email_delivery") == "register"


def test_invalid_stored_values_fall_back_to_consent() -> None:
    policy = policy_from(
        {
            "consent_legal_basis": {
                "marketing": {"basis": "contract", "note": "nicht zulässig für Werbung"},
                "unknown_purpose": {"basis": "consent"},
                "data_sharing": "kein dict",
                "email_delivery": {
                    "basis": "legitimate_interest",
                    "note": "Abwägung vom 01.10.2026",
                },
            }
        }
    )
    assert policy.basis_for("marketing") == "consent"
    assert policy.basis_for("data_sharing") == "consent"
    assert policy.basis_for("email_delivery") == "legitimate_interest"
    assert "unknown_purpose" not in policy.legal_basis
    assert policy_from({"consent_legal_basis": ["x"]}).legal_basis == {}


@pytest.mark.parametrize(
    ("purpose", "basis", "note", "valid"),
    [
        ("email_delivery", "consent", None, True),
        ("email_delivery", "contract", "Textformklausel im Vertrag", True),
        ("email_delivery", "contract", None, False),
        ("email_delivery", "contract", "zu kurz", False),
        ("email_delivery", "legitimate_interest", "   ", False),
        ("data_sharing", "legitimate_interest", "Abwägung vom 01.10.2026", True),
        ("marketing", "contract", "Vertragsklausel Nr. 7", False),
        ("marketing", "legitimate_interest", "Abwägung Bestandskunden", True),
        ("portal_terms", "contract", "Nutzungsvertrag Portal", True),
        ("portal_terms", "legitimate_interest", "Abwägung vom 01.10.2026", False),
        ("whatsapp", "consent", None, False),
        ("email_delivery", "other", "Begründung vorhanden", False),
    ],
)
def test_validate_basis(purpose: str, basis: str, note: str | None, valid: bool) -> None:
    assert (consent_rules.validate_basis(purpose, basis, note) is None) is valid


def test_register_value_replaces_only_the_purpose() -> None:
    first = consent_rules.register_value(
        None, "email_delivery", BasisEntry("contract", "Klausel im Vertrag", "t1", "u1")
    )
    second = consent_rules.register_value(
        {"consent_legal_basis": first}, "marketing", BasisEntry("consent")
    )
    assert set(second) == {"email_delivery", "marketing"}
    assert second["email_delivery"]["note"] == "Klausel im Vertrag"
    assert ConsentPolicy().legal_basis == {}
