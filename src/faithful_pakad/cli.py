# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Command-line entry point."""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from enum import IntEnum
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from faithful_pakad import __version__
from faithful_pakad.errors import PakadError
from faithful_pakad.model import Severity, Side
from faithful_pakad.outputs import build_report
from faithful_pakad.outputs.files import write_files
from faithful_pakad.outputs.render import RENDERERS, render_all, terminal_summary
from faithful_pakad.outputs.safety import terminal
from faithful_pakad.profile import load_profile
from faithful_pakad.readers import DEFAULT_MAX_BYTES, read_table
from faithful_pakad.reconcile import parse_timestamp, reconcile

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class ExitCode(IntEnum):
    """Process exit codes. These values are part of the public interface."""

    OK = 0
    FINDINGS = 1
    USAGE = 2
    INPUT_ERROR = 3
    INTERNAL_ERROR = 4


MAX_INTERNAL_MESSAGE_CHARS = 200
"""An internal error message is cut to this many characters, so a crash never dumps a report."""

FAIL_ON = ("any", "error", "never")


SCHEMAS = {
    "report": "schema/report-v1.schema.json",
    "manifest": "schema/manifest-v1.schema.json",
}
"""Schemas ``pakad schema`` can print, by document."""


def _timestamp(text: str) -> datetime:
    if parse_timestamp(text, assume_utc=True) is None:
        msg = f"not an ISO 8601 timestamp: {text!r}"
        raise argparse.ArgumentTypeError(msg)
    when = parse_timestamp(text, assume_utc=False)
    if when is None:
        msg = f"timestamp needs a time zone, for example {text}Z: {text!r}"
        raise argparse.ArgumentTypeError(msg)
    return when


