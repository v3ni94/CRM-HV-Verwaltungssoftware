"""M35-01: local model adapter, DB free parts (flag, input text, artifact status)."""

from __future__ import annotations

import json
from pathlib import Path

from mhvp.objektakte import local_model


class _Settings:
    def __init__(self, value: dict[str, object]) -> None:
        self.objektakte_classification = value


def test_flag_default_off_and_version_validated() -> None:
    assert local_model.read_flag(None) == local_model.LocalModelFlag(False, None)
    assert local_model.read_flag(_Settings({})).enabled is False  # type: ignore[arg-type]
    flag = local_model.read_flag(
        _Settings({"local_model": {"enabled": True, "version": "2026-09-01"}})  # type: ignore[arg-type]
    )
    assert flag.enabled is True
    assert flag.version == "2026-09-01"
    bad = local_model.read_flag(
        _Settings({"local_model": {"enabled": True, "version": "../etc"}})  # type: ignore[arg-type]
    )
    assert bad.version is None


def test_input_text_matches_objektakte_shape() -> None:
    text = local_model.input_text("  Hallo\n\nWelt  " + "x" * 5000, management_type="hoa")
    assert text.startswith("__mgmt_hoa__ Hallo Welt ")
    assert len(text) <= local_model.TEXT_MAX_CHARS + len("__mgmt_hoa__ ")
    assert local_model.input_text(None) == ""


def test_artifact_status_reports_files_and_versions(tmp_path: Path) -> None:
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / "model_a.joblib").write_bytes(b"x")
    (tmp_path / "v1" / "labels.json").write_text(json.dumps({"a": ["01", "02"]}))
    listing = local_model.artifact_status(tmp_path, None)
    assert listing["available_versions"] == ["v1"]
    status = local_model.artifact_status(tmp_path, "v1")
    assert status["directory_exists"]
    assert status["model_a"]
    assert not status["model_b"]
    assert status["labels"] == {"a": ["01", "02"]}
    assert isinstance(status["runtime_available"], bool)
    missing = local_model.artifact_status(tmp_path, "v2")
    assert missing["directory_exists"] is False


def test_load_predictor_refuses_when_flag_off_or_no_version(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(local_model.LocalModelUnavailableError):
        local_model.load_predictor(tmp_path, local_model.LocalModelFlag(False, "v1"))
    with pytest.raises(local_model.LocalModelUnavailableError):
        local_model.load_predictor(tmp_path, local_model.LocalModelFlag(True, None))
    with pytest.raises(local_model.LocalModelUnavailableError):
        local_model.load_predictor(tmp_path, local_model.LocalModelFlag(True, "v1"))
