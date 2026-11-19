# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Publish a set of report files together, privately, and without clobbering.

Guarantees, stated exactly:

- Files are written to private temporary files in the target directory first,
  then placed under their final names in order, so the last name in ``files``
  appears last. pakad puts the manifest last, so a manifest means every other
  file is in place.
- On file systems with hard links, every file is complete before it appears
  under its final name.
- On file systems without hard links, such as FAT and exFAT, a file is created
  exclusively under its final name and written there, so it is visible while
  being written. If writing fails, pakad removes the file it created.
- Without ``force``, an existing file is never replaced, even if it appears
  after the initial check. Placing a file fails if the name already exists.
- With ``force``, existing files are moved aside before the new ones go in. If
  any step fails, pakad removes the new files it placed and restores the old
  ones, so the directory holds either the complete old set or the complete new
  set.
- New files are readable only by the current user on Linux and macOS. A
  symbolic link at a target name is replaced, never followed.
- ``refuse_input_overwrite`` stops a run whose report or manifest name is one
  of its own inputs (the same path, a symbolic link, or a hard link), even with
  ``force``, so a source file is never replaced by a generated report.

One pakad process at a time may write to an output directory. Two runs writing
to the same directory at once can remove or restore each other's files.

A crash or power loss in the middle of publishing can still leave a mix of old
and new files, a partly written file on file systems without hard links, and
``.pakad-old-*`` backups. The manifest lists the size and SHA-256 of every file
from its run, so an incomplete or mixed set is detectable.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from faithful_pakad.errors import PakadError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


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
    try:
        _check_targets(targets, force=force)
    except OSError as exc:
        # For example a directory that exists but cannot be searched.
        msg = f"cannot check {directory} for existing reports: {exc.strerror}"
        raise PakadError(msg) from exc

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


def refuse_input_overwrite(
    inputs: Mapping[str, Path], directory: Path, names: Iterable[str]
) -> None:
    """Refuse a run that would replace one of its own inputs with a report file.

    An input and a target are the same file when their resolved paths are equal
    (this covers a symbolic link on either side and an output directory reached
    through a link, even before the target exists) or when ``os.path.samefile``
    says they share a device and inode (this covers hard links). The check does
    not depend on ``force``: a source file is never a place to publish.

    Args:
        inputs: Role of each input (for example ``"expected input"``) to its path.
        directory: The output directory, which need not exist yet.
        names: The file names this run will publish, manifest included.

    Raises:
        PakadError: An input is one of the files to be published.
    """
    try:
        planned_directory = Path(os.path.realpath(directory))
        for name in names:
            target = directory / name
            for role, source in inputs.items():
                if _same_file(source, target, planned_directory / name):
                    msg = (
                        f"the {role} {source} would be overwritten by the report file "
                        f"{target}; choose another output directory"
                    )
                    raise PakadError(msg)
    except OSError as exc:
        msg = f"cannot compare the inputs with the output directory {directory}: {exc.strerror}"
        raise PakadError(msg) from exc


def _same_file(source: Path, target: Path, planned: Path) -> bool:
    resolved = Path(os.path.realpath(source))
    if resolved in (planned, Path(os.path.realpath(target))):
        return True
    try:
        return source.samefile(target)
    except (FileNotFoundError, NotADirectoryError):
        return False


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
        _copy_new(temp, target)


def _copy_new(temp: Path, target: Path) -> None:
    """Fallback for file systems with no hard links: create exclusively, then write.

    The name is created with ``O_EXCL``, so it belongs to this run until the
    content is complete. Any failure after that removes it again.
    """
    data = temp.read_bytes()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        handle = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        target.unlink(missing_ok=True)
        raise
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


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
