# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Render a report document as JSON, CSV, Markdown, or HTML text, plus a manifest.

Every renderer reads the same report document, so all formats agree. The
manifest lists every rendered file with its size and SHA-256. Values from
the input files are untrusted: the CSV renderer neutralizes spreadsheet formulas,
the Markdown renderer escapes Markdown and HTML syntax, and the HTML renderer
escapes everything and forbids scripts and network access.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from typing import TYPE_CHECKING, Any

from faithful_pakad.model import KIND_ORDER, Kind
from faithful_pakad.normalize import count
from faithful_pakad.outputs import MANIFEST_SCHEMA_ID, MANIFEST_SCHEMA_VERSION, format_ref
from faithful_pakad.outputs.guidance import GUIDANCE
from faithful_pakad.outputs.safety import (
    csv_cell,
    escape_markdown,
    terminal,
    terminal_line,
    visible,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from faithful_pakad.outputs import Report

CSV_COLUMNS = ("id", "kind", "severity", "key", "source", "message", "details", "run_id")

MAX_SHOWN_PER_KIND = 500
"""HTML and Markdown reports show at most this many findings of each kind.

The JSON and CSV outputs always hold every finding.
"""

MAX_REFS_SHOWN = 20
"""CSV, HTML, and Markdown list at most this many source references for one finding.

A key repeated thousands of times would otherwise put every reference in one cell,
past the 32,767-character limit of a spreadsheet cell. The JSON report keeps them all.
"""

LIMIT_NOTE = (
    "This report covers only what the input files contain. It cannot detect records "
    "a source system never exported, and a clean result is not proof that the "
    "environment is correct."
)

VERIFY_NOTE = (
    "To confirm this report describes the files you hold, compute each file's SHA-256 "
    "hash and compare it with the value above."
)
VERIFY_COMMANDS = (
    ("Linux", "sha256sum FILE"),
    ("macOS", "shasum -a 256 FILE"),
    ("Windows PowerShell", "Get-FileHash -Algorithm SHA256 FILE"),
)


# Shared pieces -------------------------------------------------------------------


def _key_text(key: list[str] | None) -> str:
    return " | ".join(key) if key is not None else "—"


def _refs_text(refs: list[dict[str, Any]]) -> str:
    shown = "; ".join(format_ref(r) for r in refs[:MAX_REFS_SHOWN])
    if len(refs) > MAX_REFS_SHOWN:
        shown += f"; and {len(refs) - MAX_REFS_SHOWN:,} more (all are in pakad-report.json)"
    return shown or "—"


def _details_text(details: dict[str, str]) -> str:
    return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in details.items())


def _groups(report: Report) -> Iterator[tuple[Kind, list[dict[str, Any]]]]:
    """Yield finding kinds that occur, in report order, with their findings."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for finding in report["findings"]:
        by_kind.setdefault(finding["kind"], []).append(finding)
    for kind in KIND_ORDER:
        if kind.value in by_kind:
            yield kind, by_kind[kind.value]


def _status(report: Report) -> tuple[str, str]:
    """Return a status class and headline for the report.

    A clean result says how many checks did not run, so it is never read as a
    full pass when part of the review was skipped.
    """
    s = report["summary"]
    by_kind = s["findings_by_kind"]
    if by_kind.get("nothing-reconciled"):
        return "fail", "Nothing was reconciled: both inputs are empty"
    if s["errors"]:
        found = f"{count(s['errors'], 'error')} and {count(s['warnings'], 'warning')}"
        if by_kind.get("incomplete-export"):
            return "fail", f"An input is incomplete (more pages exist). {found} need review"
        return "fail", f"{found} need review"
    if s["warnings"]:
        return "warn", f"No errors. {count(s['warnings'], 'warning')} need review"
    if report["unknowns"]:
        skipped = count(len(report["unknowns"]), "check")
        return "warn", f"No findings in the supplied inputs, but {skipped} did not run"
    return "pass", "No findings in the supplied inputs"


def _shown(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Limit a group of findings for people-facing reports. Returns shown and hidden."""
    return findings[:MAX_SHOWN_PER_KIND], max(0, len(findings) - MAX_SHOWN_PER_KIND)


def _hidden_note(hidden: int) -> str:
    where = "in pakad-report.json and pakad-findings.csv"
    if hidden == 1:
        return f"1 more finding of this kind is {where}."
    return f"{hidden:,} more findings of this kind are {where}."


