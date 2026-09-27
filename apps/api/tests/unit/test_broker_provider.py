"""Unit tests for `mhvp.letting.broker_provider` (M28-01 stage 3)."""

import pytest

from mhvp.letting.broker_provider import (
    BrokerListingPayload,
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


@pytest.mark.parametrize(
    "cls", [FlowfactBrokerProvider, PropstackBrokerProvider, OnOfficeBrokerProvider]
)
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
