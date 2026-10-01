"""AB04 (GA04-05): ``strict_query`` rejects undeclared query parameters with 422 and leaves
the generic list parameters to routes that parse them themselves."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from mhvp.core.listparams import ListParams, ListSpec, list_params, strict_query
from mhvp.core.problems import install_problem_handlers

_SPEC = ListSpec()


def _app() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/plain", dependencies=[Depends(strict_query)])
    def plain(limit: int = 10) -> list[int]:
        return [limit]

    @app.get("/generic", dependencies=[Depends(strict_query)])
    def generic(q: str | None = None, params: ListParams = Depends(list_params)) -> list[str]:
        return params.fields

    @app.get("/spec", dependencies=[Depends(strict_query)])
    def spec(params: ListParams = Depends(_SPEC.dependency)) -> list[str]:
        return []

    return app


def test_declared_parameters_pass_and_unknown_fail() -> None:
    c = TestClient(_app())
    assert c.get("/plain", params={"limit": 3}).json() == [3]
    r = c.get("/plain", params={"unbekannt": "1"})
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "unbekannt"


def test_generic_parameters_rejected_without_parser() -> None:
    c = TestClient(_app())
    for key in ("sort", "fields", "include", "as_of", "filter[x]"):
        assert c.get("/plain", params={key: "a"}).status_code == 422, key


def test_generic_parameters_left_to_parser() -> None:
    c = TestClient(_app())
    assert c.get("/generic", params={"fields": "a", "q": "x"}).json() == ["a"]
    assert c.get("/generic", params={"bogus": "1"}).status_code == 422
    assert c.get("/spec").status_code == 200
    assert c.get("/spec", params={"sort": "x"}).status_code == 422
