# pakad

**Evidence Population Reconciler.** Reconciles an expected population against a collected evidence export and reports exactly what is missing, extra, ambiguous, or stale.

[![CI](https://github.com/faithful-oversight/faithful-pakad/actions/workflows/ci.yml/badge.svg)](https://github.com/faithful-oversight/faithful-pakad/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Status: pre-release.** The repository holds the project foundation only. No feature is implemented yet, and nothing here is ready for production use.

## About the name

*pakad* (pah-KAHD). Hebrew *paqad*: to number, to muster, to account for, and to notice who is missing.

## What it will do

- Compare a declared population (people, accounts, groups, or domains) with a collected export.
- Report missing, unexpected, duplicate, and ambiguous records, each linked to its source row and the rule applied.
- Flag collection problems such as truncated paging, missing sources, and stale capture timestamps.
- Produce a readable report and machine-readable findings.

## What it will not do

- Decide whether access is authorized. Unmatched means unmatched, not unauthorized.
- Infer identity or ownership from display names.
- Connect to live systems in the first release. Inputs are exported files.

See [docs/limitations.md](docs/limitations.md) for the full list.

## Design goals

- **Read-only.** The tool will never change the systems it examines.
- **Offline first.** Inputs will be exported files, with no network access required.
- **Explicit unknowns.** Every report will state what the tool could not see or verify.
- **Traceable findings.** Every finding will point back to its source record and the rule that produced it.
- **Synthetic test data only.** Fixtures are hand-made or generated. No real organization's data is ever committed.

## Installation

Not yet published. Once released, the package will install with:

```shell
pipx install faithful-pakad
```

To work from source, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage

```shell
pakad --version
```

## Documentation

- [Architecture](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Limitations](docs/limitations.md)
- [Releasing](docs/releasing.md)
- [Architecture decision records](docs/adr/)

## Security

Please do not report security problems in public issues. See [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md) first.

## License

Copyright 2026 Faithful Oversight, LLC. Licensed under the [Apache License, Version 2.0](LICENSE).
