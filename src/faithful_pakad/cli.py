# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from enum import IntEnum
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from faithful_pakad import __version__
from faithful_pakad.errors import PakadError
from faithful_pakad.model import Severity, Side
from faithful_pakad.outputs import build_report
from faithful_pakad.outputs.render import RENDERERS, render_all, terminal_summary
from faithful_pakad.profile import load_profile
from faithful_pakad.readers import DEFAULT_MAX_BYTES, read_table
from faithful_pakad.reconcile import reconcile

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class ExitCode(IntEnum):
    """Process exit codes. These values are part of the public interface."""

    OK = 0
    FINDINGS = 1
    USAGE = 2
    INPUT_ERROR = 3


FAIL_ON = ("any", "error", "never")


def _timestamp(text: str) -> datetime:
    value = text.strip()
    if value.endswith(("z", "Z")):
        value = value[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"not an ISO 8601 timestamp: {text!r}"
        raise argparse.ArgumentTypeError(msg) from exc
    if when.tzinfo is None:
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
    commands.add_parser("schema", help="print the JSON Schema for the JSON report")
    return parser


def _write(path: Path, text: str, *, force: bool) -> None:
    """Write a report file readable only by the current user."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        msg = f"{path} already exists; use --force to overwrite"
        raise PakadError(msg) from exc
    except OSError as exc:
        msg = f"cannot write {path}: {exc.strerror}"
        raise PakadError(msg) from exc
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    expected = read_table(args.expected, profile.expected, Side.EXPECTED, max_bytes=args.max_bytes)
    collected = read_table(
        args.collected, profile.collected, Side.COLLECTED, max_bytes=args.max_bytes
    )
    now = datetime.now(UTC)
    as_of = args.as_of or now
    result = reconcile(profile, expected, collected, as_of=as_of)
    report = build_report(result, profile, expected, collected, as_of=as_of, generated_at=now)

    out_dir: Path = args.out_dir
    try:
        out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"cannot create {out_dir}: {exc.strerror}"
        raise PakadError(msg) from exc
    written = []
    for name, text in render_all(report, args.format).items():
        _write(out_dir / name, text, force=args.force)
        written.append(out_dir / name)
    print(terminal_summary(report))  # noqa: T201
    print("\nReports:")  # noqa: T201
    for path in written:
        hint = "  <- open this in a browser" if path.suffix == ".html" else ""
        print(f"  {path}{hint}")  # noqa: T201

    if args.fail_on == "never":
        return ExitCode.OK
    errors = sum(1 for f in result.findings if f.severity is Severity.ERROR)
    failing = errors if args.fail_on == "error" else len(result.findings)
    return ExitCode.FINDINGS if failing else ExitCode.OK


def _resource(name: str) -> str:
    return files("faithful_pakad").joinpath(name).read_text(encoding="utf-8")


EXAMPLE_FILES = ("profile.toml", "expected.csv", "collected.csv")


def _example(directory: Path, *, force: bool) -> int:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"cannot create {directory}: {exc.strerror}"
        raise PakadError(msg) from exc
    for name in EXAMPLE_FILES:
        _write(directory / name, _resource(f"data/{name}"), force=force)
    d = directory
    print(f"Wrote a synthetic example to {d}. Try it:\n")  # noqa: T201
    print(  # noqa: T201
        f"  pakad reconcile -p {d / 'profile.toml'} -e {d / 'expected.csv'} "
        f"-c {d / 'collected.csv'} -o {d / 'report'} --as-of 2026-11-07T12:00:00Z"
    )
    return ExitCode.OK


def _check_profile(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    print(f"{args.profile}: valid profile {profile.name!r}")  # noqa: T201
    return ExitCode.OK


def _print_resource(name: str) -> Callable[[argparse.Namespace], int]:
    def handler(_: argparse.Namespace) -> int:
        sys.stdout.write(_resource(name))
        return ExitCode.OK

    return handler


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "reconcile": _run,
    "check-profile": _check_profile,
    "example": lambda args: _example(args.directory, force=args.force),
    "example-profile": _print_resource("data/profile.toml"),
    "schema": _print_resource("schema/report-v1.schema.json"),
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return an exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else int(ExitCode.USAGE)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return int(ExitCode.USAGE)
    try:
        return int(handler(args))
    except PakadError as exc:
        print(f"pakad: error: {exc}", file=sys.stderr)  # noqa: T201
        return int(ExitCode.INPUT_ERROR)
