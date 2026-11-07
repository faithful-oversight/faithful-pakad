# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Shared test configuration and helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "roster-vs-directory"

MINIMAL_PROFILE = """
version = 1
name = "test"
[expected]
key = ["id"]
[collected]
key = ["uid"]
"""


@pytest.fixture(autouse=True)
def plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable colored output so assertions see plain text on every Python version."""
    monkeypatch.setenv("PYTHON_COLORS", "0")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)


@pytest.fixture
def write(tmp_path: Path) -> Callable[[str, str | bytes], Path]:
    """Return a helper that writes a file under the test's temporary directory."""

    def _write(name: str, content: str | bytes) -> Path:
        path = tmp_path / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")
        return path

    return _write
