"""Unit tests for `mhvp.letting.broker_provider` (M28-01 stage 3, M28-02)."""

import base64
import json
import time
from typing import Any

import httpx
import pytest

from mhvp.letting.broker_provider import (
    BrokerAmbiguousMatchError,
    BrokerListingPayload,
    BrokerUpstreamError,
    DocumentationRequiredError,
    FakeBrokerProvider,
    FlowfactBrokerProvider,
    OnOfficeBrokerProvider,
    PropstackBrokerProvider,
    get_provider,
)

PAYLOAD = BrokerListingPayload(
    external_ref="obj-1",
    title="Schöne Wohnung",
    kind="rental",
    object_type="wohnung",
    price="700.00",
    living_area_sqm="55",
    rooms="2",
    status="active",
)

ACCESS_KEY = "test-access-key"


def _jwt(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


@pytest.mark.parametrize("cls", [PropstackBrokerProvider, OnOfficeBrokerProvider])
def test_undocumented_providers_refuse_every_operation(cls: type) -> None:
    """No provider has a verified endpoint contract yet (rule 0.1.3); every operation must
    raise DocumentationRequiredError rather than guess a request."""

    provider = cls()
    with pytest.raises(DocumentationRequiredError):
        provider.create_or_update_listing(PAYLOAD)
    with pytest.raises(DocumentationRequiredError):
        provider.set_status("ext-1", "active")
    with pytest.raises(DocumentationRequiredError):
        provider.fetch_prospects("ext-1")


def test_flowfact_still_refuses_set_status_and_fetch_prospects() -> None:
    """The BrokerProvider interface has no schema parameter these operations would need
    (docs/rules/M28-02.md open point); only create_or_update_listing is implemented."""
    provider = FlowfactBrokerProvider(access_key=ACCESS_KEY)
    with pytest.raises(DocumentationRequiredError):
        provider.set_status("ent-1", "active")
    with pytest.raises(DocumentationRequiredError):
        provider.fetch_prospects("ent-1")


def test_flowfact_without_access_key_or_schema_raises_documentation_required() -> None:
    with pytest.raises(DocumentationRequiredError):
        FlowfactBrokerProvider().create_or_update_listing(PAYLOAD)
    with pytest.raises(DocumentationRequiredError):
        FlowfactBrokerProvider(access_key=ACCESS_KEY).create_or_update_listing(PAYLOAD)


def test_flowfact_creates_an_entity_with_confirmed_field_names() -> None:
    token = _jwt(int(time.time()) + 1800)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin-token-service/public/adminUser/authenticate":
            assert request.headers["token"] == ACCESS_KEY
            return httpx.Response(200, text=token)
        if request.url.path == "/search-service/schemas/wohnung_miete":
            return httpx.Response(200, json={"entries": [], "totalCount": 0})
        if request.url.path == "/entity-service/schemas/wohnung_miete":
            seen["body"] = json.loads(request.content)
            seen["version"] = request.headers.get("x-ff-version")
            return httpx.Response(201, json={"id": "ent-1"})
        raise AssertionError(f"unexpected call {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FlowfactBrokerProvider(
        access_key=ACCESS_KEY, settings={"schema_rental": "wohnung_miete"}, http=http
    )
    payload = BrokerListingPayload(
        external_ref="obj-1",
        title="Schöne Wohnung",
        kind="rental",
        object_type="wohnung",
        price="700.00",
        living_area_sqm="55",
        rooms="2",
        status="active",
        street="Musterweg",
        house_number="1",
        postal_code="12345",
        city="Musterstadt",
    )
    result = provider.create_or_update_listing(payload)
    assert result.provider_entity_id == "ent-1"
    assert result.status == "synced"
    assert seen["version"] == "2"
    assert seen["body"]["identifier"] == {"values": ["obj-1"]}
    assert seen["body"]["headline"] == {"values": ["Schöne Wohnung"]}
    assert seen["body"]["rent"] == {"values": [700.0]}
    assert seen["body"]["addresses"]["values"][0]["street"] == "Musterweg 1"


def test_flowfact_reuses_a_single_exact_match_instead_of_creating() -> None:
    token = _jwt(int(time.time()) + 1800)
    created = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin-token-service/public/adminUser/authenticate":
            return httpx.Response(200, text=token)
        if request.url.path == "/search-service/schemas/wohnung_miete":
            entry = {"id": "ent-existing", "identifier": {"values": ["obj-1"]}}
            return httpx.Response(200, json={"entries": [entry], "totalCount": 1})
        if request.url.path == "/entity-service/schemas/wohnung_miete":
            created["count"] += 1
            return httpx.Response(201, json={"id": "ent-new"})
        raise AssertionError(f"unexpected call {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FlowfactBrokerProvider(
        access_key=ACCESS_KEY, settings={"schema_rental": "wohnung_miete"}, http=http
    )
    result = provider.create_or_update_listing(PAYLOAD)
    assert result.provider_entity_id == "ent-existing"
    assert created["count"] == 0


def test_flowfact_more_than_one_match_raises_ambiguous() -> None:
    token = _jwt(int(time.time()) + 1800)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin-token-service/public/adminUser/authenticate":
            return httpx.Response(200, text=token)
        if request.url.path == "/search-service/schemas/wohnung_miete":
            entry = {"id": "dup", "identifier": {"values": ["obj-1"]}}
            return httpx.Response(200, json={"entries": [entry, entry], "totalCount": 2})
        raise AssertionError(f"unexpected call {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FlowfactBrokerProvider(
        access_key=ACCESS_KEY, settings={"schema_rental": "wohnung_miete"}, http=http
    )
    with pytest.raises(BrokerAmbiguousMatchError):
        provider.create_or_update_listing(PAYLOAD)


def test_flowfact_rejected_access_key_raises_upstream_error_without_leaking_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Credentials invalid")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FlowfactBrokerProvider(
        access_key=ACCESS_KEY, settings={"schema_rental": "wohnung_miete"}, http=http
    )
    with pytest.raises(BrokerUpstreamError) as excinfo:
        provider.create_or_update_listing(PAYLOAD)
    assert ACCESS_KEY not in str(excinfo.value)


def test_get_provider_unknown_name_raises() -> None:
    with pytest.raises(DocumentationRequiredError):
        get_provider("does-not-exist")


def test_fake_provider_is_idempotent_and_deterministic() -> None:
    provider = FakeBrokerProvider()
    first = provider.create_or_update_listing(PAYLOAD)
    second = provider.create_or_update_listing(PAYLOAD)
    assert first.provider_entity_id == second.provider_entity_id

    updated = provider.set_status(first.provider_entity_id, "withdrawn")
    assert updated.status == "withdrawn"
    assert updated.provider_entity_id == first.provider_entity_id

    assert provider.fetch_prospects(first.provider_entity_id) == []
