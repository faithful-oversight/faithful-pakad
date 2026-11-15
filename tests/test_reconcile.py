# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the reconciliation engine."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from importlib.resources import files

import jsonschema
import pytest
from hypothesis import given
from hypothesis import strategies as st

from faithful_pakad.errors import InputError
from faithful_pakad.model import Finding, Kind, Record, Result, Side, SourceRef, Table
from faithful_pakad.outputs import build_report
from faithful_pakad.profile import parse_profile
from faithful_pakad.reconcile import parse_timestamp, reconcile
from tests.conftest import MINIMAL_PROFILE

AS_OF = datetime(2026, 11, 7, 12, tzinfo=UTC)
REPORT_SCHEMA = json.loads(
    files("faithful_pakad").joinpath("schema/report-v1.schema.json").read_text(encoding="utf-8")
)
Rows = Sequence[Mapping[str, str | None]]
NO_PAGING = MINIMAL_PROFILE + "[collection]\npage_sizes = []\n"


def table(side: Side, rows: Rows, columns: tuple[str, ...] = ()) -> Table:
    cols = columns or tuple(dict.fromkeys(c for r in rows for c in r))
    records = tuple(
        Record(SourceRef(side, f"{side}.csv", i + 2), {c: r.get(c) for c in cols})
        for i, r in enumerate(rows)
    )
    return Table(side, f"{side}.csv", "0" * 64, 0, cols, records)


def run(profile_text: str, expected: Rows, collected: Rows) -> Result:
    profile = parse_profile(profile_text)
    exp = table(
        Side.EXPECTED, expected, (*profile.expected.key, *(c.expected for c in profile.compare))
    )
    col_columns = [*profile.collected.key, *(c.collected for c in profile.compare)]
    col_columns += [
        c for c in (profile.collection.source_column, profile.collection.captured_at_column) if c
    ]
    col = table(Side.COLLECTED, collected, tuple(dict.fromkeys(col_columns)))
    return reconcile(profile, exp, col, as_of=AS_OF)


def kinds(result: Result) -> list[Kind]:
    return [f.kind for f in result.findings]


def only(result: Result, kind: Kind) -> Finding:
    found = [f for f in result.findings if f.kind is kind]
    assert len(found) == 1, found
    return found[0]


def test_perfect_match_has_no_findings() -> None:
    result = run(NO_PAGING, [{"id": "1"}, {"id": "2"}], [{"uid": "2"}, {"uid": "1"}])
    assert result.findings == ()
    assert result.matched_keys == 2


def test_missing_and_unexpected() -> None:
    result = run(NO_PAGING, [{"id": "1"}, {"id": "2"}], [{"uid": "2"}, {"uid": "3"}])
    assert kinds(result) == [Kind.MISSING, Kind.UNEXPECTED]
    missing = only(result, Kind.MISSING)
    assert missing.key == ("1",)
    assert missing.refs == (SourceRef(Side.EXPECTED, "expected.csv", 2),)
    assert only(result, Kind.UNEXPECTED).key == ("3",)


def test_leading_zeros_are_significant() -> None:
    result = run(NO_PAGING, [{"id": "007"}], [{"uid": "7"}])
    assert kinds(result) == [Kind.MISSING, Kind.UNEXPECTED]


def test_default_normalization_strips_whitespace_only() -> None:
    assert run(NO_PAGING, [{"id": " a1 "}], [{"uid": "a1"}]).findings == ()
    assert kinds(run(NO_PAGING, [{"id": "A1"}], [{"uid": "a1"}])) == [Kind.MISSING, Kind.UNEXPECTED]


def test_composite_keys() -> None:
    text = NO_PAGING.replace('key = ["id"]', 'key = ["dom", "id"]').replace(
        'key = ["uid"]', 'key = ["domain", "uid"]'
    )
    result = run(
        text, [{"dom": "a", "id": "1"}, {"dom": "b", "id": "1"}], [{"domain": "a", "uid": "1"}]
    )
    assert only(result, Kind.MISSING).key == ("b", "1")


