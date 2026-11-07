# Quickstart

This walk-through takes about five minutes. It uses synthetic data, so nothing here touches a real system.

## 1. Install

```shell
pipx install faithful-pakad
pakad --version
```

pakad runs on Windows, macOS, and Linux with Python 3.11 or newer.

## 2. Create the example

```shell
pakad example ./pakad-demo
```

This writes three files:

| File | What it is |
| --- | --- |
| `expected.csv` | The population that should exist: a small HR roster. |
| `collected.csv` | What a directory export says exists. |
| `profile.toml` | How to match and check them. Every setting has a comment. |

## 3. Run the reconciliation

```shell
pakad reconcile -p ./pakad-demo/profile.toml -e ./pakad-demo/expected.csv \
  -c ./pakad-demo/collected.csv -o ./pakad-demo/report --as-of 2026-11-07T12:00:00Z
```

On Windows PowerShell, put the command on one line or end each continued line with a backtick (`` ` ``) instead of a backslash.

`--as-of` fixes the reference time so the example's freshness check gives the same answer whenever you run it. Leave it out on real data to use the current time.

The terminal shows a summary:

```text
pakad 0.1.0: HR roster vs directory export
  expected         9 records  expected.csv
  collected       12 records  collected.csv
  matched          8 keys

7 errors and 2 warnings need review.
  Missing from the collected export            1  (missing)
  ...
```

pakad exits with code `1` because it found something. That is the expected result here.

## 4. Read the report

Open `./pakad-demo/report/pakad-report.html` in a browser. Each group of findings explains what it means and what to do next, and each finding names the file and line it came from. The **Not verified** section lists checks that could not run, and the **Evidence** section records the hash of every input.

## 5. Use your own data

```shell
pakad example-profile > my-profile.toml
```

Edit the key columns and checks to match your exports, using the [profile reference](profile.md). Then check the profile before running it:

```shell
pakad check-profile my-profile.toml
```

## Next steps

- [Command reference](usage.md) for every option and for pipeline use.
- [Reports and findings](output.md) for what each finding means.
- [Guide for assessors](assessors.md) if the report will be used as audit evidence.
