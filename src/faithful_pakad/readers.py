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
from faithful_pakad.names import display_name, error_path

if TYPE_CHECKING:
    from pathlib import Path

    from faithful_pakad.profile import TableSpec

DEFAULT_MAX_BYTES = 256 * 1024 * 1024
MAX_FIELD_CHARS = 1024 * 1024
JSON_LIST_KEYS = ("value", "records")
MAX_JSON_DEPTH = 64
"""Nested JSON values deeper than this are an input error, on every Python version."""
_SURROGATE = re.compile("[\ud800-\udfff]")
_SURROGATE_MESSAGE = "contains an unpaired surrogate, which is not valid Unicode text"

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
    name = display_name(path)
    where = error_path(path)
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        msg = f"cannot read {side} input {where}: {exc.strerror}"
        raise InputError(msg) from exc
    if len(raw) > max_bytes:
        msg = f"{where}: file is over the {max_bytes}-byte limit; raise it with --max-bytes"
        raise InputError(msg)
    try:
        text = raw.decode(spec.encoding)
    except UnicodeDecodeError as exc:
        msg = f"{where}: not valid {spec.encoding} text at byte {exc.start}"
        raise InputError(msg) from exc
    except LookupError as exc:
        msg = f"{where}: unknown encoding {spec.encoding!r}"
        raise InputError(msg) from exc

    fmt = spec.format if spec.format != "auto" else _detect_format(path)
    if fmt == "json":
        columns, records = _read_json(text, name, where, side)
    else:
        delimiter = spec.delimiter or ("\t" if path.suffix.lower() == ".tsv" else ",")
        columns, records = _read_csv(text, name, where, side, delimiter)
    return Table(
        side=side,
        file=name,
        path=where,
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
    msg = (
        f"{error_path(path)}: cannot tell the format from the extension; set format in the profile"
    )
    raise InputError(msg)


def _read_csv(
    text: str, name: str, where: str, side: Side, delimiter: str
) -> tuple[tuple[str, ...], tuple[Record, ...]]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        header = next(reader, None)
        if not header:
            msg = f"{where}: the file is empty or has no header row"
            raise InputError(msg)
        _reject_surrogates(header, where, 1)
        columns = _check_header(header, where)
        records: list[Record] = []
        last_line = reader.line_num
        for row in reader:
            start = last_line + 1
            last_line = reader.line_num
            if not row:
                continue
            _reject_surrogates(row, where, start)
            if len(row) > len(columns):
                msg = (
                    f"{where}: line {start} has {len(row)} fields but the header has {len(columns)}"
                )
                raise InputError(msg)
            # Short rows store only the fields present; absent columns read as None.
            values: dict[str, Value] = dict(zip(columns, row, strict=False))
            records.append(Record(SourceRef(side, name, start), values))
    except csv.Error as exc:
        msg = f"{where}: malformed CSV near line {reader.line_num}: {exc}"
        raise InputError(msg) from exc
    return columns, tuple(records)


def _reject_surrogates(fields: list[str], where: str, line: int) -> None:
    """Refuse a CSV row with an unpaired surrogate, naming its line and column.

    Some configured encodings, such as ``utf-7`` and ``unicode_escape``, decode
    bytes to lone surrogates. They cannot be written to a report, and replacing
    them would make different identifiers look identical.
    """
    for number, field in enumerate(fields, start=1):
        if _SURROGATE.search(field):
            msg = f"{where}: line {line}, column {number} {_SURROGATE_MESSAGE}"
            raise InputError(msg)


def _check_header(header: list[str], where: str) -> tuple[str, ...]:
    columns = tuple(h.strip() for h in header)
    if any(not c for c in columns):
        msg = f"{where}: the header has an empty column name"
        raise InputError(msg)
    seen: set[str] = set()
    for column in columns:
        if column in seen:
            msg = f"{where}: the header repeats column {column!r}"
            raise InputError(msg)
        seen.add(column)
    return columns


class _Number(str):
    """A JSON number, kept exactly as written in the file."""

    __slots__ = ()


class _UnusableValueError(ValueError):
    """A JSON value pakad will not turn into text."""


def _check_text(text: str) -> str:
    r"""Reject strings with unpaired surrogate escapes such as ``\ud800``.

    JSON allows them, but they are not valid Unicode text. Replacing them would
    make different identifiers look identical, so pakad refuses them instead.
    """
    if _SURROGATE.search(text):
        raise _UnusableValueError(_SURROGATE_MESSAGE)
    return text


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [_check_text(k) for k, _ in pairs]
    if len(set(keys)) != len(keys):
        msg = "an object repeats a property name"
        raise ValueError(msg)
    return dict(pairs)


def _reject_constant(value: str) -> None:
    msg = f"non-standard JSON number {value}"
    raise ValueError(msg)


def _read_json(
    text: str, name: str, where: str, side: Side
) -> tuple[tuple[str, ...], tuple[Record, ...]]:
    try:
        data = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_int=_Number,
            parse_float=_Number,
            object_pairs_hook=_unique_pairs,
        )
    except (ValueError, RecursionError) as exc:
        msg = f"{where}: not valid JSON: {exc}"
        raise InputError(msg) from exc
    if isinstance(data, dict):
        found = [k for k in JSON_LIST_KEYS if isinstance(data.get(k), list)]
        if len(found) != 1:
            msg = f"{where}: expected a JSON array, or an object with a 'value' or 'records' array"
            raise InputError(msg)
        data = data[found[0]]
    if not isinstance(data, list):
        msg = f"{where}: expected a JSON array of objects"
        raise InputError(msg)
    columns: dict[str, None] = {}
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            msg = f"{where}: item {index} is not a JSON object"
            raise InputError(msg)
        stripped = [k.strip() for k in item]
        if len(set(stripped)) != len(stripped):
            msg = f"{where}: item {index} repeats a property name"
            raise InputError(msg)
        rows.append(item)
        columns.update(dict.fromkeys(stripped))
    if "" in columns:
        msg = f"{where}: an object has an empty property name"
        raise InputError(msg)
    records = tuple(
        Record(SourceRef(side, name, index, "item"), _json_values(item, where, index))
        for index, item in enumerate(rows, start=1)
    )
    return tuple(columns), records


