# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Data types shared by the readers, the reconciliation engine, and the reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

Value = str | None
"""A cell value. ``None`` means the value is absent, which differs from an empty string."""


class Side(StrEnum):
    """Which input a record or finding belongs to."""

    EXPECTED = "expected"
    COLLECTED = "collected"


class Severity(StrEnum):
    """How serious a finding is."""

    ERROR = "error"
    WARNING = "warning"


class Kind(StrEnum):
    """Finding kinds. These values are part of the public output contract."""

    MISSING = "missing"
    UNEXPECTED = "unexpected"
    DUPLICATE_KEY = "duplicate-key"
    AMBIGUOUS_KEY = "ambiguous-key"
    BLANK_KEY = "blank-key"
    FIELD_MISMATCH = "field-mismatch"
    MISSING_SOURCE = "missing-source"
    STALE_RECORD = "stale-record"
    INVALID_TIMESTAMP = "invalid-timestamp"
    POSSIBLE_TRUNCATION = "possible-truncation"
    EMPTY_INPUT = "empty-input"


SEVERITY: Mapping[Kind, Severity] = {
    Kind.MISSING: Severity.ERROR,
    Kind.UNEXPECTED: Severity.ERROR,
    Kind.DUPLICATE_KEY: Severity.ERROR,
    Kind.AMBIGUOUS_KEY: Severity.ERROR,
    Kind.BLANK_KEY: Severity.ERROR,
    Kind.FIELD_MISMATCH: Severity.ERROR,
    Kind.MISSING_SOURCE: Severity.ERROR,
    Kind.STALE_RECORD: Severity.WARNING,
    Kind.INVALID_TIMESTAMP: Severity.WARNING,
    Kind.POSSIBLE_TRUNCATION: Severity.WARNING,
    Kind.EMPTY_INPUT: Severity.WARNING,
}

KIND_ORDER: tuple[Kind, ...] = tuple(Kind)
"""Order in which finding kinds appear in reports."""


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a record came from.

    For CSV inputs, ``row`` is the physical line number where the record starts,
    counting the header as line 1, and ``unit`` is ``"line"``. For JSON inputs,
    ``row`` is the 1-based position of the record in the array, and ``unit`` is
    ``"item"``.
    """

    side: Side
    file: str
    row: int
    unit: Literal["line", "item"] = "line"


@dataclass(frozen=True, slots=True)
class Record:
    """One row of an input, with every value kept as text.

    ``values`` holds only the fields present in the row. Read values with
    ``values.get(column)``: a column missing from the mapping is absent (``None``).
    Storing only present fields keeps memory proportional to the input size, even
    when records have different columns.
    """

    ref: SourceRef
    values: Mapping[str, Value]


@dataclass(frozen=True, slots=True)
class Table:
    """A fully read input file."""

    side: Side
    file: str
    sha256: str
    size_bytes: int
    columns: tuple[str, ...]
    records: tuple[Record, ...]
    path: str = ""
    """The path as the user gave it, for error messages. Reports use ``file`` instead."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One discrepancy, with links to the records that show it."""

    kind: Kind
    message: str
    key: tuple[str, ...] | None = None
    refs: tuple[SourceRef, ...] = ()
    details: Mapping[str, str] = field(default_factory=dict)

    @property
    def severity(self) -> Severity:
        """Return the severity for this finding's kind."""
        return SEVERITY[self.kind]


@dataclass(frozen=True, slots=True)
class Unknown:
    """A check that could not be performed, and why."""

    check: str
    reason: str


@dataclass(frozen=True, slots=True)
class Result:
    """The outcome of one reconciliation."""

    findings: tuple[Finding, ...]
    unknowns: tuple[Unknown, ...]
    matched_keys: int
    rules: tuple[str, ...]
