"""pain.008 (SEPA Core Direct Debit, M15, rule M15-02): XML structure per the public ISO 20022
layout, one PmtInf per sequence type, control sums, structural validation, mandate checks
(rule M3-02) and the mandatory lead time. Pure functions, no database."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from defusedxml import ElementTree as SafeElementTree  # type: ignore[import-untyped]

from mhvp.accounting import direct_debit as dd
from mhvp.accounting.direct_debit_models import DirectDebitOrder, DirectDebitRun, SequenceType
from mhvp.contacts.models import (
    ContactBankAccount,
    ContactMandateStatus,
    MandateGrantedVia,
    MandateScheme,
)
from mhvp.core.problems import ProblemError

NS = {"p": dd.NAMESPACE}


def _run() -> DirectDebitRun:
    return DirectDebitRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        ledger_id=uuid.uuid4(),
        legal_entity_id=uuid.uuid4(),
        property_bank_account_id=uuid.uuid4(),
        creditor_id="DE00ZZZ00000000000",  # placeholder shape only, no claim on the real format
        creditor_name="GdWE Testhaus & Co",
        collection_date=date(2026, 10, 15),
        lead_days=6,
        message_id="MHVPDDTEST0001",
        format=dd.PAIN_FORMAT,
    )


def _order(amount: str, seq: SequenceType, e2e: str) -> DirectDebitOrder:
    return DirectDebitOrder(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        open_item_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        contact_bank_account_id=uuid.uuid4(),
        mandate_reference=f"MREF-{e2e}",
        mandate_signed_on=date(2024, 1, 10),
        mandate_scheme="core",
        sequence_type=seq,
        amount=Decimal(amount),
        debtor_name="Müller, Jörg",
        debtor_iban="DE89370400440532013000",
        debtor_iban_fingerprint="fp",
        purpose="Hausgeld Oktober 2026",
        end_to_end_id=e2e,
        due_date=date(2026, 10, 3),
    )


def test_pain008_structure_sequence_groups_and_control_sums() -> None:
    orders = [
        _order("300.00", SequenceType.RCUR, "E2E1"),
        _order("50.50", SequenceType.FRST, "E2E2"),
        _order("0.01", SequenceType.RCUR, "E2E3"),
    ]
    xml = dd.pain008(
        _run(),
        orders,
        creditor_iban="DE02120300000000202051",
        created_at=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
    )
    root = SafeElementTree.fromstring(xml)
    assert root.tag == f"{{{dd.NAMESPACE}}}Document"
    init = root.find("p:CstmrDrctDbtInitn", NS)
    assert init is not None
    header = init.find("p:GrpHdr", NS)
    assert header is not None
    assert header.findtext("p:MsgId", namespaces=NS) == "MHVPDDTEST0001"
    assert header.findtext("p:NbOfTxs", namespaces=NS) == "3"
    assert header.findtext("p:CtrlSum", namespaces=NS) == "350.51"
    infos = init.findall("p:PmtInf", NS)
    assert [i.findtext("p:PmtTpInf/p:SeqTp", namespaces=NS) for i in infos] == ["FRST", "RCUR"]
    for info in infos:
        assert info.findtext("p:PmtMtd", namespaces=NS) == "DD"
        assert info.findtext("p:PmtTpInf/p:SvcLvl/p:Cd", namespaces=NS) == "SEPA"
        assert info.findtext("p:PmtTpInf/p:LclInstrm/p:Cd", namespaces=NS) == "CORE"
        assert info.findtext("p:ReqdColltnDt", namespaces=NS) == "2026-10-15"
        assert info.findtext("p:CdtrAcct/p:Id/p:IBAN", namespaces=NS) == "DE02120300000000202051"
        assert (
            info.findtext("p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:Id", namespaces=NS)
            == "DE00ZZZ00000000000"
        )
        assert (
            info.findtext("p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:SchmeNm/p:Prtry", namespaces=NS)
            == "SEPA"
        )
    first, recurring = infos
    assert first.findtext("p:NbOfTxs", namespaces=NS) == "1"
    assert first.findtext("p:CtrlSum", namespaces=NS) == "50.50"
    assert recurring.findtext("p:NbOfTxs", namespaces=NS) == "2"
    assert recurring.findtext("p:CtrlSum", namespaces=NS) == "300.01"
    tx = first.find("p:DrctDbtTxInf", NS)
    assert tx is not None
    assert tx.findtext("p:PmtId/p:EndToEndId", namespaces=NS) == "E2E2"
    amount = tx.find("p:InstdAmt", NS)
    assert amount is not None
    assert amount.text == "50.50"
    assert amount.get("Ccy") == "EUR"
    mandate = tx.find("p:DrctDbtTx/p:MndtRltdInf", NS)
    assert mandate is not None
    assert mandate.findtext("p:MndtId", namespaces=NS) == "MREF-E2E2"
    assert mandate.findtext("p:DtOfSgntr", namespaces=NS) == "2024-01-10"
    assert tx.findtext("p:Dbtr/p:Nm", namespaces=NS) == "Mueller, Joerg"
    assert tx.findtext("p:DbtrAcct/p:Id/p:IBAN", namespaces=NS) == "DE89370400440532013000"
    assert tx.findtext("p:RmtInf/p:Ustrd", namespaces=NS) == "Hausgeld Oktober 2026"
    assert dd.validate_pain008(xml) == []


def test_validation_detects_tampered_sums_and_missing_mandate() -> None:
    xml = dd.pain008(_run(), [_order("10.00", SequenceType.FRST, "E2E9")], creditor_iban="DE02")
    text = xml.decode()
    assert "CtrlSum" in text
    tampered = text.replace("<CtrlSum>10.00</CtrlSum>", "<CtrlSum>11.00</CtrlSum>", 1)
    assert any("GrpHdr/CtrlSum" in e for e in dd.validate_pain008(tampered.encode()))
    without_mandate = text.replace("<MndtId>MREF-E2E9</MndtId>", "<MndtId></MndtId>")
    assert any("MndtId" in e for e in dd.validate_pain008(without_mandate.encode()))
    wrong_seq = text.replace("<SeqTp>FRST</SeqTp>", "<SeqTp>OOFF</SeqTp>")
    assert any("SeqTp" in e for e in dd.validate_pain008(wrong_seq.encode()))
    assert dd.validate_pain008(b"<nope>")[0].startswith("XML nicht lesbar")
    assert dd.validate_pain008(b"<Document/>")[0].startswith("Wurzelelement")


def test_empty_run_has_no_file() -> None:
    with pytest.raises(ProblemError):
        dd.pain008(_run(), [], creditor_iban="DE02")


def test_sequence_type_from_mandate_history() -> None:
    assert dd.sequence_type(0) is SequenceType.FRST
    assert dd.sequence_type(1) is SequenceType.RCUR
    assert dd.sequence_type(7) is SequenceType.RCUR


def _account(**overrides: object) -> ContactBankAccount:
    values: dict[str, object] = {
        "contact_id": uuid.uuid4(),
        "iban": "DE89370400440532013000",
        "iban_suffix": "3000",
        "iban_fingerprint": "fp",
        "valid_from": date(2020, 1, 1),
        "valid_to": None,
        "holder": "Jörg Müller",
        "sepa_enabled": True,
        "mandate_reference": "MREF-1",
        "mandate_signed_on": date(2024, 1, 10),
        "mandate_granted_via": MandateGrantedVia.BRIEF,
        "mandate_scheme": MandateScheme.CORE,
        "mandate_status": ContactMandateStatus.ACTIVE,
        "mandate_revoked_on": None,
    }
    values.update(overrides)
    return ContactBankAccount(**values)


def test_mandate_checks_block_missing_or_revoked_mandates() -> None:
    day = date(2026, 10, 15)
    assert dd.mandate_block_reason(_account(), day) is None
    assert dd.mandate_block_reason(_account(sepa_enabled=False), day) is not None
    assert "widerrufen" in str(
        dd.mandate_block_reason(
            _account(mandate_status=ContactMandateStatus.REVOKED, mandate_revoked_on=day), day
        )
    )
    assert "Mandatsreferenz" in str(dd.mandate_block_reason(_account(mandate_reference=None), day))
    assert "Erteilungsdatum" in str(dd.mandate_block_reason(_account(mandate_signed_on=None), day))
    assert "Art der" in str(dd.mandate_block_reason(_account(mandate_granted_via=None), day))
    assert "nach dem Einzugsdatum" in str(
        dd.mandate_block_reason(_account(mandate_signed_on=date(2026, 11, 1)), day)
    )
    assert "CORE" in str(dd.mandate_block_reason(_account(mandate_scheme=MandateScheme.B2B), day))
    assert "nicht mehr gültig" in str(
        dd.mandate_block_reason(_account(valid_to=date(2026, 9, 30)), day)
    )


def test_lead_time_is_mandatory_and_enforced() -> None:
    today = date(2026, 10, 1)
    dd.check_lead_time(date(2026, 10, 7), 6, today)
    with pytest.raises(ProblemError):
        dd.check_lead_time(date(2026, 10, 6), 6, today)
    with pytest.raises(ProblemError):
        dd.check_lead_time(date(2026, 10, 7), -1, today)


def test_sepa_text_restricts_character_set() -> None:
    assert dd.sepa_text("Größe & Co. „Test“", 70) == "Groesse + Co. .Test."
    assert dd.sepa_text("x" * 100, 70) == "x" * 70
    assert dd.sepa_text("", 70) == "."


def test_pre_notification_contains_amounts_date_mandate_and_creditor() -> None:
    run = _run()
    orders = [
        _order("1234.50", SequenceType.FRST, "E2E5"),
        _order("50.00", SequenceType.FRST, "E2E6"),
    ]
    text = dd.pre_notification_text(run, orders, creditor_iban_masked="DE02 **** 2051")
    assert "1.234,50 EUR" in text
    assert "Gesamtbetrag: 1.284,50 EUR" in text
    assert "15.10.2026" in text
    assert "MREF-E2E5" in text
    assert "DE00ZZZ00000000000" in text
    assert "Entwurf" in text
    assert "DE89370400440532013000" not in text  # debtor IBAN only masked
    with pytest.raises(ProblemError):
        dd.pre_notification_text(run, [], creditor_iban_masked="DE02 **** 2051")
