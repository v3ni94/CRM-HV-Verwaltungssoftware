"""AN16 helper (GAK-105): bulk confirmation always goes through a preview token."""

from typing import Any

from fastapi.testclient import TestClient

BULK = "/api/v1/banking/bulk-confirm"


def bulk_book(
    client: TestClient, headers: dict[str, str], body: dict[str, Any], *, exceptions: bool = True
) -> Any:
    """Preview, then book the same items with the returned preview_id. ``exceptions`` confirms
    exception rows explicitly, so per item failures stay visible in the results."""
    items = body["items"]
    preview = client.post(
        BULK,
        json={"items": items, "preview": True, "confirm_exceptions": exceptions},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    return client.post(
        BULK,
        json={
            "items": items,
            "preview": False,
            "confirm_exceptions": exceptions,
            "preview_id": preview.json()["preview_id"],
        },
        headers=headers,
    )
