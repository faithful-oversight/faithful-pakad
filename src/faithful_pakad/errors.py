# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Exceptions raised by pakad."""


class PakadError(Exception):
    """Base class for errors pakad reports to the user."""


class ProfileError(PakadError):
    """The reconciliation profile is missing, malformed, or inconsistent."""


class InputError(PakadError):
    """An input file cannot be read or does not have the expected shape."""
