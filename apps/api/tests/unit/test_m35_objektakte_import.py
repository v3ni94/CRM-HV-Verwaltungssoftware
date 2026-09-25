"""Parser and mapping for the objektakte mysqldump export (M35 Stufe 1): no SQL is executed,
only `INSERT INTO ... VALUES (...);` statements are read (shared `mhvp.core.sqldump`). A small
synthetic dump built from `apps/objects/models.py` and `apps/parties/models.py` of the objektakte
repository stands in for a real export (rule 0.1.9: no real productive data in the repository)."""

import uuid

from mhvp.objektakte import objektakte_import as importer

DUMP = r"""
-- objektakte dump
INSERT INTO `objects_managedobject` (`id`,`object_number`,`name`,`street`,`house_number`,
`postal_code`,`city`,`management_type`)
VALUES (11,'623','Haus Musterstraße','Musterstraße','12','40721','Hilden','weg'),
       (12,'70000','Ausserhalb des Bereichs',NULL,NULL,NULL,NULL,'rental');

INSERT INTO `objects_unit` (`id`,`object_id`,`unit_number`,`unit_label`,`unit_type`)
VALUES (101,11,'1','EG links','apartment'),
       (102,11,'2','1. OG rechts','apartment');

INSERT INTO `parties_owner` (`id`,`type`,`first_name`,`last_name`,`company_name`,
`search_name`,`iban_last4`,`iban_hash`)
VALUES (201,'natural_person','Erika','Musterfrau',NULL,'Musterfrau, Erika','1234','deadbeef');

INSERT INTO `parties_tenant` (`id`,`type`,`first_name`,`last_name`,`company_name`,`search_name`)
VALUES (301,'natural_person','Max','Mustermann',NULL,'Mustermann, Max');

INSERT INTO `parties_ownerunitassignment` (`id`,`owner_id`,`unit_id`,`valid_from`,`valid_to`,
`share`)
VALUES (401,201,101,'2020-01-01',NULL,'1.000000');
"""


def test_parse_dump_reads_every_known_table() -> None:
    tables = importer.parse_dump(DUMP)
    assert {
        "objects_managedobject",
        "objects_unit",
        "parties_owner",
        "parties_tenant",
        "parties_ownerunitassignment",
    } <= set(tables)
    assert len(tables["objects_managedobject"]) == 2
    assert len(tables["objects_unit"]) == 2


def test_normalized_property_number_pads_and_rejects_out_of_range() -> None:
    tables = importer.parse_dump(DUMP)
    small, large = tables["objects_managedobject"]
    assert importer._normalized_property_number(small) == "623"
    assert importer._normalized_property_number(large) is None


def test_display_name_prefers_company_then_person_name() -> None:
    owner = {"company_name": "Musterfrau GmbH", "first_name": "Erika", "last_name": "Musterfrau"}
    assert importer._display_name(owner) == "Musterfrau GmbH"
    person = {"company_name": None, "first_name": "Erika", "last_name": "Musterfrau"}
    assert importer._display_name(person) == "Erika Musterfrau"


async def test_build_plan_reports_counts_and_new_properties() -> None:
    tables = importer.parse_dump(DUMP)

    class _Scalars:
        def all(self) -> list[str]:
            return []

    class _Session:
        async def scalars(self, _query: object) -> _Scalars:
            return _Scalars()

        async def scalar(self, _query: object) -> None:
            return None

    plan = await importer.build_plan(_Session(), uuid.uuid4(), tables)  # type: ignore[arg-type]
    assert plan.counts["objects_managedobject"] == 2
    # object_number "623" fits three digits and no CRM property matches -> new;
    # "70000" is out of range -> unmatched, never truncated or renumbered.
    assert plan.new_properties == 1
    assert plan.unmatched_properties == 1
    assert plan.matched_properties == 0
    assert plan.duplicates == {}


# --- Stufe 2: documents, drive nodes, review cases (row hash, status mapping) ---------------

DOCUMENT_DUMP = r"""
INSERT INTO `documents_documentcategory` (`code`,`folder_name`,`display_name`,`sort_order`)
VALUES ('02','02_Stammakte','Stammakte',20);

INSERT INTO `documents_documentsubfolder` (`id`,`category_code`,`code`,`folder_name`,
`display_name`,`sort_order`)
VALUES (51,'02','01','Vertraege','Verträge',10);

INSERT INTO `documents_documenttype` (`id`,`category_code`,`subfolder_id`,`code`,`name`,
`requires_period`,`requires_owner`,`requires_tenant`)
VALUES (71,'02',51,'vertrag_hv','Verwaltervertrag',0,1,0);

INSERT INTO `drive_drivenode` (`id`,`object_id`,`parent_node_id`,`node_kind`,`list_type`,`year`,
`drive_name`,`drive_file_id`,`drive_parent_id`,`status`)
VALUES (901,11,NULL,'main_folder',NULL,NULL,'02_Stammakte','drv-901','drv-root','active');

INSERT INTO `documents_document` (`id`,`object_id`,`sha256`,`size_bytes`,`mime_type`,
`original_name`,`current_name`,`drive_file_id`,`drive_node_id`,`status`,
`duplicate_of_document_id`,`category_code`,`subfolder_id`,`document_type_id`,`ocr_cache_key`)
VALUES (1001,11,'a1b2c3',20480,'application/pdf','vertrag.pdf','Verwaltervertrag.pdf',
'drv-file-1001',901,'ocr_done',NULL,'02',51,71,'cache-1001');

INSERT INTO `review_reviewcase` (`id`,`document_id`,`case_type`,`candidates`,`proposed_action`,
`priority`,`status`,`snoozed_until`)
VALUES (2001,1001,'category_ambiguous',NULL,NULL,80,'open',NULL);

INSERT INTO `review_reviewdecision` (`id`,`review_case_id`,`document_id`,`before_state`,
`after_state`)
VALUES (3001,2001,1001,NULL,'{"category":"02"}');
"""


def test_document_dump_parses_all_new_tables() -> None:
    tables = importer.parse_dump(DOCUMENT_DUMP)
    assert {
        "documents_documentcategory",
        "documents_documentsubfolder",
        "documents_documenttype",
        "drive_drivenode",
        "documents_document",
        "review_reviewcase",
        "review_reviewdecision",
    } <= set(tables)
    assert tables["documents_document"][0]["ocr_cache_key"] == "cache-1001"


def test_row_hash_is_stable_and_changes_with_content() -> None:
    tables = importer.parse_dump(DOCUMENT_DUMP)
    row = tables["documents_document"][0]
    first = importer._row_hash(row)
    second = importer._row_hash(dict(row))
    assert first == second
    changed = dict(row)
    changed["status"] = "filed"
    assert importer._row_hash(changed) != first


def test_document_text_status_pending_until_ocr_cache_uploaded() -> None:
    tables = importer.parse_dump(DOCUMENT_DUMP)
    row = tables["documents_document"][0]
    # status "ocr_done" implies recognised text in objektakte, but the text itself is only
    # copied by the separate OCR cache endpoint (Stufe 2 item 2), never claimed up front.
    assert importer._document_text_status(row).value == "pending"
    assert (
        importer._document_text_status(
            {"status": "registered", "mime_type": "application/pdf"}
        ).value
        == "none"
    )
