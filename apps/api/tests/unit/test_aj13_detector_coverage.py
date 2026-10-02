"""GAI-509 (AJ13): every platform setting that points to an external endpoint is either read by
a detector of the processing register (privacy/config_sources.py) or reviewed here with a reason.
A new endpoint setting fails this test until it is classified."""

import inspect
import re

from mhvp.core.config import Settings
from mhvp.privacy import config_sources

ENDPOINT = re.compile(r"(_url|_endpoint|_endpoint_url|_host|_base_url)$")

REVIEWED: dict[str, str] = {
    "availability_api_url": "eigene Plattform (Erreichbarkeitsprobe), kein Dritter",
    "availability_crm_url": "eigene Plattform (Erreichbarkeitsprobe), kein Dritter",
    "availability_portal_url": "eigene Plattform (Erreichbarkeitsprobe), kein Dritter",
    "database_url": "eigene Datenbank im Stack",
    "migration_database_url": "eigene Datenbank im Stack",
    "redis_url": "eigener Redis im Stack",
    "celery_broker_url": "eigener Broker im Stack",
    "api_public_url": "eigene Plattform",
    "web_crm_url": "eigene Plattform",
    "web_portal_url": "eigene Plattform",
}


def test_endpoint_settings_are_detected_or_reviewed() -> None:
    source = inspect.getsource(config_sources)
    missing = [
        name
        for name in Settings.model_fields
        if ENDPOINT.search(name) and name not in source and name not in REVIEWED
    ]
    assert missing == []


def test_reviewed_entries_still_exist() -> None:
    assert [n for n in REVIEWED if n not in Settings.model_fields] == []


def test_ops_detectors_registered() -> None:
    names = {d.__name__ for d in config_sources.DETECTORS}
    assert {"_oidc_relying_parties", "_ops"} <= names
