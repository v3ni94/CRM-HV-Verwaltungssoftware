"""Central OpenAPI post-processing: security schemes and standard error responses
(GAI-305, GAI-306).

Purely declarative. Authentication and error handling stay as they are; this only makes
them machine readable for integrators and generators:

* ``components.securitySchemes``: ``BearerAuth`` (session/OIDC/portal token in the
  ``Authorization`` header) and ``ApiKeyAuth`` (``X-API-Key`` header, see
  ``mhvp.core.auth.principal``).
* ``security`` per operation, derived from the dependency tree: a route is authenticated
  when ``get_principal`` is reachable from the endpoint or one of its dependencies;
  anonymous routes get an empty ``security`` list.
* ``components.responses`` with RFC 9457 problems (ADR 0004) and references per operation:
  401 and 403 for authenticated routes, 404 for routes with path parameters, 409 for
  writing routes, 422 for writing routes without a generated 422, 429 everywhere (global
  rate limit). Existing responses of an operation are never overwritten.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from mhvp.core.listparams import _walk_routes
from mhvp.core.problems import PROBLEM_CONTENT_TYPE, Problem

SECURITY_SCHEMES: dict[str, Any] = {
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "description": "Sitzungs, OIDC oder Portal Token im Header Authorization.",
    },
    "ApiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Mandanten API Schlüssel (Format mhvp_<tenant>_<prefix>_<secret>).",
    },
}
AUTH_SECURITY: list[dict[str, list[str]]] = [{"BearerAuth": []}, {"ApiKeyAuth": []}]

_STANDARD: dict[str, tuple[str, str]] = {
    "401": ("Unauthorized", "Nicht angemeldet oder Anmeldung ungültig."),
    "403": ("Forbidden", "Berechtigung fehlt oder falscher Mandant."),
    "404": ("NotFound", "Ressource nicht gefunden oder nicht sichtbar (RLS)."),
    "409": ("Conflict", "Konflikt mit dem aktuellen Zustand (Version, Sperre, Gate)."),
    "422": ("UnprocessableEntity", "Validierungsfehler."),
    "429": ("TooManyRequests", "Anfragelimit überschritten."),
}
_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
_AUTH_ROOT = "get_principal"
# Entry points imported locally inside functions (not visible as globals).
_AUTH_NAMES = frozenset({_AUTH_ROOT, "portal_user", "require_permission"})


def _responses_component() -> dict[str, Any]:
    ref = {"$ref": "#/components/schemas/Problem"}
    return {
        name: {"description": text, "content": {PROBLEM_CONTENT_TYPE: {"schema": ref}}}
        for name, text in _STANDARD.values()
    }


def _reaches_auth(fn: Any, seen: set[int], depth: int = 0) -> bool:
    if not inspect.isfunction(fn):
        fn = inspect.unwrap(fn.__call__) if callable(fn) else fn
    if not inspect.isfunction(fn) or id(fn) in seen or depth > 6:
        return False
    seen.add(id(fn))
    if fn.__name__ == _AUTH_ROOT:
        return True
    code = fn.__code__
    names = set(code.co_names) | set(code.co_freevars)
    if _AUTH_NAMES & (names | set(code.co_varnames)):
        return True
    scope: dict[str, Any] = dict(fn.__globals__)
    if fn.__closure__:
        scope.update(
            {n: c.cell_contents for n, c in zip(code.co_freevars, fn.__closure__, strict=False)}
        )
    for name in names:
        target = scope.get(name)
        if (
            inspect.isfunction(target)
            and target.__module__.startswith("mhvp")
            and _reaches_auth(target, seen, depth + 1)
        ):
            return True
    return False


def _authenticated(dependant: Any, cache: dict[int, bool]) -> bool:
    calls: list[Callable[..., Any]] = []
    stack = [dependant]
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            calls.append(dep.call)
        stack.extend(dep.dependencies)
    for call in calls:
        key = id(call)
        if key not in cache:
            cache[key] = _reaches_auth(call, set())
        if cache[key]:
            return True
    return False


def install_openapi_docs(app: Any) -> None:
    original = app.openapi
    done: list[dict[str, Any]] = []

    def custom_openapi() -> dict[str, Any]:
        schema: dict[str, Any] = original()
        if done:
            return schema
        done.append(schema)
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        schemas.setdefault(
            "Problem", Problem.model_json_schema(ref_template="#/components/schemas/{model}")
        )
        for name, sub in (schemas["Problem"].pop("$defs", None) or {}).items():
            schemas.setdefault(name, sub)
        components.setdefault("securitySchemes", {}).update(SECURITY_SCHEMES)
        components.setdefault("responses", {}).update(_responses_component())
        cache: dict[int, bool] = {}
        paths = schema.get("paths", {})
        for path, route in _walk_routes(app.routes):
            item = paths.get(path)
            if not item:
                continue
            auth = _authenticated(route.dependant, cache)
            for method in route.methods:
                op = item.get(method.lower())
                if op is None:
                    continue
                op.setdefault("security", AUTH_SECURITY if auth else [])
                responses = op.setdefault("responses", {})
                wanted = ["429"]
                if auth:
                    wanted += ["401", "403"]
                if "{" in path:
                    wanted.append("404")
                if method in _WRITE:
                    wanted += ["409", "422"]
                for status in wanted:
                    if status not in responses:
                        responses[status] = {
                            "$ref": f"#/components/responses/{_STANDARD[status][0]}"
                        }
        return schema

    app.openapi = custom_openapi
