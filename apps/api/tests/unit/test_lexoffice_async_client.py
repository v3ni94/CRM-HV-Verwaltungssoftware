"""Async Lexware Office client (rule INT-LEXO-01): documented parameters only, filter
encoding, error parsers of both formats without free text, Retry-After, organisation
mismatch, binary download with Accept variants. Fake transport only."""

from __future__ import annotations

import httpx
import pytest

from mhvp.integrations import lexoffice_async as la
from mhvp.integrations.lexoffice_ext import ratelimit
from tests.lexoffice_fake import BASE, PDF, FakeLexoffice


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeLexoffice:
    server = FakeLexoffice()
    monkeypatch.setattr(la, "TRANSPORT", server.transport())
    monkeypatch.setattr(ratelimit, "SLOT_SECONDS", 0.0)
    ratelimit.reset_local()
    return server


def _client(fake: FakeLexoffice, organization_id: str | None = None) -> la.LexofficeAsyncClient:
    return la.LexofficeAsyncClient(
        la.AsyncCredentials(api_key=fake.api_key, base_url=BASE, organization_id=organization_id)
    )


async def test_voucherlist_sends_mandatory_and_documented_params(fake: FakeLexoffice) -> None:
    fake.add_invoice(voucher_number="RE-1019")
    body = await _client(fake).list_voucherlist(
        "invoice,creditnote", "any", voucher_number="RE-1019", updated_date_from="2026-09-01"
    )
    query = fake.requests[-1]["query"]
    assert query["voucherType"] == ["invoice,creditnote"]
    assert query["voucherStatus"] == ["any"]
    assert query["updatedDateFrom"] == ["2026-09-01"]
    assert "updatedAtFrom" not in query
    assert body["content"][0]["voucherNumber"] == "RE-1019"


async def test_contact_filters_are_encoded_and_short_filters_refused(fake: FakeLexoffice) -> None:
    client = _client(fake)
    await client.list_contacts(name="Müller & Söhne <GmbH>")
    assert fake.requests[-1]["query"]["name"] == ["Müller &amp; Söhne &lt;GmbH&gt;"]
    with pytest.raises(la.LexofficeValidationError):
        await client.list_contacts(email="ab")
    assert fake.count("GET", "/v1/contacts") == 1


async def test_error_parsers_drop_free_text(fake: FakeLexoffice) -> None:
    client = _client(fake)
    with pytest.raises(la.LexofficeRejectedError) as legacy:
        await client.create_contact({"company": {"name": ""}, "roles": {"customer": {}}})
    assert legacy.value.issues == [la.Issue("company.name", "validation_failure", "missing_entity")]
    assert "validation_failure" in legacy.value.redacted()
    with pytest.raises(la.LexofficeRejectedError) as regular:
        await client._json_request("GET", "/v1/voucherlist", params={"voucherType": "invoice"})
    assert regular.value.issues == [la.Issue("voucherStatus", "NOTNULL")]
    assert "must not be null" not in regular.value.redacted()
    assert regular.value.trace_id == "t-400"


async def test_status_mapping(fake: FakeLexoffice) -> None:
    client = _client(fake)
    fake.fail_next.append((429, {"Retry-After": "120"}))
    with pytest.raises(la.LexofficeRateLimitedError) as limited:
        await client.get_profile()
    assert limited.value.retry_after == 120
    assert limited.value.retryable
    fake.fail_next.append((503, {}))
    with pytest.raises(la.LexofficeUnavailableError) as unavailable:
        await client.get_profile()
    assert unavailable.value.retryable
    assert not unavailable.value.maybe_processed
    fake.fail_next.append((504, {}))
    with pytest.raises(la.LexofficeUnavailableError) as gateway:
        await client.get_profile()
    assert gateway.value.maybe_processed
    with pytest.raises(la.LexofficeAuthError):
        await la.LexofficeAsyncClient(
            la.AsyncCredentials(api_key="wrong", base_url=BASE)
        ).get_profile()
    with pytest.raises(la.LexofficeNotFoundError):
        await client.get_contact("missing")


async def test_organization_mismatch_raised(fake: FakeLexoffice) -> None:
    with pytest.raises(la.LexofficeOrganizationMismatchError):
        await _client(fake, organization_id="other-org").get_profile()
    assert (await _client(fake, organization_id=fake.organization_id).get_profile())["companyName"]


async def test_download_accept_variants_and_draft_conflict(fake: FakeLexoffice) -> None:
    client = _client(fake)
    invoice = fake.add_invoice(voucher_number="RE-7", xrechnung=True)
    pdf = await client.download_invoice_file(invoice["id"], accept="application/pdf")
    assert pdf.content == PDF
    assert pdf.filename == "Rechnung-RE-7.pdf"
    assert fake.requests[-1]["accept"] == "application/pdf"
    xml = await client.download_invoice_file(invoice["id"], accept="*/*")
    assert xml.content_type == "application/xml"
    draft = fake.add_invoice(voucher_number="RE-8", status="draft")
    with pytest.raises(la.LexofficeConflictError):
        await client.download_invoice_file(draft["id"])
    with pytest.raises(la.LexofficeNotFoundError):
        await client.download_invoice_file("missing")


async def test_download_ceiling(monkeypatch: pytest.MonkeyPatch, fake: FakeLexoffice) -> None:
    monkeypatch.setattr(la, "MAX_DOWNLOAD_BYTES", 10)
    invoice = fake.add_invoice(voucher_number="RE-9")
    with pytest.raises(la.LexofficeUnavailableError, match="zu groß"):
        await _client(fake).download_invoice_file(invoice["id"])


async def test_create_invoice_never_sends_finalize(fake: FakeLexoffice) -> None:
    result = await _client(fake).create_invoice(
        {
            "voucherDate": "2026-09-29T00:00:00.000+02:00",
            "address": {"name": "Hardy Harter"},
            "lineItems": [
                {"quantity": 1, "unitPrice": {"netAmount": 100.0, "taxRatePercentage": 19}}
            ],
        }
    )
    assert result["id"]
    assert fake.requests[-1]["query"] == {}


def test_filename_from_disposition() -> None:
    assert la.filename_from_disposition('attachment; filename="a/b.pdf"') == "a_b.pdf"
    assert (
        la.filename_from_disposition("inline; filename*=UTF-8''Rechnung%20.pdf")
        == "Rechnung%20.pdf"
    )
    assert la.filename_from_disposition(None) is None


def test_parse_issues_ignores_args_and_additional_data() -> None:
    issues, trace = la.parse_issues(
        {
            "IssueList": [{"i18nKey": "k", "source": "s", "type": "t", "args": ["secret"]}],
            "details": [{"violation": "V", "field": "f", "message": "secret", "additionalData": 1}],
            "traceId": "abc",
        }
    )
    assert issues == [la.Issue("s", "t", "k"), la.Issue("f", "V")]
    assert trace == "abc"
    assert all("secret" not in str(i) for i in issues)


def test_sync_transport_unused_by_async_client() -> None:
    assert isinstance(FakeLexoffice().transport(), httpx.MockTransport)
