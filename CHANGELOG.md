# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