def test_duplicate_and_ambiguous_keys() -> None:
    text = NO_PAGING + '[match]\nnormalize = ["strip", "casefold"]\n'
    result = run(text, [{"id": "a"}, {"id": "a"}], [{"uid": "A"}, {"uid": "a"}])
    dup = only(result, Kind.DUPLICATE_KEY)
    assert dup.refs[0].side is Side.EXPECTED
    assert len(dup.refs) == 2
    amb = only(result, Kind.AMBIGUOUS_KEY)
    assert amb.details["raw_values"] == "A; a"
    assert result.matched_keys == 1


def test_blank_keys() -> None:
    result = run(NO_PAGING, [{"id": "  "}, {"id": None}], [{"uid": "1"}])
    blanks = [f for f in result.findings if f.kind is Kind.BLANK_KEY]
    assert [b.refs[0].row for b in blanks] == [2, 3]
    assert "empty after normalization" in blanks[0].message
    assert "is absent" in blanks[1].message


COMPARE = NO_PAGING + (
    "[[compare]]\nexpected = 'status'\ncollected = 'enabled'\n"
    "normalize = ['strip', 'casefold']\nequivalents = { 'TRUE' = 'active' }\n"
)


def test_field_compare_with_equivalents() -> None:
    expected = [{"id": "1", "status": "Active"}, {"id": "2", "status": "terminated"}]
    collected = [{"uid": "1", "enabled": "true "}, {"uid": "2", "enabled": "TRUE"}]
    mismatch = only(run(COMPARE, expected, collected), Kind.FIELD_MISMATCH)
    assert mismatch.key == ("2",)
    assert mismatch.details["expected_value"] == "terminated"
    assert mismatch.details["collected_value"] == "TRUE"
    assert len(mismatch.refs) == 2


def test_absent_values_never_match() -> None:
    result = run(COMPARE, [{"id": "1", "status": None}], [{"uid": "1", "enabled": None}])
    mismatch = only(result, Kind.FIELD_MISMATCH)
    assert mismatch.details["expected_value"] == "(absent)"
    assert "both absent" in mismatch.message
    result = run(COMPARE, [{"id": "1", "status": "x"}], [{"uid": "1", "enabled": None}])
    assert "differ" in only(result, Kind.FIELD_MISMATCH).message


def test_compare_skips_duplicates_and_says_so() -> None:
    result = run(
        COMPARE,
        [{"id": "1", "status": "x"}],
        [{"uid": "1", "enabled": "y"}, {"uid": "1", "enabled": "z"}],
    )
    assert Kind.FIELD_MISMATCH not in kinds(result)
    assert any(u.check == "field comparison" for u in result.unknowns)


SOURCES = NO_PAGING.replace(
    "page_sizes = []",
    "page_sizes = []\nsource_column = 'domain'\nexpected_sources = ['A.example', 'b.example']",
)


def test_missing_source() -> None:
    result = run(SOURCES, [{"id": "1"}], [{"uid": "1", "domain": " a.EXAMPLE "}])
    missing = only(result, Kind.MISSING_SOURCE)
    assert missing.details["source"] == "b.example"
    assert not any(u.check == "source coverage" for u in result.unknowns)


FRESH = NO_PAGING.replace(
    "page_sizes = []", "page_sizes = []\ncaptured_at_column = 'at'\nmax_age_hours = 24"
)


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("2026-11-07T00:00:00Z", None),
        ("2026-11-06T12:00:00+00:00", None),
        ("2026-11-05T12:00:00-05:00", Kind.STALE_RECORD),
        ("2026-11-07 06:00:00", Kind.INVALID_TIMESTAMP),
        ("yesterday", Kind.INVALID_TIMESTAMP),
        (None, Kind.INVALID_TIMESTAMP),
    ],
)
def test_freshness(value: str | None, kind: Kind | None) -> None:
    result = run(FRESH, [{"id": "1"}], [{"uid": "1", "at": value}])
    assert kinds(result) == ([kind] if kind else [])


