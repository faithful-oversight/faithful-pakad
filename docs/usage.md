# Command reference

```text
pakad [--version] COMMAND [options]
```

| Command | What it does |
| --- | --- |
| `reconcile` | Compare two files and write reports. |
| `check-profile` | Validate a profile without reading any data. |
| `example` | Write a synthetic example: a profile and two CSV files. |
| `example-profile` | Print a commented example profile. |
| `schema` | Print the JSON Schema for the JSON report, or with `schema manifest`, for the run manifest. |

Run `pakad COMMAND --help` for the options of any command.

## reconcile

```shell
pakad reconcile -p PROFILE -e EXPECTED -c COLLECTED -o OUT_DIR [options]
```

| Option | Meaning |
| --- | --- |
| `-p`, `--profile` | Profile TOML file. See the [profile reference](profile.md). |
| `-e`, `--expected` | The population that should exist. CSV or JSON. |
| `-c`, `--collected` | The export that was collected. CSV or JSON. |
| `-o`, `--out-dir` | Directory for the reports. Created if needed. |
| `-f`, `--format` | Comma-separated list of `html`, `json`, `csv`, `md`. Default: all four. |
| `--as-of` | Reference time for freshness checks, in ISO 8601 with a time zone, for example `2026-11-07T12:00:00Z`. Default: now. |
| `--fail-on` | When to exit with code 1: `any` finding (default), only `error` findings, or `never`. |
| `--max-bytes` | Refuse input files larger than this many bytes. Default: 268435456 (256 MiB). |
| `--force` | Overwrite report files that already exist. Without it, pakad refuses. |

### File formats

pakad picks the format from the file extension: `.csv`, `.tsv`, and `.txt` are read as delimited text, and `.json` as JSON. Set `format` in the profile to override.

- **CSV:** the first row is the header. Values are never converted, so `000123` stays `000123`. A row with fewer fields than the header has the missing values recorded as absent, which differs from empty. A row with more fields than the header stops the run with an input error that names the line, because pakad cannot tell which value belongs to which column.
- **JSON:** an array of objects, or an object with a `value` or `records` array, which covers Microsoft Graph and many PowerShell exports. If such an object carries a non-empty `@odata.nextLink`, or an `@odata.count` or `count` that differs from the number of records, pakad reports a `possible-truncation` warning, because the file is one page of a larger result. Numbers keep the exact text from the file, so `1.0` stays `1.0`. Booleans become `true` or `false`, `null` is absent, and nested arrays and objects become compact JSON text, up to 64 levels of arrays and objects inside one value. Repeated property names and unpaired surrogate escapes such as `\ud800` are input errors, because pakad will not alter an identifier to make it readable. The same holds for CSV: if the configured `encoding` (for example `utf-7` or `unicode_escape`) decodes to an unpaired surrogate, the error names the file, line, and column.

### Report files

pakad writes the reports you choose with `--format`, then `pakad-manifest.json`, into the output directory. Files are readable only by your user account on Linux and macOS. Without `--force`, pakad never replaces an existing file, even one created while it runs. With `--force`, it moves the old reports aside first and puts them back if anything fails, so the directory holds either the old set or the new set.

Each file is complete before it appears, on file systems with hard links. On file systems without them, such as FAT and exFAT on many USB drives, each file is visible while pakad writes it, and pakad removes it again if writing fails. In both cases the manifest is written last, so its presence means every other file is in place.

Run one pakad at a time per output directory. Two runs writing to the same directory at once can remove or restore each other's files.

Only a crash or power loss while writing can leave a partial file or a mix of old and new files. The manifest lists the size and SHA-256 of every file from its run, so either case is detectable: see [Reports and findings](output.md#run-manifest).

| File | Format |
| --- | --- |
| `pakad-report.html` | Self-contained web page. Open it in any browser. |
| `pakad-report.json` | Machine-readable report. See [Reports and findings](output.md). |
| `pakad-findings.csv` | One row per finding. |
| `pakad-report.md` | Markdown report for pull requests and tickets. |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success, and nothing reached the `--fail-on` threshold. |
| `1` | Findings reached the `--fail-on` threshold. |
| `2` | The command was used incorrectly, for example an unknown option. |
| `3` | An input or output problem: a missing or malformed file, an invalid profile, or a report file that already exists. |
| `4` | An internal error in pakad. This is a bug; please report it. The message shows only the error type and the first 200 characters of its text. |

## Use in a pipeline

pakad needs no network access and no secrets, so it runs anywhere Python does.

GitHub Actions:

```yaml
- name: Reconcile evidence
  run: |
    pipx install faithful-pakad
    pakad reconcile -p evidence/profile.toml -e evidence/roster.csv \
      -c evidence/export.csv -o reports --fail-on error
- name: Keep the reports
  if: always()
  uses: actions/upload-artifact@v4  # pin to a full commit SHA in real workflows
  with:
    name: pakad-reports
    path: reports/
```

PowerShell:

```powershell
pakad reconcile -p .\profile.toml -e .\roster.csv -c .\export.csv -o .\reports --fail-on error
if ($LASTEXITCODE -eq 1) { Write-Warning "pakad found errors; see .\reports\pakad-report.html" }
```

## check-profile

```shell
pakad check-profile PROFILE
```

Validates the profile and exits with code `0`, or prints what is wrong and exits with code `3`. Unknown settings are errors, so a misspelled setting can never switch a check off silently.

## example

```shell
pakad example DIRECTORY [--force]
```

Writes `profile.toml`, `expected.csv`, and `collected.csv` into the directory and prints the command that runs them. The data is synthetic and produces every kind of finding.
