"""M7-09, M12-01: KI-Kontierung ``propose_posting`` (umgesetzt, deaktiviert bis Freigabe).
Schema-Validierung, Datenminimierung im Prompt, Ablehnung im Gateway ohne Mandantenschalter
oder ohne freigegebenen Anbieter. Erwartungswerte von Hand gesetzt."""

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from mhvp.ai import gateway, tasks
from mhvp.ai.models import AiTask
from mhvp.banking import ai_posting
from mhvp.core.problems import ErrorCodes, ProblemError

IBAN = "DE89370400440532013000"


def _valid() -> dict[str, Any]:
    return {
        "proposals": [
            {
                "transaction_ref": "T1",
                "ledger_ref": "B1",
                "account_number": "1400",
                "counterpart_role": "debtor",
                "cost_object": "104-01",
                "splits": [
                    {
                        "account_number": "1400",
                        "amount": "850.00",
                        "cost_object": "104-01",
                        "open_item_ref": "O1",
                    }
                ],
                "reasoning": "Vertragsnummer im Verwendungszweck.",
                "confidence": 0.9,
            }
        ],
        "questions": [],
    }


def _payload() -> dict[str, Any]:
    return ai_posting.build_input(
        {
            "booking_date": date(2026, 9, 1),
            "amount": Decimal("850.00"),
            "currency": "EUR",
            "purpose": f"Miete 09/2026 Vertrag V-4711 Herr Max Mustermann IBAN {IBAN} "
            "max@example.org " + "x" * 200,
            "transaction_code": "166",
            "counterpart_name": "Max Mustermann",
            "counterpart_iban": IBAN,
        },
        "WEG Musterstraße 1",
        [
            {"number": "1400", "name": "Forderungen", "category": "asset", "type": "balance"},
            {"number": "14001", "name": "Max Mustermann", "personal": True},
        ],
        [
            {
                "account_number": "14001",
                "kind": "receivable",
                "due_date": date(2026, 9, 3),
                "remaining": Decimal("850"),
                "contract_number": "V-4711",
            }
        ],
        "104",
        ["104-01"],
        redact=["Max Mustermann"],
    )


def test_schema_is_registered_and_validates() -> None:
    schema = tasks.SCHEMAS[AiTask.PROPOSE_POSTING]
    assert schema is tasks.PostingProposalResult
    assert tasks.DEFAULT_TIERS[AiTask.PROPOSE_POSTING] == "large"
    parsed = schema.model_validate(_valid())
    assert parsed.proposals[0].splits[0].open_item_ref == "O1"
    assert "proposals" in tasks.json_schema(AiTask.PROPOSE_POSTING)["properties"]


def test_schema_rejects_extra_fields_and_missing_values() -> None:
    schema = tasks.SCHEMAS[AiTask.PROPOSE_POSTING]
    extra = _valid()
    extra["proposals"][0]["book_now"] = True
    with pytest.raises(ValidationError):
        schema.model_validate(extra)
    missing = _valid()
    del missing["proposals"][0]["confidence"]
    with pytest.raises(ValidationError):
        schema.model_validate(missing)
    wrong_role = _valid()
    wrong_role["proposals"][0]["counterpart_role"] = "owner"
    with pytest.raises(ValidationError):
        schema.model_validate(wrong_role)


def test_prompt_exists_is_german_and_restricts_to_given_accounts() -> None:
    prompt = tasks.prompt(AiTask.PROPOSE_POSTING)
    assert prompt.version == "v1"
    assert "ausschließlich Kontonummern aus accounts" in prompt.system
    assert "keine IBAN" in prompt.system


def test_prompt_input_contains_no_iban_no_name_and_short_purpose() -> None:
    payload = _payload()
    text = ai_posting.prompt_text(payload)
    assert IBAN not in text
    assert IBAN[:8] not in text
    assert "Mustermann" not in text
    assert "max@example.org" not in text
    purpose = payload["transactions"][0]["purpose"]
    assert len(purpose) <= ai_posting.PURPOSE_MAX_CHARS
    assert purpose.startswith("Miete 09/2026 Vertrag V-4711")
    assert payload["accounts"][1]["name"] == ai_posting.PERSONAL_ACCOUNT
    assert "counterpart_name" not in json.dumps(payload)
    ai_posting.assert_minimised(payload, [IBAN])


def test_assert_minimised_blocks_a_leaked_iban() -> None:
    payload = _payload()
    payload["ledger"]["name"] = f"Konto {IBAN}"
    with pytest.raises(ProblemError):
        ai_posting.assert_minimised(payload, [IBAN])


def test_normalize_never_postable_and_drops_unknown_account() -> None:
    output = _valid()
    output["proposals"][0]["account_number"] = "9999"
    result = ai_posting.normalize_result(
        output, amount="850.00", accounts={"1400"}, open_items={"O1"}, cost_objects={"104-01"}
    )
    assert result["account_number"] is None
    assert result["postable"] is False
    assert len(result["splits"]) == 1


class _Session:
    """Fake session: ``scalar`` answers the tenant switch, ``scalars`` the provider configs."""

    def __init__(self, enabled: bool | None) -> None:
        self.enabled = enabled

    async def scalar(self, *_: Any, **__: Any) -> Any:
        return self.enabled

    async def scalars(self, *_: Any, **__: Any) -> Any:
        class _R:
            def all(self) -> list[Any]:
                return []

        return _R()


@pytest.mark.parametrize("enabled", [None, False])
async def test_gateway_blocks_without_tenant_switch(enabled: bool | None) -> None:
    reason = await gateway.posting_block_reason(_Session(enabled))  # type: ignore[arg-type]
    assert reason is not None
    assert reason.startswith("KI-Kontierung ist nicht freigegeben")


async def test_gateway_blocks_without_released_provider() -> None:
    reason = await gateway.posting_block_reason(_Session(True))  # type: ignore[arg-type]
    assert reason is not None
    assert reason.startswith("KI-Kontierung ist nicht freigegeben")
    assert "Anbieter" in reason


def test_problem_code_is_registered() -> None:
    code = ErrorCodes.AI_POSTING_NOT_RELEASED
    assert code.code == "MHVP-AI-0001"
    assert code.status == 403
    assert code.title == "KI-Kontierung ist nicht freigegeben"
