# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Write output files all at once, privately, and without partial results."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from faithful_pakad.errors import PakadError

if TYPE_CHECKING:
    from collections.abc import Mapping


def write_files(directory: Path, files: Mapping[str, str], *, force: bool) -> list[Path]:
    """Write every file, or none of them.

    Each file is written to a private temporary file in the target directory and
    then moved into place, so a failure never leaves a partial or empty report,
    and ``force`` never truncates an old report before the new one is complete.
    New files are readable only by the current user on Linux and macOS. An
    existing file is replaced, not followed if it is a symbolic link.

    Raises:
        PakadError: A target exists and ``force`` is false, or writing fails.
    """
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"cannot create {directory}: {exc.strerror}"
        raise PakadError(msg) from exc
    targets = [directory / name for name in files]
    existing = [str(t) for t in targets if t.exists() or t.is_symlink()]
    if existing and not force:
        noun = "exists" if len(existing) == 1 else "exist"
        msg = f"{', '.join(existing)} already {noun}; use --force to replace"
        raise PakadError(msg)

    staged: list[tuple[Path, Path]] = []
    try:
        for target, text in zip(targets, files.values(), strict=True):
            staged.append((_stage(directory, text), target))
        for temp, target in staged:
            temp.replace(target)
    except OSError as exc:
        msg = f"cannot write reports in {directory}: {exc.strerror}"
        raise PakadError(msg) from exc
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
    return targets


def _stage(directory: Path, text: str) -> Path:
    """Write text to a new private temporary file and return its path."""
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".pakad-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return Path(temp)
