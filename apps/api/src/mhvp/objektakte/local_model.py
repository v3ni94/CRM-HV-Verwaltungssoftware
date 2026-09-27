"""Adapter for objektakte's local classification model (M35 technical preparation, open
question M35-01, docs/plans/M35-objektakte-uebernahme.md sections 2 and 3.2).

objektakte stage 2 (``src/apps/classification/stage2.py`` there) is a scikit-learn pipeline
(TF-IDF character 3-5 grams and word 1-2 grams, logistic regression) saved with joblib under
``<DATA_DIR>/models/<version>/``: ``model_a.joblib`` (main category, labels ``01`` to ``05`` and
``nicht_objektbezogen``), optional ``model_b.joblib`` (subfolder plus type in 05) and
``labels.json``. The input is the document text (whitespace collapsed, first
``classification.text_max_chars`` = 4000 characters by default) prefixed with context tokens
such as ``__mgmt_weg__``; without those tokens the model still answers, with slightly lower
confidence (checked against nothing here: the accuracy of a model whose training data the
CRM does not hold is exactly what M35-01 asks the operator to decide).

This adapter:

- loads the artifact only when the tenant flag
  ``TenantSettings.objektakte_classification["local_model"]["enabled"]`` is true (default
  off) and the version directory exists; joblib and scikit-learn are optional imports, their
  absence is reported as ``unavailable`` (they are not CRM dependencies today; adding them
  and pinning the version objektakte trained with is part of the decision M35-01),
- produces a **proposal only**: ``document.source_meta["classification"]`` with
  ``stage="local_model"`` and, when an open review case exists, ``case.candidates
  ["local_model"]``; never ``document.category_id`` (rule 0.1.6, same contract as the rule
  stage and the AI stage),
- maps a label to a CRM category by ``DocumentCategory.code`` when one matches, otherwise
  leaves ``category_id`` empty and keeps the raw label.

``Predictor`` is a small protocol so tests inject a fake model; ``JoblibPredictor`` is the
production loader.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from mhvp.documents.models import Document, DocumentCategory
from mhvp.objektakte.models import DocumentReviewCase, ReviewCaseStatus
from mhvp.platform.models import TenantSettings

log = logging.getLogger(__name__)

FLAG_KEY = "local_model"
TEXT_MAX_CHARS = 4000
CATEGORY_LABELS = ("01", "02", "03", "04", "05", "nicht_objektbezogen")
_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


@dataclass(frozen=True)
class ScoredLabel:
    label: str
    p: float


class Predictor(Protocol):
    version: str

    def predict(self, text: str) -> list[ScoredLabel]: ...


@dataclass(frozen=True)
class LocalModelFlag:
    enabled: bool
    version: str | None
    management_token: bool = True


def read_flag(settings: TenantSettings | None) -> LocalModelFlag:
    raw = ((settings.objektakte_classification if settings else {}) or {}).get(FLAG_KEY) or {}
    version = raw.get("version")
    if version is not None and not _VERSION_RE.match(str(version)):
        version = None
    return LocalModelFlag(
        enabled=bool(raw.get("enabled", False)),
        version=str(version) if version else None,
        management_token=bool(raw.get("management_token", True)),
    )


def artifact_status(models_dir: str | Path, version: str | None) -> dict[str, Any]:
    """What the CRM can say about the artifact without loading it (for the settings page and
    the decision M35-01): directory present, files present, joblib importable, labels."""
    base = Path(models_dir)
    status: dict[str, Any] = {
        "models_dir": str(base),
        "version": version,
        "directory_exists": False,
        "model_a": False,
        "model_b": False,
        "labels": None,
        "runtime_available": _runtime_available(),
    }
    if not version:
        versions = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
        status["available_versions"] = versions
        return status
    target = base / version
    status["directory_exists"] = target.is_dir()
    if target.is_dir():
        status["model_a"] = (target / "model_a.joblib").is_file()
        status["model_b"] = (target / "model_b.joblib").is_file()
        labels_file = target / "labels.json"
        if labels_file.is_file():
            try:
                status["labels"] = json.loads(labels_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                status["labels"] = "unreadable"
    return status


def _runtime_available() -> bool:
    try:
        import joblib  # type: ignore[import-not-found]  # noqa: F401
        import sklearn  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


class JoblibPredictor:
    """Production loader; raises ``LocalModelUnavailableError`` when the artifact or runtime is
    missing. The unpickled object must offer ``predict_proba`` and ``classes_`` (scikit-learn
    pipeline); anything else is refused."""

    def __init__(self, version: str, artifact_dir: Path) -> None:
        try:
            import joblib
        except ImportError as exc:
            raise LocalModelUnavailableError("joblib/scikit-learn nicht installiert") from exc
        path = artifact_dir / "model_a.joblib"
        if not path.is_file():
            raise LocalModelUnavailableError("model_a.joblib fehlt")
        self.version = version
        self._model = joblib.load(path)
        if not hasattr(self._model, "predict_proba") or not hasattr(self._model, "classes_"):
            raise LocalModelUnavailableError("Artefakt ist kein scikit-learn-Klassifikator")

    def predict(self, text: str) -> list[ScoredLabel]:
        probs = self._model.predict_proba([text])[0]
        ranked = sorted(
            zip(self._model.classes_, probs, strict=True), key=lambda pair: -float(pair[1])
        )
        return [ScoredLabel(str(label), float(p)) for label, p in ranked]


class LocalModelUnavailableError(Exception):
    """Safe message for the API (no path of another tenant, no traceback)."""


def input_text(text: str | None, *, management_type: str | None = None) -> str:
    """objektakte ``input_text``: context tokens then whitespace collapsed text, capped."""
    tokens = [f"__mgmt_{management_type}__"] if management_type else []
    body = " ".join((text or "").split())[:TEXT_MAX_CHARS]
    return " ".join([*tokens, body]).strip()


def load_predictor(models_dir: str | Path, flag: LocalModelFlag) -> Predictor:
    if not flag.enabled:
        raise LocalModelUnavailableError("Lokales Modell ist für diesen Mandanten ausgeschaltet")
    if not flag.version:
        raise LocalModelUnavailableError("Keine Modellversion eingestellt")
    return JoblibPredictor(flag.version, Path(models_dir) / flag.version)


async def propose_with_local_model(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document: Document,
    predictor: Predictor,
    *,
    management_type: str | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Run the model over the document text and record the result as a proposal. Returns the
    proposal dict (also stored on the document and on the open review case, if any)."""
    if not document.ocr_text:
        raise LocalModelUnavailableError("Dokument hat keinen erkannten Text")
    scored = predictor.predict(input_text(document.ocr_text, management_type=management_type))
    if not scored:
        raise LocalModelUnavailableError("Modell lieferte kein Ergebnis")
    codes = {
        row.code: row.id
        for row in (
            await session.scalars(
                select(DocumentCategory).where(DocumentCategory.tenant_id == tenant_id)
            )
        ).all()
    }
    candidates = [
        {
            "label": item.label,
            "category_id": str(codes[item.label]) if item.label in codes else None,
            "confidence": round(item.p, 4),
        }
        for item in scored[:top_n]
    ]
    proposal = {
        "stage": "local_model",
        "status": "proposal",
        "model_version": predictor.version,
        "document_class": candidates[0]["label"],
        "category": candidates[0]["category_id"],
        "confidence": candidates[0]["confidence"],
        "candidates": candidates,
    }
    meta = dict(document.source_meta or {})
    meta["classification"] = {**(meta.get("classification") or {}), **proposal}
    document.source_meta = meta
    flag_modified(document, "source_meta")

    case = await session.scalar(
        select(DocumentReviewCase).where(
            DocumentReviewCase.tenant_id == tenant_id,
            DocumentReviewCase.document_id == document.id,
            DocumentReviewCase.status == ReviewCaseStatus.OPEN,
        )
    )
    if case is not None:
        case.candidates = {**(case.candidates or {}), "local_model": proposal}
        flag_modified(case, "candidates")
    await session.flush()
    return proposal