def test_naive_timestamps_can_be_utc() -> None:
    text = FRESH.replace("max_age_hours = 24", "max_age_hours = 24\nnaive_timestamps = 'utc'")
    assert run(text, [{"id": "1"}], [{"uid": "1", "at": "2026-11-07 06:00:00"}]).findings == ()


def test_stale_details() -> None:
    result = run(FRESH, [{"id": "1"}], [{"uid": "1", "at": "2026-11-04T12:00:00Z"}])
    stale = only(result, Kind.STALE_RECORD)
    assert "3.0 days" in stale.message
    assert stale.details["max_age_hours"] == "24"


def test_possible_truncation_overall_and_per_source() -> None:
    text = MINIMAL_PROFILE + "[collection]\npage_sizes = [2]\nsource_column = 'domain'\n"
    collected = [{"uid": str(i), "domain": "a" if i < 2 else "b"} for i in range(3)]
    result = run(text, [{"id": str(i)} for i in range(3)], collected)
    trunc = only(result, Kind.POSSIBLE_TRUNCATION)
    assert trunc.details["source"] == "a"


def test_a_source_name_cannot_hide_the_overall_count() -> None:
    text = MINIMAL_PROFILE + "[collection]\npage_sizes = [3]\nsource_column = 'domain'\n"
    domains = ["(all records)", "x", "x"]
    collected = [{"uid": str(i), "domain": d} for i, d in enumerate(domains)]
    result = run(text, [{"id": str(i)} for i in range(3)], collected)
    assert only(result, Kind.POSSIBLE_TRUNCATION).details["scope"] == "all records"


def test_empty_export_is_not_flagged_as_truncated() -> None:
    result = run(MINIMAL_PROFILE + "[collection]\npage_sizes = [2]\n", [{"id": "1"}], [])
    assert kinds(result) == [Kind.MISSING, Kind.EMPTY_INPUT]


def test_empty_inputs_are_never_a_clean_result() -> None:
    result = run(NO_PAGING, [], [])
    assert kinds(result) == [Kind.NOTHING_RECONCILED]
    assert result.findings[0].severity.value == "error"
    one = run(NO_PAGING, [{"id": "1"}], [])
    assert Kind.EMPTY_INPUT in kinds(one)
    assert Kind.NOTHING_RECONCILED not in kinds(one)
    assert only(one, Kind.EMPTY_INPUT).severity.value == "warning"


def test_future_capture_times_are_invalid() -> None:
    result = run(FRESH, [{"id": "1"}], [{"uid": "1", "at": "2026-11-07T12:04:00Z"}])
    assert result.findings == ()
    result = run(FRESH, [{"id": "1"}], [{"uid": "1", "at": "2030-01-01T00:00:00Z"}])
    assert "later than the reference time" in only(result, Kind.INVALID_TIMESTAMP).message


def test_stale_ages_under_two_days_use_hours() -> None:
    result = run(FRESH, [{"id": "1"}], [{"uid": "1", "at": "2026-11-06T06:00:00Z"}])
    assert "30.0 hours" in only(result, Kind.STALE_RECORD).message


def test_missing_and_unexpected_show_the_raw_key() -> None:
    text = NO_PAGING + '[match]\nnormalize = ["strip", "casefold"]\n'
    result = run(text, [{"id": "  ALICE "}], [{"uid": "bob"}])
    assert only(result, Kind.MISSING).details["raw_key"] == "  ALICE "
    assert only(result, Kind.MISSING).key == ("alice",)
    assert only(result, Kind.UNEXPECTED).details["raw_key"] == "bob"


