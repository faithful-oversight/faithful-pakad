# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests for the command line."""

from __future__ import annotations

import hashlib
import io
import json
import os
import runpy
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from faithful_pakad import __version__
from faithful_pakad.cli import ExitCode, main
from tests.conftest import EXAMPLE_DIR, MINIMAL_PROFILE

if TYPE_CHECKING:
    from collections.abc import Callable

AS_OF = "2026-11-07T12:00:00Z"
SAMPLE_DIR = EXAMPLE_DIR / "sample-report"
NO_BREAK_SPACE = chr(0xA0)


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


def assert_manifest_matches(directory: Path) -> None:
    """Every file the manifest lists exists with the recorded size and SHA-256."""
    manifest = json.loads((directory / "pakad-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        data = (directory / entry["name"]).read_bytes()
        assert len(data) == entry["bytes"], entry["name"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]
    listed = {entry["name"] for entry in manifest["files"]} | {"pakad-manifest.json"}
    assert {p.name for p in directory.iterdir() if p.name.startswith("pakad-")} == listed


def stable(directory: Path, name: str) -> str:
    """Read a report with the parts that change between runs and releases replaced."""
    generated = json.loads((directory / "pakad-report.json").read_text(encoding="utf-8"))[
        "generated_at"
    ]
    version = json.loads((directory / "pakad-report.json").read_text(encoding="utf-8"))["tool"][
        "version"
    ]
    run_id = json.loads((directory / "pakad-report.json").read_text(encoding="utf-8"))["run_id"]
    text = (directory / name).read_text(encoding="utf-8")
    return (
        text.replace(generated, "<generated>")
        .replace(version, "<version>")
        .replace(run_id, "<run-id>")
    )


def test_example_matches_committed_sample_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sample reports in examples/ are exactly what the current code produces."""
    assert main(example_args(tmp_path)) == ExitCode.FINDINGS
    for name in ("pakad-report.html", "pakad-report.json", "pakad-findings.csv", "pakad-report.md"):
        assert stable(tmp_path, name) == stable(SAMPLE_DIR, name), (
            f"{name} is out of date; regenerate it as examples/README.md describes"
        )
    for directory in (tmp_path, SAMPLE_DIR):
        assert_manifest_matches(directory)
    fresh = json.loads((tmp_path / "pakad-manifest.json").read_text(encoding="utf-8"))
    sample = json.loads((SAMPLE_DIR / "pakad-manifest.json").read_text(encoding="utf-8"))
    for manifest in (fresh, sample):
        manifest.pop("generated_at")
        manifest.pop("run_id")
        manifest["tool"].pop("version")
        for entry in manifest["files"]:
            entry.pop("bytes")
            entry.pop("sha256")
    assert fresh == sample, "pakad-manifest.json is out of date; regenerate the sample reports"
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
        "pakad-manifest.json",
        "pakad-report.json",
        "pakad-report.md",
    ]


def test_clean_run_csv_is_tied_to_its_run_by_the_manifest(
    write: Callable[[str, str | bytes], Path], tmp_path: Path
) -> None:
    """A findings CSV with no rows has nowhere to record its run; the manifest does."""
    profile = write("p.toml", MINIMAL_PROFILE + "[collection]\npage_sizes = []\n")
    exp = write("e.json", json.dumps([{"id": "1"}]))
    col = write("c.csv", "uid\n1\n")
    out = tmp_path / "o"
    args = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(col), "-o", str(out)]
    assert main([*args, "-f", "csv,json"]) == ExitCode.OK
    assert (out / "pakad-findings.csv").read_bytes().count(b"\r\n") == 1
    manifest = json.loads((out / "pakad-manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out / "pakad-report.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == report["run_id"]
    assert [f["name"] for f in manifest["files"]] == ["pakad-findings.csv", "pakad-report.json"]
    assert_manifest_matches(out)


def test_reports_are_private_and_never_silently_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(example_args(tmp_path, "-f", "json"))
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "pakad-report.json").stat().st_mode) == 0o600
    assert main(example_args(tmp_path, "-f", "json")) == ExitCode.INPUT_ERROR
    assert "already exist; use --force to replace" in capsys.readouterr().err
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
    assert capsys.readouterr().err.startswith(
        f"pakad: error: cannot read expected input {tmp_path / 'absent.csv'}"
    )


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
    assert main(["schema", "manifest"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out)["title"] == "pakad run manifest"
    assert main(["schema", "other"]) == ExitCode.USAGE


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


def test_no_partial_reports_when_a_target_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pakad-report.md").write_text("old evidence")
    assert main(example_args(tmp_path)) == ExitCode.INPUT_ERROR
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pakad-report.md"]
    assert (tmp_path / "pakad-report.md").read_text() == "old evidence"
    assert "already exists; use --force" in capsys.readouterr().err


@pytest.mark.parametrize("fail_after", [0, 1, 3, 5])
def test_failed_publish_restores_the_complete_old_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fail_after: int,
) -> None:
    """Fail after some files are already swapped in: the old set must come back intact."""
    assert main(example_args(tmp_path)) == ExitCode.FINDINGS
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    real_replace = Path.replace
    calls = {"n": 0}

    def flaky(self: Path, target: Path) -> Path:
        calls["n"] += 1
        if calls["n"] > fail_after and ".pakad-old-" not in self.name:
            raise OSError(28, "No space left on device")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    assert main(example_args(tmp_path, "--force")) == ExitCode.INPUT_ERROR
    assert "the directory is unchanged" in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_a_directory_at_a_report_name_is_refused_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pakad-report.json").mkdir()
    assert main(example_args(tmp_path, "--force")) == ExitCode.INPUT_ERROR
    assert "is a directory" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pakad-report.json"]


def test_a_file_appearing_during_publish_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --force, a report name taken after the first check is left alone."""
    real_link = os.link

    def racing_link(src: str, dst: str) -> None:
        if str(dst).endswith("pakad-report.json"):
            Path(dst).write_text("someone else")
        real_link(src, dst)

    monkeypatch.setattr(os, "link", racing_link)
    assert main(example_args(tmp_path)) == ExitCode.INPUT_ERROR
    assert "appeared while writing" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == ["pakad-report.json"]
    assert (tmp_path / "pakad-report.json").read_text() == "someone else"


def test_publish_without_hard_links_still_refuses_to_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(*_: object) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    assert main(example_args(tmp_path, "-f", "json")) == ExitCode.FINDINGS
    assert json.loads((tmp_path / "pakad-report.json").read_text())["tool"]["name"] == "pakad"
    assert main(example_args(tmp_path, "-f", "json")) == ExitCode.INPUT_ERROR


def test_recorded_reference_time_reproduces_the_findings(
    write: Callable[[str, str | bytes], Path], tmp_path: Path
) -> None:
    """Replaying with the as_of a report records gives identical findings."""
    profile = write(
        "p.toml",
        MINIMAL_PROFILE + "[collection]\npage_sizes = []\ncaptured_at_column = 't'\n"
        "max_age_hours = 1\n",
    )
    exp = write("e.csv", "id\n1\n")
    col = write("c.csv", "uid,t\n1,2026-11-07T11:00:00.5Z\n")
    base = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(col), "-f", "json"]
    first = tmp_path / "first"
    assert main([*base, "-o", str(first), "--as-of", "2026-11-07T12:00:00.6Z"]) == 1
    report = json.loads((first / "pakad-report.json").read_text())
    assert report["as_of"] == "2026-11-07T12:00:00.600000+00:00"
    again = tmp_path / "again"
    assert main([*base, "-o", str(again), "--as-of", report["as_of"]]) == 1
    replay = json.loads((again / "pakad-report.json").read_text())
    assert [f["kind"] for f in replay["findings"]] == [f["kind"] for f in report["findings"]]
    assert [f["kind"] for f in report["findings"]] == ["stale-record"]


def test_every_report_file_shares_one_run_id(tmp_path: Path) -> None:
    main(example_args(tmp_path))
    run_id = json.loads((tmp_path / "pakad-report.json").read_text())["run_id"]
    for name in ("pakad-report.html", "pakad-findings.csv", "pakad-report.md"):
        assert run_id in (tmp_path / name).read_text()
    other = tmp_path / "other"
    main(example_args(other))
    assert json.loads((other / "pakad-report.json").read_text())["run_id"] != run_id


def test_example_command_is_quoted_for_paths_with_spaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "my demo"
    assert main(["example", str(target)]) == ExitCode.OK
    out = capsys.readouterr().out
    quoted = f'"{target / "profile.toml"}"' if os.name == "nt" else f"'{target / 'profile.toml'}'"
    assert quoted in out


def test_multi_line_terminal_output_keeps_its_line_breaks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["example", str(tmp_path / "ex")]) == ExitCode.OK
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("Wrote a synthetic example to ")
    assert lines[1] == ""
    assert lines[2].startswith("  pakad reconcile ")

    assert main(example_args(tmp_path / "out")) == ExitCode.FINDINGS
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("pakad ")
    assert any(line.startswith("  expected ") for line in lines)
    assert "Reports:" in lines


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow control characters in names")
def test_success_messages_cannot_inject_terminal_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "x\x1b[2Jy"
    assert main(["example", str(target)]) == ExitCode.OK
    assert main(["check-profile", str(target / "profile.toml")]) == ExitCode.OK
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\u001b" in out


