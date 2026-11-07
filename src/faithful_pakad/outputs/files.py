# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Publish a set of report files together, privately, and without clobbering.

Guarantees, stated exactly:

- Every file is complete before it appears under its final name. Files are
  written to private temporary files in the target directory first.
- Without ``force``, an existing file is never replaced, even if it appears
  after the initial check. Each file is linked into place, which fails if the
  name already exists.
- With ``force``, existing files are moved aside before the new ones go in. If
  any step fails, pakad removes the new files it placed and restores the old
  ones, so the directory holds either the complete old set or the complete new
  set.
- New files are readable only by the current user on Linux and macOS. A
  symbolic link at a target name is replaced, never followed.

A crash or power loss in the middle of publishing can still leave a mix of old
and new files, plus ``.pakad-old-*`` backups. Every report carries the same run
ID, so a mixed set is detectable: compare the run IDs.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from faithful_pakad.errors import PakadError

if TYPE_CHECKING:
    from collections.abc import Mapping


def write_files(directory: Path, files: Mapping[str, str], *, force: bool) -> list[Path]:
    """Publish every file, or leave the directory as it was.

    Raises:
        PakadError: A target exists and ``force`` is false, a target is a
            directory, or writing fails. The directory is left as it was.
    """
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"cannot create {directory}: {exc.strerror}"
        raise PakadError(msg) from exc
    targets = [directory / name for name in files]
    _check_targets(targets, force=force)

    staged: list[Path] = []
    try:
        staged.extend(_stage(directory, text) for text in files.values())
        pairs = list(zip(staged, targets, strict=True))
        if force:
            _replace_all(directory, pairs)
        else:
            _link_all(pairs)
    except OSError as exc:
        msg = f"cannot write reports in {directory}: {exc.strerror}; the directory is unchanged"
        raise PakadError(msg) from exc
    finally:
        for temp in staged:
            temp.unlink(missing_ok=True)
    return targets


def _check_targets(targets: list[Path], *, force: bool) -> None:
    folders = [str(t) for t in targets if t.is_dir() and not t.is_symlink()]
    if folders:
        msg = f"{', '.join(folders)} is a directory; choose another output directory"
        raise PakadError(msg)
    existing = [str(t) for t in targets if t.exists() or t.is_symlink()]
    if existing and not force:
        noun = "exists" if len(existing) == 1 else "exist"
        msg = f"{', '.join(existing)} already {noun}; use --force to replace"
        raise PakadError(msg)


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


def _link_all(pairs: list[tuple[Path, Path]]) -> None:
    """Place each file only if its name is free; undo every placement on failure."""
    placed: list[Path] = []
    try:
        for temp, target in pairs:
            _place_new(temp, target)
            placed.append(target)
    except FileExistsError as exc:
        _remove(placed)
        msg = f"{exc.filename} appeared while writing; use --force to replace"
        raise PakadError(msg) from exc
    except BaseException:
        _remove(placed)
        raise


def _place_new(temp: Path, target: Path) -> None:
    """Create ``target`` with the content of ``temp``, failing if it exists."""
    try:
        os.link(temp, target)
    except FileExistsError:
        raise
    except OSError:
        # Some file systems, such as FAT, have no hard links. Exclusive creation
        # still refuses to overwrite, but writes the content in place.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(temp.read_bytes())


def _replace_all(directory: Path, pairs: list[tuple[Path, Path]]) -> None:
    """Swap in every new file, restoring the old set if any step fails."""
    backups: list[tuple[Path, Path]] = []
    placed: list[Path] = []
    try:
        for _, target in pairs:
            if target.exists() or target.is_symlink():
                backup = _backup_name(directory)
                try:
                    target.replace(backup)
                except BaseException:
                    backup.unlink(missing_ok=True)
                    raise
                backups.append((backup, target))
        for temp, target in pairs:
            temp.replace(target)
            placed.append(target)
    except BaseException:
        _remove(placed)
        for backup, target in backups:
            backup.replace(target)
        raise
    _remove([backup for backup, _ in backups])


def _backup_name(directory: Path) -> Path:
    fd, name = tempfile.mkstemp(dir=directory, prefix=".pakad-old-", suffix=".bak")
    os.close(fd)
    return Path(name)


def _remove(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
