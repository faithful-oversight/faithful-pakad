# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for profile loading and validation."""

from __future__ import annotations

import os
import stat
import sys
import threading
from typing import TYPE_CHECKING

import pytest

from faithful_pakad.cli import ExitCode, main
from faithful_pakad.errors import ProfileError
from faithful_pakad.profile import DEFAULT_PAGE_SIZES, load_profile, parse_profile
from tests.conftest import EXAMPLE_DIR, MINIMAL_PROFILE

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_minimal_profile_uses_defaults() -> None:
    profile = parse_profile(MINIMAL_PROFILE)
    assert profile.name == "test"
    assert profile.expected.key == ("id",)
    assert profile.collected.key == ("uid",)
    assert profile.expected.format == "auto"
    assert profile.expected.encoding == "utf-8-sig"
    assert profile.key_normalize == ("strip",)
    assert profile.compare == ()
    assert profile.collection.page_sizes == DEFAULT_PAGE_SIZES
    assert profile.collection.naive_timestamps == "reject"


def test_example_profile_loads_with_hash() -> None:
    profile = load_profile(EXAMPLE_DIR / "profile.toml")
    assert profile.file == "profile.toml"
    assert len(profile.sha256) == 64
    assert profile.compare[0].equivalents == {"true": "active", "false": "terminated"}
    assert profile.collection.expected_sources[-1] == "apac.corp.example"
    assert profile.collection.max_age_hours == 24


def test_key_given_as_a_string_is_accepted() -> None:
    text = MINIMAL_PROFILE.replace('key = ["id"]', 'key = "id"')
    assert parse_profile(text).expected.key == ("id",)


def test_page_sizes_are_sorted_and_deduplicated() -> None:
    text = MINIMAL_PROFILE + "[collection]\npage_sizes = [500, 100, 500]\n"
    assert parse_profile(text).collection.page_sizes == (100, 500)


def test_name_defaults_when_absent() -> None:
    assert parse_profile(MINIMAL_PROFILE.replace('name = "test"', "")).name == "unnamed profile"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda _: "not toml [", "not valid TOML"),
        (lambda t: t.replace("version = 1", "version = 2"), "version must be 1"),
        (lambda t: t.replace("version = 1", ""), "version must be 1"),
        (lambda t: "colour = 1\n" + t, "profile: unknown setting: colour"),
        (lambda t: t.replace('[collected]\nkey = ["uid"]', ""), "collected: is required"),
        (lambda t: t.replace('key = ["uid"]', "key = []"), "must name at least one column"),
        (lambda t: t.replace('key = ["uid"]', 'key = ["a", "b"]'), "same number of columns"),
        (lambda t: t.replace('key = ["uid"]', 'key = ["a", "a"]'), "must not repeat"),
        (lambda t: t.replace('key = ["uid"]', "key = [1]"), "non-empty strings"),
        (lambda t: t.replace('key = ["uid"]', 'key = ["uid"]\ndelimiter = ";;"'), "single char"),
        (lambda t: t.replace('key = ["uid"]', 'key = ["uid"]\nformat = "xml"'), "one of auto"),
        (lambda t: t.replace('key = ["uid"]', 'key = ["uid"]\nencoding = ""'), "non-empty str"),
        (lambda t: t.replace('name = "test"', "name = 5"), "non-empty string"),
        (lambda t: t + "[match]\nnormalize = ['shout']\n", "unknown normalization step"),
        (lambda t: "match = 3\n" + t, "must be a table"),
        (lambda t: t + "[[compare]]\nexpected = 'a'\n", "needs both"),
        (lambda t: "compare = 1\n" + t, "array of tables"),
        (lambda t: t + "[[compare]]\nexpected='a'\ncollected='b'\nequivalents={x=1}\n", "string"),
        (lambda t: t + "[collection]\nexpected_sources = ['a']\n", "needs collection.source"),
        (lambda t: t + "[collection]\ncaptured_at_column = 'c'\n", "set together"),
        (
            lambda t: t + "[collection]\nmax_age_hours = 0\ncaptured_at_column='c'\n",
            "greater than 0",
        ),
        (lambda t: t + "[collection]\nmax_age_hours = true\ncaptured_at_column='c'\n", "greater"),
        (lambda t: t + "[collection]\nmax_age_hours = inf\ncaptured_at_column='c'\n", "at most"),
        (lambda t: t + "[collection]\nmax_age_hours = nan\ncaptured_at_column='c'\n", "at most"),
        (lambda t: t + "[collection]\nmax_age_hours = 1e9\ncaptured_at_column='c'\n", "at most"),
        (
            lambda t: t.replace('key = ["uid"]', 'key = ["uid"]\ndelimiter = \'"\''),
            "other than a quote",
        ),
        (
            lambda t: t.replace('key = ["uid"]', 'key = ["uid"]\nencoding = "nope"'),
            "not a known text",
        ),
        (
            lambda t: t.replace('key = ["uid"]', 'key = ["uid"]\nencoding = "base64"'),
            "not a known text",
        ),
        (
            lambda t: (
                t + "[[compare]]\nexpected='a'\ncollected='b'\nequivalents={' X'='1', 'X'='2'}\n"
            ),
            "same as another entry",
        ),
        (lambda t: t + "[collection]\npage_sizes = [0]\n", "positive whole"),
        (lambda t: t + "[collection]\nnaive_timestamps = 'local'\n", "one of reject"),
    ],
)
def test_invalid_profiles_are_rejected(change: Callable[[str], str], message: str) -> None:
    with pytest.raises(ProfileError, match=message.replace("(", r"\(").replace(")", r"\)")):
        parse_profile(change(MINIMAL_PROFILE))


