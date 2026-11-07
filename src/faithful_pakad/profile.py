# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Load and validate reconciliation profiles.

A profile is a TOML file that says which columns identify a record, how to
normalize them, which fields to compare, and which collection checks to run.
Validation is strict: unknown settings are errors, so a typo never silently
turns a check off.
"""

from __future__ import annotations

import codecs
import hashlib
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NoReturn

from faithful_pakad.errors import ProfileError
from faithful_pakad.normalize import STEPS, normalize

if TYPE_CHECKING:
    from collections.abc import Mapping

SUPPORTED_VERSION = 1
FORMATS = ("auto", "csv", "json")
NAIVE_TIMESTAMP_POLICIES = ("reject", "utc")
DEFAULT_PAGE_SIZES = (1000, 1500, 5000)
MAX_PROFILE_BYTES = 1024 * 1024
MAX_AGE_HOURS = 87_600  # ten years
FORBIDDEN_DELIMITERS = ('"', "\r", "\n")

Format = Literal["auto", "csv", "json"]


@dataclass(frozen=True, slots=True)
class TableSpec:
    """How to read one input and which columns form its key."""

    key: tuple[str, ...]
    format: Format = "auto"
    delimiter: str | None = None
    encoding: str = "utf-8-sig"


@dataclass(frozen=True, slots=True)
class CompareSpec:
    """A field compared between matched records."""

    expected: str
    collected: str
    normalize: tuple[str, ...] = ("strip",)
    equivalents: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CollectionSpec:
    """Checks on the collected export as a whole."""

    source_column: str | None = None
    expected_sources: tuple[str, ...] = ()
    captured_at_column: str | None = None
    max_age_hours: float | None = None
    naive_timestamps: Literal["reject", "utc"] = "reject"
    page_sizes: tuple[int, ...] = DEFAULT_PAGE_SIZES


@dataclass(frozen=True, slots=True)
class Profile:
    """A validated reconciliation profile."""

    name: str
    expected: TableSpec
    collected: TableSpec
    key_normalize: tuple[str, ...]
    compare: tuple[CompareSpec, ...]
    collection: CollectionSpec
    file: str
    sha256: str


class _Section:
    """Typed, strict access to one table of a parsed TOML document."""

    def __init__(self, data: Mapping[str, Any], where: str) -> None:
        self._data = dict(data)
        self._where = where

    def error(self, name: str, problem: str) -> NoReturn:
        msg = f"{self._where}.{name}: {problem}"
        raise ProfileError(msg)

    def string(self, name: str, default: str | None = None) -> str | None:
        value = self._data.pop(name, default)
        if value is not None and (not isinstance(value, str) or not value):
            self.error(name, "must be a non-empty string")
        return value

    def string_list(self, name: str, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
        value = self._data.pop(name, list(default))
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            self.error(name, "must be a string or a list of non-empty strings")
        if len(set(value)) != len(value):
            self.error(name, "must not repeat values")
        return tuple(value)

    def number(self, name: str) -> float | None:
        value = self._data.pop(name, None)
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or not 0 < value <= MAX_AGE_HOURS
        ):
            self.error(name, f"must be a number greater than 0 and at most {MAX_AGE_HOURS}")
        return float(value)

    def int_list(self, name: str, default: tuple[int, ...]) -> tuple[int, ...]:
        value = self._data.pop(name, list(default))
        if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value
        ):
            self.error(name, "must be a list of positive whole numbers")
        return tuple(sorted(set(value)))

    def table(self, name: str, *, required: bool = False) -> _Section:
        value = self._data.pop(name, None)
        if value is None:
            if required:
                self.error(name, "is required")
            value = {}
        if not isinstance(value, dict):
            self.error(name, "must be a table")
        return _Section(value, f"{self._where}.{name}")

    def table_list(self, name: str) -> list[_Section]:
        value = self._data.pop(name, [])
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            self.error(name, "must be an array of tables")
        return [_Section(v, f"{self._where}.{name}[{i}]") for i, v in enumerate(value)]

    def raw_mapping(self, name: str) -> dict[str, str]:
        value = self._data.pop(name, {})
        if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
            self.error(name, "must be a table of string values")
        return dict(value)

    def choice(self, name: str, choices: tuple[str, ...], default: str) -> str:
        value = self._data.pop(name, default)
        if value not in choices:
            self.error(name, f"must be one of {', '.join(choices)}")
        return str(value)

    def raw(self, name: str) -> object:
        return self._data.pop(name, None)

    def finish(self) -> None:
        if self._data:
            unknown = ", ".join(sorted(self._data))
            noun = "setting" if len(self._data) == 1 else "settings"
            msg = f"{self._where}: unknown {noun}: {unknown}"
            raise ProfileError(msg)


def _steps(section: _Section, name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    steps = section.string_list(name, default=default)
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        msg = (
            f"unknown normalization step {', '.join(unknown)}; "
            f"available: {', '.join(sorted(STEPS))}"
        )
        raise ProfileError(msg)
    return steps


def _table_spec(section: _Section) -> TableSpec:
    key = section.string_list("key")
    if not key:
        section.error("key", "must name at least one column")
    fmt = section.choice("format", FORMATS, "auto")
    delimiter = section.string("delimiter")
    if delimiter is not None and (len(delimiter) != 1 or delimiter in FORBIDDEN_DELIMITERS):
        section.error("delimiter", "must be a single character other than a quote or line break")
    encoding = section.string("encoding", "utf-8-sig") or "utf-8-sig"
    if not _is_text_encoding(encoding):
        section.error("encoding", f"{encoding!r} is not a known text encoding")
    section.finish()
    return TableSpec(
        key=key,
        format=fmt,  # type: ignore[arg-type]  # validated by choice()
        delimiter=delimiter,
        encoding=encoding,
    )


def _is_text_encoding(name: str) -> bool:
    try:
        info = codecs.lookup(name)
    except LookupError:
        return False
    return bool(getattr(info, "_is_text_encoding", True))


def _compare_spec(section: _Section) -> CompareSpec:
    expected = section.string("expected")
    collected = section.string("collected")
    if expected is None or collected is None:
        msg = "each [[compare]] entry needs both 'expected' and 'collected' column names"
        raise ProfileError(msg)
    steps = _steps(section, "normalize", ("strip",))
    equivalents: dict[str, str] = {}
    for raw, meaning in section.raw_mapping("equivalents").items():
        key = normalize(raw, steps)
        if key in equivalents:
            section.error(
                "equivalents", f"{raw!r} is the same as another entry after normalization"
            )
        equivalents[key] = normalize(meaning, steps)
    section.finish()
    return CompareSpec(expected, collected, steps, equivalents)


def _collection_spec(section: _Section) -> CollectionSpec:
    source_column = section.string("source_column")
    expected_sources = section.string_list("expected_sources")
    if expected_sources and source_column is None:
        msg = "collection.expected_sources needs collection.source_column"
        raise ProfileError(msg)
    captured_at_column = section.string("captured_at_column")
    max_age_hours = section.number("max_age_hours")
    if (captured_at_column is None) != (max_age_hours is None):
        msg = "collection.captured_at_column and collection.max_age_hours must be set together"
        raise ProfileError(msg)
    naive = section.choice("naive_timestamps", NAIVE_TIMESTAMP_POLICIES, "reject")
    page_sizes = section.int_list("page_sizes", DEFAULT_PAGE_SIZES)
    section.finish()
    return CollectionSpec(
        source_column=source_column,
        expected_sources=expected_sources,
        captured_at_column=captured_at_column,
        max_age_hours=max_age_hours,
        naive_timestamps=naive,  # type: ignore[arg-type]  # validated by choice()
        page_sizes=page_sizes,
    )


def parse_profile(text: str, *, file: str = "<profile>", sha256: str = "") -> Profile:
    """Parse and validate profile text.

    Args:
        text: TOML text.
        file: Name shown in reports.
        sha256: Hash of the profile file, recorded in reports.

    Returns:
        The validated profile.

    Raises:
        ProfileError: The text is not valid TOML or not a valid profile.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"profile is not valid TOML: {exc}"
        raise ProfileError(msg) from exc
    root = _Section(data, "profile")
    version = root.raw("version")
    if version != SUPPORTED_VERSION:
        msg = f"profile.version must be {SUPPORTED_VERSION}"
        raise ProfileError(msg)
    name = root.string("name") or "unnamed profile"
    expected = _table_spec(root.table("expected", required=True))
    collected = _table_spec(root.table("collected", required=True))
    if len(expected.key) != len(collected.key):
        msg = "expected.key and collected.key must name the same number of columns"
        raise ProfileError(msg)
    match = root.table("match")
    key_normalize = _steps(match, "normalize", ("strip",))
    match.finish()
    compare = tuple(_compare_spec(section) for section in root.table_list("compare"))
    collection = _collection_spec(root.table("collection"))
    root.finish()
    return Profile(
        name=name,
        expected=expected,
        collected=collected,
        key_normalize=key_normalize,
        compare=compare,
        collection=collection,
        file=file,
        sha256=sha256,
    )


def load_profile(path: Path) -> Profile:
    """Read and validate a profile file.

    Raises:
        ProfileError: The file cannot be read or is not a valid profile.
    """
    try:
        if path.stat().st_size > MAX_PROFILE_BYTES:
            msg = f"{path.name}: profile is larger than {MAX_PROFILE_BYTES} bytes"
            raise ProfileError(msg)
        raw = path.read_bytes()
    except OSError as exc:
        msg = f"cannot read profile {path.name}: {exc.strerror}"
        raise ProfileError(msg) from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        msg = f"{path.name}: profile must be UTF-8 text"
        raise ProfileError(msg) from exc
    return parse_profile(text, file=Path(path).name, sha256=hashlib.sha256(raw).hexdigest())
