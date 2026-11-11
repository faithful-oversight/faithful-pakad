# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for turning input paths into report-safe names."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from faithful_pakad.names import display_name


def test_a_plain_name_is_returned_as_it_is() -> None:
    assert display_name(Path("some") / "dir" / "expected.csv") == "expected.csv"
    assert display_name(Path("naïve.csv")) == "naïve.csv"


@pytest.mark.skipif(
    sys.platform in ("win32", "darwin"),
    reason="Windows and macOS file systems cannot hold file names that are not valid UTF-8",
)
def test_bytes_that_are_not_utf8_are_shown_as_hex_escapes() -> None:
    name = display_name(Path(os.fsdecode(b"dir/a\xffb.csv")))
    assert name == "a\\xffb.csv"
    name.encode("utf-8")  # the result can always be written to a report
