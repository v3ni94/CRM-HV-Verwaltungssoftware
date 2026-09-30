"""M15-02, M15-04, M15-06, M15-01 without database: ISO 20022 status report parsing,
bank limits, lead days per sequence type, pre-notification distance, reconciliation findings.
Expected values are written out and recomputable by hand."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from mhvp.accounting import direct_debit as dd
from mhvp.accounting.direct_debit_feedback import _finding
from mhvp.accounting.direct_debit_models import SequenceType
from mhvp.banking import bank_status
from mhvp.banking.payment_run import limit_findings
from mhvp.core.config import Settings
from mhvp.core.problems import ProblemError

PAIN002 = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.002.001.10">
 <CstmrPmtStsRpt>
  <GrpHdr><MsgId>STS-1</MsgId><CreDtTm>2026-09-30T10:00:00</CreDtTm></GrpHdr>
  <OrgnlGrpInfAndSts><OrgnlMsgId>MHVPABC</OrgnlMsgId><OrgnlMsgNmId>pain.001.001.09</OrgnlMsgNmId>
   <GrpSts>PART</GrpSts></OrgnlGrpInfAndSts>
  <OrgnlPmtInfAndSts><OrgnlPmtInfId>P1</OrgnlPmtInfId>
   <TxInfAndSts><OrgnlEndToEndId>E2EOK</OrgnlEndToEndId><TxSts>ACCP</TxSts></TxInfAndSts>
   <TxInfAndSts><OrgnlEndToEndId>E2ENO</OrgnlEndToEndId><TxSts>RJCT</TxSts>
    <StsRsnInf><Rsn><Cd>AC04</Cd></Rsn></StsRsnInf>
    <OrgnlTxRef><Amt><InstdAmt Ccy="EUR">120.50</InstdAmt></Amt></OrgnlTxRef></TxInfAndSts>
  </OrgnlPmtInfAndSts>
 </CstmrPmtStsRpt>
</Document>"""

CAMT054 = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
 <BkToCstmrDbtCdtNtfctn>
  <GrpHdr><MsgId>N-1</MsgId></GrpHdr>
  <Ntfctn><Id>1</Id>
   <Ntry><Amt Ccy="EUR">350.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
    <NtryDtls><TxDtls><Refs><EndToEndId>E2EDD1</EndToEndId></Refs>
     <Amt Ccy="EUR">350.00</Amt></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="EUR">353.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
    <NtryDtls><TxDtls><Refs><EndToEndId>E2EDD2</EndToEndId></Refs>
     <AmtDtls><TxAmt><Amt Ccy="EUR">350.00</Amt></TxAmt></AmtDtls>
     <RtrInf><Rsn><Cd>MD06</Cd></Rsn></RtrInf></TxDtls></NtryDtls></Ntry>
  </Ntfctn>
 </BkToCstmrDbtCdtNtfctn>
