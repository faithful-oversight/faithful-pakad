# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for report building, rendering, and output safety."""

from __future__ import annotations

import csv
import hashlib
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
    CSV_COLUMNS,
    RENDERERS,
    _hidden_note,
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
CSV_HEADER = ("id", "kind", "severity", "key", "source", "message", "details", "run_id")
EVIL = '=HYPERLINK("http://x")<script>alert(1)</script>|`*_[a](b)&amp;'
SCHEMA = json.loads(files("faithful_pakad").joinpath("schema/report-v1.schema.json").read_text())
MANIFEST_SCHEMA = json.loads(
    files("faithful_pakad").joinpath("schema/manifest-v1.schema.json").read_text()
)


def make_report(
    findings: tuple[Finding, ...] = (), unknowns: tuple[Unknown, ...] = ()
) -> dict[str, Any]:
    profile = parse_profile(MINIMAL_PROFILE.replace('"test"', '"<b>profile</b>"'))
    exp = Table(Side.EXPECTED, "e.csv", "a" * 64, 10, ("id",), ())
    col = Table(Side.COLLECTED, "c.json", "b" * 64, 20, ("uid",), ())
    result = Result(findings, unknowns, 0, ("rule one",))
    run_id = "0123456789abcdef" * 2
    return build_report(result, profile, exp, col, as_of=AS_OF, generated_at=AS_OF, run_id=run_id)


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
    assert report["summary"]["errors"] == 9
    assert report["summary"]["warnings"] == 4
    assert report["schema_version"] == "1.1"
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
    assert rows[0] == [*CSV_HEADER]
    assert {row[7] for row in rows[1:]} == {"0123456789abcdef" * 2}
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
        "pakad-manifest.json",
    }
    assert list(out)[-1] == "pakad-manifest.json"


@pytest.mark.parametrize("findings", [(), ALL_KINDS])
def test_manifest_lists_every_file_with_its_digest(findings: tuple[Finding, ...]) -> None:
    report = make_report(findings)
    out = render_all(report, list(RENDERERS))
    manifest = json.loads(out["pakad-manifest.json"])
    jsonschema.validate(manifest, MANIFEST_SCHEMA, format_checker=jsonschema.FormatChecker())
    assert manifest["run_id"] == report["run_id"]
    assert manifest["generated_at"] == report["generated_at"]
    assert manifest["tool"] == report["tool"]
    assert [f["name"] for f in manifest["files"]] == list(out)[:-1]
    for entry in manifest["files"]:
        data = out[entry["name"]].encode("utf-8")
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()


def test_manifest_covers_only_the_chosen_formats() -> None:
    out = render_all(make_report(), ["csv"])
    assert list(out) == ["pakad-findings.csv", "pakad-manifest.json"]
    assert out["pakad-findings.csv"] == ",".join(CSV_COLUMNS) + "\r\n"
    assert [f["name"] for f in json.loads(out["pakad-manifest.json"])["files"]] == [
        "pakad-findings.csv"
    ]


def test_terminal_summary() -> None:
    text = terminal_summary(make_report(ALL_KINDS, (Unknown("a", "b"),)))
    assert "Possible paging truncation" in text
    assert "1 check not verified" in text


def test_format_ref_names_the_input() -> None:
    """Two inputs with the same file name stay distinguishable."""
    ref = {"input": "expected", "file": "users.csv", "row": 3, "unit": "line"}
    assert format_ref(ref) == "expected: users.csv line 3"
    assert CSV_COLUMNS == CSV_HEADER


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


@pytest.mark.parametrize("value", ["@SUM(A1)", "+1", "-1+1", "\t=x", "\uff1dcmd"])
def test_known_formula_prefixes(value: str) -> None:
    assert neutralize_formula(value) == "'" + value


def test_unknowns_prevent_a_full_pass_headline() -> None:
    page = render_html(make_report((), (Unknown("source coverage", "Not checked."),)))
    assert "No findings in the supplied inputs, but 1 check did not run." in page
    assert "No findings in the supplied inputs, but 1 check did not run." in render_markdown(
        make_report((), (Unknown("a", "b"),))
    )


def test_large_groups_are_capped_in_people_facing_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("faithful_pakad.outputs.render.MAX_SHOWN_PER_KIND", 1)
    findings = (Finding(Kind.MISSING, "a", ("1",)), Finding(Kind.MISSING, "b", ("2",)))
    report = make_report(findings)
    for text in (render_html(report), render_markdown(report)):
        assert "1 more finding of this kind is in pakad-report.json and pakad-findings.csv." in text
        assert "F00002" not in text
    assert "F00002" in render_csv(report)
    assert len(json.loads(render_json(report))["findings"]) == 2


def test_the_hidden_findings_note_has_the_right_number() -> None:
    assert (
        _hidden_note(1)
        == "1 more finding of this kind is in pakad-report.json and pakad-findings.csv."
    )
    assert (
        _hidden_note(2)
        == "2 more findings of this kind are in pakad-report.json and pakad-findings.csv."
    )
    assert _hidden_note(1500).startswith("1,500 more findings of this kind are in")


def test_a_finding_with_thousands_of_references_stays_within_a_spreadsheet_cell() -> None:
    """PAKAD-C10: one CSV cell must not pass 32,767 characters; JSON keeps every reference."""
    refs = tuple(SourceRef(Side.COLLECTED, "c.csv", row) for row in range(2, 3002))
    finding = Finding(Kind.DUPLICATE_KEY, "dup", ("A1",), refs)
    report = make_report((finding,))
    cells = [c for row in csv.reader(io.StringIO(render_csv(report), newline="")) for c in row]
    assert max(len(c) for c in cells) < 32_767
    source = next(c for c in cells if c.startswith("collected: c.csv line 2"))
    assert source.count("collected: c.csv") == 20
    assert "and 2,980 more (all are in pakad-report.json)" in source
    for text in (render_html(report), render_markdown(report)):
        assert "and 2,980 more" in text
        assert "line 3001" not in text
    assert len(json.loads(render_json(report))["findings"][0]["refs"]) == 3000


def test_a_few_references_are_all_listed() -> None:
    refs = tuple(SourceRef(Side.COLLECTED, "c.csv", row) for row in range(2, 22))
    text = render_csv(make_report((Finding(Kind.DUPLICATE_KEY, "dup", ("A1",), refs),)))
    assert "line 21" in text
    assert "more (all are" not in text


INVISIBLE = "a\x1b[31mred\u202etxt.exe\x00"


def test_invisible_characters_are_shown_not_hidden() -> None:
    finding = Finding(Kind.MISSING, "m", (INVISIBLE,), details={"v": INVISIBLE})
    report = make_report((finding,))
    for text in (render_html(report), render_markdown(report), render_csv(report)):
        assert "\x1b" not in text
        assert "\u202e" not in text
        assert "\x00" not in text
        assert "\\u202e" in text
        assert "\\u001b" in text
    assert json.loads(render_json(report))["findings"][0]["key"] == [INVISIBLE]
    assert "\x1b" not in terminal_summary(make_report((Finding(Kind.MISSING, INVISIBLE),)))


def test_markdown_breaks_autolinks() -> None:
    escaped = escape_markdown("see http://evil.example and www.evil.example or a@evil.example")
    assert "http://evil" not in escaped
    assert "www.evil" not in escaped
    assert "a@evil" not in escaped
    assert escaped.replace("\u2060", "") == (
        "see http://evil.example and www.evil.example or a@evil.example"
    )
