"""AL06-01 (AM15): the upload body limit group is a fixed path list, kept in sync with the app.

Every route with a multipart (or other non JSON) request body must be in ``UPLOAD_PATHS``
(otherwise uploads would hit the smaller default limit), and every entry must still exist as
such a route (otherwise the larger limit would apply to a route that never parses uploads).
The OAuth token endpoint (form encoded, small) deliberately stays in the default group.
"""

from __future__ import annotations

from mhvp.core.body_limit import UPLOAD_PATHS, path_group
from mhvp.main import create_app

FORM_NOT_UPLOAD = {"/api/v1/oidc/token"}


def _multipart_routes() -> set[str]:
    found: set[str] = set()
    for path, ops in create_app().openapi()["paths"].items():
        for method, op in ops.items():
            content = (op.get("requestBody") or {}).get("content", {})
            if any(kind != "application/json" for kind in content):
                assert method == "post", (method, path)
                found.add(path)
    return found


def test_upload_paths_match_application_routes() -> None:
    routes = _multipart_routes() - FORM_NOT_UPLOAD
    assert set(UPLOAD_PATHS) == routes, {
        "missing_in_UPLOAD_PATHS": sorted(routes - set(UPLOAD_PATHS)),
        "stale_in_UPLOAD_PATHS": sorted(set(UPLOAD_PATHS) - routes),
    }
    assert len(UPLOAD_PATHS) == len(set(UPLOAD_PATHS))


def test_each_registered_path_is_upload_group_and_form_route_is_default() -> None:
    for template in UPLOAD_PATHS:
        concrete = template.replace("{", "x").replace("}", "")
        assert path_group(concrete) == "upload", template
    assert path_group("/api/v1/oidc/token") == "default"
    assert path_group("/api/v1/auth/login") == "default"
