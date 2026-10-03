"""GAK-303: catalogue and emit sites of the work order completion agree on every path."""

from pathlib import Path

from mhvp.automation.event_catalog import DYNAMIC_VARIANTS, EVENT_CATALOG

SRC = Path(__file__).resolve().parents[2] / "src" / "mhvp"


def test_both_completion_names_are_in_the_catalogue() -> None:
    assert "work_order.completed" in EVENT_CATALOG
    produced = {name for names in DYNAMIC_VARIANTS.values() for name in names}
    assert "work_order.done" in produced  # older name, still emitted next to completed


def test_every_path_to_done_calls_the_shared_helper() -> None:
    for relative in ("tickets/routers.py", "portal/routers.py", "automation/services.py"):
        text = (SRC / relative).read_text(encoding="utf-8")
        assert "emit_completed_if_done(" in text, relative


def test_completed_is_emitted_only_in_the_shared_helper() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.name != "order_events.py"
        and 'type="work_order.completed"' in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
