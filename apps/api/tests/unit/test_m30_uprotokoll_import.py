"""Parser for the U-Protokoll mysqldump export (M30 stage 4): no SQL is executed, only
`INSERT INTO ... VALUES (...);` statements are read. A small synthetic dump built from
`database/migrations/001_create_schema.sql` of v3ni94/UProtkoll stands in for a real export
(rule 0.1.9: no real productive data in the repository)."""

from datetime import date, time
from decimal import Decimal

from mhvp.handover import uprotokoll_import as importer

DUMP = r"""
-- MariaDB dump 10.19
SET NAMES utf8mb4;
/* multi
   line comment, ignored */
INSERT INTO `properties` (`id`, `street`, `house_number`, `postal_code`, `city`, `label`)
VALUES (1,'Musterstraße','12','40721','Hilden','Haus Muster');

INSERT INTO `protocols` (`id`, `protocol_number`, `protocol_type`, `status`, `version`,
`property_id`, `street`, `house_number`, `postal_code`, `city`, `handover_date`,
`handover_start`, `internal_note`, `hide_time_information`)
VALUES
(101,'UP-000101','rental','completed',1,1,'Musterstraße','12','40721','Hilden',
 '2026-01-15','09:30:00','Schlüssel doppelt vorhanden, Rücksprache mit Eigentümer O''Brien',0),
(102,'UP-000102','general','draft',1,NULL,'Andere Str.','3','12345','Nirgendwo',NULL,NULL,NULL,1);

INSERT INTO `protocol_participants` (`id`,`protocol_id`,`role`,`first_name`,`last_name`,
`email`,`sort_order`)
VALUES (501,101,'moving_out','Erika','Musterfrau','erika@example.test',0),
       (502,101,'moving_in','Max','Mustermann',NULL,1);

INSERT INTO `protocol_meters` (`id`,`protocol_id`,`meter_type`,`meter_number`,`meter_value`,
`unit`,`reading_date`)
VALUES (701,101,'electricity','12345678','04512.7','kWh','2026-01-15');

INSERT INTO `protocol_notes` (`id`,`protocol_id`,`category`,`text`,`is_internal`)
VALUES (901,101,'hint','Zähler schwer zugänglich',0);

INSERT INTO `protocol_files` (`id`,`protocol_id`,`file_category`,`original_filename`,
`stored_filename`,`storage_path`,`mime_type`,`sha256`,`is_internal`)
VALUES (1201,101,'photo','flur.jpg','a1b2.jpg','protocols/101/a1b2.jpg','image/jpeg',
 'deadbeef00000000000000000000000000000000000000000000000000000001',0);

INSERT INTO `users` (`id`,`username`,`email`,`password_hash`,`role`)
VALUES (1,'admin','admin@example.test','x','admin');
"""


def test_parse_dump_reads_every_table() -> None:
    tables = importer.parse_dump(DUMP)
    assert {
        "properties",
        "protocols",
        "protocol_participants",
        "protocol_meters",
        "protocol_notes",
        "protocol_files",
        "users",
    } <= set(tables)
    assert len(tables["protocols"]) == 2
    assert len(tables["protocol_participants"]) == 2


def test_parse_dump_handles_quotes_escapes_and_null() -> None:
    tables = importer.parse_dump(DUMP)
    first, second = tables["protocols"]
    assert first["protocol_number"] == "UP-000101"
    assert "O'Brien" in first["internal_note"]
    assert second["property_id"] is None
    assert second["handover_date"] is None
    assert first["hide_time_information"] == 0
    assert second["hide_time_information"] == 1


def test_parse_dump_ignores_comments() -> None:
    tables = importer.parse_dump(DUMP)
    # the block comment and the leading -- line must not become part of any value
    assert not any("multi" in str(v) for row in tables["protocols"] for v in row.values())


def test_parse_dump_skips_malformed_statement_without_raising() -> None:
    broken = DUMP + "\nINSERT INTO `protocol_keys` (`id`,`protocol_id`) VALUES (1,2,3);\n"
    tables = importer.parse_dump(broken)
    assert tables.get("protocol_keys", []) == []


def test_coerce_typed_conversions() -> None:
    assert importer._to_date("2026-01-15") == date(2026, 1, 15)
    assert importer._to_date(None) is None
    assert importer._to_time("09:30:00") == time(9, 30, 0)
    assert importer._to_decimal("04512.7") == Decimal("4512.7")
    assert importer._to_decimal(None) is None
    assert importer._to_bool(1) is True
    assert importer._to_bool(0) is False
    assert importer._to_bool("0") is False


async def test_build_plan_reports_counts_and_unmatched_objects() -> None:
    tables = importer.parse_dump(DUMP)

    class _Scalars:
        def all(self) -> list[str]:
            return []

    class _Session:
        async def scalars(self, _query: object) -> _Scalars:
            return _Scalars()

        async def scalar(self, _query: object) -> None:
            return None

    import uuid

    plan = await importer.build_plan(_Session(), uuid.uuid4(), tables)  # type: ignore[arg-type]
    assert plan.counts["protocols"] == 2
    # property_id=1 exists in the dump but no CRM property matches in this fake session
    assert plan.unmatched_objects == 1
    assert plan.duplicates == 0
    assert len(plan.protocols) == 2


def test_import_result_serializes_counts() -> None:
    result = importer.ImportResult(created={"protocols": 2}, skipped_duplicates=1)
    data = result.as_dict()
    assert data["created"] == {"protocols": 2}
    assert data["skipped_duplicates"] == 1
