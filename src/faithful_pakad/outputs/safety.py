# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Make untrusted values safe for each output format."""

from __future__ import annotations

import re

FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")
"""Leading characters that spreadsheet programs may treat as the start of a formula.

Includes the full-width forms, which some spreadsheet programs also accept.
"""

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|~&])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def neutralize_formula(value: str) -> str:
    """Stop a spreadsheet from treating a cell as a formula.

    A value that starts with a formula trigger gets a leading apostrophe, which
    spreadsheets display as plain text. Applying this twice changes nothing more.
    """
    if value.startswith(FORMULA_TRIGGERS):
        return "'" + value
    return value


def escape_markdown(value: str) -> str:
    """Escape text for a Markdown table cell or paragraph.

    Backslash-escapes the characters that can change meaning inside a table cell
    or after a list marker: emphasis, code, links, table pipes, entities, and
    ``<`` and ``>`` so the text cannot open an HTML tag. Line breaks and control
    characters become visible placeholders, so a value cannot start a new block.
    """
    value = _CONTROL.sub("�", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ↵ ")
    return _MD_SPECIAL.sub(r"\\\1", value)
