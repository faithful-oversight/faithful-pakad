# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Reconcile an expected population against a collected export.

Everything here is a pure function of its arguments: no file access, no output,
no clock. That keeps results reproducible and easy to test.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from faithful_pakad.errors import InputError
from faithful_pakad.model import (
    KIND_ORDER,
    Finding,
    Kind,
    Record,
    Result,
    Table,
    Unknown,
)
from faithful_pakad.normalize import count, normalize

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from faithful_pakad.profile import CollectionSpec, CompareSpec, Profile, TableSpec

Key = tuple[str, ...]

FUTURE_TOLERANCE = timedelta(minutes=5)
"""Capture times this far past the reference time are allowed, for small clock differences."""


def reconcile(profile: Profile, expected: Table, collected: Table, *, as_of: datetime) -> Result:
    """Compare the expected population with the collected export.

    Args:
        profile: Validated profile.
        expected: The population that should be present.
        collected: The export that was actually collected.
        as_of: Reference time for freshness checks. Must be timezone-aware.

    Returns:
        Findings, unknowns, the number of matched keys, and the rules applied.

    Raises:
        InputError: A column named in the profile is not in an input.
        ValueError: ``as_of`` is not timezone-aware.
    """
    if as_of.tzinfo is None:
        msg = "as_of must be timezone-aware"
        raise ValueError(msg)
    _require_columns(expected, _expected_columns(profile))
    _require_columns(collected, _collected_columns(profile))

    findings: list[Finding] = [_empty(t) for t in (expected, collected) if not t.records]
    findings.extend(_declared_paging(t) for t in (expected, collected) if t.paging_signals)
    unknowns: list[Unknown] = []
    expected_index = _index(expected, profile.expected, profile.key_normalize, findings)
    collected_index = _index(collected, profile.collected, profile.key_normalize, findings)

    findings.extend(_presence(expected_index, collected_index, profile))
    matched = expected_index.keys() & collected_index.keys()
    findings.extend(_compare(profile, expected_index, collected_index, matched, unknowns))
    findings.extend(_collection(profile.collection, collected, as_of, unknowns))

    return Result(
        findings=tuple(sorted(findings, key=_sort_key)),
        unknowns=tuple(unknowns),
        matched_keys=len(matched),
        rules=_rules(profile),
    )


def _empty(table: Table) -> Finding:
    return Finding(
        kind=Kind.EMPTY_INPUT,
        message=f"The {table.side} input has no records.",
        details={"input": table.side.value, "file": table.file},
    )


def _declared_paging(table: Table) -> Finding:
    """Report a file that says it is one page of a larger result, whatever the page size."""
    return Finding(
        kind=Kind.POSSIBLE_TRUNCATION,
        message=(
            f"The {table.side} input says it is incomplete, so records may be missing from it."
        ),
        details={
            "input": table.side.value,
            "file": table.file,
            "signal": "; ".join(table.paging_signals),
        },
    )


def _raw_key(records: Sequence[Record], columns: Sequence[str]) -> str:
    """Return the key as written in the first record, before normalization."""
    return " | ".join(records[0].values.get(c) or "" for c in columns)


def _expected_columns(profile: Profile) -> list[str]:
    return [*profile.expected.key, *(c.expected for c in profile.compare)]


def _collected_columns(profile: Profile) -> list[str]:
    spec = profile.collection
    optional = [c for c in (spec.source_column, spec.captured_at_column) if c]
    return [*profile.collected.key, *(c.collected for c in profile.compare), *optional]


def _require_columns(table: Table, needed: Iterable[str]) -> None:
    if not table.records and not table.columns:
        # A JSON export with no records has no columns to check. It is reported as an
        # empty input instead of sending the user to fix a profile that may be right.
        return
    missing = [c for c in dict.fromkeys(needed) if c not in table.columns]
    if missing:
        available = ", ".join(table.columns) or "none"
        msg = (
            f"{table.path or table.file} ({table.side} input) is missing "
            f"{count(len(missing), 'column')}: {', '.join(missing)}; "
            f"available: {available}"
        )
        raise InputError(msg)


def _index(
    table: Table, spec: TableSpec, steps: Sequence[str], findings: list[Finding]
) -> dict[Key, list[Record]]:
    """Group records by normalized key. Records with a blank key become findings."""
    index: dict[Key, list[Record]] = defaultdict(list)
    for record in table.records:
        raw = [record.values.get(c) for c in spec.key]
        if any(v is None for v in raw):
            findings.append(_blank(record, spec.key, "is absent"))
            continue
        key = tuple(normalize(v, steps) for v in raw if v is not None)
        if any(not part for part in key):
            findings.append(_blank(record, spec.key, "is empty after normalization"))
            continue
        index[key].append(record)
    findings.extend(_duplicates(table, spec, index))
    return dict(index)


def _blank(record: Record, key_columns: Sequence[str], problem: str) -> Finding:
    return Finding(
        kind=Kind.BLANK_KEY,
        message=f"A {record.ref.side} record has a key that {problem}, so it cannot be matched.",
        refs=(record.ref,),
        details={"key_columns": ", ".join(key_columns)},
    )


