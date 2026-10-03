"""AL06-02: api, web-crm and web-portal publish no ports in the compose files."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "check_compose_exposure", ROOT / "scripts" / "check_compose_exposure.py"
)
assert _spec is not None
assert _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_repo_compose_files_are_clean() -> None:
    assert mod.main(["--root", str(ROOT)]) == 0


def test_detects_published_port_on_crm() -> None:
    text = 'services:\n  web-crm:\n    image: x\n    ports:\n      - "3000:3000"\n'
    assert mod.find_violations(text) == ["web-crm: ports"]


def test_detects_host_network_and_ignores_other_services() -> None:
    text = (
        "services:\n  api:\n    network_mode: host\n  beszel:\n    ports:\n"
        '      - "127.0.0.1:8090:8090"\nvolumes:\n  web-portal:\n'
    )
    assert mod.find_violations(text) == ["api: network_mode"]
