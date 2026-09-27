"""M18-01 DATEV batch self check: a clean sample passes, deliberately broken batches report every
finding with rule id, line and source status; common practice rules never fail a file."""

from datetime import date

from mhvp.accounting import datev_check


def _sample() -> str:
    return datev_check.sample_batch(
        consultant_number="1234567",
        client_number="12345",
        chart_of_accounts="SKR03",
        account_length=4,
        fiscal_year_start=date(2026, 1, 1),
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        generated="20260927000000000",
    )


def test_sample_batch_has_no_errors_and_twenty_rows() -> None:
    report = datev_check.check_batch(_sample())
    assert report.booking_rows == 20
    assert report.errors == 0
    # Only common practice findings (header field count) may remain, never a documented rule.
    assert all(f.source == "zu_pruefen" for f in report.findings)
    assert report.status in {"formal_ok", "mit_hinweisen"}
    text = datev_check.report_text(report)
    assert "Prüfbericht DATEV-Buchungsstapel" in text
    assert "DC-01" in text
    as_dict = report.as_dict()
    assert {r["id"] for r in as_dict["rules"]} == set(datev_check.RULES)
    assert all(r["source"] in {"belegt", "zu_pruefen"} for r in as_dict["rules"])


def test_broken_header_and_rows_are_reported_per_rule() -> None:
    lines = _sample().split("\r\n")
    header = lines[0].split(";")
    header[0] = '"DTVF"'
    header[1] = '"7"'
    header[2] = '"20"'
    header[10] = '"ABC"'
    header[14] = '"20261301"'
    lines[0] = ";".join(header)
    # Row 3: negative amount, wrong S/H, empty Gegenkonto, bad date, too long text.
    lines[2] = ";".join(
        [
            '"-250,00"',
            '"X"',
            '"1200"',
            '""',
            '"3213"',
            '"' + "x" * 61 + '"',
            '"TB-0001"',
        ]
    )
    # Row 4: wrong field count.
    lines[3] = '"1,00";"S";"1200"'
    # Row 5: account with six digits against Sachkontenlänge 4 (DC-15).
    lines[4] = '"1,00";"S";"120000";"8400";"0101";"Test";"TB"'
    report = datev_check.check_batch("\r\n".join(lines))
    rules = {f.rule for f in report.findings}
    assert {"DC-01", "DC-02", "DC-03", "DC-06", "DC-07"} <= rules
    assert {"DC-11", "DC-12", "DC-13", "DC-14", "DC-15", "DC-16", "DC-18"} <= rules
    assert report.status == "fehlerhaft"
    by_line = {(f.rule, f.line) for f in report.findings}
    assert ("DC-11", 4) in by_line
    assert ("DC-14", 3) in by_line
    assert ("DC-15", 5) in by_line
    # Common practice rules are warnings, documented rules errors.
    for f in report.findings:
        if f.source == "zu_pruefen":
            assert f.severity == "warning"


def test_bu_key_only_checked_when_present_and_filled() -> None:
    content = (
        '"EXTF";"700";"21";"Buchungsstapel";"7";"20260927000000000";"";"RE";"";"";"1234567";'
        '"12345";"20260101";"4";"20260101";"20261231";"";"";"1";"SKR03";"0"\r\n'
        '"Umsatz (ohne Soll/Haben-Kz)";"Soll/Haben-Kennzeichen";"Konto";'
        '"Gegenkonto (ohne BU-Schlüssel)";"BU-Schlüssel";"Belegdatum";"Buchungstext";'
        '"Belegfeld 1"\r\n'
        '"10,00";"S";"1200";"8400";"";"0101";"ok";"1"\r\n'
        '"10,00";"S";"1200";"8400";"9";"0101";"ok";"2"\r\n'
        '"10,00";"S";"1200";"8400";"ab";"0101";"ok";"3"\r\n'
    )
    report = datev_check.check_batch(content)
    bu = [f for f in report.findings if f.rule == "DC-19"]
    assert [f.line for f in bu] == [5]
    assert report.errors == 0


def test_empty_batch_encoding_and_line_endings() -> None:
    content = _sample().split("\r\n")
    empty = "\r\n".join(content[:2]) + "\r\n"
    report = datev_check.check_batch(empty)
    assert {f.rule for f in report.findings} >= {"DC-22"}
    assert report.status == "fehlerhaft"
    lf = _sample().replace("\r\n", "\n").replace("Testbuchung", "Testbuchung €ā")
    report = datev_check.check_batch(lf)
    assert {"DC-20", "DC-21"} <= {f.rule for f in report.findings}
