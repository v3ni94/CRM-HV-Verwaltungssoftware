"""GAM-402 guard: every foreign key on contact.id is classified for the access export."""

import importlib
import pkgutil

import mhvp
from mhvp.contacts import access_export_sources as more
from mhvp.core.db.base import Base


def _load_models() -> None:
    for mod in pkgutil.walk_packages(mhvp.__path__, "mhvp."):
        if mod.name.endswith((".models", ".telephony")):
            importlib.import_module(mod.name)


def test_every_contact_foreign_key_is_classified() -> None:
    _load_models()
    known = more.classified()
    missing = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name != "contact" or fk.column.name != "id":
                    continue
                key = (table.name, column.name)
                if key in known:
                    continue
                if table.name.startswith("contact_") and column.name == "contact_id":
                    continue  # own child tables, base export
                missing.append(key)
    assert not missing, f"Auskunftsexport: Quelle nicht eingeordnet: {missing}"


def test_sources_have_existing_columns_and_switches() -> None:
    _load_models()
    from mhvp.contacts.access_export import SOURCE_SWITCHES

    keys = [s.key for s in more.FURTHER_SOURCES]
    assert len(keys) == len(set(keys))
    for src in more.FURTHER_SOURCES:
        assert src.switch in SOURCE_SWITCHES
        table = Base.metadata.tables[src.table]
        for name in (src.column, *src.fields):
            assert name in table.columns, (src.table, name)
        assert not any("hash" in f or "fingerprint" in f or f.endswith("_enc") for f in src.fields)
