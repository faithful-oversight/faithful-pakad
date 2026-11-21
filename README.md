# pakad

**Evidence Population Reconciler.** Reconcile an expected population against a collected evidence export. See exactly what is missing, extra, duplicated, ambiguous, or stale, with every finding traced back to its source row.

[![CI](https://github.com/faithful-oversight/faithful-pakad/actions/workflows/ci.yml/badge.svg)](https://github.com/faithful-oversight/faithful-pakad/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/faithful-pakad)](https://pypi.org/project/faithful-pakad/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Status:** version 0.1.2, beta, available on PyPI. The tests use synthetic data only, and run in continuous integration on Linux (Python 3.11 to 3.14), Windows, and macOS. No claim is made that it has been validated against real exports from production systems, so check its first reports against your own data. See [Limitations](docs/limitations.md). Documentation is on the [docs site](https://faithful-oversight.github.io/faithful-pakad/) and in the [docs folder](docs/index.md).

![A pakad HTML report showing summary cards and findings grouped by kind](docs/images/report-example.png)

## Why pakad

Audit evidence often starts with two lists: who *should* be there, such as an HR roster or an approved access list, and what a system export *says* is there. Comparing them by hand in a spreadsheet is slow, easy to get wrong, and hard to defend. Leading zeros vanish, duplicates hide, a paged export silently stops at 1,000 rows, and nobody can say afterward which files the conclusion came from.

pakad does the comparison the same way every time and writes a report an assessor can rely on:

- **Missing and unexpected records**, matched on the key columns you choose.
- **Duplicate and ambiguous keys**, including values that only collide after normalization, such as `A0108` and `a0108`.
- **Field mismatches** on matched records, with equivalents, so `TRUE` can count as `active`.
- **Collection problems:** expected sources with no records, stale capture times, and counts that suggest a paged export stopped early.
- **What it could not verify**, stated in every report rather than left out.
- **Evidence details**, including SHA-256 hashes of every input and the profile, the rules applied, the reference time, and the tool version.

## How it differs from existing tools

Spreadsheet formulas, ad-hoc scripts, and generic data-comparison tools can all compare two lists, but they can decide quietly: convert types, hide duplicates, and say nothing about checks that did not run. General-purpose governance, risk, and compliance products track controls and evidence, and are a different kind of tool. pakad does one narrow job. It matches two exports on keys you choose, by exact text and the normalization steps you list, and it treats duplicates, ambiguity, and unchecked checks as findings. Every report names the files by SHA-256 hash and lists the rules applied. It runs offline and never connects to a system.

## A look at the output

Real output from the synthetic example, which exits with code `1` because it has findings:

```text
pakad 0.1.2: HR roster vs directory export
  expected         9 records  expected.csv
  collected       12 records  collected.csv
  matched          8 keys

7 errors and 2 warnings need review.
  Missing from the collected export            1  (missing)
  Not in the expected population               1  (unexpected)
  Duplicate keys                               1  (duplicate-key)
  Keys that collide after normalization        1  (ambiguous-key)
  Records without a usable key                 1  (blank-key)
  Field values that disagree                   1  (field-mismatch)
  Expected sources with no records             1  (missing-source)
  Stale records                                1  (stale-record)
  Unusable capture times                       1  (invalid-timestamp)
1 check not verified; see the report.
```

The full [sample reports](examples/roster-vs-directory/sample-report/) are committed, in all four formats.

## About the name

*pakad* (pah-KAHD). Hebrew *paqad*: to number, to muster, to account for, and to notice who is missing.

## Install

pakad needs Python 3.11 or newer and has no runtime dependencies.

```shell
pipx install faithful-pakad
pipx ensurepath
```

`pipx ensurepath` puts pipx's tool folder on your PATH; run it once and open a new terminal. With pip, use `pip install faithful-pakad`. For a fixed version, use `faithful-pakad==0.1.2`.

To try the development version from GitHub, run `pipx install git+https://github.com/faithful-oversight/faithful-pakad`. To work from a clone, run `pipx install .` in the repository.

## Try it in one minute

```shell
pakad example ./pakad-demo
pakad reconcile -p ./pakad-demo/profile.toml -e ./pakad-demo/expected.csv \
  -c ./pakad-demo/collected.csv -o ./pakad-demo/report --as-of 2026-11-07T12:00:00Z
```

Open `./pakad-demo/report/pakad-report.html` in any browser. The example data is synthetic and shows every kind of finding. The same reports are committed in [examples/roster-vs-directory/sample-report](examples/roster-vs-directory/sample-report/).

## Use it on your own data

1. Export the expected population and the collected evidence as CSV or JSON.
2. Write a profile that names the key columns and the checks you want. Start from `pakad example-profile > profile.toml`, then see the [profile reference](docs/profile.md).
3. Check it with `pakad check-profile profile.toml`.
4. Run `pakad reconcile` and open the HTML report.

## Outputs

| File | For |
| --- | --- |
| `pakad-report.html` | People. One self-contained page that works offline in any browser, in light or dark mode, and prints cleanly. |
| `pakad-report.json` | Automation. Follows a published, versioned [JSON Schema](src/faithful_pakad/schema/report-v1.schema.json). |
| `pakad-findings.csv` | Spreadsheets and ticketing. Protected against formula injection. |
| `pakad-report.md` | Pull requests, tickets, and change records. |
| `pakad-manifest.json` | Evidence handling. The run ID and the SHA-256 of every other report file, written last. |

Exit codes make pakad easy to use in pipelines: `0` no findings, `1` findings, `2` usage error, `3` input or output error, and `4` an internal error, so a crash is never mistaken for findings. Use `--fail-on error` to pass when there are only warnings.

## Design principles

- **Read-only and offline.** pakad reads files you give it and writes reports. It never connects to a network or changes a system.
- **Text, not guesses.** Every value stays text, so identifiers keep their leading zeros and formatting.
- **Explicit rules.** Normalization and comparisons happen only as the profile says, and each report lists the rules applied.
- **Explicit unknowns.** A check that did not run is reported as not verified, never as passed.
- **Safe output.** Reports escape every input value, and the HTML page cannot run scripts or load anything.

## Documentation

- [Quickstart](docs/quickstart.md)
- [Command reference](docs/usage.md)
- [Profile reference](docs/profile.md)
- [Reports and findings](docs/output.md)
- [Guide for assessors](docs/assessors.md)
- [Limitations](docs/limitations.md)
- [Architecture](docs/architecture.md) and [threat model](docs/threat-model.md)
- [Releasing](docs/releasing.md) and [decision records](docs/adr/)

## Security

Please do not report security problems in public issues. See [SECURITY.md](SECURITY.md).

## Not affiliated

pakad is not affiliated with, endorsed by, or sponsored by Microsoft. Product names in the documentation, such as Microsoft Graph and PowerShell, appear only to describe the file formats pakad can read.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md) first.

## License

Copyright 2026 Faithful Oversight, LLC. Licensed under the [Apache License, Version 2.0](LICENSE).
