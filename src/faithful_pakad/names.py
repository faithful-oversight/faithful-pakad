# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Turn input paths into names that are safe to put in reports."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def display_name(path: Path) -> str:
    r"""Return a file's name as valid text, showing bytes that are not UTF-8 as ``\xff``.

    On Linux a file name is a sequence of bytes, and Python holds the bytes that are
    not UTF-8 as lone surrogates, which cannot be written to a report or manifest.
    """
    return os.fsencode(path.name).decode("utf-8", "backslashreplace")


def error_path(path: Path) -> str:
    r"""Return a path as the user gave it, as valid text for an error message.

    Error messages name the whole path, so a mistyped directory is easy to spot.
    Reports keep only the file name (see ``display_name``), so no directory layout
    is recorded in them. Bytes that are not UTF-8 are shown as ``\xff``.
    """
    return os.fsencode(str(path)).decode("utf-8", "backslashreplace")
