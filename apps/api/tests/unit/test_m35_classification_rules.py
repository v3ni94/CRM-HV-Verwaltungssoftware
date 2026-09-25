"""M35 Stufe 3, rule stage (docs/rules/M35-02.md): pattern matching in isolation, no DB."""

import uuid
from datetime import UTC, datetime

from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus
from mhvp.objektakte.classification import _match, _text_field
from mhvp.objektakte.models import ClassificationPatternType, ObjektakteClassificationRule


def _doc(**overrides: object) -> Document:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "title": "Test",
        "filename": "verwalterbestellung_2026.pdf",
        "mime_type": "application/pdf",
        "size": 10,
        "sha256": "a" * 64,
        "storage": StorageKind.MINIO,
        "storage_ref": "ref",
        "ocr_text": "Bestellung zum Verwalter der WEG",
        "text_status": TextStatus.EXTRACTED,
        "source": DocumentSource.UPLOAD,
        "visibility": [],
        "source_meta": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Document(**defaults)


def _rule(
    pattern_type: ClassificationPatternType, pattern_value: str
) -> ObjektakteClassificationRule:
    return ObjektakteClassificationRule(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="test",
        pattern_type=pattern_type,
        pattern_value=pattern_value,
        priority=100,
        active=True,
        confidence=0.9,
    )


def test_filename_regex_matches_case_insensitively() -> None:
    rule = _rule(ClassificationPatternType.FILENAME_REGEX, r"verwalterbestellung")
    doc = _doc(filename="Verwalterbestellung_2026.PDF")
    assert _match(rule, doc) is not None


def test_filename_regex_no_match() -> None:
    rule = _rule(ClassificationPatternType.FILENAME_REGEX, r"kuendigung")
    doc = _doc()
    assert _match(rule, doc) is None


def test_text_keyword_matches_reference_r05_ford_001() -> None:
    rule = _rule(ClassificationPatternType.TEXT_KEYWORD, r"forderungsaufstellung|forderungskonto")
    doc = _doc(ocr_text="Anbei die Forderungsaufstellung zum Konto 12/34")
    assert _match(rule, doc) == "Forderungsaufstellung"


def test_text_keyword_no_ocr_text_never_matches() -> None:
    rule = _rule(ClassificationPatternType.TEXT_KEYWORD, r"forderungsaufstellung")
    doc = _doc(ocr_text=None)
    assert _match(rule, doc) is None


def test_sender_domain_reads_source_meta() -> None:
    rule = _rule(ClassificationPatternType.SENDER_DOMAIN, r"@hausverwaltung-fremd\.de$")
    doc = _doc(source_meta={"sender_email": "buero@hausverwaltung-fremd.de"})
    assert _match(rule, doc) is not None
    assert _text_field(ClassificationPatternType.SENDER_DOMAIN, _doc(source_meta=None)) is None


def test_drive_folder_reads_source_meta() -> None:
    rule = _rule(ClassificationPatternType.DRIVE_FOLDER, r"^05_Eigentuemer")
    doc = _doc(source_meta={"drive_folder_path": "05_Eigentuemer/Musterfrau"})
    assert _match(rule, doc) is not None


def test_invalid_regex_never_matches_instead_of_raising() -> None:
    rule = _rule(ClassificationPatternType.FILENAME_REGEX, r"(unbalanced[")
    doc = _doc()
    assert _match(rule, doc) is None
