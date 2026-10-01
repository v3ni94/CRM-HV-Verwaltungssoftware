"""AC01 review of waves 12 and 13: strict_query answers 401 before 422 for unauthenticated
callers of authenticated routes; platform hosts cannot be bound to one tenant."""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from mhvp.core.auth.principal import get_principal, require_permission
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ProblemError, install_problem_handlers
from mhvp.platform.admin_routers import TenantDomainIn, _platform_hosts, add_tenant_domain


def _app() -> FastAPI:
    app = FastAPI()
    app.state.settings = SimpleNamespace()
    install_problem_handlers(app)

    @app.get("/public", dependencies=[Depends(strict_query)])
    def public(limit: int = 10) -> list[int]:
        return [limit]

    @app.get("/auth", dependencies=[Depends(strict_query)])
    async def auth(request: Request, _: object = Depends(get_principal)) -> list[int]:
        return []

    @app.get("/perm", dependencies=[Depends(strict_query)])
    async def perm(_: object = Depends(require_permission("contacts:read"))) -> list[int]:
        return []

    return app


def test_unauthenticated_caller_gets_401_not_422() -> None:
    c = TestClient(_app())
    for path in ("/auth", "/perm"):
        r = c.get(path, params={"unbekannt": "1"})
        assert r.status_code == 401, path
        assert "unbekannt" not in r.text
        assert c.get(path).status_code == 401


def test_public_route_keeps_422_and_credentials_keep_422() -> None:
    c = TestClient(_app())
    assert c.get("/public", params={"unbekannt": "1"}).status_code == 422
    # A caller presenting credentials still gets the precise 422 (declared parameters are
    # public through OpenAPI anyway).
    r = c.get("/perm", params={"unbekannt": "1"}, headers={"x-api-key": "x"})
    assert r.status_code == 422


def _request() -> SimpleNamespace:
    settings = SimpleNamespace(
        jwt_issuer="https://api.example.de",
        api_public_url=None,
        web_crm_url="https://crm.example.de:443/",
        web_portal_url="https://portal.example.de",
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))


def test_platform_hosts_from_settings() -> None:
    assert _platform_hosts(_request()) == {  # type: ignore[arg-type]
        "api.example.de",
        "crm.example.de",
        "portal.example.de",
    }


@pytest.mark.parametrize("host", ["crm.example.de", "Portal.Example.de.", "api.example.de"])
def test_platform_host_rejected_as_tenant_domain(host: str) -> None:
    principal = SimpleNamespace(user_id=uuid.uuid4())
    with pytest.raises(ProblemError) as exc:
        asyncio.run(
            add_tenant_domain(
                uuid.uuid4(),
                TenantDomainIn(host=host),
                _request(),  # type: ignore[arg-type]
                principal,  # type: ignore[arg-type]
            )
        )
    assert exc.value.status == 422
