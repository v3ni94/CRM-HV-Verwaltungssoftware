"""AN14-04 (GAJ-301): every module that reads or stores attachment document ids is checked
against the payment file lock, or reviewed with a reason why it cannot hand one out."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "mhvp"


# Paths that apply the check (``payment_files.`` must appear in the module).
CHECKED = {
    "communication/attachments.py": "send: ensure_released (G2)",
    "communication/draft_attachments.py": "draft: ensure_no_payment_attachment (422)",
    "communication/forwarding_dispatch.py": "forward job: releasable_ids",
    "documents/distribution.py": "distribution job: releasable_ids",
    "tickets/routers.py": "ticket mail and templates: ensure_no_payment_attachment (422)",
    "portal/notice_routers.py": "portal notices: ensure_no_payment_attachment (422)",
    "integrations/schadenstool/services.py": "damage tool handover: 422",
    "hoa/inspection.py": "inspection package: 422 (AN14-03)",
}

# Modules that touch the ids but never hand document content out of the platform.
REVIEWED = {
    "automation/services.py": "copies template ids into a draft; template ids are checked on "
    "save (tickets/routers.py) and the send path checks G2 (attachments.py)",
    "receipts/routers.py": "membership check of an inbound mail attachment",
    "accounting/routers.py": "incoming invoice attachments (input, not sent)",
    "accounting/models.py": "column definition",
    "accounting/raw_responses.py": "response model field definitions only (AP22)",
    "accounting/invoice_checks.py": "reads inbound invoice attachments for checks",
    "integrations/lexoffice_ext/invoice_copy.py": "attaches the generated invoice copy only",
    "communication/duplicates.py": "duplicate detection and merge of inbound mails",
    "communication/dispatch.py": "serial dispatch attaches the generated letter only",
    "communication/routers.py": "field list of the message output; send via attachments.py",
    "communication/receipts.py": "lookup of inbound receipts",
    "communication/invoice_intake.py": "inbound invoice intake",
    "communication/services.py": "stores attachments of inbound mails",
    "communication/suggest.py": "reads inbound attachments for AI suggestions (internal)",
    "communication/models.py": "column definition",
    "tickets/models.py": "column definition",
    "documents/payment_files.py": "the lock itself",
    "documents/intake.py": "inbound document intake",
}


def _modules() -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "attachment_document_ids" in text:
            found.add(path.relative_to(SRC).as_posix())
    return found


def test_every_attachment_path_is_checked_or_reviewed() -> None:
    unknown = _modules() - set(CHECKED) - set(REVIEWED)
    assert not unknown, f"new attachment paths need a payment file check or review: {unknown}"


def test_checked_paths_call_the_payment_file_lock() -> None:
    for rel in CHECKED:
        text = (SRC / rel).read_text(encoding="utf-8")
        assert "payment_files." in text, rel


def test_lists_have_no_stale_entries() -> None:
    for rel in [*CHECKED, *REVIEWED]:
        assert (SRC / rel).exists(), rel
