# Architecture

pakad is a command-line tool and a Python library with no runtime dependencies beyond the Python standard library.

```text
profile.toml ──► profile   strict validation, typed settings
inputs       ──► readers   CSV and JSON to text-only tables, with source line numbers
                    │
                    ▼
                 reconcile pure function: tables in, findings and unknowns out
                    │
                    ▼
                 outputs   one report document, rendered as HTML, JSON, CSV, Markdown
                    │
                    ▼
                 cli       arguments, file writing, exit codes
```

| Module | Responsibility |
| --- | --- |
| `profile` | Parse and validate the TOML profile. Unknown settings are errors. |
| `readers` | Read inputs safely: size limit, strict decoding, no type conversion. |
| `normalize` | Named, explicit normalization steps. |
| `reconcile` | Matching and every check. No file access, no output, no clock. |
| `model` | Data types and the finding kinds, which are part of the output contract. |
| `outputs` | Build the report document, and render each format with format-specific escaping. |
| `cli` | Command-line interface. |

## Rules the design follows

- **Separation.** Readers handle input, `reconcile` is pure logic, and the renderers handle output. The engine never reads files or prints.
- **One report document.** Every format is rendered from the same document, so the formats cannot disagree.
- **A versioned contract.** The JSON report follows a published JSON Schema. See [Reports and findings](output.md) for the compatibility promise.
- **No prompts.** pakad never asks questions, so it runs unchanged in scripts and pipelines.
- **Structured exit codes.** `0` success, `1` findings, `2` usage error, `3` input or output error.
- **Unknowns are results.** When pakad cannot check something, it reports it as not verified, never as passed.
- **Read-only and offline.** No network code and no telemetry.

## Decisions

Significant decisions are recorded in [architecture decision records](adr/index.md).