</Document>"""


def test_pain002_transaction_status_and_reason() -> None:
    report = bank_status.parse(PAIN002)
    assert report.kind == "pain.002"
    assert report.message_id == "STS-1"
    assert report.original_message_id == "MHVPABC"
    assert report.group_status == "PART"
    assert [(x.end_to_end_id, x.status, x.reason_code) for x in report.lines] == [
        ("E2EOK", "accepted", None),
        ("E2ENO", "rejected", "AC04"),
    ]
    assert report.lines[1].amount == Decimal("120.50")


def test_camt054_collection_and_return() -> None:
    report = bank_status.parse(CAMT054)
    assert report.kind == "camt.054"
    assert [(x.end_to_end_id, x.status, x.reason_code, x.amount) for x in report.lines] == [
        ("E2EDD1", "collected", None, Decimal("350.00")),
        ("E2EDD2", "returned", "MD06", Decimal("350.00")),  # transaction amount, not entry
    ]


@pytest.mark.parametrize(
    "data",
    [
        b"not xml",
        b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:camt.053.001.02'>"
        b"<BkToCstmrStmt/></Document>",
    ],
)
def test_other_documents_are_refused(data: bytes) -> None:
    with pytest.raises(ProblemError):
        bank_status.parse(data)


def _order(amount: str, day: date, name: str = "A") -> SimpleNamespace:
    return SimpleNamespace(amount=Decimal(amount), execution_date=day, counterpart_name=name)


def test_limits_single_and_daily() -> None:
    config = SimpleNamespace(single_order_limit=Decimal("1000.00"), daily_limit=Decimal("1500.00"))
    d = date(2026, 10, 5)
    # 800,00 + 600,00 = 1.400,00 plus 200,00 already handed out = 1.600,00 > 1.500,00
    findings = limit_findings(
        [_order("800.00", d), _order("600.00", d)],  # type: ignore[list-item]
        config,  # type: ignore[arg-type]
        {d: Decimal("200.00")},
    )
    assert findings == ["Ausführung 05.10.2026: Summe 1600.00 EUR über dem Tageslimit 1500.00 EUR"]
    single = limit_findings([_order("1000.01", d, "B")], config)  # type: ignore[list-item,arg-type]
    assert single == ["B: 1000.01 EUR über dem Einzelauftragslimit 1000.00 EUR"]
    assert limit_findings([_order("5000.00", d)], None) == []  # type: ignore[list-item]


def test_lead_days_per_sequence_type() -> None:
    config = SimpleNamespace(dd_lead_days_frst=5, dd_lead_days_rcur=2)
    today = date(2026, 10, 1)
    assert dd.sequence_lead_block(config, SequenceType.FRST, date(2026, 10, 6), today) is None
    blocked = dd.sequence_lead_block(config, SequenceType.FRST, date(2026, 10, 5), today)
    assert blocked is not None
    assert "FRST von 5 Tagen" in blocked
    assert "zu verifizieren" in blocked
    assert dd.sequence_lead_block(config, SequenceType.RCUR, date(2026, 10, 3), today) is None
    assert dd.sequence_lead_block(None, SequenceType.FRST, today, today) is None
    empty = SimpleNamespace(dd_lead_days_frst=None, dd_lead_days_rcur=None)
    assert dd.sequence_lead_block(empty, SequenceType.FRST, today, today) is None


def test_pre_notification_distance() -> None:
    today = date(2026, 10, 1)
    warn = dd.pre_notification_check(None, date(2026, 10, 8), today, 14)
    assert warn == {
        "required_days": 14,
        "configured": False,
        "days_until_collection": 7,
        "ok": False,
        "source_status": "zu verifizieren",
    }
    config = SimpleNamespace(pre_notification_days=5)
    assert dd.pre_notification_check(config, date(2026, 10, 8), today, 14)["ok"] is True
    with pytest.raises(ProblemError):
        dd.pre_notification_check(
            SimpleNamespace(pre_notification_days=10), date(2026, 10, 8), today, 14
        )


def _dd(status: str, amount: str = "350.00", collected: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        bank_status=status,
        amount=Decimal(amount),
        collected_amount=Decimal(collected) if collected else None,
    )


def test_reconciliation_findings() -> None:
    assert _finding(_dd("open"), Decimal("350.00")) is None  # type: ignore[arg-type]
    assert "noch nicht ausgeglichen" in (_finding(_dd("collected"), Decimal("350.00")) or "")  # type: ignore[arg-type]
    assert _finding(_dd("collected"), Decimal("0.00")) is None  # type: ignore[arg-type]
    assert "Teileinzug" in (_finding(_dd("collected", collected="300.00"), Decimal("50.00")) or "")  # type: ignore[arg-type]
    assert "Storno" in (_finding(_dd("returned"), Decimal("0.00")) or "")  # type: ignore[arg-type]
    assert _finding(_dd("returned"), Decimal("350.00")) is None  # type: ignore[arg-type]
    assert "Zuordnung" in (_finding(_dd("rejected"), Decimal("0.00")) or "")  # type: ignore[arg-type]


def test_weekly_payment_run_preview_is_scheduled(settings: Settings) -> None:
    """S15-02: Monday 08:00, task registered on the worker (preview only)."""
    from mhvp.worker import create_celery

    app = create_celery(settings)
    entry = app.conf.beat_schedule["payments-payment-run-preview"]
    assert entry["task"] == "mhvp.payments.payment_run"
    assert entry["schedule"].day_of_week == {1}
    assert entry["schedule"].hour == {8}
    assert entry["schedule"].minute == {0}
    assert "mhvp.banking.payment_run_tasks" in app.conf.include
