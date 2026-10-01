"""M2-05 (password policy 12 + offline breach list), M2-02 (property scope), M2-03 (WebAuthn
prepared, not active). Expected results are fixed values from the operator decision 9 a."""

import uuid
from pathlib import Path

import pytest

from mhvp.core.auth import breached, passwords, scope, webauthn
from mhvp.core.auth.principal import Principal
from mhvp.core.problems import ProblemError


@pytest.fixture(autouse=True)
def _reset_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(breached.ENV_FILE, raising=False)
    breached.reset_sources()


def test_bundled_list_rejects_known_passwords_case_insensitive() -> None:
    assert breached.is_breached("passwort1234")
    assert breached.is_breached("Passwort1234")
    assert not breached.is_breached("Kranich Ufer Leuchte 7")
    assert passwords.policy_violation("Passwort1234") is not None
    assert passwords.policy_violation("Kranich Ufer Leuchte 7") is None


def test_bundled_list_contains_only_sha1_digests() -> None:
    assert all(len(h) == 40 and h == h.upper() for h in breached.BUNDLED_SHA1)


def test_file_source_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = "Ein eigenes langes Passwort"
    assert not breached.is_breached(candidate)
    hashes = tmp_path / "pwned.txt"
    hashes.write_text(f"{breached.sha1_upper(candidate)}:42\nnot-a-hash\n", encoding="ascii")
    monkeypatch.setenv(breached.ENV_FILE, str(hashes))
    breached.reset_sources()
    assert breached.is_breached(candidate)


def test_missing_file_falls_back_to_bundled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(breached.ENV_FILE, "/nonexistent/pwned.txt")
    breached.reset_sources()
    assert breached.is_breached("passwort1234")
    assert not breached.is_breached("Kranich Ufer Leuchte 7")


def test_registered_source() -> None:
    class Always:
        def contains(self, sha1_hex_upper: str) -> bool:
            return True

    breached.register_source(Always())
    assert breached.is_breached("anything at all here")


P1, P2 = uuid.uuid4(), uuid.uuid4()


def _principal(roles: tuple[str, ...], property_ids: tuple[uuid.UUID, ...]) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        permissions=frozenset(),
        roles=roles,
        property_ids=property_ids,
    )


def test_property_scope_empty_list_is_unrestricted() -> None:
    principal = _principal(("standard",), ())
    assert scope.allowed_property_ids(principal) is None
    assert scope.property_allowed(principal, P2)
    assert scope.property_allowed(principal, None)


def test_property_scope_limits_standard_role() -> None:
    principal = _principal(("standard", "caretaker"), (P1,))
    assert scope.allowed_property_ids(principal) == frozenset({P1})
    assert scope.property_allowed(principal, P1)
    assert not scope.property_allowed(principal, P2)
    assert not scope.property_allowed(principal, None)
    with pytest.raises(ProblemError) as exc:
        scope.ensure_property_allowed(principal, P2)
    assert exc.value.status == 404


def test_property_scope_ignored_for_admin_api_key_and_switch() -> None:
    assert scope.allowed_property_ids(_principal(("standard", "administrator"), (P1,))) is None
    key = Principal(
        user_id=None, tenant_id=uuid.uuid4(), permissions=frozenset(), api_key_id=uuid.uuid4()
    )
    assert scope.allowed_property_ids(key) is None
    switched = Principal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        permissions=frozenset(),
        is_platform_admin=True,
        platform_access_reason="support",
        property_ids=(P1,),
    )
    assert scope.allowed_property_ids(switched) is None


def test_webauthn_not_available() -> None:
    from tests.conftest import make_settings

    # Off by default (S16-01): only the operator release switches passkeys on.
    settings = make_settings()
    assert webauthn.is_available(settings) is False
    with pytest.raises(ProblemError) as exc:
        webauthn.ensure_available(settings)
    assert exc.value.error.code == "MHVP-AUTH-0012"
    assert exc.value.status == 503


def test_portal_roles_derived_from_relations() -> None:
    from mhvp.core.auth.portal_roles import PortalRelations, PortalRole, derive_portal_roles

    assert derive_portal_roles(PortalRelations()) == ()
    assert derive_portal_roles(PortalRelations(active_rental_contracts=1)) == (
        PortalRole.TENANT_RESIDENT,
    )
    assert derive_portal_roles(PortalRelations(board_seats=1)) == ()
    assert derive_portal_roles(PortalRelations(active_ownerships=2, board_seats=1)) == (
        PortalRole.OWNER,
        PortalRole.BOARD_MEMBER,
    )
    assert derive_portal_roles(
        PortalRelations(active_rental_contracts=1, service_provider_relations=1)
    ) == (PortalRole.TENANT_RESIDENT, PortalRole.SERVICE_PROVIDER)