def test_unknowns_list_unconfigured_checks() -> None:
    checks = {u.check for u in run(NO_PAGING, [{"id": "1"}], [{"uid": "1"}]).unknowns}
    assert checks == {
        "field comparison",
        "source coverage",
        "record freshness",
        "paging truncation",
    }


def test_no_compare_fields_is_listed_as_not_checked_even_when_all_else_is_configured() -> None:
    """PAKAD-C03: a presence-only profile must never read as a clean, complete pass."""
    text = SOURCES.replace(
        "page_sizes = []",
        "page_sizes = [1000]\ncaptured_at_column = 'at'\nmax_age_hours = 24",
    )
    collected = [{"uid": "1", "domain": "a.example", "at": "2026-11-07T11:00:00Z"}]
    collected.append({"uid": "2", "domain": "b.example", "at": "2026-11-07T11:00:00Z"})
    result = run(text, [{"id": "1"}, {"id": "2"}], collected)
    assert result.findings == ()
    assert [u.check for u in result.unknowns] == ["field comparison"]
    assert "[[compare]]" in result.unknowns[0].reason
    assert "only key presence was compared" in result.unknowns[0].reason


def test_configured_compare_is_not_listed_as_unchecked() -> None:
    result = run(COMPARE, [{"id": "1", "status": "x"}], [{"uid": "1", "enabled": "x"}])
    assert not any(u.check == "field comparison" for u in result.unknowns)


def test_rules_describe_the_profile() -> None:
    text = COMPARE.replace(
        "page_sizes = []",
        "page_sizes = [1000]\nsource_column='d'\nexpected_sources=['x']\n"
        "captured_at_column='t'\nmax_age_hours=1.5",
    )
    rules = parse_and_rules(text)
    assert rules[0].startswith("Match expected [id] to collected [uid]")
    assert rules[1].endswith("; equivalents: true = active.")
    assert any("1.5 hours" in r for r in rules)
    assert any("multiples of 1000" in r for r in rules)
    assert any("Every expected source" in r for r in rules)


def parse_and_rules(text: str) -> tuple[str, ...]:
    return run(text, [], []).rules


def test_missing_columns_are_input_errors() -> None:
    profile = parse_profile(MINIMAL_PROFILE)
    exp = table(Side.EXPECTED, [{"other": "1"}])
    col = table(Side.COLLECTED, [{"uid": "1"}])
    with pytest.raises(
        InputError,
        match=r"expected.csv \(expected input\) is missing 1 column: id; available: other",
    ):
        reconcile(profile, exp, col, as_of=AS_OF)


def test_as_of_must_be_aware() -> None:
    profile = parse_profile(MINIMAL_PROFILE)
    naive = datetime(2026, 1, 1)  # noqa: DTZ001 - deliberately naive
    with pytest.raises(ValueError, match="timezone-aware"):
        reconcile(profile, table(Side.EXPECTED, []), table(Side.COLLECTED, []), as_of=naive)


def test_parse_timestamp() -> None:
    assert parse_timestamp("2026-01-01T00:00:00z", assume_utc=False) == datetime(
        2026, 1, 1, tzinfo=UTC
    )
    assert parse_timestamp("2026-01-01", assume_utc=True) == datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_timestamp("2026-01-01", assume_utc=False) is None


KEYS = st.lists(st.text(alphabet="abc01 ", min_size=1, max_size=3), max_size=15)


@given(expected=KEYS, collected=KEYS)
def test_every_key_is_accounted_for(expected: list[str], collected: list[str]) -> None:
    """Every usable key is matched or reported as missing or unexpected, never lost."""
    result = run(NO_PAGING, [{"id": k} for k in expected], [{"uid": k} for k in collected])
    exp_keys = {k.strip() for k in expected if k.strip()}
    col_keys = {k.strip() for k in collected if k.strip()}
    missing = {f.key[0] for f in result.findings if f.kind is Kind.MISSING and f.key}
    unexpected = {f.key[0] for f in result.findings if f.kind is Kind.UNEXPECTED and f.key}
    assert missing == exp_keys - col_keys
    assert unexpected == col_keys - exp_keys
    assert result.matched_keys == len(exp_keys & col_keys)
    blanks = sum(1 for f in result.findings if f.kind is Kind.BLANK_KEY)
    assert blanks == sum(1 for k in [*expected, *collected] if not k.strip())


