"""M35 Stufe 3, rule stage acceptance (docs/rules/M35-02.md): regex/keyword/folder rules
against a real document row, threshold vs. review case, and tenant separation (RLS)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentSource,
    StorageKind,
    TextStatus,
)
from mhvp.objektakte.classification import classify_document
from mhvp.objektakte.models import ClassificationPatternType, ObjektakteClassificationRule
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


async def _make_tenant(settings: Any, slug: str) -> uuid.UUID:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant, _ = await services.provision_tenant(factory, slug=slug, name=slug)
        return tenant
    finally:
        await engine.dispose()


async def _document(session: Any, tenant_id: uuid.UUID, **overrides: Any) -> Document:
    defaults: dict[str, Any] = {
        "title": "Test",
        "filename": "dokument.pdf",
        "mime_type": "application/pdf",
        "size": 10,
        "sha256": uuid.uuid4().hex + uuid.uuid4().hex,
        "storage": StorageKind.MINIO,
        "storage_ref": "ref",
        "text_status": TextStatus.EXTRACTED,
        "source": DocumentSource.UPLOAD,
        "visibility": [],
        "tenant_id": tenant_id,
    }
    defaults.update(overrides)
    doc = Document(**defaults)
    session.add(doc)
    await session.flush()
    return doc


async def _category(session: Any, tenant_id: uuid.UUID, code: str) -> DocumentCategory:
    cat = DocumentCategory(tenant_id=tenant_id, code=code, name=code)
    session.add(cat)
    await session.flush()
    return cat


async def _rule(
    session: Any,
    tenant_id: uuid.UUID,
    *,
    pattern_type: ClassificationPatternType,
    pattern_value: str,
    category_id: uuid.UUID | None = None,
    confidence: float = 0.9,
    priority: int = 100,
) -> ObjektakteClassificationRule:
    rule = ObjektakteClassificationRule(
        tenant_id=tenant_id,
        name=f"rule-{pattern_type.value}",
        pattern_type=pattern_type,
        pattern_value=pattern_value,
        target_category_id=category_id,
        target_document_type="verwalterbestellung",
        priority=priority,
        active=True,
        confidence=confidence,
    )
    session.add(rule)
    await session.flush()
    return rule


@pytest.mark.asyncio
async def test_above_threshold_yields_proposal_not_final_category(
    database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    tenant_id = await _make_tenant(settings, f"m35c-{RUN}")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            cat = await _category(session, tenant_id, "01")
            await _rule(
                session,
                tenant_id,
                pattern_type=ClassificationPatternType.FILENAME_REGEX,
                pattern_value="verwalterbestellung",
                category_id=cat.id,
                confidence=0.9,
            )
            doc = await _document(session, tenant_id, filename="Verwalterbestellung_2026.pdf")
            result = await classify_document(session, tenant_id, doc)
            assert result.applied_as_proposal
            assert doc.category_id is None  # never applied automatically (rule 0.1.6)
            classification = doc.source_meta["classification"]
            assert classification["stage"] == "rules"
            assert classification["status"] == "proposal"
            assert classification["category_id"] == str(cat.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_below_threshold_creates_review_case(database: Database, redis_url: str) -> None:
    settings = _settings(database, redis_url)
    tenant_id = await _make_tenant(settings, f"m35d-{RUN}")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            cat = await _category(session, tenant_id, "05")
            await _rule(
                session,
                tenant_id,
                pattern_type=ClassificationPatternType.TEXT_KEYWORD,
                pattern_value="forderungsaufstellung|forderungskonto",
                category_id=cat.id,
                confidence=0.5,  # below the 0.85 default threshold
            )
            doc = await _document(session, tenant_id, ocr_text="Anbei die Forderungsaufstellung")
            result = await classify_document(session, tenant_id, doc)
            assert not result.applied_as_proposal
            assert result.review_case_id is not None
            assert doc.source_meta["classification"]["status"] == "review"

            from mhvp.objektakte.models import DocumentReviewCase

            row = (
                await session.execute(
                    select(DocumentReviewCase).where(DocumentReviewCase.id == result.review_case_id)
                )
            ).scalar_one()
            assert row.stage == "rules"
            assert row.document_id == doc.id
            assert row.candidates["candidates"][0]["category_id"] == str(cat.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_no_matching_rule_creates_review_case_without_candidates(
    database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    tenant_id = await _make_tenant(settings, f"m35e-{RUN}")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            doc = await _document(session, tenant_id, filename="unbekannt.pdf")
            result = await classify_document(session, tenant_id, doc)
            assert not result.applied_as_proposal
            assert result.candidates == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_separation_rule_of_one_tenant_never_fires_for_another(
    database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    tenant_a = await _make_tenant(settings, f"m35f-a-{RUN}")
    tenant_b = await _make_tenant(settings, f"m35f-b-{RUN}")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_a) as session:
            cat = await _category(session, tenant_a, "01")
            await _rule(
                session,
                tenant_a,
                pattern_type=ClassificationPatternType.FILENAME_REGEX,
                pattern_value="verwalterbestellung",
                category_id=cat.id,
            )
        async with tenant_transaction(factory, tenant_b) as session:
            doc = await _document(session, tenant_b, filename="Verwalterbestellung_2026.pdf")
            result = await classify_document(session, tenant_b, doc)
            # Tenant B's own rule table is empty and RLS hides tenant A's row (ADR 0002).
            assert result.candidates == []
    finally:
        await engine.dispose()
