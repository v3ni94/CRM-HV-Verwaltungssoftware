"""GAI-305/306: security schemes, per operation security and standard problem responses."""

from typing import Any

import pytest

from mhvp.openapi import build_openapi


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return build_openapi()


def test_security_schemes_and_responses(spec: dict[str, Any]) -> None:
    components = spec["components"]
    assert set(components["securitySchemes"]) == {"BearerAuth", "ApiKeyAuth"}
    for name in (
        "Unauthorized",
        "Forbidden",
        "NotFound",
        "Conflict",
        "UnprocessableEntity",
        "TooManyRequests",
    ):
        content = components["responses"][name]["content"]
        assert content["application/problem+json"]["schema"]["$ref"].endswith("/Problem")
    assert "Problem" in components["schemas"]


def test_authenticated_route_documents_security_and_errors(spec: dict[str, Any]) -> None:
    op = spec["paths"]["/api/v1/portal/me"]["get"]
    assert op["security"] == [{"BearerAuth": []}, {"ApiKeyAuth": []}]
    assert {"401", "403", "429"} <= set(op["responses"])


def test_anonymous_route_has_empty_security(spec: dict[str, Any]) -> None:
    op = spec["paths"]["/api/v1/portal/magic-link/request"]["post"]
    assert op["security"] == []
    assert "401" not in op["responses"]
    assert {"409", "422", "429"} <= set(op["responses"])


def test_every_operation_has_security_field(spec: dict[str, Any]) -> None:
    methods = ("get", "post", "put", "patch", "delete")
    missing = [
        (m, p)
        for p, item in spec["paths"].items()
        for m in methods
        if m in item and "security" not in item[m]
    ]
    assert missing == []


def test_path_parameter_routes_document_404(spec: dict[str, Any]) -> None:
    for path, item in spec["paths"].items():
        if "{" in path:
            for op in item.values():
                if isinstance(op, dict) and "responses" in op:
                    assert "404" in op["responses"], path