@given(expected=KEYS, collected=KEYS)
def test_results_are_deterministic(expected: list[str], collected: list[str]) -> None:
    first = run(NO_PAGING, [{"id": k} for k in expected], [{"uid": k} for k in collected])
    again = run(NO_PAGING, [{"id": k} for k in expected], [{"uid": k} for k in collected])
    assert first == again


def test_a_file_that_says_it_is_one_page_is_a_finding_even_without_page_sizes() -> None:
    """PAKAD-C02: the finding does not depend on the configured page sizes."""
    profile = parse_profile(NO_PAGING)
    exp = table(Side.EXPECTED, [{"id": "1"}])
    col = table(Side.COLLECTED, [{"uid": "1"}])
    incomplete = dataclasses.replace(col, incomplete_signals=("@odata.nextLink is present",))
    result = reconcile(profile, exp, incomplete, as_of=AS_OF)
    found = only(result, Kind.INCOMPLETE_EXPORT)
    assert found.severity.value == "error"
    assert found.details["input"] == "collected"
    assert found.details["signal"] == "@odata.nextLink is present"
    assert Kind.POSSIBLE_TRUNCATION not in kinds(result)
    differs = dataclasses.replace(col, paging_signals=("count is 9, but the file holds 1",))
    soft = only(reconcile(profile, exp, differs, as_of=AS_OF), Kind.POSSIBLE_TRUNCATION)
    assert soft.severity.value == "warning"


def test_a_table_with_no_records_and_no_columns_is_empty_not_a_missing_column() -> None:
    """PAKAD-C09: an empty JSON export (``[]``) has no columns to check."""
    profile = parse_profile(NO_PAGING)
    exp = table(Side.EXPECTED, [{"id": "1"}])
    col = Table(Side.COLLECTED, "collected.json", "0" * 64, 0, (), ())
    result = reconcile(profile, exp, col, as_of=AS_OF)
    assert kinds(result) == [Kind.MISSING, Kind.EMPTY_INPUT]
    assert only(result, Kind.EMPTY_INPUT).details["file"] == "collected.json"


def test_a_header_only_table_still_needs_the_profile_columns() -> None:
    profile = parse_profile(NO_PAGING)
    exp = table(Side.EXPECTED, [{"id": "1"}])
    col = table(Side.COLLECTED, [], columns=("other",))
    with pytest.raises(InputError, match="is missing 1 column: uid"):
        reconcile(profile, exp, col, as_of=AS_OF)


def test_an_equivalent_adds_an_accepted_form_and_never_hides_an_identical_value() -> None:
    """PAKAD-C11: the collected value is not rewritten before the comparison."""
    text = NO_PAGING + (
        "[[compare]]\nexpected = 'enabled'\ncollected = 'enabled'\n"
        "equivalents = { 'true' = 'active' }\n"
    )
    same = run(text, [{"id": "1", "enabled": "true"}], [{"uid": "1", "enabled": "true"}])
    assert same.findings == ()
    mapped = run(text, [{"id": "1", "enabled": "active"}], [{"uid": "1", "enabled": "true"}])
    assert mapped.findings == ()
    other = run(text, [{"id": "1", "enabled": "inactive"}], [{"uid": "1", "enabled": "true"}])
    assert kinds(other) == [Kind.FIELD_MISMATCH]
    # The mapping runs from the collected value to the expected value only.
    reverse = run(text, [{"id": "1", "enabled": "true"}], [{"uid": "1", "enabled": "active"}])
    assert kinds(reverse) == [Kind.FIELD_MISMATCH]


