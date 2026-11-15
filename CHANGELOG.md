# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-11-14

### Fixed

- A profile with no `[[compare]]` fields now lists "field comparison" under Not verified, so a presence-only run is no longer reported as a clean pass.
- A JSON export with a non-empty `@odata.nextLink` is now an `incomplete-export` error instead of being accepted as complete, so the run exits 1 under `--fail-on any` and `error`. An `@odata.count` or `count` that differs from the number of records is a `possible-truncation` warning.
- When the summary cannot be printed (a closed pipe such as `pakad ... | head`, or output that cannot encode a character in a path), the run now keeps its real exit code instead of ending with exit 4. The reports were already written.
- Error messages now name the whole path you gave, not only the file name. Reports still record only the file name.
- A large `--max-bytes` value no longer makes a tiny file fail with exit 4 (`MemoryError` or `OverflowError`). Files are now read in blocks.
- An output directory that exists but cannot be searched (for example mode 0600) is now an input error (exit 3) with a clear message, not an internal error (exit 4).
- A deeply nested profile is now a profile error (exit 3, "profile is nested too deeply") instead of an internal error (exit 4).
- An empty JSON export (`[]` or `{"value": []}`) is now reported as an empty input, like a header-only CSV, instead of failing with "is missing 1 column".
- When both inputs are empty, the report now has one `nothing-reconciled` error with the headline "Nothing was reconciled: both inputs are empty", and the run exits 1 under `--fail-on any` and `error`. A single empty input stays a warning.
- A key repeated thousands of times no longer puts every source reference into one CSV cell, which went past a spreadsheet's 32,767-character limit. The CSV, HTML, and Markdown reports list the first 20 references and say how many more there are; the JSON report keeps all of them.
- A profile's `equivalents` no longer turns identical values into a `field-mismatch`. A collected value that equals the expected value always matches; an equivalent only adds another accepted form.
- The report now states a configured `max_age_hours` exactly (for example `1.23456789`, not `1.23457`), in both the rules applied and the stale-record details.
- The note about findings left out of the HTML and Markdown reports now reads correctly for one finding ("1 more finding of this kind is in ...").
- A plain negative number such as `-1` is no longer given a leading apostrophe in the CSV report, so a tool reading the file gets the number. Anything else that starts with a minus sign is still neutralized.
- The source archive's own tests now run in the build check: it unpacks the archive outside the checkout and runs the whole suite there, instead of only collecting the tests.
- Editing a pull request title now reruns the title check, so a corrected title clears the required check.
- The dependency audit writes its export to a private temporary directory, so a planted link or a second run at the same time cannot interfere.
- The DCO check now fails when it cannot list the commits to check, instead of reporting success.
- The release script now treats only a clean "not found" answer as an absent tag; an authentication, rate-limit, network, or malformed answer stops the release.
- The dependency audit always includes every optional extra, and a new check fails it when a package named by an extra is missing from the audited export.
- The release evidence is now one SBOM per scope: `sbom-base.cdx.json` for the base install, and `sbom-all-extras.cdx.json` when the project defines optional extras. Each states its scope, and tests check what each one holds.
- The sign-off check no longer lets a commit skip sign-off by claiming Dependabot as its author. Dependabot is exempt only on its own pull requests.
- The required "All checks passed" check now fails if a CI job is missing, and a skipped title or sign-off check no longer counts as a pass on a pull request.
- `scripts/check.sh workflows` prints a clear message instead of a stack trace when GitHub rejects the token.
- `SECURITY.md` no longer says that no release has been published. It says the latest release is supported.

### Changed

