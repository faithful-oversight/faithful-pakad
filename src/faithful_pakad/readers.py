# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Read CSV and JSON exports into tables of text values.

Inputs are untrusted. The readers enforce a size limit, decode strictly, never
convert values to numbers or dates, and report problems with the line or
position where they occur.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from typing import TYPE_CHECKING, Any

from faithful_pakad.errors import InputError
from faithful_pakad.model import Record, Side, SourceRef, Table, Value

if TYPE_CHECKING:
    from pathlib import Path

    from faithful_pakad.profile import TableSpec

DEFAULT_MAX_BYTES = 256 * 1024 * 1024
MAX_FIELD_CHARS = 1024 * 1024
JSON_LIST_KEYS = ("value", "records")
_SURROGATE = re.compile("[\ud800-\udfff]")

csv.field_size_limit(MAX_FIELD_CHARS)


def read_table(
    path: Path, spec: TableSpec, side: Side, *, max_bytes: int = DEFAULT_MAX_BYTES
) -> Table:
    """Read one input file.

    Args:
        path: File to read.
        spec: Format, delimiter, and encoding settings from the profile.
        side: Whether this is the expected or the collected input.
        max_bytes: Refuse files larger than this.

    Returns:
        The table, with every value as text or ``None`` when absent.

    Raises:
        InputError: The file cannot be read, is too large, or is malformed.
    """
    name = path.name
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        msg = f"cannot read {side} input {name}: {exc.strerror}"
        raise InputError(msg) from exc
    if len(raw) > max_bytes:
        msg = f"{name}: file is over the {max_bytes}-byte limit; raise it with --max-bytes"
        raise InputError(msg)
    try:
        text = raw.decode(spec.encoding)
    except UnicodeDecodeError as exc:
        msg = f"{name}: not valid {spec.encoding} text at byte {exc.start}"
        raise InputError(msg) from exc
    except LookupError as exc:
        msg = f"{name}: unknown encoding {spec.encoding!r}"
        raise InputError(msg) from exc

    fmt = spec.format if spec.format != "auto" else _detect_format(path)
    if fmt == "json":
        columns, records = _read_json(text, name, side)
    else:
        delimiter = spec.delimiter or ("\t" if path.suffix.lower() == ".tsv" else ",")
        columns, records = _read_csv(text, name, side, delimiter)
    return Table(
        side=side,
        file=name,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        columns=columns,
        records=records,
    )


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        return "csv"
    if suffix == ".json":
        return "json"
    msg = f"{path.name}: cannot tell the format from the extension; set format in the profile"
    raise InputError(msg)


def _read_csv(
    text: str, name: str, side: Side, delimiter: str
) -> tuple[tuple[str, ...], tuple[Record, ...]]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        header = next(reader, None)
        if not header:
            msg = f"{name}: the file is empty or has no header row"
            raise InputError(msg)
        columns = _check_header(header, name)
        records: list[Record] = []
        last_line = reader.line_num
        for row in reader:
            start = last_line + 1
            last_line = reader.line_num
            if not row:
                continue
            if len(row) > len(columns):
                msg = (
                    f"{name}: line {start} has {len(row)} fields but the header has {len(columns)}"
                )
                raise InputError(msg)
            values: dict[str, Value] = dict.fromkeys(columns)
            values.update(zip(columns, row, strict=False))
            records.append(Record(SourceRef(side, name, start), values))
    except csv.Error as exc:
        msg = f"{name}: malformed CSV near line {reader.line_num}: {exc}"
        raise InputError(msg) from exc
    return columns, tuple(records)


def _check_header(header: list[str], name: str) -> tuple[str, ...]:
    columns = tuple(h.strip() for h in header)
    if any(not c for c in columns):
        msg = f"{name}: the header has an empty column name"
        raise InputError(msg)
    seen: set[str] = set()
    for column in columns:
        if column in seen:
            msg = f"{name}: the header repeats column {column!r}"
            raise InputError(msg)
        seen.add(column)
    return columns


class _Number(str):
    """A JSON number, kept exactly as written in the file."""

    __slots__ = ()


def _clean(text: str) -> str:
    """Replace lone surrogates, which JSON allows but UTF-8 cannot encode."""
    return _SURROGATE.sub("\ufffd", text)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    pairs = [(_clean(k), v) for k, v in pairs]
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        msg = "an object repeats a property name"
        raise ValueError(msg)
    return dict(pairs)


def _reject_constant(value: str) -> None:
    msg = f"non-standard JSON number {value}"
    raise ValueError(msg)


def _read_json(text: str, name: str, side: Side) -> tuple[tuple[str, ...], tuple[Record, ...]]:
    try:
        data = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_int=_Number,
            parse_float=_Number,
            object_pairs_hook=_unique_pairs,
        )
    except (ValueError, RecursionError) as exc:
        msg = f"{name}: not valid JSON: {exc}"
        raise InputError(msg) from exc
    if isinstance(data, dict):
        found = [k for k in JSON_LIST_KEYS if isinstance(data.get(k), list)]
        if len(found) != 1:
            msg = f"{name}: expected a JSON array, or an object with a 'value' or 'records' array"
            raise InputError(msg)
        data = data[found[0]]
    if not isinstance(data, list):
        msg = f"{name}: expected a JSON array of objects"
        raise InputError(msg)
    columns: dict[str, None] = {}
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            msg = f"{name}: item {index} is not a JSON object"
            raise InputError(msg)
        stripped = [k.strip() for k in item]
        if len(set(stripped)) != len(stripped):
            msg = f"{name}: item {index} repeats a property name"
            raise InputError(msg)
        rows.append(item)
        columns.update(dict.fromkeys(stripped))
    if "" in columns:
        msg = f"{name}: an object has an empty property name"
        raise InputError(msg)
    ordered = tuple(columns)
    records = tuple(
        Record(
            SourceRef(side, name, index, "item"),
            dict.fromkeys(ordered) | {k.strip(): _json_text(v) for k, v in item.items()},
        )
        for index, item in enumerate(rows, start=1)
    )
    return ordered, records


def _json_text(value: object) -> Value:
    """Turn a JSON value into text without guessing at types.

    Numbers keep the exact text from the file, so ``1.0`` stays ``1.0``. Nested
    arrays and objects become compact JSON text.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value if isinstance(value, _Number) else _clean(value)
    return _compact(value)


def _compact(value: object) -> str:
    if isinstance(value, _Number):
        return str(value)
    if isinstance(value, str):
        return json.dumps(_clean(value), ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(_compact(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items())
        pairs = (f"{json.dumps(k, ensure_ascii=False)}: {_compact(v)}" for k, v in items)
        return "{" + ", ".join(pairs) + "}"
    # json.loads produces no other types.
    msg = f"unexpected JSON value type {type(value).__name__}"  # pragma: no cover
    raise TypeError(msg)  # pragma: no cover
