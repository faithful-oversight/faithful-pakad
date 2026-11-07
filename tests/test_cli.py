# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests for the command line."""

from __future__ import annotations

import json
import os
import runpy
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from faithful_pakad import __version__
from faithful_pakad.cli import ExitCode, main
from tests.conftest import EXAMPLE_DIR, MINIMAL_PROFILE

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

AS_OF = "2026-11-07T12:00:00Z"
SAMPLE_DIR = EXAMPLE_DIR / "sample-report"


def example_args(out: Path, *extra: str) -> list[str]:
    return [
        "reconcile",
        "-p",
        str(EXAMPLE_DIR / "profile.toml"),
        "-e",
        str(EXAMPLE_DIR / "expected.csv"),
        "-c",
        str(EXAMPLE_DIR / "collected.csv"),
        "-o",
        str(out),
        "--as-of",
        AS_OF,
        *extra,
    ]


def stable(directory: Path, name: str) -> str:
    """Read a report with the parts that change between runs and releases replaced."""
    generated = json.loads((directory / "pakad-report.json").read_text(encoding="utf-8"))[
        "generated_at"
    ]
    version = json.loads((directory / "pakad-report.json").read_text(encoding="utf-8"))["tool"][
        "version"
    ]
    text = (directory / name).read_text(encoding="utf-8")
    return text.replace(generated, "<generated>").replace(version, "<version>")


def test_example_matches_committed_sample_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sample reports in examples/ are exactly what the current code produces."""
    assert main(example_args(tmp_path)) == ExitCode.FINDINGS
    for name in ("pakad-report.html", "pakad-report.json", "pakad-findings.csv", "pakad-report.md"):
        assert stable(tmp_path, name) == stable(SAMPLE_DIR, name), (
            f"{name} is out of date; regenerate it as examples/README.md describes"
        )
    out = capsys.readouterr().out
    assert "7 errors and 2 warnings need review." in out
    assert "pakad-report.html  <- open this in a browser" in out


@pytest.mark.parametrize(
    ("fail_on", "code"),
    [("any", ExitCode.FINDINGS), ("error", ExitCode.FINDINGS), ("never", ExitCode.OK)],
)
def test_fail_on(tmp_path: Path, fail_on: str, code: ExitCode) -> None:
    assert main(example_args(tmp_path, "--fail-on", fail_on)) == code


def test_fail_on_error_ignores_warnings(
    write: Callable[[str, str | bytes], Path], tmp_path: Path
) -> None:
    profile = write("p.toml", MINIMAL_PROFILE + "[collection]\npage_sizes = [1]\n")
    exp = write("e.csv", "id\n1\n")
    col = write("c.csv", "uid\n1\n")
    base = [
        "reconcile",
        "-p",
        str(profile),
        "-e",
        str(exp),
        "-c",
        str(col),
        "-o",
        str(tmp_path / "o"),
    ]
    assert main([*base, "--fail-on", "error", "-f", "json"]) == ExitCode.OK
    assert main([*base, "--fail-on", "any", "-f", "json", "--force"]) == ExitCode.FINDINGS


def test_clean_run_exits_zero(write: Callable[[str, str | bytes], Path], tmp_path: Path) -> None:
    profile = write("p.toml", MINIMAL_PROFILE + "[collection]\npage_sizes = []\n")
    exp = write("e.json", json.dumps([{"id": "1"}]))
    col = write("c.csv", "uid\n1\n")
    args = [
        "reconcile",
        "-p",
        str(profile),
        "-e",
        str(exp),
        "-c",
        str(col),
        "-o",
        str(tmp_path / "o"),
    ]
    assert main([*args, "-f", "json,md"]) == ExitCode.OK
    assert sorted(p.name for p in (tmp_path / "o").iterdir()) == [
        "pakad-report.json",
        "pakad-report.md",
    ]


def test_reports_are_private_and_never_silently_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(example_args(tmp_path, "-f", "json"))
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "pakad-report.json").stat().st_mode) == 0o600
    assert main(example_args(tmp_path, "-f", "json")) == ExitCode.INPUT_ERROR
    assert "already exists; use --force" in capsys.readouterr().err
    assert main(example_args(tmp_path, "-f", "json", "--force")) == ExitCode.FINDINGS


def test_unwritable_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert main(example_args(blocker / "sub")) == ExitCode.INPUT_ERROR
    assert "cannot create" in capsys.readouterr().err


def test_input_errors_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = example_args(tmp_path)
    args[args.index("-e") + 1] = str(tmp_path / "absent.csv")
    assert main(args) == ExitCode.INPUT_ERROR
    assert capsys.readouterr().err.startswith("pakad: error: cannot read expected input absent.csv")


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--as-of", "yesterday"], "not an ISO 8601 timestamp"),
        (["--as-of", "2026-11-07T12:00:00"], "needs a time zone"),
        (["-f", "pdf"], "choose from html, json, csv, md"),
        (["--max-bytes", "0"], "must be greater than zero"),
        (["--max-bytes", "lots"], "not a whole number"),
    ],
)
def test_usage_errors_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    assert main([*example_args(tmp_path), *extra]) == ExitCode.USAGE
    assert message in capsys.readouterr().err


def test_check_profile(
    capsys: pytest.CaptureFixture[str], write: Callable[[str, str | bytes], Path]
) -> None:
    assert main(["check-profile", str(EXAMPLE_DIR / "profile.toml")]) == ExitCode.OK
    assert "valid profile 'HR roster vs directory export'" in capsys.readouterr().out
    assert main(["check-profile", str(write("bad.toml", "version = 9"))]) == ExitCode.INPUT_ERROR


def test_example_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "try"
    assert main(["example", str(target)]) == ExitCode.OK
    for name in ("profile.toml", "expected.csv", "collected.csv"):
        assert (target / name).read_bytes() == (EXAMPLE_DIR / name).read_bytes()
    assert "pakad reconcile -p" in capsys.readouterr().out
    assert main(["example", str(target)]) == ExitCode.INPUT_ERROR
    assert main(["example", str(target), "--force"]) == ExitCode.OK
    blocker = tmp_path / "f"
    blocker.write_text("x")
    assert main(["example", str(blocker / "sub")]) == ExitCode.INPUT_ERROR


def test_example_profile_and_schema(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["example-profile"]) == ExitCode.OK
    assert capsys.readouterr().out == (EXAMPLE_DIR / "profile.toml").read_text(encoding="utf-8")
    assert main(["schema"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out)["title"] == "pakad reconciliation report"


def test_version_and_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == ExitCode.OK
    assert __version__ in capsys.readouterr().out
    assert main([]) == ExitCode.USAGE
    assert "usage: pakad" in capsys.readouterr().out
    assert main(["--no-such-option"]) == ExitCode.USAGE


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["pakad", "--version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("faithful_pakad", run_name="__main__")
    assert exc.value.code == ExitCode.OK
