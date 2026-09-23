"""Schema names in the OpenAPI document must stay stable for the generated client: a new model
with an existing class name renames both to module paths and breaks the frontend (M11 CI)."""

import json
from pathlib import Path

KNOWN = {
    "mhvp__ai__schemas__ProviderIn",
    "mhvp__ai__schemas__ProviderOut",
    "mhvp__contacts__schemas__BankAccountIn",
    "mhvp__contacts__schemas__BankAccountOut",
    "mhvp__core__auth__routers__TenantOut",
    "mhvp__platform__schemas__TenantOut",
    "mhvp__properties__schemas__BankAccountIn",
    "mhvp__properties__schemas__BankAccountOut",
    "mhvp__properties__schemas__ProviderIn",
    "mhvp__properties__schemas__ProviderOut",
}


def test_no_new_schema_name_collisions() -> None:
    spec = json.loads((Path(__file__).parents[2] / "openapi.json").read_text())
    prefixed = {name for name in spec["components"]["schemas"] if name.startswith("mhvp__")}
    assert prefixed <= KNOWN, sorted(prefixed - KNOWN)