def test_equivalents_are_normalized() -> None:
    text = MINIMAL_PROFILE + (
        "[[compare]]\nexpected = 'a'\ncollected = 'b'\n"
        "normalize = ['strip', 'casefold']\nequivalents = { ' TRUE ' = 'Active' }\n"
    )
    assert parse_profile(text).compare[0].equivalents == {"true": "active"}


def test_load_profile_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="cannot read profile"):
        load_profile(tmp_path / "absent.toml")


def test_load_profile_rejects_non_utf8(write: Callable[[str, str | bytes], Path]) -> None:
    with pytest.raises(ProfileError, match="must be UTF-8"):
        load_profile(write("p.toml", b"\xff\xfe\x00bad"))


def test_load_profile_rejects_huge_file(write: Callable[[str, str | bytes], Path]) -> None:
    with pytest.raises(ProfileError, match="larger than"):
        load_profile(write("p.toml", "#" * (1024 * 1024 + 1)))


@pytest.mark.parametrize("version", ["true", "1.0", '"1"', "2", "-1"])
def test_version_must_be_exactly_the_integer_1(version: str) -> None:
    with pytest.raises(ProfileError, match="version must be 1"):
        parse_profile(MINIMAL_PROFILE.replace("version = 1", f"version = {version}"))


@pytest.mark.parametrize("age", ["9" * 401, "-" + "9" * 401, "87601", "-1"])
def test_huge_or_out_of_range_ages_are_profile_errors(age: str) -> None:
    text = MINIMAL_PROFILE + f"[collection]\ncaptured_at_column = 't'\nmax_age_hours = {age}\n"
    with pytest.raises(ProfileError, match="at most 87600"):
        parse_profile(text)


@pytest.mark.parametrize("age", ["87600", "0.001", "24"])
def test_boundary_ages_are_accepted(age: str) -> None:
    text = MINIMAL_PROFILE + f"[collection]\ncaptured_at_column = 't'\nmax_age_hours = {age}\n"
    assert parse_profile(text).collection.max_age_hours == float(age)


@pytest.mark.parametrize(
    "nested",
    ["x = " + "[" * 100_000, "x = " + "{a=" * 100_000, "[[a]]\nb = " + "[" * 100_000],
    ids=["arrays", "inline-tables", "array-of-tables"],
)
def test_a_deeply_nested_profile_is_a_profile_error(nested: str) -> None:
    """PAKAD-C08: tomllib raises RecursionError, which must not become exit 4."""
    with pytest.raises(ProfileError, match="nested too deeply"):
        parse_profile("version = 1\n" + nested + "\n")


