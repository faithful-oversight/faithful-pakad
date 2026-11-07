# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for report building, rendering, and output safety."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

import jsonschema
import pytest
from hypothesis import given
from hypothesis import strategies as st

from faithful_pakad.model import Finding, Kind, Result, Side, SourceRef, Table, Unknown
from faithful_pakad.outputs import build_report, format_ref
from faithful_pakad.outputs.guidance import GUIDANCE
from faithful_pakad.outputs.render import (
    RENDERERS,
    render_all,
    render_csv,
    render_html,
    render_json,
    render_markdown,
    terminal_summary,
)
from faithful_pakad.outputs.safety import FORMULA_TRIGGERS, escape_markdown, neutralize_formula
from faithful_pakad.profile import parse_profile
from tests.conftest import MINIMAL_PROFILE

AS_OF = datetime(2026, 11, 7, 12, tzinfo=UTC)
EVIL = '=HYPERLINK("http://x")<script>alert(1)</script>|`*_[a](b)&amp;'
SCHEMA = json.loads(files("faithful_pakad").joinpath("schema/report-v1.schema.json").read_text())


def make_report(
    findings: tuple[Finding, ...] = (), unknowns: tuple[Unknown, ...] = ()
) -> dict[str, Any]:
    profile = parse_profile(MINIMAL_PROFILE.replace('"test"', '"<b>profile</b>"'))
    exp = Table(Side.EXPECTED, "e.csv", "a" * 64, 10, ("id",), ())
    col = Table(Side.COLLECTED, "c.json", "b" * 64, 20, ("uid",), ())
    result = Result(findings, unknowns, 0, ("rule one",))
    return build_report(result, profile, exp, col, as_of=AS_OF, generated_at=AS_OF)


ALL_KINDS = tuple(
    Finding(
        kind=kind,
        message=f"message {EVIL}",
        key=(EVIL, "k2") if i % 2 else None,
        refs=(SourceRef(Side.EXPECTED, "e.csv", 2), SourceRef(Side.COLLECTED, "c.json", 1, "item")),
        details={"value": EVIL},
    )
    for i, kind in enumerate(Kind)
)


def test_report_matches_schema_with_every_kind() -> None:
    report = make_report(ALL_KINDS, (Unknown("check", EVIL),))
    jsonschema.validate(report, SCHEMA, format_checker=jsonschema.FormatChecker())
    assert report["summary"]["errors"] == 7
    assert report["summary"]["warnings"] == 3
    assert all(n == 1 for n in report["summary"]["findings_by_kind"].values())
    assert report["findings"][0]["id"] == "F00001"
    assert report["findings"][0]["refs"][1] == {
        "input": "collected",
        "file": "c.json",
        "row": 1,
        "unit": "item",
    }


def test_empty_report_matches_schema() -> None:
    jsonschema.validate(make_report(), SCHEMA)


def test_json_round_trips() -> None:
    report = make_report(ALL_KINDS)
    assert json.loads(render_json(report)) == report


def test_every_kind_has_guidance() -> None:
    assert set(GUIDANCE) == set(Kind)


def test_csv_neutralizes_formulas() -> None:
    rows = list(csv.reader(io.StringIO(render_csv(make_report(ALL_KINDS)))))
    assert rows[0] == ["id", "kind", "severity", "key", "source", "message", "details"]
    assert len(rows) == 1 + len(Kind)
    for row in rows[1:]:
        assert not any(cell.startswith(FORMULA_TRIGGERS) for cell in row)
    assert rows[2][3].startswith("'=HYPERLINK")


def test_html_escapes_everything_and_blocks_scripts() -> None:
    page = render_html(make_report(ALL_KINDS, (Unknown("check", EVIL),)))
    assert "<script>" not in page
    assert "<b>profile</b>" not in page
    assert "&lt;script&gt;" in page
    assert "default-src 'none'" in page
    assert "http://x" not in page.split("<body>")[0]
    for kind in Kind:
        assert f'id="{kind.value}"' in page


def test_html_clean_report() -> None:
    page = render_html(make_report())
    assert "No findings in the supplied inputs." in page
    assert "Every configured check ran." in page
    assert "<p>No findings.</p>" in page


def test_markdown_escapes_html_and_tables() -> None:
    text = render_markdown(make_report(ALL_KINDS, (Unknown("check", EVIL),)))
    assert "<script>" not in text
    assert "\\<script\\>" in text
    assert "\\|" in text
    assert "### Stale records (1)" in text


def test_markdown_clean_report() -> None:
    text = render_markdown(make_report())
    assert "No findings." in text
    assert "Every configured check ran." in text


def test_status_headlines() -> None:
    warning = Finding(Kind.STALE_RECORD, "m")
    error = Finding(Kind.MISSING, "m")
    assert "No errors. 1 warning need review" in render_html(make_report((warning,)))
    assert "1 error and 1 warning need review" in render_html(make_report((error, warning)))


def test_render_all_names() -> None:
    out = render_all(make_report(), list(RENDERERS))
    assert set(out) == {
        "pakad-report.html",
        "pakad-report.json",
        "pakad-findings.csv",
        "pakad-report.md",
    }


def test_terminal_summary() -> None:
    text = terminal_summary(make_report(ALL_KINDS, (Unknown("a", "b"),)))
    assert "Possible paging truncation" in text
    assert "1 check not verified" in text


def test_format_ref() -> None:
    assert (
        format_ref({"input": "expected", "file": "a.csv", "row": 3, "unit": "line"})
        == "a.csv line 3"
    )


@given(st.text())
def test_formula_neutralization_is_safe_and_idempotent(value: str) -> None:
    once = neutralize_formula(value)
    assert not once.startswith(FORMULA_TRIGGERS)
    assert neutralize_formula(once) == once
    assert once.removeprefix("'") == value or once == value


@given(st.text())
def test_markdown_escape_never_leaves_raw_markup(value: str) -> None:
    escaped = escape_markdown(value)
    assert "\n" not in escaped
    assert "\r" not in escaped
    unescaped = escaped.replace("\\\\", "")
    for char in "<>|`":
        assert char not in unescaped.replace(f"\\{char}", "")


@pytest.mark.parametrize("value", ["@SUM(A1)", "+1", "-1", "\t=x", "\uff1dcmd"])
def test_known_formula_prefixes(value: str) -> None:
    assert neutralize_formula(value) == "'" + value
