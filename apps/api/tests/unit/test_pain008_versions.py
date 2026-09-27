"""pain.008 in both public versions against the ISO 20022 XSDs (M15-01 follow-up), SeqTp
derivation and the pre-notification lead time default."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.accounting import direct_debit as dd
from mhvp.accounting.direct_debit_models import SequenceType
from mhvp.core.problems import ProblemError

XSD_DIR = Path(__file__).resolve().parents[1] / "data" / "iso20022"


def _run() -> Any:
    return SimpleNamespace(
        message_id="MSG8",
        creditor_name="GdWE Test",
        creditor_id="DE98ZZZ09999999999",
        collection_date=date(2026, 10, 5),
    )


def _orders(n: int = 4) -> list[Any]:
    return [
        SimpleNamespace(
            amount=Decimal("300.00") + i,
            sequence_type=SequenceType.FRST if i % 2 else SequenceType.RCUR,
            end_to_end_id=f"E{i}",
            mandate_reference=f"M{i}",
            mandate_signed_on=date(2024, 1, 1),
            debtor_name="Anna Zahler",
            debtor_iban="DE89370400440532013000",
            purpose="Hausgeld",
        )
        for i in range(n)
    ]


def _xsd_errors(version: str, data: bytes) -> list[str]:
    xmlschema = pytest.importorskip("xmlschema")
    schema = xmlschema.XMLSchema(str(XSD_DIR / f"{version}.xsd"))
    return [str(e)[:200] for e in schema.iter_errors(data)]


@pytest.mark.parametrize("version", dd.PAIN008_VERSIONS)
def test_pain008_validates_against_xsd(version: str) -> None:
    xml = dd.pain008(
        _run(),
        _orders(),
        creditor_iban="DE02120300000000202051",
        creditor_bic="MARKDEF1100",
        version=version,
        created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
    )
    assert _xsd_errors(version, xml) == []
    assert dd.validate_pain008(xml) == []
    text = xml.decode()
    assert "<SeqTp>FRST</SeqTp>" in text
    assert "<SeqTp>RCUR</SeqTp>" in text
    assert text.count("<PmtInf>") == 2  # one batch per sequence type


def test_pain008_unknown_version_and_empty() -> None:
    with pytest.raises(ProblemError):
        dd.pain008(
            _run(),
            _orders(),
            creditor_iban="DE02120300000000202051",
            version="pain.008.001.99",
        )
    with pytest.raises(ProblemError):
        dd.pain008(_run(), [], creditor_iban="DE02120300000000202051")


def test_validate_pain008_detects_manipulation_and_unknown_namespace() -> None:
    xml = dd.pain008(_run(), _orders(2), creditor_iban="DE02120300000000202051").decode()
    tampered = xml.replace(
        '<InstdAmt Ccy="EUR">301.00</InstdAmt>', '<InstdAmt Ccy="EUR">999.00</InstdAmt>'
    )
    problems = dd.validate_pain008(tampered.encode())
    assert any("CtrlSum" in p for p in problems)
    assert dd.validate_pain008(b"<nope/>")
    assert dd.validate_pain008(b"not xml")


def test_sequence_type_derivation() -> None:
    assert dd.sequence_type(0) is SequenceType.FRST
    assert dd.sequence_type(1) is SequenceType.RCUR
    assert dd.sequence_type(5) is SequenceType.RCUR


def test_pre_notification_text_states_configurable_lead_time() -> None:
    orders = _orders(1)
    text = dd.pre_notification_text(
        _run(), orders, creditor_iban_masked="DE02...2051", lead_days=10
    )
    assert "mindestens 10 Tage" in text
    assert "Entwurf" in text
    default_text = dd.pre_notification_text(_run(), orders, creditor_iban_masked="DE02...2051")
    assert f"mindestens {dd.PRE_NOTIFICATION_LEAD_DAYS_DEFAULT} Tage" in default_text