def _summary_rows(report: Report) -> list[tuple[str, str]]:
    s = report["summary"]
    return [
        ("Expected records", str(s["expected_records"])),
        ("Collected records", str(s["collected_records"])),
        ("Matched keys", str(s["matched_keys"])),
        ("Errors", str(s["errors"])),
        ("Warnings", str(s["warnings"])),
    ]


def _input_rows(report: Report) -> list[tuple[str, str, str, str, str]]:
    rows = [
        (side.capitalize(), i["file"], str(i["records"]), str(i["bytes"]), i["sha256"])
        for side, i in report["inputs"].items()
    ]
    p = report["profile"]
    rows.append(("Profile", p["file"], "—", "—", p["sha256"]))
    return rows


# JSON and CSV --------------------------------------------------------------------


def render_json(report: Report) -> str:
    """Render the report as indented JSON that follows the published schema."""
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def render_csv(report: Report) -> str:
    """Render findings as CSV, with every cell protected against formula injection."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for f in report["findings"]:
        row = (
            f["id"],
            f["kind"],
            f["severity"],
            _key_text(f["key"]),
            _refs_text(f["refs"]),
            f["message"],
            _details_text(f["details"]),
            report["run_id"],
        )
        writer.writerow([csv_cell(cell) for cell in row])
    return buffer.getvalue()


# Markdown ------------------------------------------------------------------------


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    md = escape_markdown
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(md(c) for c in row) + " |" for row in rows),
    ]


def _md_findings(report: Report) -> list[str]:
    md = escape_markdown
    lines: list[str] = []
    for kind, all_findings in _groups(report):
        guide = GUIDANCE[kind]
        findings, hidden = _shown(all_findings)
        lines += [
            f"### {md(guide.title)} ({len(all_findings)})",
            "",
            f"`{kind.value}`, {findings[0]['severity']}. {md(guide.meaning)}",
            "",
            f"**What to do:** {md(guide.next_step)}",
            "",
            *_md_table(
                ("ID", "Key", "Source", "Details"),
                [
                    (
                        f["id"],
                        _key_text(f["key"]),
                        _refs_text(f["refs"]),
                        _details_text(f["details"]),
                    )
                    for f in findings
                ],
            ),
            "",
        ]
        if hidden:
            lines += [f"*{md(_hidden_note(hidden))}*", ""]
    return lines or ["No findings.", ""]


def render_markdown(report: Report) -> str:
    """Render the report as GitHub-flavored Markdown with every input value escaped."""
    md = escape_markdown
    _, headline = _status(report)
    unknowns = [f"- **{md(u['check'])}:** {md(u['reason'])}" for u in report["unknowns"]]
    lines = [
        f"# Reconciliation report: {md(report['profile']['name'])}",
        "",
        f"**{md(headline)}.**",
        "",
        (
            f"Reference time {md(report['as_of'])}. Generated {md(report['generated_at'])} "
            f"by pakad {md(report['tool']['version'])}. Run ID `{md(report['run_id'])}`."
        ),
        "",
        f"> {md(LIMIT_NOTE)}",
        "",
        "## Summary",
        "",
        *_md_table(("Measure", "Value"), _summary_rows(report)),
        "",
        "## Not verified",
        "",
        *(unknowns or ["Every configured check ran."]),
        "",
        "## Findings",
        "",
        *_md_findings(report),
        "## Evidence",
        "",
        *_md_table(("Input", "File", "Records", "Bytes", "SHA-256"), _input_rows(report)),
        "",
        "Rules applied:",
        "",
        *(f"- {md(rule)}" for rule in report["rules"]),
        "",
        f"{md(VERIFY_NOTE)}",
        "",
        *(f"- {name}: `{command}`" for name, command in VERIFY_COMMANDS),
        "",
    ]
    return "\n".join(lines)


# HTML ----------------------------------------------------------------------------

_CSS = """
:root{--fg:#1f2328;--muted:#59636e;--bg:#fff;--panel:#f6f8fa;--line:#d1d9e0;
--pass:#1a7f37;--warn:#9a6700;--fail:#cf222e;--accent:#0969da;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--fg:#e6edf3;--muted:#9198a1;--bg:#0d1117;
--panel:#151b23;--line:#3d444d;--pass:#3fb950;--warn:#d29922;--fail:#f85149;--accent:#4493f8}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
main{max-width:76rem;margin:0 auto;padding:2rem 1.25rem 4rem}
header p{color:var(--muted);margin:.25rem 0}
h1{font-size:1.65rem;margin:0 0 .25rem}h2{font-size:1.2rem;margin:2.25rem 0 .75rem}
nav{display:flex;flex-wrap:wrap;gap:.25rem 1rem;margin:1rem 0;font-size:.9rem}
a{color:var(--accent)}
.status{border-radius:8px;padding:.85rem 1rem;margin:1.25rem 0;font-weight:600;
border:1px solid currentColor;background:var(--panel)}
.status.pass{color:var(--pass)}.status.warn{color:var(--warn)}.status.fail{color:var(--fail)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.75rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:.75rem 1rem}
.card b{display:block;font-size:1.6rem;line-height:1.2}
.card span{color:var(--muted);font-size:.85rem}
.card.fail b{color:var(--fail)}.card.warn b{color:var(--warn)}
.note{border-left:4px solid var(--warn);background:var(--panel);padding:.6rem 1rem;margin:1rem 0}
details{border:1px solid var(--line);border-radius:8px;margin:.75rem 0;background:var(--bg)}
summary{cursor:pointer;padding:.7rem 1rem;font-weight:600;background:var(--panel);border-radius:8px}
details[open] summary{border-bottom:1px solid var(--line);border-radius:8px 8px 0 0}
.group{padding:.25rem 1rem 1rem}.group p{margin:.5rem 0}
.pill{display:inline-block;border-radius:999px;padding:0 .55rem;font-size:.8rem;font-weight:600;
border:1px solid currentColor;margin-left:.4rem}
.pill.error{color:var(--fail)}.pill.warning{color:var(--warn)}
.table{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border:1px solid var(--line);padding:.4rem .55rem;text-align:left;vertical-align:top}
th{background:var(--panel)}td{overflow-wrap:break-word}td:first-child{white-space:nowrap}
.group table{min-width:40rem}
code{font:.85em ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;
overflow-wrap:anywhere}
footer{margin-top:3rem;color:var(--muted);font-size:.85rem}
@media print{nav{display:none}main{max-width:none;padding:0}details{break-inside:avoid-page}
summary{background:none}a{color:inherit;text-decoration:none}}
"""


CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'"
"""Content security policy: no scripts, no network access, no form submission."""

NAV = "".join(
    f'<a href="#{anchor}">{label}</a>'
    for anchor, label in (
        ("summary", "Summary"),
        ("not-verified", "Not verified"),
        ("findings", "Findings"),
        ("evidence", "Evidence"),
    )
)


def _h(value: object) -> str:
    return html.escape(visible(str(value)), quote=True)


def _html_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], code_column: int = -1
) -> str:
    head = "".join(f'<th scope="col">{_h(h)}</th>' for h in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td><code>{_h(v)}</code></td>" if i == code_column else f"<td>{_h(v)}</td>"
            for i, v in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    return f'<div class="table">{table}</div>'


def _html_cards(report: Report) -> str:
    s = report["summary"]
    cards = [
        ("", s["expected_records"], "expected records"),
        ("", s["collected_records"], "collected records"),
        ("", s["matched_keys"], "matched keys"),
        ("fail" if s["errors"] else "", s["errors"], "errors"),
        ("warn" if s["warnings"] else "", s["warnings"], "warnings"),
    ]
    items = "".join(
        f'<div class="card {c}"><b>{_h(n)}</b><span>{_h(label)}</span></div>'
        for c, n, label in cards
    )
    return f'<div class="cards">{items}</div>'


def _html_findings(report: Report) -> str:
    groups = []
    for kind, all_findings in _groups(report):
        guide = GUIDANCE[kind]
        findings, hidden = _shown(all_findings)
        severity = findings[0]["severity"]
        note = f"<p><em>{_h(_hidden_note(hidden))}</em></p>" if hidden else ""
        rows = [
            (f["id"], _key_text(f["key"]), _refs_text(f["refs"]), _details_text(f["details"]))
            for f in findings
        ]
        groups.append(
            f'<details open id="{_h(kind.value)}"><summary>{_h(guide.title)} '
            f'<span class="pill {_h(severity)}">{len(all_findings)} {_h(severity)}</span></summary>'
            f'<div class="group"><p>{_h(guide.meaning)} <code>{_h(kind.value)}</code></p>'
            f"<p><strong>What to do:</strong> {_h(guide.next_step)}</p>"
            f"{_html_table(('ID', 'Key', 'Source', 'Details'), rows)}{note}</div></details>"
        )
    return "".join(groups) or "<p>No findings.</p>"


def render_html(report: Report) -> str:
    """Render the report as one self-contained HTML page.

    The page works offline in any modern browser, adapts to light and dark mode,
    and prints cleanly. Its content security policy forbids scripts and every
    network request, and every value from the inputs is escaped.
    """
    status_class, headline = _status(report)
    name = report["profile"]["name"]
    unknowns = "".join(
        f"<li><strong>{_h(u['check'])}:</strong> {_h(u['reason'])}</li>" for u in report["unknowns"]
    )
    verify = "".join(f"<li>{_h(n)}: <code>{_h(c)}</code></li>" for n, c in VERIFY_COMMANDS)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="pakad {_h(report["tool"]["version"])}">
<title>Reconciliation report: {_h(name)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<header>
<h1>Reconciliation report: {_h(name)}</h1>
<p>Reference time {_h(report["as_of"])} · Generated {_h(report["generated_at"])}
· pakad {_h(report["tool"]["version"])}</p>
</header>
<nav aria-label="Sections">{NAV}</nav>
<p class="status {status_class}" role="status">{_h(headline)}.</p>
<section id="summary" aria-labelledby="summary-h"><h2 id="summary-h">Summary</h2>
{_html_cards(report)}
<p class="note">{_h(LIMIT_NOTE)}</p></section>
<section id="not-verified" aria-labelledby="nv-h"><h2 id="nv-h">Not verified</h2>
{f"<ul>{unknowns}</ul>" if unknowns else "<p>Every configured check ran.</p>"}</section>
<section id="findings" aria-labelledby="findings-h"><h2 id="findings-h">Findings</h2>
{_html_findings(report)}</section>
<section id="evidence" aria-labelledby="evidence-h"><h2 id="evidence-h">Evidence</h2>
{_html_table(("Input", "File", "Records", "Bytes", "SHA-256"), _input_rows(report), code_column=4)}
<h3>Rules applied</h3>
<ul>{"".join(f"<li>{_h(r)}</li>" for r in report["rules"])}</ul>
<h3>Verify the inputs</h3>
<p>{_h(VERIFY_NOTE)}</p>
<ul>{verify}</ul></section>
<footer>Run ID <code>{_h(report["run_id"])}</code>, shared by every file from this run.
Report schema version {_h(report["schema_version"])}.
Produced by pakad, an open source tool from Faithful Oversight, LLC.</footer>
</main>
</body>
</html>
"""


RENDERERS: dict[str, tuple[str, Callable[[Report], str]]] = {
    "html": ("pakad-report.html", render_html),
    "json": ("pakad-report.json", render_json),
    "csv": ("pakad-findings.csv", render_csv),
    "md": ("pakad-report.md", render_markdown),
}
"""Output formats, in default order: file name and renderer."""


MANIFEST_NAME = "pakad-manifest.json"
"""Written with every run, after every other file."""


def render_manifest(report: Report, outputs: Mapping[str, str]) -> str:
    """List each rendered file with its size and SHA-256, under the report's run ID.

    The manifest ties every file to its run, including a findings CSV with no
    rows, and makes a truncated, edited, or mixed set of files detectable.
    """
    files = []
    for name, text in outputs.items():
        data = text.encode("utf-8")
        files.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "$schema": MANIFEST_SCHEMA_ID,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tool": report["tool"],
        "run_id": report["run_id"],
        "generated_at": report["generated_at"],
        "files": files,
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def render_all(report: Report, formats: list[str]) -> dict[str, str]:
    """Render the report in each requested format, then the manifest, last.

    Returns file name to text, in the order the files should be placed.
    """
    outputs = {RENDERERS[fmt][0]: RENDERERS[fmt][1](report) for fmt in formats}
    outputs[MANIFEST_NAME] = render_manifest(report, outputs)
    return outputs


def terminal_summary(report: Report) -> str:
    """Plain-text summary for the terminal.

    Every name that came from a file or a profile is made single-line before it
    is placed into the layout, so no name can add a line of its own.
    """
    s: dict[str, Any] = report["summary"]
    inputs = report["inputs"]
    name = terminal_line(report["profile"]["name"])
    expected_file = terminal_line(inputs["expected"]["file"])
    collected_file = terminal_line(inputs["collected"]["file"])
    _, headline = _status(report)
    lines = [
        f"pakad {report['tool']['version']}: {name}",
        f"  expected   {s['expected_records']:>7} records  {expected_file}",
        f"  collected  {s['collected_records']:>7} records  {collected_file}",
        f"  matched    {s['matched_keys']:>7} keys",
        "",
        f"{headline}.",
    ]
    lines += [
        f"  {GUIDANCE[kind].title:<40} {len(findings):>5}  ({kind.value})"
        for kind, findings in _groups(report)
    ]
    if report["unknowns"]:
        lines.append(f"{count(len(report['unknowns']), 'check')} not verified; see the report.")
    return terminal("\n".join(lines))
