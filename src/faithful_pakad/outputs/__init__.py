# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Report builders and writers.

``build_report`` turns a result into the versioned report document. Every other
format is rendered from that document, so all formats always agree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from faithful_pakad import __version__
from faithful_pakad.model import KIND_ORDER, Severity

if TYPE_CHECKING:
    from datetime import datetime

    from faithful_pakad.model import Finding, Result, SourceRef, Table
    from faithful_pakad.profile import Profile

SCHEMA_VERSION = "1.0"
SCHEMA_ID = "https://faithful-oversight.github.io/faithful-pakad/schema/report-v1.schema.json"
"""Identifier of the report schema. ``pakad schema`` prints the same schema offline."""

Report = dict[str, Any]


def build_report(  # noqa: PLR0913 - each argument is a distinct part of the report
    result: Result,
    profile: Profile,
    expected: Table,
    collected: Table,
    *,
    as_of: datetime,
    generated_at: datetime,
    run_id: str,
) -> Report:
    """Build the report document that every output format is rendered from."""
    counts = dict.fromkeys((k.value for k in KIND_ORDER), 0)
    for finding in result.findings:
        counts[finding.kind.value] += 1
    errors = sum(1 for f in result.findings if f.severity is Severity.ERROR)
    return {
        "$schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "pakad", "version": __version__},
        "run_id": run_id,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        # Full precision, so replaying with --as-of reproduces the same findings.
        "as_of": as_of.isoformat(),
        "profile": {"name": profile.name, "file": profile.file, "sha256": profile.sha256},
        "inputs": {"expected": _input(expected), "collected": _input(collected)},
        "summary": {
            "expected_records": len(expected.records),
            "collected_records": len(collected.records),
            "matched_keys": result.matched_keys,
            "errors": errors,
            "warnings": len(result.findings) - errors,
            "findings_by_kind": counts,
        },
        "rules": list(result.rules),
        "unknowns": [{"check": u.check, "reason": u.reason} for u in result.unknowns],
        "findings": [_finding(i, f) for i, f in enumerate(result.findings, start=1)],
    }


def _input(table: Table) -> dict[str, Any]:
    return {
        "file": table.file,
        "sha256": table.sha256,
        "bytes": table.size_bytes,
        "records": len(table.records),
        "columns": list(table.columns),
    }


def _finding(number: int, finding: Finding) -> dict[str, Any]:
    return {
        "id": f"F{number:05d}",
        "kind": finding.kind.value,
        "severity": finding.severity.value,
        "message": finding.message,
        "key": list(finding.key) if finding.key is not None else None,
        "refs": [_ref(r) for r in finding.refs],
        "details": dict(finding.details),
    }


def _ref(ref: SourceRef) -> dict[str, Any]:
    return {"input": ref.side.value, "file": ref.file, "row": ref.row, "unit": ref.unit}


def format_ref(ref: dict[str, Any]) -> str:
    """Render a reference for people, for example ``collected: users.csv line 7``.

    The input name comes first, so two inputs with the same file name stay distinct.
    """
    return f"{ref['input']}: {ref['file']} {ref['unit']} {ref['row']}"