@pytest.mark.skipif(os.name != "posix", reason="symbolic links need extra rights on Windows")
def test_force_replaces_a_symlink_instead_of_following_it(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("do not touch")
    out = tmp_path / "out"
    out.mkdir()
    (out / "pakad-report.json").symlink_to(outside)
    assert main(example_args(out, "-f", "json", "--force")) == ExitCode.FINDINGS
    assert outside.read_text() == "do not touch"
    assert not (out / "pakad-report.json").is_symlink()
    assert stat.S_IMODE((out / "pakad-report.json").stat().st_mode) == 0o600


def test_internal_errors_exit_4_not_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_: object, **__: object) -> None:
        msg = "\x1b[31mboom"
        raise RuntimeError(msg)

    monkeypatch.setattr("faithful_pakad.cli.reconcile", boom)
    assert main(example_args(tmp_path)) == ExitCode.INTERNAL_ERROR
    err = capsys.readouterr().err
    assert "pakad: internal error" in err
    assert "This is a bug" in err
    assert "\x1b" not in err


def test_error_messages_cannot_inject_terminal_codes(
    write: Callable[[str, str | bytes], Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = write("p.toml", MINIMAL_PROFILE)
    exp = write("e.csv", "id\n1\n")
    # The error message lists the available columns, so a crafted header reaches it.
    col = write("c.csv", "other\x1b[2J\n1\n")
    out = tmp_path / "o"
    args = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(col), "-o", str(out)]
    assert main(args) == ExitCode.INPUT_ERROR
    err = capsys.readouterr().err
    assert "\x1b" not in err
    assert "other\\u001b[2J" in err


@pytest.mark.skipif(
    sys.platform in ("win32", "darwin"),
    reason="Windows and macOS file systems cannot hold file names that are not valid UTF-8",
)
def test_input_file_names_that_are_not_utf8_are_shown_as_escapes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = tmp_path / os.fsdecode(b"profile\xff.toml")
    expected = tmp_path / os.fsdecode(b"expected\xff.csv")
    collected = tmp_path / os.fsdecode(b"collected\xff.csv")
    for target, name in ((profile, "profile.toml"), (expected, "expected.csv")):
        target.write_bytes((EXAMPLE_DIR / name).read_bytes())
    collected.write_bytes((EXAMPLE_DIR / "collected.csv").read_bytes())
    out = tmp_path / "out"
    args = ["reconcile", "-p", str(profile), "-e", str(expected), "-c", str(collected)]
    assert main([*args, "-o", str(out), "--as-of", AS_OF]) == ExitCode.FINDINGS
    capsys.readouterr()

    report = json.loads((out / "pakad-report.json").read_text(encoding="utf-8"))
    assert report["profile"]["file"] == "profile\\xff.toml"
    assert report["inputs"]["expected"]["file"] == "expected\\xff.csv"
    assert report["inputs"]["collected"]["file"] == "collected\\xff.csv"
    assert_manifest_matches(out)
    for text in out.iterdir():
        text.read_text(encoding="utf-8")  # every report file is valid UTF-8


@pytest.mark.skipif(
    sys.platform in ("win32", "darwin"),
    reason="Windows and macOS file systems cannot hold file names that are not valid UTF-8",
)
def test_error_messages_show_names_that_are_not_utf8_as_escapes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / os.fsdecode(b"missing\xff.csv")
    assert main(["check-profile", str(missing)]) == ExitCode.INPUT_ERROR
    assert f"cannot read profile {tmp_path}/missing\\xff.csv" in capsys.readouterr().err


@pytest.mark.parametrize(
    "case", [("utf-7", b"id\n+2AA-\n"), ("unicode_escape", b"id\n\\ud800\n")], ids=str
)
@pytest.mark.parametrize("side", ["expected", "collected"])
def test_csv_text_with_an_unpaired_surrogate_is_an_input_error(
    write: Callable[[str, str | bytes], Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: tuple[str, bytes],
    side: str,
) -> None:
    """Some encodings decode to lone surrogates; they must not crash the run with exit 4."""
    encoding, payload = case
    sides = {"expected": 'key = ["id"]\n', "collected": 'key = ["id"]\n'}
    sides[side] += f'encoding = "{encoding}"\n'
    profile = write(
        "p.toml",
        'version = 1\nname = "t"\n' + "".join(f"[{name}]\n{body}" for name, body in sides.items()),
    )
    bad = write("bad.csv", payload)
    good = write("good.csv", b"id\n1\n")
    exp, col = (bad, good) if side == "expected" else (good, bad)
    args = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(col)]
    assert main([*args, "-o", str(tmp_path / "o")]) == ExitCode.INPUT_ERROR
    err = capsys.readouterr().err
    assert err.startswith(f"pakad: error: {bad}: line 2, column 1 contains an unpaired surrogate")
    assert "Traceback" not in err
    assert not (tmp_path / "o").exists()


def test_csv_header_with_an_unpaired_surrogate_is_an_input_error(
    write: Callable[[str, str | bytes], Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = write("p.toml", MINIMAL_PROFILE.replace('["id"]', '["id"]\nencoding = "utf-7"', 1))
    bad = write("bad.csv", b"id,+2AA-\n1,2\n")
    good = write("good.csv", b"uid\n1\n")
    args = ["reconcile", "-p", str(profile), "-e", str(bad), "-c", str(good)]
    assert main([*args, "-o", str(tmp_path / "o")]) == ExitCode.INPUT_ERROR
    err = capsys.readouterr().err
    assert f"{bad}: line 1, column 2 contains an unpaired surrogate" in err
    assert "Traceback" not in err


def test_internal_errors_print_only_the_type_and_a_short_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_: object, **__: object) -> None:
        msg = "report: " + "x" * 5000 + "\x1b[2J"
        raise ValueError(msg)

    monkeypatch.setattr("faithful_pakad.cli.reconcile", boom)
    assert main(example_args(tmp_path)) == ExitCode.INTERNAL_ERROR
    err = capsys.readouterr().err
    assert err.startswith("pakad: internal error: ValueError: report: xxx")
    assert "..." in err
    assert "\x1b" not in err
    assert len(err) < 600


# Output that cannot be printed never changes the result -------------------------------


class ClosedPipe:
    """A standard output whose reader has gone away."""

    encoding = "utf-8"

    def write(self, text: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def test_a_closed_pipe_keeps_the_real_exit_code_and_complete_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PAKAD-C01: ``pakad reconcile ... | head`` is not an internal error."""
    monkeypatch.setattr(sys, "stdout", ClosedPipe())
    code = main(example_args(tmp_path))
    replaced = sys.stdout
    assert isinstance(replaced, io.TextIOWrapper), "output must go to the null device"
    replaced.close()
    assert code == ExitCode.FINDINGS
    assert_manifest_matches(tmp_path)
    assert (tmp_path / "pakad-report.html").is_file()


def test_a_closed_pipe_while_printing_a_resource_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", ClosedPipe())
    code = main(["example-profile"])
    replaced = sys.stdout
    assert isinstance(replaced, io.TextIOWrapper)
    replaced.close()
    assert code == ExitCode.OK


def test_a_closed_pipe_while_printing_help_or_a_version_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", ClosedPipe())
    assert main(["--version"]) == ExitCode.OK
    assert main([]) == ExitCode.USAGE


def run_pakad(
    args: list[str], env: dict[str, str], tmp: Path, *, close_stdout: bool = False
) -> subprocess.CompletedProcess[bytes]:
    full_env = {k: v for k, v in os.environ.items() if k not in {"PYTHONIOENCODING", "PYTHONUTF8"}}
    full_env.update(env)
    command = [sys.executable, "-m", "faithful_pakad", *args]
    if not close_stdout:
        return subprocess.run(  # noqa: S603 - fixed arguments, run from the test suite
            command, env=full_env, capture_output=True, check=False, cwd=tmp
        )
    process = subprocess.Popen(  # noqa: S603 - fixed arguments, run from the test suite
        command, env=full_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp
    )
    assert process.stdout is not None
    process.stdout.close()
    _, stderr = process.communicate()
    return subprocess.CompletedProcess(command, process.returncode, b"", stderr)


def test_ascii_only_output_with_a_non_ascii_path_keeps_the_exit_code(tmp_path: Path) -> None:
    """PAKAD-C01: output that cannot encode a path character is not an internal error."""
    out = tmp_path / "out-ü"
    result = run_pakad(example_args(out), {"PYTHONIOENCODING": "ascii"}, tmp_path)
    assert result.returncode == ExitCode.FINDINGS, result.stderr
    assert b"internal error" not in result.stderr
    assert b"out-\\xfc" in result.stdout
    assert_manifest_matches(out)


def test_ascii_only_error_message_with_a_non_ascii_path_keeps_the_exit_code(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "gone-ü.csv"
    args = example_args(tmp_path / "o")
    args[args.index("-e") + 1] = str(missing)
    result = run_pakad(args, {"PYTHONIOENCODING": "ascii"}, tmp_path)
    assert result.returncode == ExitCode.INPUT_ERROR, result.stderr
    assert b"internal error" not in result.stderr


def test_a_closed_pipe_in_a_real_process_keeps_the_exit_code(tmp_path: Path) -> None:
    result = run_pakad(example_args(tmp_path), {}, tmp_path, close_stdout=True)
    assert result.returncode == ExitCode.FINDINGS, result.stderr
    assert b"Traceback" not in result.stderr
    assert b"internal error" not in result.stderr
    assert_manifest_matches(tmp_path)


def test_error_messages_name_the_whole_path_but_reports_keep_only_the_file_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PAKAD-UX-06: a mistyped directory must be visible in the message."""
    typo = tmp_path / "no-such-dir" / "profile.toml"
    assert main(["check-profile", str(typo)]) == ExitCode.INPUT_ERROR
    assert f"cannot read profile {typo}:" in capsys.readouterr().err

    out = tmp_path / "out"
    assert main(example_args(out)) == ExitCode.FINDINGS
    report = (out / "pakad-report.json").read_text(encoding="utf-8")
    assert str(EXAMPLE_DIR) not in report
    assert str(tmp_path) not in report


def test_a_paged_graph_export_is_reported_not_accepted_as_complete(
    write: Callable[[str, str | bytes], Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PAKAD-C02: ``@odata.nextLink`` means the export is one page of a larger result."""
    profile = write("p.toml", MINIMAL_PROFILE)
    exp = write("e.csv", "id\nA1\n")
    page = write(
        "graph.json",
        '{"@odata.nextLink": "https://graph.example/v1.0/users?$skiptoken=abc",'
        ' "value": [{"uid": "A1"}]}',
    )
    args = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(page), "-o", str(tmp_path)]
    assert main([*args, "-f", "json,md"]) == ExitCode.FINDINGS
    report = json.loads((tmp_path / "pakad-report.json").read_text(encoding="utf-8"))
    kinds = [f["kind"] for f in report["findings"]]
    assert kinds == ["possible-truncation"]
    assert "@odata.nextLink is present" in report["findings"][0]["details"]["signal"]
    assert "No findings" not in capsys.readouterr().out


def test_a_no_break_space_in_a_key_is_visible_in_the_report(
    write: Callable[[str, str | bytes], Path], tmp_path: Path
) -> None:
    """PAKAD-C05: two keys that differ only by a look-alike space must not print the same."""
    profile = write("p.toml", MINIMAL_PROFILE)
    exp = write("e.csv", "id\nA 1\n")
    col = write("c.csv", "uid\nA" + NO_BREAK_SPACE + "1\n")
    args = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(col), "-o", str(tmp_path)]
    assert main([*args, "-f", "md,csv,html"]) == ExitCode.FINDINGS
    for name in ("pakad-report.md", "pakad-findings.csv", "pakad-report.html"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert NO_BREAK_SPACE not in text, name
        assert "A\\u00a01" in text.replace("\\\\", "\\"), name


@pytest.mark.parametrize("empty", ["[]", '{"value": []}', '{"records": []}'])
def test_an_empty_json_export_is_an_empty_input_not_a_profile_problem(
    write: Callable[[str, str | bytes], Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    empty: str,
) -> None:
    """PAKAD-C09: the same situation as a header-only CSV gets the same finding."""
    profile = write("p.toml", MINIMAL_PROFILE)
    exp = write("e.csv", "id\nA1\n")
    col = write("c.json", empty)
    args = ["reconcile", "-p", str(profile), "-e", str(exp), "-c", str(col), "-o", str(tmp_path)]
    assert main([*args, "-f", "json"]) == ExitCode.FINDINGS
    report = json.loads((tmp_path / "pakad-report.json").read_text(encoding="utf-8"))
    assert sorted(f["kind"] for f in report["findings"]) == ["empty-input", "missing"]
    assert "missing 1 column" not in capsys.readouterr().err
