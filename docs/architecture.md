# Architecture

pakad is a command-line tool and a Python library with one runtime dependency beyond the Python standard library: [faithful-core](https://github.com/faithful-oversight/faithful-core), the shared foundation library of the Faithful Oversight tools, pinned to an exact version.

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
| `errors` | `PakadError`, which is faithful-core's `FaithfulError`, and the error classes pakad uses: `InputError`, `ProfileError`, and `OutputError`. |
| `names` | Turn input paths into names that are safe to put in reports and error messages. |
| `outputs` | Build the report document, render each format, and write the files all at once, through faithful-core. |
| `cli` | Command-line interface. |

## The shared library

faithful-core holds the code that every Faithful Oversight tool needs to behave the same way. pakad uses it for:

- the base error and the exit codes;
- making untrusted text safe for the terminal, CSV, Markdown, and HTML;
- printing that never changes an exit code;
- publishing a set of files all together, without replacing a file the tool reads;
- small helpers for the report renderers: the content security policy, HTML and Markdown escaping, Markdown tables, plural nouns, and JSON output.

The library's own pages describe how each of these works. pakad's tests cover them through the commands, and the library's tests cover them directly. The decision is recorded in [ADR 5](adr/0005-shared-core-library.md).

## Rules the design follows

- **Separation.** Readers handle input, `reconcile` is pure logic, and the renderers handle output. The engine never reads files or prints.
- **One report document.** Every format is rendered from the same document, so the formats cannot disagree.
- **A versioned contract.** The JSON report follows a published JSON Schema. See [Reports and findings](output.md) for the compatibility promise.
- **No prompts.** pakad never asks questions, so it runs unchanged in scripts and pipelines.
- **Structured exit codes.** `0` success, `1` findings, `2` usage error, `3` input or output error, `4` internal error.
- **Careful output.** Reports are complete before they appear, are never overwritten without `--force`, and are swapped in with rollback on failure. A shared run ID and a manifest of file hashes, written last, make any partial or mixed set detectable.
- **Unknowns are results.** When pakad cannot check something, it reports it as not verified, never as passed.
- **Read-only and offline.** No network code and no telemetry.

## Decisions

Significant decisions are recorded in [architecture decision records](adr/index.md).
