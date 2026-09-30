"""Acceptance cases SD-03 (PÜ10) and SD-04 (PÜ11) on the world of the A22 access tests.

Expected values by hand: the owner holds no board role; the three documents linked to the
community only (resolution, minutes, economic plan) are visible for him, the foreign
community, the private SEV file and the other owner's contract file are not. The tenant of
the statement sees exactly the released (redacted) version of the receipt, never the original;
the original stays linked with role generated."""

# ruff: noqa: F811
from typing import Any

from fastapi.testclient import TestClient

from mhvp.portal import access
from tests.integration.test_m21_portal import (  # noqa: F401  (fixtures)
    AccessWorld,
    P,
    _ok,
    _portal_ids,
    access_client,
    access_world,
    world,
)

GDWE_DOCS = ("beschluss", "protokoll", "wirtschaftsplan")
PRIVATE_DOCS = ("fremde_gdwe", "sev_vertrag", "sev_akte", "o2_kaufvertrag")


def test_sd03_pue10_owner_right_is_no_board_privilege(
    access_client: TestClient, access_world: AccessWorld
) -> None:
    """SD-03 (PÜ10): every entitled owner reads the community documents beyond his own
    statement (§ 18 Abs. 4 WEG), without a board role; data of another community and private
    SEV or contract files are not released."""
    me: Any = _ok(access_client.get(f"{P}/me", headers=access_world.owner1))
    assert "board" not in me["roles"]
    visible = _portal_ids(access_client, access_world.owner1)
    assert {access_world.docs[k] for k in GDWE_DOCS} <= visible
    assert not {access_world.docs[k] for k in PRIVATE_DOCS} & visible
    for kind in GDWE_DOCS:
        response = access_client.get(
            f"{P}/documents/{access_world.docs[kind]}/download", headers=access_world.owner1
        )
        assert response.status_code == 200
    for kind in PRIVATE_DOCS:
        response = access_client.get(
            f"{P}/documents/{access_world.docs[kind]}/download", headers=access_world.owner1
        )
        assert response.status_code == 404


def test_sd04_pue11_tenant_receipt_inspection_with_redaction(
    access_client: TestClient, access_world: AccessWorld
) -> None:
    """SD-04 (PÜ11, § 556 Abs. 4 BGB, D31): electronic provision of the receipt of the own
    statement as released version with redaction note; original protected and kept; the
    neighbour tenant sees nothing. Partial: creating a redacted copy with reason and scope
    is not yet available (M25-01, see P08.json open_points)."""
    released = access_world.docs["beleg_freigabe"]
    original = access_world.docs["beleg_original"]
    ids = _portal_ids(access_client, access_world.tenant_a)
    assert ids == {released}
    assert original not in ids
    listed = {
        d["id"]: d for d in _ok(access_client.get(f"{P}/documents", headers=access_world.tenant_a))
    }
    assert listed[released]["redaction_note"] == access.REDACTION_NOTE
    assert (
        access_client.get(
            f"{P}/documents/{original}/download", headers=access_world.tenant_a
        ).status_code
        == 404
    )
    assert _portal_ids(access_client, access_world.tenant_b) == set()
    out = _ok(access_client.get(f"/api/v1/documents/{released}", headers=access_world.admin))
    assert any(
        x["entity_type"] == "document" and x["entity_id"] == original and x["role"] == "generated"
        for x in out["links"]
    )
