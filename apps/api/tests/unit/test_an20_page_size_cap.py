"""GAK-301 (section 12): page_size and limit of every list are capped at 200."""

from __future__ import annotations

from mhvp.core.listparams import MAX_PAGE_SIZE
from mhvp.main import create_app

PAGE_PARAMS = {"page_size", "limit", "per_page"}


def test_max_page_size_is_200() -> None:
    assert MAX_PAGE_SIZE == 200


def test_no_list_parameter_allows_more_than_200() -> None:
    too_big: list[str] = []
    for path, ops in create_app().openapi()["paths"].items():
        for method, op in ops.items():
            for param in op.get("parameters", []):
                if param.get("in") != "query" or param["name"] not in PAGE_PARAMS:
                    continue
                schema = param.get("schema", {})
                options = schema.get("anyOf", [schema])
                for option in options:
                    maximum = option.get("maximum")
                    if maximum is not None and maximum > MAX_PAGE_SIZE:
                        too_big.append(f"{method.upper()} {path} {param['name']}={maximum}")
                    if option.get("default") is not None and option["default"] > MAX_PAGE_SIZE:
                        too_big.append(f"{method.upper()} {path} {param['name']} default")
    assert not too_big, too_big
