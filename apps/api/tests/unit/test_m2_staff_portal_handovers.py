"""M2-08 Restpunkt: staff read endpoints for handover protocols are registered and the exempt
role check that triggers the automatic withdrawal of a staff portal access."""

from mhvp.portal.staff_access import is_staff_role_exempt


def test_staff_handover_routes_registered() -> None:
    from mhvp.handover.portal import staff_router

    paths = {(r.path, tuple(sorted(r.methods))) for r in staff_router.routes}  # type: ignore[attr-defined]
    assert ("/portal/handovers", ("GET",)) in paths
    assert ("/portal/handovers/{protocol_id}", ("GET",)) in paths


def test_exempt_role_sets_trigger_revocation() -> None:
    assert is_staff_role_exempt(["read_only"])
    assert is_staff_role_exempt(["tax_advisor", "portal_user"])
    assert is_staff_role_exempt([])
    assert not is_staff_role_exempt(["read_only", "standard"])
