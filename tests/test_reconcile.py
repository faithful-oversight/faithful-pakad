# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the reconciliation engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from faithful_pakad.errors import InputError
from faithful_pakad.model import Finding, Kind, Record, Result, Side, SourceRef, Table
from faithful_pakad.profile import parse_profile
from faithful_pakad.reconcile import parse_timestamp, reconcile
from tests.conftest import MINIMAL_PROFILE

AS_OF = datetime(2026, 11, 7, 12, tzinfo=UTC)
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
    assert kinds(result) == [Kind.EMPTY_INPUT, Kind.EMPTY_INPUT]
    assert [f.details["input"] for f in result.findings] == ["expected", "collected"]


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
    assert checks == {"source coverage", "record freshness", "paging truncation"}


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