@pytest.mark.parametrize(
    ("configured", "shown"),
    [("24", "24"), ("1.5", "1.5"), ("1.23456789", "1.23456789"), ("0.1", "0.1")],
)
def test_the_age_limit_is_reported_exactly_as_configured(configured: str, shown: str) -> None:
    """PAKAD-C15: the report states the rule applied, not a rounded copy of it."""
    text = FRESH.replace("max_age_hours = 24", f"max_age_hours = {configured}")
    assert any(f"at most {shown} hours old" in rule for rule in parse_and_rules(text))
    old = "2026-11-01T12:00:00Z"
    stale = only(run(text, [{"id": "1"}], [{"uid": "1", "at": old}]), Kind.STALE_RECORD)
    assert stale.details["max_age_hours"] == shown


FOLDING = NO_PAGING + "[match]\nnormalize = ['strip', 'casefold']\n"
RAW_KEYS = st.lists(
    st.sampled_from(["a", "A", " a", "a ", "b", "B", "", " ", "ß", "SS", "ss", chr(0xA0)]),
    max_size=8,
)


def oracle(raw: list[str]) -> dict[str, list[str]]:
    """Group raw keys by normalized key, the straightforward way."""
    groups: dict[str, list[str]] = {}
    for value in raw:
        norm = value.strip().casefold()
        if norm:
            groups.setdefault(norm, []).append(value)
    return groups


@given(expected=RAW_KEYS, collected=RAW_KEYS)
def test_reconcile_agrees_with_a_simple_oracle_and_the_schema(
    expected: list[str], collected: list[str]
) -> None:
    """PAKAD-C13: counts per kind, matched keys and the report schema, on random inputs."""
    result = run(FOLDING, [{"id": k} for k in expected], [{"uid": k} for k in collected])
    exp, col = oracle(expected), oracle(collected)
    counts = {kind: kinds(result).count(kind) for kind in Kind}
    assert counts[Kind.MISSING] == len(exp.keys() - col.keys())
    assert counts[Kind.UNEXPECTED] == len(col.keys() - exp.keys())
    assert result.matched_keys == len(exp.keys() & col.keys())
    assert counts[Kind.BLANK_KEY] == sum(1 for k in [*expected, *collected] if not k.strip())
    repeated = [g for side in (exp, col) for g in side.values() if len(g) > 1]
    assert counts[Kind.AMBIGUOUS_KEY] == sum(1 for g in repeated if len(set(g)) > 1)
    assert counts[Kind.DUPLICATE_KEY] == sum(1 for g in repeated if len(set(g)) == 1)

    profile = parse_profile(FOLDING)
    exp_table = table(Side.EXPECTED, [{"id": k} for k in expected], ("id",))
    col_table = table(Side.COLLECTED, [{"uid": k} for k in collected], ("uid",))
    report = build_report(
        result,
        profile,
        exp_table,
        col_table,
        as_of=AS_OF,
        generated_at=AS_OF,
        run_id="0" * 32,
    )
    jsonschema.validate(report, REPORT_SCHEMA, format_checker=jsonschema.FormatChecker())


@pytest.mark.parametrize(
    ("offset_hours", "kind"),
    [
        (24, None),  # exactly the limit is still fresh
        (24.0003, Kind.STALE_RECORD),  # one second over
        (-5 / 60, None),  # exactly five minutes after the reference time is allowed
        (-5 / 60 - 1 / 3600, Kind.INVALID_TIMESTAMP),  # one second later is not
    ],
)
def test_freshness_boundaries(offset_hours: float, kind: Kind | None) -> None:
    """PAKAD-C13: the age limit and the clock tolerance are inclusive."""
    captured = (AS_OF - timedelta(hours=offset_hours)).isoformat()
    result = run(FRESH, [{"id": "1"}], [{"uid": "1", "at": captured}])
    assert kinds(result) == ([kind] if kind else [])
