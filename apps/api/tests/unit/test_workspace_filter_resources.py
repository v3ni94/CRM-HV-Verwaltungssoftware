"""GAI-110: saved filters accept the extended list resources and still reject unknown ones."""

import pytest
from pydantic import ValidationError

from mhvp.workspace import routers


def _body_model() -> type:
    return routers.FilterIn


NEW = ["journal", "open_items", "dunning_cases", "hoa_properties", "work_orders"]


@pytest.mark.parametrize("resource", NEW)
def test_new_resources_accepted(resource: str) -> None:
    assert resource in routers.FILTER_RESOURCES
    _body_model()(resource=resource, name="Test", params={"status": "open"})


def test_unknown_resource_rejected() -> None:
    with pytest.raises(ValidationError):
        _body_model()(resource="x", name="Test", params={})
