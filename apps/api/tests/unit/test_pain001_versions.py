"""pain.001 in both DK versions against the public ISO 20022 XSDs (M15-01), structural check,
checksum and count, submitter scaffolds (V2)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.banking import ebics, payment_submitters, payments
from mhvp.core.problems import ProblemError

XSD_DIR = Path(__file__).resolve().parents[1] / "data" / "iso20022"


def _orders(n: int = 3) -> list[Any]:
    return [
        SimpleNamespace(
            amount=Decimal("10.50") + i,
            end_to_end_id=f"E2E-{i}",
            counterpart_name="Firma Müller & Söhne",
            counterpart_iban="DE89370400440532013000",
            purpose="Rechnung 4711 § 3",
            execution_date=date(2026, 10, 5 + i % 2),
        )
        for i in range(n)
    ]


def _xsd_errors(version: str, data: bytes) -> list[str]:
    xmlschema = pytest.importorskip("xmlschema")
    schema = xmlschema.XMLSchema(str(XSD_DIR / f"{version}.xsd"))
    return [str(e)[:200] for e in schema.iter_errors(data)]


@pytest.mark.parametrize("version", payments.PAIN001_VERSIONS)
@pytest.mark.parametrize("bic", [None, "MARKDEF1100"])
def test_pain001_validates_against_xsd(version: str, bic: str | None) -> None:
    xml = payments.pain001(
        "MSG1",
        "GdWE Test",
        "DE02120300000000202051",
        _orders(),
        version=version,
        debtor_bic=bic,
        created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
    )
    assert _xsd_errors(version, xml) == []
    assert payments.validate_pain001(xml) == []
    text = xml.decode()
    assert "<NbOfTxs>3</NbOfTxs>" in text
    assert "<CtrlSum>34.50</CtrlSum>" in text
    assert text.count("<PmtInf>") == 2
    assert "&amp;" not in text  # SEPA character set
    assert "§" not in text
    if bic:
        assert ("<BICFI>" if version.endswith("09") else "<BIC>") + bic in text
    else:
        assert "<Id>NOTPROVIDED</Id>" in text


def test_pain001_unknown_version_and_empty() -> None:
    with pytest.raises(ProblemError):
        payments.pain001("M", "N", "DE02120300000000202051", _orders(), version="pain.001.001.99")
    with pytest.raises(ProblemError):
        payments.pain001("M", "N", "DE02120300000000202051", [])


def test_validate_pain001_detects_manipulation() -> None:
    xml = payments.pain001("MSG1", "GdWE", "DE02120300000000202051", _orders(2)).decode()
    tampered = xml.replace(
        '<InstdAmt Ccy="EUR">10.50</InstdAmt>', '<InstdAmt Ccy="EUR">99.50</InstdAmt>'
    )
    problems = payments.validate_pain001(tampered.encode())
    assert any("CtrlSum" in p for p in problems)
    assert payments.validate_pain001(b"<nope/>")
    assert payments.validate_pain001(b"not xml")
    dup = xml.replace("E2E-1", "E2E-0")
    assert any("EndToEndId" in p for p in payments.validate_pain001(dup.encode()))
    assert payments.file_sha256(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_pain008_default_version_validates_against_xsd() -> None:
    from mhvp.accounting import direct_debit as dd
    from mhvp.accounting.direct_debit_models import SequenceType

    run = SimpleNamespace(
        message_id="MSG8",
        creditor_name="GdWE Test",
        creditor_id="DE98ZZZ09999999999",
        collection_date=date(2026, 10, 5),
    )
    orders = [
        SimpleNamespace(
            amount=Decimal("300.00"),
            sequence_type=SequenceType.FRST if i % 2 else SequenceType.RCUR,
            end_to_end_id=f"E{i}",
            mandate_reference=f"M{i}",
            mandate_signed_on=date(2024, 1, 1),
            debtor_name="Anna Zahler",
            debtor_iban="DE89370400440532013000",
            purpose="Hausgeld",
        )
        for i in range(4)
    ]
    xml = dd.pain008(run, orders, creditor_iban="DE02120300000000202051", creditor_bic=None)  # type: ignore[arg-type]
    assert _xsd_errors("pain.008.001.02", xml) == []


@pytest.mark.asyncio
async def test_submitter_scaffolds_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    session: Any = None
    batch: Any = SimpleNamespace(document_id=None, file_sha256=None, submitted_at=None)
    for channel in ("fints", "ebics"):
        with pytest.raises(ProblemError) as info:
            await payment_submitters.submitter_for(channel).submit(
                session, batch, b"", user_id=None, reference=None
            )
        assert info.value.error.code in ("MHVP-BANK-0017", "MHVP-BANK-0018")
    monkeypatch.setenv(payment_submitters.FINTS_SUBMISSION_FLAG, "1")
    ready: Any = SimpleNamespace(document_id="d", file_sha256="x", submitted_at=None)
    with pytest.raises(ProblemError) as info:
        await payment_submitters.FintsSubmitter().submit(
            session, ready, b"", user_id=None, reference=None
        )
    assert info.value.error.code == "MHVP-BANK-0017"  # flag alone never activates it
    assert not ebics.readiness().ready
    with pytest.raises(ProblemError) as info:
        await ebics.EbicsSubmitter().submit(session, ready, b"", user_id=None, reference=None)
    assert "Vertrag" in str(info.value.detail)
    with pytest.raises(ProblemError):
        payment_submitters.submitter_for("post")
