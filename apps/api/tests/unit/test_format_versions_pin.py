"""ADR 0020: pinned format versions and cross version compatibility (GA03-09).

Changing a supported version set or a default fails here until the ADR and this pin are
updated together. The pain versions used side by side must carry the same business content.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.accounting import direct_debit as dd
from mhvp.accounting.direct_debit_models import SequenceType
from mhvp.banking import payments

XSD_DIR = Path(__file__).resolve().parents[1] / "data" / "iso20022"
ADR = Path(__file__).resolve().parents[4] / "docs" / "adr" / "0020-formatversionen.md"
CREATED = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def test_supported_versions_are_pinned() -> None:
    assert payments.PAIN001_VERSIONS == ("pain.001.001.03", "pain.001.001.09")
    assert payments.PAIN008_VERSIONS == ("pain.008.001.02", "pain.008.001.08")
    assert dd.PAIN008_VERSIONS == payments.PAIN008_VERSIONS
    assert payments.PAIN_FORMAT == "pain.001.001.09"
    assert dd.PAIN_FORMAT == "pain.008.001.02"


@pytest.mark.parametrize("version", [*payments.PAIN001_VERSIONS, *payments.PAIN008_VERSIONS])
def test_xsd_present_and_adr_names_version(version: str) -> None:
    assert (XSD_DIR / f"{version}.xsd").is_file()
    assert version in ADR.read_text(encoding="utf-8")


def _credit_orders() -> list[Any]:
    return [
        SimpleNamespace(
            amount=Decimal("10.50") + i,
            end_to_end_id=f"E2E-{i}",
            counterpart_name="Firma Test",
            counterpart_iban="DE89370400440532013000",
            purpose="Rechnung 4711",
            execution_date=date(2026, 10, 5),
        )
        for i in range(3)
    ]


def _debit_orders() -> list[Any]:
    return [
        SimpleNamespace(
            amount=Decimal("300.00") + i,
            sequence_type=SequenceType.RCUR,
            end_to_end_id=f"D{i}",
            mandate_reference=f"M{i}",
            mandate_signed_on=date(2024, 1, 1),
            debtor_name="Anna Zahler",
            debtor_iban="DE89370400440532013000",
            purpose="Hausgeld",
        )
        for i in range(3)
    ]


def _facts(xml: bytes) -> tuple[str, str, list[str]]:
    text = xml.decode()
    return (
        re.search(r"<NbOfTxs>(\d+)</NbOfTxs>", text).group(1),  # type: ignore[union-attr]
        re.search(r"<CtrlSum>([\d.]+)</CtrlSum>", text).group(1),  # type: ignore[union-attr]
        sorted(re.findall(r"<EndToEndId>([^<]+)</EndToEndId>", text)),
    )


def test_pain001_versions_carry_same_content() -> None:
    results = [
        _facts(
            payments.pain001(
                "MSG1",
                "GdWE Test",
                "DE02120300000000202051",
                _credit_orders(),
                version=v,
                created_at=CREATED,
            )
        )
        for v in payments.PAIN001_VERSIONS
    ]
    assert results[0] == results[1] == ("3", "34.50", ["E2E-0", "E2E-1", "E2E-2"])


def test_pain008_versions_carry_same_content() -> None:
    run = SimpleNamespace(
        message_id="MSG8",
        creditor_name="GdWE Test",
        creditor_id="DE98ZZZ09999999999",
        collection_date=date(2026, 10, 5),
    )
    results = [
        _facts(
            dd.pain008(
                run,
                _debit_orders(),
                creditor_iban="DE02120300000000202051",
                version=v,
                created_at=CREATED,
            )
        )
        for v in payments.PAIN008_VERSIONS
    ]
    assert results[0] == results[1] == ("3", "903.00", ["D0", "D1", "D2"])