def _formats(text: str) -> list[str]:
    chosen = [f.strip().lower() for f in text.split(",") if f.strip()]
    unknown = [f for f in chosen if f not in RENDERERS]
    if not chosen or unknown:
        msg = f"choose from {', '.join(RENDERERS)}"
        raise argparse.ArgumentTypeError(msg)
    return list(dict.fromkeys(chosen))


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        msg = f"not a whole number: {text!r}"
        raise argparse.ArgumentTypeError(msg) from exc
    if value <= 0:
        msg = "must be greater than zero"
        raise argparse.ArgumentTypeError(msg)
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="pakad",
        description="Evidence Population Reconciler. Reconcile an expected population "
        "against a collected export and report what is missing, extra, ambiguous, or stale.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    run = commands.add_parser("reconcile", help="reconcile two files and write reports")
    run.add_argument("-p", "--profile", type=Path, required=True, help="profile TOML file")
    run.add_argument("-e", "--expected", type=Path, required=True, help="expected population")
    run.add_argument("-c", "--collected", type=Path, required=True, help="collected export")
    run.add_argument("-o", "--out-dir", type=Path, required=True, help="directory for reports")
    run.add_argument(
        "-f",
        "--format",
        type=_formats,
        default=list(RENDERERS),
        help=f"comma-separated formats (default: {','.join(RENDERERS)})",
    )
    run.add_argument(
        "--as-of",
        type=_timestamp,
        help="reference time for freshness checks, ISO 8601 with a time zone (default: now)",
    )
    run.add_argument(
        "--fail-on",
        choices=FAIL_ON,
        default="any",
        help="exit 1 on any finding, only on errors, or never (default: any)",
    )
    run.add_argument(
        "--max-bytes",
        type=_positive_int,
        default=DEFAULT_MAX_BYTES,
        help=f"refuse input files larger than this (default: {DEFAULT_MAX_BYTES})",
    )
    run.add_argument("--force", action="store_true", help="overwrite existing report files")

    check = commands.add_parser("check-profile", help="validate a profile and exit")
    check.add_argument("profile", type=Path)

    example = commands.add_parser(
        "example", help="write a synthetic example (profile and two CSV files) to try pakad"
    )
    example.add_argument("directory", type=Path, help="directory to create the example in")
    example.add_argument("--force", action="store_true", help="overwrite existing files")

    commands.add_parser("example-profile", help="print a commented example profile")
    schema = commands.add_parser(
        "schema", help="print the JSON Schema for the JSON report or the run manifest"
    )
    schema.add_argument(
        "document",
        nargs="?",
        choices=sorted(SCHEMAS),
        default="report",
        help="which schema to print (default: report)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    expected = read_table(args.expected, profile.expected, Side.EXPECTED, max_bytes=args.max_bytes)
    collected = read_table(
        args.collected, profile.collected, Side.COLLECTED, max_bytes=args.max_bytes
    )
    # Whole seconds keep the default reference time readable. A time given with
    # --as-of is used and recorded at full precision.
    now = datetime.now(UTC).replace(microsecond=0)
    as_of = args.as_of or now
    result = reconcile(profile, expected, collected, as_of=as_of)
    report = build_report(
        result,
        profile,
        expected,
        collected,
        as_of=as_of,
        generated_at=now,
        run_id=uuid.uuid4().hex,
    )

    written = write_files(args.out_dir, render_all(report, args.format), force=args.force)

    # The result is decided before anything is printed, so a failure to print can
    # never change it.
    if args.fail_on == "never":
        code = ExitCode.OK
    else:
        errors = sum(1 for f in result.findings if f.severity is Severity.ERROR)
        failing = errors if args.fail_on == "error" else len(result.findings)
        code = ExitCode.FINDINGS if failing else ExitCode.OK

    lines = [terminal_summary(report), "", "Reports:"]
    for path in written:
        hint = "  <- open this in a browser" if path.suffix == ".html" else ""
        lines.append(f"  {terminal(str(path))}{hint}")
    _out("\n".join(lines))
    return code


def _quiet_stdout() -> None:
    """Point standard output at the null device after the reader has gone away.

    This is the pattern the Python documentation gives for a closed pipe: without
    it, flushing the broken stream while the interpreter shuts down raises again.
    """
    with contextlib.suppress(Exception):
        sys.stdout.flush()
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        with contextlib.suppress(Exception):
            os.dup2(devnull, sys.stdout.fileno())
    finally:
        os.close(devnull)
    # Kept open on purpose: it replaces standard output for the rest of the process.
    sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115


def _out(text: str, *, end: str = "\n") -> None:
    """Print to standard output. A closed pipe stops the printing and nothing else."""
    try:
        sys.stdout.write(text + end)
        sys.stdout.flush()
    except BrokenPipeError:
        _quiet_stdout()


def _err(text: str) -> None:
    """Print to standard error. A stream that cannot be written to is ignored."""
    with contextlib.suppress(OSError, ValueError):
        sys.stderr.write(text + "\n")
        sys.stderr.flush()


def _make_streams_safe() -> None:
    r"""Make printing unable to fail on a character the stream cannot encode.

    Redirected output on Windows, ``LANG=C`` and ``PYTHONIOENCODING=ascii`` can all
    leave a stream that rejects characters such as an accented letter in a path.
    Such characters print as ``\xeb`` or ``\u00eb`` instead of ending the run.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):
                reconfigure(errors="backslashreplace")


def _resource(name: str) -> str:
    return files("faithful_pakad").joinpath(name).read_text(encoding="utf-8")


EXAMPLE_FILES = ("profile.toml", "expected.csv", "collected.csv")


def _example(directory: Path, *, force: bool) -> int:
    write_files(directory, {name: _resource(f"data/{name}") for name in EXAMPLE_FILES}, force=force)
    command = _command_line(
        "pakad",
        "reconcile",
        "-p",
        str(directory / "profile.toml"),
        "-e",
        str(directory / "expected.csv"),
        "-c",
        str(directory / "collected.csv"),
        "-o",
        str(directory / "report"),
        "--as-of",
        "2026-11-07T12:00:00Z",
    )
    _out(terminal(f"Wrote a synthetic example to {directory}. Try it:\n\n  {command}"))
    return ExitCode.OK


def _command_line(*parts: str) -> str:
    """Quote a command for copying into this platform's usual shell."""
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _check_profile(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    _out(terminal(f"{args.profile}: valid profile {profile.name!r}"))
    return ExitCode.OK


def _print_resource(name: str) -> Callable[[argparse.Namespace], int]:
    def handler(_: argparse.Namespace) -> int:
        _out(_resource(name), end="")
        return ExitCode.OK

    return handler


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "reconcile": _run,
    "check-profile": _check_profile,
    "example": lambda args: _example(args.directory, force=args.force),
    "example-profile": _print_resource("data/profile.toml"),
    "schema": lambda args: _print_resource(SCHEMAS[args.document])(args),
}


def _short(message: str) -> str:
    """Return a message cut to a short, terminal-safe line of text."""
    if len(message) > MAX_INTERNAL_MESSAGE_CHARS:
        message = message[:MAX_INTERNAL_MESSAGE_CHARS] + "..."
    return terminal(message)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return an exit code."""
    _make_streams_safe()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else int(ExitCode.USAGE)
    except BrokenPipeError:
        # --help or --version printed into a pipe that was already closed.
        _quiet_stdout()
        return int(ExitCode.OK)
    handler = COMMANDS.get(args.command)
    if handler is None:
        try:
            parser.print_help()
        except BrokenPipeError:
            _quiet_stdout()
        return int(ExitCode.USAGE)
    try:
        return int(handler(args))
    except PakadError as exc:
        _err(f"pakad: error: {terminal(str(exc))}")
        return int(ExitCode.INPUT_ERROR)
    except Exception as exc:  # noqa: BLE001 - last resort, so a crash never looks like findings
        _err(
            f"pakad: internal error: {type(exc).__name__}: {_short(str(exc))}\n"
            "This is a bug. Please report it: "
            "https://github.com/faithful-oversight/faithful-pakad/issues"
        )
        return int(ExitCode.INTERNAL_ERROR)
