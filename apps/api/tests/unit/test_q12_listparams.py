"""Generic list parameters (S12-03): parsing, filter conversion, sort, sparse fields."""

import uuid

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from starlette.requests import Request

from mhvp.core.listparams import (
    ListParams,
    apply_filters,
    apply_sort,
    check_include,
    list_params,
    sparse,
)
from mhvp.core.problems import ProblemError
from mhvp.tickets.models import Ticket


def _request(query: str) -> Request:
    return Request({"type": "http", "query_string": query.encode(), "headers": []})


def test_parse_all_parameters() -> None:
    params = list_params(
        _request(
            "filter[status]=new,in_progress&filter[priority]=high&sort=-created_at,number"
            "&fields=title&include=property"
        )
    )
    assert params.filters == {"status": ["new", "in_progress"], "priority": ["high"]}
    assert params.sort == [("created_at", True), ("number", False)]
    assert params.fields == ["title"]
    assert params.include == ["property"]


def test_filters_convert_and_refuse() -> None:
    allowed = {"status": Ticket.status, "property_id": Ticket.property_id, "number": Ticket.number}
    pid = uuid.uuid4()
    query = apply_filters(
        select(Ticket),
        ListParams(filters={"status": ["new", "in_progress"], "property_id": [str(pid)]}),
        allowed,
    )
    sql = str(query.compile())
    assert "ticket.status IN" in sql
    assert "ticket.property_id =" in sql
    with pytest.raises(ProblemError):
        apply_filters(select(Ticket), ListParams(filters={"x": ["1"]}), allowed)
    with pytest.raises(ProblemError):
        apply_filters(select(Ticket), ListParams(filters={"number": ["abc"]}), allowed)
    with pytest.raises(ProblemError):
        apply_filters(select(Ticket), ListParams(filters={"status": ["robot"]}), allowed)
    null_query = apply_filters(
        select(Ticket), ListParams(filters={"property_id": ["null"]}), allowed
    )
    assert "ticket.property_id IS NULL" in str(null_query.compile())


def test_sort_and_include() -> None:
    query = apply_sort(
        select(Ticket),
        ListParams(sort=[("number", True)]),
        {"number": Ticket.number},
        (Ticket.id,),
    )
    assert "ORDER BY ticket.number DESC NULLS LAST, ticket.id" in str(query.compile())
    with pytest.raises(ProblemError):
        apply_sort(select(Ticket), ListParams(sort=[("x", False)]), {}, ())
    assert check_include(ListParams(include=["property"]), ("property",)) == {"property"}
    with pytest.raises(ProblemError):
        check_include(ListParams(include=["unit"]), ("property",))


class _Item(BaseModel):
    id: int
    title: str
    secret: str


class _Page(BaseModel):
    items: list[_Item]
    total: int


def test_sparse_page_and_list() -> None:
    page = _Page(items=[_Item(id=1, title="a", secret="s")], total=1)
    assert sparse(page, ListParams(), _Item) is page
    response = sparse(page, ListParams(fields=["title"]), _Item)
    assert response.body == b'{"items":[{"id":1,"title":"a"}],"total":1}'
    listed = sparse([{"id": 1, "title": "a", "x": 2}], ListParams(fields=["x"]), None)
    assert listed.body == b'[{"id":1,"x":2}]'
    with pytest.raises(ProblemError):
        sparse(page, ListParams(fields=["nope"]), _Item)
