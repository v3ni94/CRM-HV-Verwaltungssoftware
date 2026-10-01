"""M34 Nachtrag 27.09.2026: which `mhvp.ai` tasks get `mask_identifiers` applied to the
assembled prompt context (`gateway.MASKED_TASKS`, 9.1 Datenschutz), and that the masking itself
still keeps names and street addresses (needed for a salutation and for extraction elsewhere)
while removing IBAN, e-mail and phone. The provider-facing integration test
(`test_m7_ai.py::test_masked_tasks_do_not_send_iban_or_email_to_the_provider`) covers the
gateway wiring; this file is the pure-logic complement (no DB, no provider)."""

from mhvp.ai import gateway
from mhvp.ai.models import AiTask
from mhvp.objektakte.masking import mask_identifiers


def test_masked_tasks_are_exactly_the_ones_that_do_not_need_raw_pii() -> None:
    expected = {
        AiTask.ANSWER_QUESTION,
        AiTask.SUMMARIZE,
        AiTask.CHECK_STATEMENT,
        AiTask.CLASSIFY_EMAIL,
        AiTask.CLASSIFY_DOCUMENT,
        AiTask.DRAFT_REPLY,
        AiTask.REPLY_DRAFT,
        AiTask.CALL_SUMMARY,
        AiTask.RENT_INCREASE_CHECK,
    }
    assert expected == gateway.MASKED_TASKS
    # Extraction and tasks that need a raw IBAN or the raw sample values stay excluded.
    assert gateway.MASKED_TASKS.isdisjoint(gateway.CHUNKED_TASKS)
    for excluded in (AiTask.EXTRACT_INVOICE, AiTask.PROPOSE_POSTING, AiTask.MAP_COLUMNS):
        assert excluded not in gateway.MASKED_TASKS


def test_mask_identifiers_removes_iban_email_phone_but_keeps_name_and_street() -> None:
    text = (
        "Max Mustermann, Musterstraße 12, 40000 Musterstadt. "
        "IBAN DE02120300000000202051. E-Mail max@example.org. Telefon 0221 1234567."
    )
    masked = mask_identifiers(text)
    assert "DE02120300000000202051" not in masked
    assert "max@example.org" not in masked
    assert "0221 1234567" not in masked
    assert "[IBAN]" in masked
    assert "[E-MAIL]" in masked
    assert "[TELEFON]" in masked
    # Documented, deliberate behaviour of mask_identifiers (names kept, contact change task and
    # now also the masked-task prompt context need the salutation); Musterstraße is untouched.
    assert "Max Mustermann" in masked
    assert "Musterstraße 12" in masked