- The JSON report schema is now version 1.1. It adds the `incomplete-export` and `nothing-reconciled` finding kinds; their counts are optional, so 1.0 reports still validate.
- The profile documentation now says that normalization steps run in the order listed and that `nfkc` should come first, because a later `casefold` or `strip` cleans up what NFKC creates. The step table and the example profile list `nfkc` first.
- The limitations page now states measured memory use: about 650 to 1,100 bytes per record, or 14 to 80 times the file size depending on row width, instead of "several times the file size". It also says that `--max-bytes` limits bytes, not records.
- A presence-only profile (no `[[compare]]` fields) now gets the headline "No findings in the supplied inputs, but 1 check did not run" where it used to get a plain pass. The example profile compares fields and is unchanged.
- The README now leads with an install route that works before the first PyPI release (`pipx install git+https://github.com/faithful-oversight/faithful-pakad`), a status line, a short comparison with other approaches, a link to the documentation folder, and a real excerpt of the example report. The quickstart shows the current version.
- The package keywords no longer include "compliance", and the README and NOTICE say that pakad is not affiliated with or endorsed by Microsoft.
- Dependabot groups minor and patch updates of runtime dependencies into one pull request.
- `CONTRIBUTING.md` lists every tool a clean machine needs and which checks need network access or a token.
- The releasing guide covers the first PyPI publish, a failed PyPI step, scheduled checks that stop after 60 idle days, both SBOM files, and the pinned tools.

### Security

- Characters that look like a space but are not the ASCII space (no-break space, the en and em spaces, the ideographic space, and the blank braille pattern) now print as visible escapes in every report format and in the terminal, so two keys that differ only by one of them no longer look identical, and such a character cannot sit in front of a formula in the CSV report.
- A release now stops with a clear message when the `FO_PUBLIC` setting disagrees with whether the repository is public, so a public release cannot skip provenance and PyPI by mistake.
- Release jobs check the built files against `SHA256SUMS` before attesting, uploading or publishing.
- uv and the Vale style packages used in CI are pinned to exact versions, and the style packages are checked against a SHA-256 before use.

## [0.1.1] - 2026-11-11

### Fixed

- Invisible characters are now escaped more completely: zero-width and other format characters, line and paragraph separators, filler characters, tag characters, and variation selectors, with eight-digit escapes outside the Basic Multilingual Plane.
- The terminal now shows a carriage return and a tab in input text as `\r` and `\t`, so they cannot overwrite earlier output.
- An input or profile filename that is not valid UTF-8 no longer crashes the run with exit 4; the bad byte shows as `\xff` in reports and the manifest.
- An internal error now prints only the error type and a short message, not the whole exception, which could dump an entire report to the terminal.
- A CSV decoded with a configured text encoding, such as `utf-7` or `unicode_escape`, that produces an unpaired surrogate is now an input error (exit 3) naming the file, line, and column, instead of crashing the run with exit 4.
- The source archive now includes `scripts`, which its tests import, and the build check collects the tests from an extracted copy.

### Changed

- The release workflow waits up to 20 minutes for CI to finish on the release commit, instead of failing when it is started right after a merge.
- The license check no longer replaces a license a package states with a generic classifier; reviewed exceptions are pinned to a package version.
- The license check now also reads optional extras, skips requirements for other platforms, and accepts an SPDX-style License field; the dependency review allow list adds MIT-0 and MPL-2.0.

## [0.1.0] - 2026-11-07

First release.

### Added

- `pakad reconcile`: compare an expected population with a collected export, matched on one or more key columns with explicit normalization.
- Findings for missing, unexpected, duplicate, ambiguous, and blank keys, field mismatches with equivalent values, missing sources, stale and invalid capture times, and possible paging truncation.
- A "Not verified" list in every report for checks that did not run.
- Reports as self-contained HTML, JSON with a published JSON Schema, formula-safe CSV, and Markdown, all rendered from one report document and sharing one run ID.
- A run manifest, `pakad-manifest.json`, written last, with a published JSON Schema. It lists the run ID and the size and SHA-256 of every report file, so a partial, edited, or mixed set is detectable, including a findings CSV with no rows.
- Careful report publishing: no overwriting without `--force`, rollback when a forced replacement fails, and files that are complete before they appear, or removed if writing fails on file systems without hard links.
- Evidence details in every report: SHA-256 of each input and the profile, rules applied, reference time, and tool version.
- `pakad check-profile`, `pakad example`, `pakad example-profile`, and `pakad schema` for the report and manifest schemas.
- Strict TOML profiles that reject unknown settings.
- Safe CSV and JSON readers: size limits, strict decoding, no type conversion, and line numbers for every record.
- Documentation site built with Sphinx, with a quickstart, command, profile, and output references, a guide for assessors, and decision records.
- Project foundation: license, contribution and security policies, continuous integration, and a release pipeline that builds once with a pinned backend, tests the exact wheel, writes a reproducible SBOM, proves a rebuild gives identical bytes, and verifies every published file's digest.
