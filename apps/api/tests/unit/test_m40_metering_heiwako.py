"""M40-02: bved 3.10 file exchange (ARGE HeiWaKo) parser and the file adapters of Techem,
Brunata Minol and BRUNATA-METRONA. Synthetic files built from the field positions of the
bved 3.10 PDF (Q14); no provider file is used and nothing is stored."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from mhvp.metering import heiwako
from mhvp.metering.adapters import TestOutcome, adapter_for
from mhvp.metering.adapters_heiwako import (
    BrunataMetronaFileAdapter,
    BrunataMinolFileAdapter,
    HeiwakoFileAdapter,
    TechemFileAdapter,
)
from mhvp.metering.providers import Function

# Builders --------------------------------------------------------------------------------


def _put(buf: list[str], start: int, end: int, value: str, *, numeric: bool = False) -> None:
    width = end - start + 1
    text = value.rjust(width, "0") if numeric else value.ljust(width)
    if numeric and value.startswith("-"):
        text = "-" + value[1:].rjust(width - 1, "0")
    assert len(text) == width, (start, end, value)
    buf[start - 1 : end] = list(text)


def _amount(value: str) -> str:
    """'123.45' -> '12345' (two implied decimals, sign kept)."""
    negative = value.startswith("-")
    whole, _, frac = value.lstrip("-").partition(".")
    return ("-" if negative else "") + whole + frac.ljust(2, "0")


def _header(buf: list[str], record_type: str, prop: str, unit: str, customer: str) -> None:
    _put(buf, 1, 1, record_type)
    _put(buf, 2, 6, "03.10")
    _put(buf, 7, 16, customer, numeric=True)
    _put(buf, 17, 18, "TE")
    _put(buf, 19, 31, prop + unit)


def l_line(prop: str, period: tuple[str, str], currency: str = "EUR") -> str:
    buf = [" "] * 2048
    _header(buf, "L", prop, "0000", "4711")
    _put(buf, 32, 32, "3")
    _put(buf, 33, 67, "Musterstraße 1")
    _put(buf, 68, 70, "D")
    _put(buf, 71, 80, "40721")
    _put(buf, 81, 115, "Hilden")
    _put(buf, 116, 121, period[0])
    _put(buf, 122, 127, period[1])
    _put(buf, 128, 142, "OBJ-0001")
    _put(buf, 143, 143, "0")
    _put(buf, 147, 147, "0")
    _put(buf, 148, 150, currency)
    _put(buf, 151, 151, "1")
    _put(buf, 152, 158, "0123456", numeric=True)  # 1234,56 m2
    _put(buf, 2048, 2048, "L")
    return "".join(buf)


def m_line(prop: str, unit: str, name: str, *, vacancy: str = "0") -> str:
    buf = [" "] * 2048
    _header(buf, "M", prop, unit, "4711")
    _put(buf, 32, 51, f"WE-{unit}")
    _put(buf, 52, 52, "1")
    _put(buf, 53, 87, name)
    _put(buf, 193, 227, "Musterstraße 1")
    _put(buf, 228, 230, "D")
    _put(buf, 231, 240, "40721")
    _put(buf, 241, 275, "Hilden")
    _put(buf, 499, 504, "010125")
    _put(buf, 505, 510, "311225")
    _put(buf, 511, 511, "0")
    _put(buf, 512, 512, "0")
    _put(buf, 513, 522, _amount("75.50"), numeric=True)
    _put(buf, 523, 532, _amount("1200.00"), numeric=True)
    _put(buf, 1167, 1167, vacancy)
    _put(buf, 1168, 1168, "0")
    _put(buf, 1169, 1171, "001", numeric=True)
    _put(buf, 2048, 2048, "M")
    return "".join(buf)


def d_line(
    prop: str,
    unit: str,
    *,
    cost_type: str,
    total: str,
    prepaid: str | None,
    balance: str | None,
    end: str = "311225",
) -> str:
    buf = [" "] * 1024
    _header(buf, "D", prop, unit, "4711")
    _put(buf, 32, 51, f"WE-{unit}")
    _put(buf, 52, 57, end)
    _put(buf, 58, 67, _amount(total), numeric=True)
    if prepaid is not None:
        _put(buf, 78, 87, _amount(prepaid), numeric=True)
    if balance is not None:
        _put(buf, 128, 137, _amount(balance), numeric=True)
    _put(buf, 148, 150, cost_type)
    _put(buf, 151, 159, "000123456", numeric=True)  # 123,456 shares
    _put(buf, 160, 162, "004")
    _put(buf, 166, 200, "Mustermann")
    _put(buf, 201, 203, "EUR")
    _put(buf, 1024, 1024, "D")
    return "".join(buf)


def a_line(prop: str, unit: str, client_ref: str) -> str:
    buf = [" "] * 128
    _header(buf, "A", prop, unit, "4711")
    _put(buf, 32, 51, client_ref)
    _put(buf, 128, 128, "A")
    return "".join(buf)


def e898_line(prop: str, path: str) -> str:
    buf = [" "] * 120
    _put(buf, 1, 4, "E898")
    _put(buf, 5, 11, "1", numeric=True)
    _put(buf, 12, 13, "TE")
    _put(buf, 14, 31, prop + "000100010")
    _put(buf, 32, 51, "WE-0001")
    _put(buf, 53, 108, path)
    _put(buf, 109, 111, "1", numeric=True)
    _put(buf, 112, 117, "311225")
    _put(buf, 118, 120, "HKA")
    return "".join(buf)


def encode(*lines: str) -> bytes:
    return ("\r\n".join(lines) + "\r\n").encode("iso-8859-15")


PROP = "000123456"


# Parser ----------------------------------------------------------------------------------


def test_parse_dtm_file_l_and_m_records() -> None:
    raw = encode(
        l_line(PROP, ("010125", "311225")),
        m_line(PROP, "0001", "Mustermann, Max"),
        m_line(PROP, "0002", "Leerstand", vacancy="1"),
    )
    parsed = heiwako.parse_file(raw, filename="DTM310_20260927120000123.DAT")
    assert parsed.kind == "DTM310" and parsed.errors == []  # noqa: PT018
    (prop,) = parsed.of_type("L")
    assert prop.header.provider_property_number == PROP
    assert prop.header.provider_unit_number is None  # '0000'
    assert prop.period_from == date(2025, 1, 1) and prop.period_to == date(2025, 12, 31)  # noqa: PT018
    assert prop.currency == "EUR" and prop.weg_flag == 1  # noqa: PT018
    assert prop.total_area == Decimal("1234.56")
    assert prop.city == "Hilden" and prop.street == "Musterstraße 1"  # noqa: PT018
    users = parsed.of_type("M")
    assert [u.header.provider_unit_number for u in users] == ["0001", "0002"]
    assert users[0].user_names[0] == "Mustermann, Max"
    assert users[0].heating_shares == Decimal("75.50")
    assert users[0].heating_prepayment_gross == Decimal("1200.00")
    assert users[0].heating_prepayment_net is None  # blank, never zero
    assert users[0].heating_shares_key == 1
    assert users[0].occupancy_from == date(2025, 1, 1)
    assert users[1].vacancy_flag == 1


def test_parse_dtd_file_d_records_amounts_and_negative_balance() -> None:
    raw = encode(
        d_line(PROP, "0001", cost_type="001", total="850.25", prepaid="1200.00", balance="-349.75"),
        d_line(PROP, "0001", cost_type="002", total="120.00", prepaid=None, balance=None),
    )
    parsed = heiwako.parse_file(raw, filename="DTD310_20260927120000123.DAT")
    assert parsed.errors == []
    first, second = parsed.of_type("D")
    assert first.total_gross == Decimal("850.25")
    assert first.prepayment_gross == Decimal("1200.00")
    assert first.balance_gross == Decimal("-349.75")  # Guthaben des Nutzers
    assert first.consumption_shares == Decimal("123.456")
    assert first.cost_type_key == "001" and first.consumption_unit_key == "004"  # noqa: PT018
    assert first.usage_period_end == date(2025, 12, 31)
    assert second.prepayment_gross is None and second.balance_gross is None  # noqa: PT018


def test_parse_a_and_e898_records() -> None:
    a = heiwako.parse_file(encode(a_line(PROP, "0001", "MIETER-77")), filename="DTA310_x.DAT")
    assert a.errors == [] and a.of_type("A")[0].client_ref == "MIETER-77"  # noqa: PT018
    e = heiwako.parse_file(encode(e898_line(PROP, "bilder/hka_0001.pdf")), filename="DTE898_x.DAT")
    assert e.errors == []
    (img,) = e.of_type("E898")
    assert img.image_path == "bilder/hka_0001.pdf" and img.document_kind == "HKA"  # noqa: PT018
    assert img.page == 1 and img.usage_period_end == date(2025, 12, 31)  # noqa: PT018


def test_faulty_lines_are_reported_and_skipped_never_guessed() -> None:
    good = d_line(PROP, "0001", cost_type="001", total="10.00", prepaid=None, balance=None)
    short = good[:-10]  # wrong length
    bad_end = good[:-1] + "X"
    bad_number = list(good)
    bad_number[57:67] = list("00000ABC00")
    unknown = "K" + " " * 1023
    raw = encode(
        good, short, bad_end, "".join(bad_number), unknown, l_line(PROP, ("010125", "311225"))
    )
    parsed = heiwako.parse_file(raw, filename="DTD310_x.DAT")
    assert len(parsed.of_type("D")) == 1
    assert len(parsed.errors) == 5
    assert "Zeile 2" in parsed.errors[0] and "1024 Zeichen" in parsed.errors[0]  # noqa: PT018
    assert "Satzende" in parsed.errors[1]
    assert "numerisches Feld" in parsed.errors[2]
    assert "nicht verarbeitet" in parsed.errors[3]  # K record
    assert "passt nicht zum Dateinamen" in parsed.errors[4]  # L in a DTD file


def test_file_kind_detection_and_wrong_version() -> None:
    assert heiwako.detect_file_kind("pfad/DTD310_20260927120000123.DAT") == "DTD310"
    assert heiwako.detect_file_kind("dte898_1.dat") == "DTE898"
    assert heiwako.detect_file_kind("ergebnisse.csv") is None
    line = a_line(PROP, "0001", "X")
    line = line[:1] + "02.99" + line[6:]
    parsed = heiwako.parse_file(encode(line))
    assert parsed.kind is None and "Version" in parsed.errors[0]  # noqa: PT018


# Mapping D -> billing results ------------------------------------------------------------


def test_billing_results_need_period_start_from_l_record_or_parameter() -> None:
    d = heiwako.parse_file(
        encode(
            d_line(
                PROP, "0001", cost_type="001", total="850.25", prepaid="1200.00", balance="-349.75"
            )
        )
    ).of_type("D")
    results, problems = heiwako.billing_results_from_d(d)
    assert results == [] and "nicht bestimmbar" in problems[0]  # noqa: PT018
    results, problems = heiwako.billing_results_from_d(
        d, periods={PROP: (date(2025, 1, 1), date(2025, 12, 31))}
    )
    assert problems == []
    (rec,) = results
    assert rec.external_billing_unit == PROP and rec.external_unit_number == "0001"  # noqa: PT018
    assert rec.period_from == date(2025, 1, 1) and rec.period_to == date(2025, 12, 31)  # noqa: PT018
    assert rec.amount == Decimal("850.25") and rec.currency == "EUR"  # noqa: PT018
    assert rec.external_document_ref == f"D/{PROP}/2025-12-31/0001/001"
    assert rec.payload["balance_gross"] == "-349.75"
    assert rec.payload["prepayment_gross"] == "1200.00"
    # explicit period start when no DTM file accompanies the results
    results, problems = heiwako.billing_results_from_d(d, period_from=date(2025, 1, 1))
    assert problems == [] and results[0].period_from == date(2025, 1, 1)  # noqa: PT018


def test_usage_period_end_is_capped_by_billing_period() -> None:
    d = heiwako.parse_file(
        encode(
            d_line(
                PROP,
                "0001",
                cost_type="001",
                total="1.00",
                prepaid=None,
                balance=None,
                end="150126",
            )
        )
    ).of_type("D")
    results, _ = heiwako.billing_results_from_d(
        d, periods={PROP: (date(2025, 1, 1), date(2025, 12, 31))}
    )
    assert results[0].period_to == date(2025, 12, 31)


# Adapters --------------------------------------------------------------------------------


def test_file_adapters_registered_without_online_functions() -> None:
    techem = adapter_for("techem", {})
    minol = adapter_for("brunata_minol", {})
    metrona = adapter_for("brunata_metrona", {})
    assert isinstance(techem, TechemFileAdapter)
    assert isinstance(minol, BrunataMinolFileAdapter)
    assert isinstance(metrona, BrunataMetronaFileAdapter)
    for adapter in (techem, minol, metrona):
        assert isinstance(adapter, HeiwakoFileAdapter)
        assert adapter.implemented == frozenset()  # no online function is documented
        assert adapter.setup_submission is None
        assert adapter.required_secrets == frozenset()
        assert "27.09.2026" in adapter.spec_version
        outcome = adapter.test_connection(config={}, secrets={}, environment="test")
        assert outcome.outcome == TestOutcome.NOT_IMPLEMENTED
        assert "Dokumentation erforderlich" in outcome.detail
        with pytest.raises(NotImplementedError):
            adapter.send_roles()
        with pytest.raises(NotImplementedError):
            adapter.send_billing_input()
        assert Function.BILLING_RESULT not in adapter.implemented
    # the fake adapter is never selected outside the test environment
    assert (
        adapter_for("techem", {"adapter": "fake", "_environment": "production"}).code
        == "techem_file"
    )


def test_import_files_combines_dtm_period_with_dtd_results_and_flags_undocumented() -> None:
    files = {
        "DTM310_20260927120000123.DAT": encode(
            l_line(PROP, ("010125", "311225")), m_line(PROP, "0001", "Mustermann, Max")
        ),
        "DTD310_20260927120000123.DAT": encode(
            d_line(
                PROP, "0001", cost_type="001", total="850.25", prepaid="1200.00", balance="-349.75"
            )
        ),
        "DTE898_20260927120000123.DAT": encode(e898_line(PROP, "hka.pdf")),
    }
    techem = TechemFileAdapter().import_files(files)
    assert techem.errors == []
    assert len(techem.billing_results) == 1 and len(techem.users) == 1  # noqa: PT018
    assert techem.billing_results[0].period_from == date(2025, 1, 1)
    by_name = {f["name"]: f for f in techem.files}
    assert by_name["DTD310_20260927120000123.DAT"]["record_counts"] == {"D": 1}
    # Techem names LM and E898 publicly, not D: reported, not refused
    assert by_name["DTD310_20260927120000123.DAT"]["undocumented_record_types"] == ["D"]
    assert by_name["DTM310_20260927120000123.DAT"]["undocumented_record_types"] == []
    minol = BrunataMinolFileAdapter().import_files(files)
    assert all(f["undocumented_record_types"] == [] for f in minol.files)
    assert len(minol.images) == 1


def test_import_files_reports_unknown_names_and_missing_period() -> None:
    result = BrunataMetronaFileAdapter().import_files(
        {
            "ergebnisse.dat": encode(
                d_line(PROP, "0001", cost_type="001", total="1.00", prepaid=None, balance=None)
            )
        }
    )
    assert result.billing_results == []
    assert any("Dateiname entspricht nicht dem Standard" in e for e in result.errors)
    assert any("nicht bestimmbar" in e for e in result.errors)
    assert not result.ok


def test_write_a_records_roundtrip_through_the_parser() -> None:
    """GA09-01: the A record writer produces 128 byte lines that the parser reads back."""
    parsed = heiwako.parse_file(
        heiwako.write_a_records(
            [
                heiwako.ARecord(
                    header=heiwako._Header(
                        record_type="A",
                        version="03.10",
                        customer_number="4711",
                        provider_key="TE",
                        provider_ref=None,
                        provider_property_number="123456789",
                        provider_unit_number="0012",
                    ),
                    client_ref="OBJ-0001/WE 12",
                )
            ]
        ),
        filename="DTA310_20261001120000000.DAT",
    )
    assert parsed.errors == []
    (record,) = parsed.of_type("A")
    assert record.client_ref == "OBJ-0001/WE 12"
    assert record.header.customer_number == "0000004711"
    assert record.header.provider_key == "TE"
    assert record.header.provider_property_number == "123456789"
    assert record.header.provider_unit_number == "0012"


def test_write_a_records_rejects_oversized_reference() -> None:
    bad = heiwako.ARecord(
        header=heiwako._Header("A", "03.10", None, None, None, None, None), client_ref="x" * 21
    )
    with pytest.raises(ValueError, match="passt nicht"):
        heiwako.write_a_records([bad])


def test_write_l_and_m_records_roundtrip_and_byte_identity() -> None:
    l_text = l_line(PROP, ("010125", "311225"))
    m_text = m_line(PROP, "0001", "Mustermann, Max")
    parsed = heiwako.parse_file(encode(l_text, m_text), filename="DTM310_20260927120000123.DAT")
    (l_rec,) = parsed.of_type("L")
    (m_rec,) = parsed.of_type("M")
    raw = heiwako.write_l_records([l_rec]) + heiwako.write_m_records([m_rec])
    # Fixtures only use documented positions, so the export reproduces them byte for byte.
    assert raw == encode(l_text, m_text)
    again = heiwako.parse_file(raw, filename="DTM310_20260927120000124.DAT")
    assert again.errors == []
    assert again.of_type("L") == [l_rec]
    assert again.of_type("M") == [m_rec]


def test_write_m_record_negative_amount_blank_stays_blank_and_vacancy() -> None:
    parsed = heiwako.parse_file(encode(m_line(PROP, "0002", "Leerstand", vacancy="1")))
    (rec,) = parsed.of_type("M")
    changed = replace(rec, heating_prepayment_net=Decimal("-12.30"), vacancy_flag=1)
    (back,) = heiwako.parse_file(heiwako.write_m_records([changed])).of_type("M")
    assert back.heating_prepayment_net == Decimal("-12.30")
    assert back.cold_water_shares is None  # blank, never zero
    assert back.vacancy_flag == 1
    assert len(heiwako.write_m_records([changed])) == 2048 + 2


def test_write_l_m_records_reject_oversized_values() -> None:
    (rec,) = heiwako.parse_file(encode(l_line(PROP, ("010125", "311225")))).of_type("L")
    with pytest.raises(ValueError, match="passt nicht"):
        heiwako.write_l_records([replace(rec, total_area=Decimal("123456789.00"))])
    with pytest.raises(ValueError, match="passt nicht"):
        heiwako.write_l_records([replace(rec, city="x" * 36)])
    with pytest.raises(ValueError, match="zweistelligem"):
        heiwako.write_l_records([replace(rec, period_from=date(2070, 1, 1))])