def _json_values(item: dict[str, Any], where: str, index: int) -> dict[str, Value]:
    """Convert one JSON object. Only properties present are stored."""
    values: dict[str, Value] = {}
    for key, raw in item.items():
        try:
            values[key.strip()] = _json_text(raw)
        except _UnusableValueError as exc:
            msg = f"{where}: item {index}, property {key.strip()!r} {exc}"
            raise InputError(msg) from exc
    return values


def _json_text(value: object) -> Value:
    """Turn a JSON value into text without guessing at types.

    Numbers keep the exact text from the file, so ``1.0`` stays ``1.0``. Nested
    arrays and objects become compact JSON text, up to ``MAX_JSON_DEPTH`` levels of
    arrays and objects.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value if isinstance(value, _Number) else _check_text(value)
    return _compact(value, 1)


def _compact(value: object, depth: int) -> str:
    """Render ``value``, which sits at ``depth`` counting the field's own value as 1.

    Only arrays and objects count toward ``MAX_JSON_DEPTH``. A scalar inside the
    deepest allowed array is fine, so the limit is the same with or without one.
    """
    if isinstance(value, _Number):
        return str(value)
    if isinstance(value, str):
        return json.dumps(_check_text(value), ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if depth > MAX_JSON_DEPTH:
        msg = f"is nested more than {MAX_JSON_DEPTH} levels deep"
        raise _UnusableValueError(msg)
    if isinstance(value, list):
        return "[" + ", ".join(_compact(v, depth + 1) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items())
        pairs = (f"{json.dumps(k, ensure_ascii=False)}: {_compact(v, depth + 1)}" for k, v in items)
        return "{" + ", ".join(pairs) + "}"
    # json.loads produces no other types.
    msg = f"unexpected JSON value type {type(value).__name__}"  # pragma: no cover
    raise TypeError(msg)  # pragma: no cover
