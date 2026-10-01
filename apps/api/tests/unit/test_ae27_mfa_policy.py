"""AE27 (M2-04, M21-09): pure second factor policy rule and the setup step token.

Expected results are fixed by the rule in docs/rules/M2-04.md: the default is ``voluntary``
(operator decision M2-01, nobody among the staff is covered, also without a stored row),
``all_staff`` covers every role except ``portal_user``, ``roles`` only the listed codes; the
portal role is covered only with ``portal_required``.
"""

import uuid

import pytest
from pydantic import SecretStr

from mhvp.core.auth import tokens
from mhvp.core.auth.mfa_policy import (
    CRM_MODES,
    DEFAULT_CRM_MODE,
    DEFAULT_POLICY,
    AuthMfaPolicy,
    MfaPolicy,
    requires_second_factor,
)
from mhvp.core.config import Settings
from tests.conftest import make_settings

_PEM = tokens.generate_private_key_pem()


def _settings() -> Settings:
    return make_settings(jwt_private_key=SecretStr(_PEM), jwt_issuer="http://testserver")


@pytest.mark.parametrize(
    ("policy", "roles", "expected"),
    [
        # Default (no stored row): voluntary, nobody is forced to set up a factor (M2-01).
        (DEFAULT_POLICY, ["tenant_admin"], False),
        (DEFAULT_POLICY, ["caretaker"], False),
        (DEFAULT_POLICY, ["custom_role_x"], False),
        (DEFAULT_POLICY, ["portal_user"], False),
        (DEFAULT_POLICY, ["portal_user", "standard"], False),
        (DEFAULT_POLICY, [], False),
        # Tenant choice all_staff: every CRM role (system or custom), the portal role not.
        (MfaPolicy(crm_mode="all_staff"), ["tenant_admin"], True),
        (MfaPolicy(crm_mode="all_staff"), ["caretaker"], True),
        (MfaPolicy(crm_mode="all_staff"), ["custom_role_x"], True),
        (MfaPolicy(crm_mode="all_staff"), ["portal_user"], False),
        (MfaPolicy(crm_mode="all_staff"), ["portal_user", "standard"], True),
        (MfaPolicy(crm_mode="all_staff"), [], False),
        (MfaPolicy(crm_mode="all_staff", portal_required=True), ["portal_user"], True),
        # Voluntary stated explicitly (operator decision M2-01).
        (MfaPolicy(crm_mode="voluntary"), ["tenant_admin"], False),
        (MfaPolicy(crm_mode="voluntary", portal_required=True), ["portal_user"], True),
        (MfaPolicy(crm_mode="voluntary", portal_required=True), ["standard"], False),
        # Listed roles only.
        (MfaPolicy(crm_mode="roles", crm_role_codes=("administrator",)), ["administrator"], True),
        (MfaPolicy(crm_mode="roles", crm_role_codes=("administrator",)), ["standard"], False),
        (
            MfaPolicy(crm_mode="roles", crm_role_codes=("administrator",)),
            ["standard", "administrator"],
            True,
        ),
        # The portal role is never covered through the role list.
        (MfaPolicy(crm_mode="roles", crm_role_codes=("portal_user",)), ["portal_user"], False),
        (MfaPolicy(portal_required=True), ["portal_user"], True),
    ],
)
def test_requires_second_factor(policy: MfaPolicy, roles: list[str], expected: bool) -> None:
    assert requires_second_factor(policy, roles) is expected


def test_default_policy_is_voluntary_without_portal() -> None:
    assert DEFAULT_CRM_MODE == "voluntary"
    assert DEFAULT_POLICY.crm_mode == "voluntary"
    assert DEFAULT_POLICY.crm_role_codes == ()
    assert DEFAULT_POLICY.portal_required is False
    assert DEFAULT_POLICY.stored is False
    assert MfaPolicy().crm_mode == "voluntary"


def test_model_and_policy_without_row_share_the_default() -> None:
    """ORM default and server default of the column follow the same default as the rule."""
    column = AuthMfaPolicy.__table__.c.crm_mode
    assert column.default is not None
    assert getattr(column.default, "arg", None) == DEFAULT_CRM_MODE
    assert column.server_default is not None
    assert getattr(column.server_default, "arg", None) == DEFAULT_CRM_MODE
    assert DEFAULT_CRM_MODE in CRM_MODES


def test_setup_token_is_not_an_mfa_token_and_vice_versa() -> None:
    settings = _settings()
    user, tenant = uuid.uuid4(), uuid.uuid4()
    setup = tokens.issue_mfa_setup_token(settings, user, tenant_id=tenant)
    assert tokens.decode_mfa_setup_token(settings, setup) == (user, tenant)
    with pytest.raises(tokens.TokenError):
        tokens.decode_mfa_token(settings, setup)
    mfa = tokens.issue_mfa_token(settings, user)
    with pytest.raises(tokens.TokenError):
        tokens.decode_mfa_setup_token(settings, mfa)
    access = tokens.issue_access_token(settings, tokens.AccessClaims(user_id=user, tenant_id=None))
    with pytest.raises(tokens.TokenError):
        tokens.decode_mfa_setup_token(settings, access)


def test_mfa_token_tenant_claim() -> None:
    settings = _settings()
    user, tenant = uuid.uuid4(), uuid.uuid4()
    assert tokens.mfa_token_tenant(settings, tokens.issue_mfa_token(settings, user)) is None
    with_tenant = tokens.issue_mfa_token(settings, user, tenant_id=tenant)
    assert tokens.decode_mfa_token(settings, with_tenant) == user
    assert tokens.mfa_token_tenant(settings, with_tenant) == tenant
    assert tokens.mfa_token_tenant(settings, "not-a-token") is None
    setup = tokens.issue_mfa_setup_token(settings, user)
    assert tokens.decode_mfa_setup_token(settings, setup) == (user, None)
