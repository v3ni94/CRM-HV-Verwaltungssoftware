"""GA04-05: ListSpec parses generic list parameters, rejects undeclared ones with 422 and
narrows queries (filter, sort, as_of) without a database."""

from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import Date, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from mhvp.core.listparams import ListParams, ListSpec
from mhvp.core.problems import ProblemError


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "aa04_row"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


SPEC = ListSpec(
    filters={"status": _Row.status},
    sort={"status": _Row.status},
    includes=("owner",),
    valid_from=_Row.valid_from,
    valid_to=_Row.valid_to,
)
PLAIN = ListSpec(filters={"status": _Row.status})


def _app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, status_code=422)

    @app.get("/rows")
    async def rows(
        request: Request, limit: int = 10, params: ListParams = Depends(SPEC.dependency)
    ) -> dict[str, Any]:
        query = SPEC.apply(select(_Row), params, (_Row.id,), request)
        return {"sql": str(query.compile(compile_kwargs={"literal_binds": True}))}

    @app.get("/plain")
    async def plain(params: ListParams = Depends(PLAIN.dependency)) -> dict[str, Any]:
        return {"filters": params.filters}

    return app


def test_accepts_declared_and_generic_parameters() -> None:
    client = TestClient(_app())
    r = client.get(
        "/rows",
        params={
            "limit": 5,
            "filter[status]": "a,b",
            "sort": "-status",
            "include": "owner",
            "as_of": "2026-06-30",
        },
    )
    assert r.status_code == 200, r.text
    sql = r.json()["sql"]
    assert "status IN ('a', 'b')" in sql
    assert "ORDER BY aa04_row.status DESC NULLS LAST, aa04_row.id" in sql
    assert "valid_from <= '2026-06-30'" in sql
    assert "valid_to >= '2026-06-30'" in sql


def test_rejects_unknown_parameters() -> None:
    client = TestClient(_app())
    for bad in (
        {"bogus": "1"},
        {"filter[nope]": "1"},
        {"sort": "id"},
        {"include": "x"},
        {"as_of": "31.12.2026"},
    ):
        assert client.get("/rows", params=bad).status_code == 422, bad
    assert client.get("/plain", params={"as_of": "2026-01-01"}).status_code == 422
    assert client.get("/plain", params={"sort": "status"}).status_code == 422
    assert client.get("/plain", params={"filter[status]": "x"}).json() == {
        "filters": {"status": ["x"]}
    }


def test_default_order_without_sort() -> None:
    client = TestClient(_app())
    sql = client.get("/rows").json()["sql"]
    assert sql.rstrip().endswith("ORDER BY aa04_row.id")