def test_a_deeply_nested_profile_file_gives_exit_3(
    write: Callable[[str, str | bytes], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    path = write("deep.toml", "version = 1\nx = " + "[" * 100_000 + "]" * 100_000 + "\n")
    assert main(["check-profile", str(path)]) == ExitCode.INPUT_ERROR
    err = capsys.readouterr().err
    assert "profile is nested too deeply" in err
    assert "internal error" not in err


@pytest.mark.parametrize(
    "body",
    [
        "junk = " + "9" * 5000,
        "junk = -" + "9" * 5000,
        "[extra]\nlist = [" + "9" * 5000 + "]",
        "[collection]\nmax_age_hours = " + "9" * 5000,
        "[collection]\npage_sizes = [" + "9" * 5000 + "]",
    ],
    ids=["junk", "negative", "in-list", "age", "page-size"],
)
def test_an_oversized_integer_is_a_profile_error(body: str) -> None:
    """PAK-4: the interpreter's integer limit (4300 digits) must not become exit 4."""
    with pytest.raises(ProfileError, match="integer with too many digits"):
        parse_profile(MINIMAL_PROFILE + body + "\n")


def test_an_oversized_integer_in_a_profile_file_gives_exit_3(
    write: Callable[[str, str | bytes], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    path = write("big.toml", MINIMAL_PROFILE + "junk = " + "9" * 5000 + "\n")
    assert path.stat().st_size < 1024 * 1024
    assert main(["check-profile", str(path)]) == ExitCode.INPUT_ERROR
    err = capsys.readouterr().err
    assert "integer with too many digits" in err
    assert "internal error" not in err
    assert "Exceeds the limit" not in err


def test_the_interpreters_integer_limit_is_left_alone() -> None:
    """The fix maps the failure; it does not raise the limit for the whole process."""
    limit = sys.get_int_max_str_digits()
    with pytest.raises(ProfileError):
        parse_profile(MINIMAL_PROFILE + "junk = " + "9" * (limit + 1) + "\n")
    assert sys.get_int_max_str_digits() == limit


MAX_BYTES = 1024 * 1024


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_a_named_pipe_is_not_a_profile_even_when_it_reports_size_zero(tmp_path: Path) -> None:
    """PAK-5: a stream supplied 1,048,655 bytes past a size check that saw zero."""
    fifo = tmp_path / "p.toml"
    os.mkfifo(fifo)
    payload = (
        MINIMAL_PROFILE + "# " + "x" * (MAX_BYTES + 79 - len(MINIMAL_PROFILE)) + "\n"
    ).encode()
    assert len(payload) > MAX_BYTES
    assert fifo.stat().st_size == 0

    def feed() -> None:
        try:
            with fifo.open("wb") as writer:
                writer.write(payload)
        except OSError:
            pass  # the reader refused the pipe and closed it

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    try:
        with pytest.raises(ProfileError, match="must be a regular file"):
            load_profile(fifo)
    finally:
        # Release a feeder still waiting for a reader.
        drain = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        os.close(drain)
        feeder.join(timeout=10)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_a_named_pipe_with_no_writer_is_refused_instead_of_waiting(tmp_path: Path) -> None:
    fifo = tmp_path / "p.toml"
    os.mkfifo(fifo)
    with pytest.raises(ProfileError, match="must be a regular file"):
        load_profile(fifo)


def test_a_directory_is_not_a_profile(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match=r"cannot read profile|must be a regular file"):
        load_profile(tmp_path)


def test_the_size_limit_holds_when_the_file_grows_after_the_size_check(
    write: Callable[[str, str | bytes], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PAK-5: the limit applies to the bytes actually read, not to an earlier size."""
    path = write("grow.toml", MINIMAL_PROFILE + "#" * (MAX_BYTES + 10))
    regular = os.stat_result((stat.S_IFREG | 0o600, 0, 0, 1, 0, 0, 100, 0, 0, 0))
    monkeypatch.setattr("faithful_pakad.profile.os.fstat", lambda _fd: regular)
    with pytest.raises(ProfileError, match="larger than"):
        load_profile(path)


def test_a_profile_of_exactly_the_limit_is_accepted(
    write: Callable[[str, str | bytes], Path],
) -> None:
    padding = MAX_BYTES - len(MINIMAL_PROFILE.encode()) - 2
    path = write("edge.toml", MINIMAL_PROFILE + "#" + "x" * padding + "\n")
    assert path.stat().st_size == MAX_BYTES
    assert load_profile(path).name == "test"
    longer = write("over.toml", MINIMAL_PROFILE + "#" + "x" * (padding + 1) + "\n")
    assert longer.stat().st_size == MAX_BYTES + 1
    with pytest.raises(ProfileError, match="larger than"):
        load_profile(longer)
