# mhvp.receipts

Belegeingang (M14, backlog item 15): AI extraction of incoming invoices as a reviewable draft.
Plan: `docs/plans/M14-belegeingang.md`. Specification: docs/MASTER-PROMPT.md 6.4, 9, rules
0.1.6, 0.1.7, 0.1.13.

* Files: `models.py` (`ReceiptDraft`), `masking.py` (masking before the provider call, IBAN
  candidates), `extraction.py` (prepare, materialize, per-field confidence, property match),
  `schemas.py`, `routers.py` (`/api/v1/receipts`). Migration `0080_receipt_draft`.
* A draft is never an invoice and never a posting. `confirm` creates an `Invoice` as an open,
  unposted draft (review not started) from the values the reviewer entered, through the same
  `mhvp.ai.imports.apply_invoice` path as the chat proposal; `reject` closes the draft without
  one. Posting and payment release stay in `mhvp.accounting` (6.9.9).
* Masking (rule 0.1.13): the provider receives only the masked text (IBAN, BIC, e-mail, phone,
  titled person names replaced by placeholders; company names kept, since the supplier name is
  the extraction target). The run's ``document_ids`` are empty so the gateway never re-reads
  the unmasked original; the draft stores the masked excerpt for verification.
* IBAN (rule 0.1.6): the model never sees an IBAN. Candidates are detected deterministically in
  the unmasked text, stored encrypted, shown masked (`DE89 ... 3000`, checksum flag) and never
  written to the invoice unless the reviewer types the IBAN and sends ``iban_confirmed=true``.
* Confidence per field (`extraction.field_confidences`): derived from the model's overall
  confidence and deterministic checks (parseable date and amount, net + vat = gross, warnings
  naming the field, currency assumed). It is a review aid, not proof (rule 0.1.6).
* Property reference: `property_number_guess` is matched locally against the tenant's
  properties (number 0.9, street and house number 0.7, street 0.5) as a suggestion only.
* Execution: inline with ``ai_inline`` (tests), otherwise Celery task ``mhvp.ai.run`` on the
  ``io`` queue; the finished run is folded into the draft on the next read (`materialize`).
* API: `POST /receipts/drafts` (document, source upload or mail_attachment with message id),
  `POST /receipts/drafts/paperless`, `GET /receipts/drafts?status=open|...`,
  `GET /receipts/drafts/{id}`, `POST .../confirm`, `POST .../reject`. Permissions
  ``accounting:read`` and ``accounting:create``.
* CRM: `/rechnungen/belegeingang` (`components/receipts/ReceiptIntake.tsx`).
* Tests: `tests/unit/test_m14_receipt_drafts.py`, `tests/integration/test_m14_receipt_drafts.py`,
  offline evaluation `tests/ai_eval/extract_invoice/cases.jsonl` (`make ai-eval`).
