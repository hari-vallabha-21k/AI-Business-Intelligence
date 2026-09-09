"""Parsing, cleaning and quality: the steps before anything is calculated."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.semantic.engine import map_dataframe
from app.services.cleaning import build_label_map, clean_dates, clean_numeric, normalize_label
from app.services.ingest import build_records, records_to_frame
from app.services.parsing import FileError, parse_upload
from app.services.profiling import profile_dataframe
from app.services.quality import assess_file


def test_iso_dates_are_not_read_day_first():
    """Regression: 2026-01-02 must be 2 January, not 1 February."""
    parsed = clean_dates(pd.Series(["2026-01-02", "2026-01-03", "2026-02-11"]))
    assert list(parsed.dt.strftime("%Y-%m-%d")) == ["2026-01-02", "2026-01-03", "2026-02-11"]


def test_ambiguous_slash_dates_are_read_day_first():
    parsed = clean_dates(pd.Series(["02/01/2026", "11/02/2026"]))
    assert list(parsed.dt.strftime("%Y-%m-%d")) == ["2026-01-02", "2026-02-11"]


def test_unparseable_dates_become_null_not_an_error():
    parsed = clean_dates(pd.Series(["2026-01-02", "not a date", None]))
    assert parsed.isna().sum() == 2


def test_currency_and_separators_are_stripped():
    values = clean_numeric(pd.Series(["₹45,000", "38000", "1,20,000.50", "(500)", "n/a"]))
    assert list(values[:4]) == [45000.0, 38000.0, 120000.50, -500.0]
    assert pd.isna(values.iloc[4])


def test_label_variants_collapse_but_distinct_names_do_not():
    mapping, log = build_label_map(
        pd.Series(["Jubilee Hills", "jubilee hills", "JUBILEE-HILLS", "Banjara Hills"])
    )
    assert len({mapping[v] for v in ["Jubilee Hills", "jubilee hills", "JUBILEE-HILLS"]}) == 1
    assert mapping["Banjara Hills"] != mapping["Jubilee Hills"]
    assert log[0]["rows_affected"] == 2


def test_normalize_label_is_stable():
    assert normalize_label(" Jubilee-Hills  ") == normalize_label("JUBILEE HILLS") == "jubilee hills"


def test_csv_and_excel_parse_to_the_same_frame():
    df = pd.DataFrame({"branch": ["A"], "revenue": [100]})
    csv = parse_upload("f.csv", df.to_csv(index=False).encode())

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    xlsx = parse_upload("f.xlsx", buffer.getvalue())

    pd.testing.assert_frame_equal(csv, xlsx)


@pytest.mark.parametrize(
    ("filename", "content", "fragment"),
    [
        ("data.csv", b"", "empty"),
        ("data.pdf", b"%PDF-1.4", "Excel"),
        ("data.xlsx", b"not really a spreadsheet", "couldn't read"),
        ("blank.csv", b"a,b\n,\n,\n", "no data rows"),
    ],
)
def test_bad_uploads_get_readable_messages(filename, content, fragment):
    """PRD sec. 34: never a stack trace, never a silent failure."""
    with pytest.raises(FileError) as exc:
        parse_upload(filename, content)
    assert fragment.lower() in str(exc.value).lower()


def test_blank_rows_and_columns_are_dropped():
    raw = b"branch,revenue,\nA,100,\n,,\nB,200,\n"
    df = parse_upload("f.csv", raw)
    assert len(df) == 2
    assert list(df.columns) == ["branch", "revenue"]


def test_raw_values_survive_cleaning():
    """PRD sec. 11: the original data is preserved."""
    df = pd.DataFrame(
        {"emp_id": ["E1"], "location": ["jubilee hills"], "monthly_pay": ["₹45,000"]}
    )
    _, proposals = map_dataframe(df, profile_dataframe(df)[1])
    records, _, _, _ = build_records(df, proposals)
    assert records[0]["EMPLOYEE_COMPENSATION"] == 45000.0
    assert records[0]["_raw"]["monthly_pay"] == "₹45,000"


def test_multiple_pay_columns_are_summed_into_one_concept():
    df = pd.DataFrame(
        {"emp_id": ["E1", "E2"], "basic_pay": [30000, 25000], "gross_pay": [5000, 4000],
         "designation": ["manager", "waiter"]}
    )
    _, proposals = map_dataframe(df, profile_dataframe(df)[1])
    records, log, _, _ = build_records(df, proposals)
    frame = records_to_frame(records)
    assert frame["EMPLOYEE_COMPENSATION"].sum() == 64000
    assert any(entry["type"] == "measure_combined" for entry in log)


def test_default_branch_is_applied_and_logged():
    df = pd.DataFrame({"emp_id": ["E1"], "monthly_pay": [40000], "designation": ["waiter"]})
    _, proposals = map_dataframe(df, profile_dataframe(df)[1])
    records, log, _, _ = build_records(df, proposals, default_branch="Branch A")
    assert records[0]["BRANCH"] == "Branch A"
    assert any(entry["type"] == "branch_defaulted" for entry in log)


def test_period_is_derived_from_the_date_column():
    df = pd.DataFrame(
        {"bill_no": ["a", "b"], "order_date": ["2026-03-04", "2026-03-28"],
         "branch": ["A", "A"], "revenue": [10.0, 20.0]}
    )
    _, proposals = map_dataframe(df, profile_dataframe(df)[1])
    _, _, start, end = build_records(df, proposals)
    assert (start.isoformat(), end.isoformat()) == ("2026-03-04", "2026-03-28")


def test_quality_flags_missing_branch_and_date():
    df = pd.DataFrame({"emp_id": ["E1", "E2"], "monthly_pay": [40000, 38000],
                       "designation": ["manager", "waiter"]})
    profile, signals = profile_dataframe(df)
    kind, proposals = map_dataframe(df, signals)
    codes = {i.code for i in assess_file(df, profile, proposals, kind)}
    assert {"missing_branch", "missing_date"} <= codes


def test_quality_flags_duplicates_and_sparse_columns():
    df = pd.DataFrame(
        {
            "emp_id": ["E1", "E1", "E2"],
            "monthly_pay": [40000, 40000, 38000],
            "designation": ["manager", "manager", "waiter"],
            "branch": ["A", "A", "A"],
            "department": [None, None, "Kitchen"],
        }
    )
    profile, signals = profile_dataframe(df)
    kind, proposals = map_dataframe(df, signals)
    issues = assess_file(df, profile, proposals, kind)
    codes = {i.code for i in issues}
    assert "duplicate_rows" in codes
    assert any(i.code == "missing_values" and i.column_name == "department" for i in issues)


def test_negative_salary_is_flagged():
    df = pd.DataFrame({"emp_id": ["E1"], "monthly_pay": [-40000], "branch": ["A"],
                       "designation": ["waiter"]})
    profile, signals = profile_dataframe(df)
    kind, proposals = map_dataframe(df, signals)
    assert any(i.code == "negative_values" for i in assess_file(df, profile, proposals, kind))


def test_profile_counts_missing_and_unique():
    df = pd.DataFrame({"branch": ["A", "A", None], "revenue": [1.0, 2.0, 3.0]})
    profile, _ = profile_dataframe(df)
    branch = next(c for c in profile["columns"] if c["name"] == "branch")
    assert branch["missing"] == 1 and branch["unique"] == 1
    assert profile["row_count"] == 3 and profile["column_count"] == 2
