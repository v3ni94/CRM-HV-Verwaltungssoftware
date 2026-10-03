"""Every setting documented in infra/env.prod.example must reach the containers.

Operator report 27.09.2026: MHVP_FINTS_PRODUCT_ID was set in .env.prod but never handed to
the api and worker containers, because infra/compose.yaml passes an explicit variable list
(``x-app-env``). ``--env-file`` only feeds the substitution, not the container environment,
so a key missing from the compose files silently has no effect.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "infra" / "env.prod.example"
COMPOSE = [ROOT / "infra" / "compose.yaml", ROOT / "infra" / "compose.prod.yaml"]


def _documented_keys() -> set[str]:
    keys = set()
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#?(MHVP_[A-Z0-9_]+)=", line.strip())
        if match:
            keys.add(match.group(1))
    return keys


def test_every_documented_setting_is_wired_into_compose() -> None:
    compose = "\n".join(path.read_text(encoding="utf-8") for path in COMPOSE)
    missing = sorted(key for key in _documented_keys() if "${" + key not in compose)
    assert missing == [], f"not passed to the containers: {missing}"


def test_fints_product_id_reaches_the_app_environment() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")
    app_env = compose.split("x-app-env:", 1)[1].split("\nx-", 1)[0]
    assert "MHVP_FINTS_PRODUCT_ID: ${MHVP_FINTS_PRODUCT_ID:-}" in app_env


def test_beat_schedule_on_volume_and_heavy_worker_profile() -> None:
    """GAI-319 (AK05): beat keeps its schedule file on a named volume, the optional profile
    worker-heavy consumes exactly ai, ocr and bank, every overlay gives it an image."""
    import yaml

    base = yaml.safe_load((ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8"))
    services = base["services"]
    beat = services["beat"]
    schedule = beat["command"][beat["command"].index("--schedule") + 1]
    assert schedule.startswith("/var/lib/mhvp/beat/")
    assert "beat-schedule:/var/lib/mhvp/beat" in beat["volumes"]
    assert "beat-schedule" in base["volumes"]
    heavy = services["worker-heavy"]
    assert heavy["profiles"] == ["worker-heavy"]
    assert heavy["command"][heavy["command"].index("-Q") + 1] == "ai,ocr,bank"
    for overlay in ("compose.dev.yaml", "compose.prod.yaml"):
        text = (ROOT / "infra" / overlay).read_text(encoding="utf-8")
        assert "\n  worker-heavy:\n" in text, overlay
    dockerfile = (ROOT / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert "chown mhvp:mhvp /var/lib/mhvp/beat" in dockerfile
