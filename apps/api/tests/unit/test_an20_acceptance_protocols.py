"""GAK-403: acceptance protocols carry the annex D.3 columns; the legacy list only shrinks."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_acceptance_protocols.py"
spec = importlib.util.spec_from_file_location("check_acceptance_protocols", SCRIPT)
assert spec is not None
assert spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_template_has_all_d3_columns_and_head_fields() -> None:
    assert mod.problems(mod.ACCEPTANCE / "PROTOKOLL-ANHANG-D-VORLAGE.md") == []


def test_new_protocols_follow_d3() -> None:
    assert [p for f in mod.protocol_files() for p in mod.problems(f)] == []


def test_legacy_protocols_exist_and_still_lack_d3() -> None:
    # Ratchet: once a legacy protocol is completed, it must leave LEGACY.
    for name in mod.LEGACY:
        path = mod.ACCEPTANCE / name
        assert path.exists(), name
        assert mod.problems(path), f"{name} is complete now: remove it from LEGACY"
