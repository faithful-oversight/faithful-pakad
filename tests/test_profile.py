# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for profile loading and validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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
        (lambda t: t + "[collection]\nmax_age_hours = 0\ncaptured_at_column='c'\n", "positive"),
        (lambda t: t + "[collection]\nmax_age_hours = true\ncaptured_at_column='c'\n", "positive"),
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
