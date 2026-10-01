"""R07: ``embed`` adds included relations and keeps sparse fields (S12-03)."""

import json
import uuid

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mhvp.core.listparams import ListParams, embed


class _Item(BaseModel):
    id: uuid.UUID
    name: str
    other: int


class _Page(BaseModel):
    items: list[_Item]
    total: int


def test_embed_page_list_and_fields() -> None:
    a = uuid.uuid4()
    page = _Page(items=[_Item(id=a, name="A", other=1)], total=1)
    out = embed(page, ListParams(fields=["name"]), _Item, {"rel": lambda i: {"x": i["name"]}})
    assert isinstance(out, JSONResponse)
    assert json.loads(out.body) == {
        "items": [{"id": str(a), "name": "A", "rel": {"x": "A"}}],
        "total": 1,
    }
    rows = embed([{"id": "1", "k": 2}], ListParams(), None, {"rel": lambda i: i["k"] * 2})
    assert json.loads(rows.body) == [{"id": "1", "k": 2, "rel": 4}]
    # Without includes the result is returned as before.
    assert embed(page, ListParams(), _Item, {}) is page