def _duplicates(table: Table, spec: TableSpec, index: dict[Key, list[Record]]) -> Iterator[Finding]:
    for key, records in index.items():
        if len(records) < 2:  # noqa: PLR2004 - two records make a duplicate
            continue
        raw_keys = {tuple(r.values.get(c) or "" for c in spec.key) for r in records}
        ambiguous = len(raw_keys) > 1
        kind = Kind.AMBIGUOUS_KEY if ambiguous else Kind.DUPLICATE_KEY
        detail = (
            "Different raw values become the same key after normalization"
            if ambiguous
            else "The same key appears more than once"
        )
        yield Finding(
            kind=kind,
            message=f"{detail} in the {table.side} input ({len(records)} records).",
            key=key,
            refs=tuple(r.ref for r in records),
            details={"raw_values": "; ".join(sorted(" | ".join(k) for k in raw_keys))},
        )


def _presence(
    expected: dict[Key, list[Record]], collected: dict[Key, list[Record]], profile: Profile
) -> Iterator[Finding]:
    for key in expected.keys() - collected.keys():
        yield Finding(
            kind=Kind.MISSING,
            message="Expected record has no match in the collected export.",
            key=key,
            refs=tuple(r.ref for r in expected[key]),
            details={
                "key_columns": ", ".join(profile.expected.key),
                "raw_key": _raw_key(expected[key], profile.expected.key),
            },
        )
    for key in collected.keys() - expected.keys():
        yield Finding(
            kind=Kind.UNEXPECTED,
            message="Collected record is not in the expected population.",
            key=key,
            refs=tuple(r.ref for r in collected[key]),
            details={
                "key_columns": ", ".join(profile.collected.key),
                "raw_key": _raw_key(collected[key], profile.collected.key),
            },
        )


def _compare(
    profile: Profile,
    expected: dict[Key, list[Record]],
    collected: dict[Key, list[Record]],
    matched: set[Key],
    unknowns: list[Unknown],
) -> Iterator[Finding]:
    if not profile.compare:
        unknowns.append(
            Unknown(
                check="field comparison",
                reason=(
                    "Not checked: the profile lists no [[compare]] fields, "
                    "so only key presence was compared."
                ),
            )
        )
        return
    skipped = 0
    for key in matched:
        if len(expected[key]) != 1 or len(collected[key]) != 1:
            skipped += 1
            continue
        for spec in profile.compare:
            finding = _compare_one(spec, key, expected[key][0], collected[key][0])
            if finding:
                yield finding
    if skipped:
        unknowns.append(
            Unknown(
                check="field comparison",
                reason=(
                    f"Skipped for {count(skipped, 'matched key')} with duplicate records, "
                    "because the records to compare cannot be chosen safely."
                ),
            )
        )


def _compare_one(spec: CompareSpec, key: Key, exp: Record, col: Record) -> Finding | None:
    exp_raw = exp.values.get(spec.expected)
    col_raw = col.values.get(spec.collected)
    if exp_raw is not None and col_raw is not None:
        exp_value = normalize(exp_raw, spec.normalize)
        col_value = normalize(col_raw, spec.normalize)
        # An equivalent is an extra accepted form, never a replacement: identical
        # values always match, even when the value is also listed as an equivalent.
        if col_value == exp_value or spec.equivalents.get(col_value) == exp_value:
            return None
    if exp_raw is None and col_raw is None:
        message = f"{spec.expected} (expected) and {spec.collected} (collected) are both absent."
    else:
        message = f"{spec.expected} (expected) and {spec.collected} (collected) differ."
    return Finding(
        kind=Kind.FIELD_MISMATCH,
        message=message,
        key=key,
        refs=(exp.ref, col.ref),
        details={
            "field": f"{spec.expected} / {spec.collected}",
            "expected_value": _show(exp_raw),
            "collected_value": _show(col_raw),
        },
    )


def _show(value: str | None) -> str:
    return "(absent)" if value is None else value


def _collection(
    spec: CollectionSpec, collected: Table, as_of: datetime, unknowns: list[Unknown]
) -> Iterator[Finding]:
    yield from _sources(spec, collected, unknowns)
    yield from _freshness(spec, collected, as_of, unknowns)
    yield from _truncation(spec, collected, unknowns)


def _source_counts(spec: CollectionSpec, collected: Table) -> Counter[str]:
    column = spec.source_column
    if column is None:
        return Counter()
    return Counter(
        normalize(v, ("strip", "casefold"))
        for r in collected.records
        if (v := r.values.get(column)) is not None
    )


def _sources(spec: CollectionSpec, collected: Table, unknowns: list[Unknown]) -> Iterator[Finding]:
    if not spec.expected_sources:
        unknowns.append(
            Unknown(
                check="source coverage",
                reason="Not checked: the profile lists no expected sources.",
            )
        )
        return
    counts = _source_counts(spec, collected)
    for source in spec.expected_sources:
        if counts[normalize(source, ("strip", "casefold"))] == 0:
            yield Finding(
                kind=Kind.MISSING_SOURCE,
                message=f"No collected records come from expected source {source!r}.",
                details={"source_column": spec.source_column or "", "source": source},
            )


