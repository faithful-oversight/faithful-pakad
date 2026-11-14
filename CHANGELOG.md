# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The source archive's own tests now run in the build check: it unpacks the archive outside the checkout and runs the whole suite there, instead of only collecting the tests.
- Editing a pull request title now reruns the title check, so a corrected title clears the required check.
- The dependency audit writes its export to a private temporary directory, so a planted link or a second run at the same time cannot interfere.
- The DCO check now fails when it cannot list the commits to check, instead of reporting success.
- The release script now treats only a clean "not found" answer as an absent tag; an authentication, rate-limit, network, or malformed answer stops the release.

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
