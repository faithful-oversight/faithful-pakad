# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the normalization steps."""

from __future__ import annotations

import pytest

from faithful_pakad.normalize import STEPS, normalize

GREEK_UPSILON_HOOK = "\u03d2"
GREEK_UPSILON = "\u03a5"


def test_steps_run_in_the_order_given_and_the_order_matters() -> None:
    """PAKAD-C12: the documented advice is to list nfkc first."""
    nfkc_first = ("nfkc", "casefold")
    assert normalize(GREEK_UPSILON_HOOK, nfkc_first) == normalize(GREEK_UPSILON, nfkc_first)
    casefold_first = ("casefold", "nfkc")
    assert normalize(GREEK_UPSILON_HOOK, casefold_first) != normalize(GREEK_UPSILON, casefold_first)


@pytest.mark.parametrize("value", ["\u03d2", "\u00a8", "\u1d2c", "  A\u00a0b ", "\uff21\uff11"])
def test_listing_nfkc_first_is_stable_when_applied_twice(value: str) -> None:
    steps = ("nfkc", "strip", "collapse-whitespace", "casefold")
    assert set(steps) == set(STEPS)
    once = normalize(value, steps)
    assert normalize(once, steps) == once