def _freshness(
    spec: CollectionSpec, collected: Table, as_of: datetime, unknowns: list[Unknown]
) -> Iterator[Finding]:
    column = spec.captured_at_column
    if column is None or spec.max_age_hours is None:
        unknowns.append(
            Unknown(
                check="record freshness",
                reason="Not checked: the profile sets no capture time column.",
            )
        )
        return
    limit = timedelta(hours=spec.max_age_hours)
    for record in collected.records:
        raw = record.values.get(column)
        when = parse_timestamp(raw, assume_utc=spec.naive_timestamps == "utc")
        if when is None:
            yield Finding(
                kind=Kind.INVALID_TIMESTAMP,
                message=f"Capture time in {column} is absent or not a usable ISO 8601 timestamp.",
                refs=(record.ref,),
                details={"column": column, "value": _show(raw)},
            )
        elif when > as_of + FUTURE_TOLERANCE:
            yield Finding(
                kind=Kind.INVALID_TIMESTAMP,
                message=f"Capture time in {column} is later than the reference time.",
                refs=(record.ref,),
                details={"column": column, "value": _show(raw), "as_of": as_of.isoformat()},
            )
        elif as_of - when > limit:
            yield Finding(
                kind=Kind.STALE_RECORD,
                message=f"Record was captured {_age(as_of - when)} before the reference time.",
                refs=(record.ref,),
                details={
                    "column": column,
                    "captured_at": when.isoformat(),
                    "max_age_hours": _hours(spec.max_age_hours),
                },
            )


def _hours(value: float) -> str:
    """Return an age limit exactly as configured: the shortest text that reads back the same."""
    text = repr(value)
    return text.removesuffix(".0")


def _age(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 48:  # noqa: PLR2004 - switch to days after two days
        return f"{hours:.1f} hours"
    return f"{hours / 24:,.1f} days"


def parse_timestamp(value: str | None, *, assume_utc: bool) -> datetime | None:
    """Parse an ISO 8601 timestamp.

    Returns ``None`` when the value is absent or invalid, or when it has no time
    zone and ``assume_utc`` is false.
    """
    if value is None:
        return None
    text = value.strip()
    if text.endswith(("z", "Z")):
        text = text[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=UTC) if assume_utc else None
    return when


def _truncation(
    spec: CollectionSpec, collected: Table, unknowns: list[Unknown]
) -> Iterator[Finding]:
    if not spec.page_sizes:
        unknowns.append(
            Unknown(check="paging truncation", reason="Not checked: no page sizes configured.")
        )
        return
    # The overall count is a separate entry, so no source name can replace it.
    groups: list[tuple[str | None, int]] = [(None, len(collected.records))]
    groups.extend(_source_counts(spec, collected).items())
    for source, records in groups:
        sizes = [p for p in spec.page_sizes if records and records % p == 0]
        if sizes:
            details = {"records": str(records), "page_sizes": _join(sizes)}
            details |= {"scope": "all records"} if source is None else {"source": source}
            yield Finding(
                kind=Kind.POSSIBLE_TRUNCATION,
                message=(
                    f"{records} records is an exact multiple of a common page size, "
                    "which can mean a paged export stopped early."
                ),
                details=details,
            )


def _join(values: Iterable[int]) -> str:
    return ", ".join(str(v) for v in values)


def _rules(profile: Profile) -> tuple[str, ...]:
    rules = [
        (
            f"Match expected [{', '.join(profile.expected.key)}] to collected "
            f"[{', '.join(profile.collected.key)}] after normalization: "
            f"{', '.join(profile.key_normalize) or 'none'}."
        ),
    ]
    rules.extend(
        f"Compare {c.expected} with {c.collected} after normalization: "
        f"{', '.join(c.normalize) or 'none'}"
        + (f"; equivalents: {_equivalents(c)}" if c.equivalents else "")
        + "."
        for c in profile.compare
    )
    spec = profile.collection
    if spec.expected_sources:
        rules.append(
            f"Every expected source must appear in {spec.source_column}: "
            f"{', '.join(spec.expected_sources)}."
        )
    if spec.captured_at_column and spec.max_age_hours is not None:
        rules.append(
            f"Records in {spec.captured_at_column} must be at most "
            f"{_hours(spec.max_age_hours)} hours old (naive timestamps: {spec.naive_timestamps})."
        )
    if spec.page_sizes:
        rules.append(f"Warn when record counts are exact multiples of {_join(spec.page_sizes)}.")
    return tuple(rules)


def _equivalents(spec: CompareSpec) -> str:
    return ", ".join(f"{k} = {v}" for k, v in spec.equivalents.items())


def _sort_key(finding: Finding) -> tuple[int, tuple[str, ...], tuple[tuple[str, str, int], ...]]:
    refs = tuple((r.side.value, r.file, r.row) for r in finding.refs)
    return (KIND_ORDER.index(finding.kind), finding.key or (), refs)
