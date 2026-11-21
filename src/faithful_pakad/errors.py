# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Exceptions raised by pakad.

``InputError`` and ``OutputError`` come from faithful-core. ``PakadError`` is its
``FaithfulError``, so one ``except PakadError`` also catches an error raised inside the
library. ``ProfileError`` is pakad's own.
"""

from faithful_core.errors import FaithfulError, InputError, OutputError

__all__ = ["InputError", "OutputError", "PakadError", "ProfileError"]

PakadError = FaithfulError
"""Base class for errors pakad reports to the user."""


class ProfileError(PakadError):
    """The reconciliation profile is missing, malformed, or inconsistent."""
