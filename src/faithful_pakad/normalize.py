# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Explicit, named text normalization steps.

Normalization never changes a value's type. Identifiers stay text, so leading
zeros and other formatting survive unless a step removes them on purpose.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_WHITESPACE = re.compile(r"\s+")

STEPS: dict[str, Callable[[str], str]] = {
    "strip": str.strip,
    "casefold": str.casefold,
    "collapse-whitespace": lambda value: _WHITESPACE.sub(" ", value),
    "nfkc": lambda value: unicodedata.normalize("NFKC", value),
}
"""Available steps, by the name used in profiles."""


def normalize(value: str, steps: Sequence[str]) -> str:
    """Apply normalization steps to a value, in the order given.

    Args:
        value: The text to normalize.
        steps: Step names from ``STEPS``. Profiles are validated before use, so an
            unknown name here is a programming error.

    Returns:
        The normalized text.
    """
    for step in steps:
        value = STEPS[step](value)
    return value


def count(number: int, noun: str, plural: str | None = None) -> str:
    """Return a number with its noun, for example ``1 error`` or ``2 errors``."""
    word = noun if number == 1 else (plural or noun + "s")
    return f"{number} {word}"
