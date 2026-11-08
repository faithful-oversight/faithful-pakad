# Threat model

> Review this model whenever an input format, output format, or dependency changes.

## What the tool protects

- **The operator's data.** Inputs are CSV and JSON exports supplied by the operator. They can hold sensitive account, group, and configuration details, and so can the reports.
- **The integrity of results.** Reviewers and assessors rely on the output as evidence.
- **The operator's machine.** The tool processes files that may come from systems the operator does not fully trust.
- **The supply chain.** Users install release artifacts built by this project's pipeline.

## Trust boundaries

1. Input files enter the tool. They are untrusted.
2. Output files leave the tool and are opened in browsers, spreadsheets, and review systems.
3. Release artifacts leave the build pipeline and are installed by users.

## Threats and controls (STRIDE)

The **Status** column says whether each control is in place today. Branch rules depend on repository settings, which are applied outside the code.

| Category | Threat | Control | Status |
| --- | --- | --- | --- |
| Spoofing | A tampered release artifact is installed in place of the real one. | Releases are built once by the release workflow from a commit on `main`, with a pinned, hash-verified build backend. The exact wheel is tested, then published with a `SHA256SUMS` file and a software bill of materials. Publishing verifies every asset's digest on GitHub and PyPI. Build provenance attestations are added once the repository is public. | In place (attestations when public) |
| Tampering | A crafted input file changes results, for example by injecting duplicate keys, changing identifier types, or using invalid Unicode that a lossy cleanup would merge. | Values are never converted or altered. Duplicate and ambiguous keys are findings. Duplicate column names, duplicate JSON properties, and unpaired surrogate escapes are input errors. Every finding links to its source record. | In place |
| Tampering | A malicious change enters the code base. | Pull requests only, a required passing check, resolved conversations, no force pushes to `main`, signed-off commits, and actions pinned to full commit hashes. | In place (branch rules need settings) |
| Repudiation | A user cannot show which inputs and rules produced a report. | Reports record the tool version, the SHA-256 of each input and of the profile, the rules applied, and the reference time. | In place |
| Information disclosure | Reports leak more data than needed, or test fixtures contain real data. | Reports include only keys and compared fields, never whole records. Report files are created readable only by the current user on Linux and macOS, and are never silently overwritten. Fixtures are synthetic. Secret scanning runs on every change and across the full history. | In place |
| Tampering | A failed or interrupted run leaves partial reports, or overwrites good evidence. | Reports are written to private temporary files first. Without `--force`, each is linked into place only if the name is free. With `--force`, old reports are moved aside and restored if any step fails. A symbolic link at a report name is replaced, not followed. On file systems without hard links, a file is created exclusively, written in place, and removed if writing fails. A manifest written last lists the run ID, size, and SHA-256 of every file, so a set left partial or mixed by a crash is detectable. One pakad run at a time may write to a directory. | In place |
| Spoofing | Input text disguises itself on screen, for example with terminal escape sequences or right-to-left overrides that make `exe.txt` display as `txt.exe`. | Control, bidirectional formatting, and lone surrogate characters appear as visible escapes in the terminal and in HTML, Markdown, and CSV reports. | In place |
| Repudiation | A crash is mistaken for a normal result in a pipeline. | Unexpected errors exit with code 4, distinct from findings (1) and input errors (3). Empty inputs are reported as findings rather than passing cleanly. | In place |
| Information disclosure | The tool sends data over the network. | No network code and no telemetry. | In place |
| Denial of service | Oversized, sparse, or deeply nested inputs exhaust memory or time. | A per-file size limit (256 MiB by default) enforced while reading, a 1 MiB limit per CSV field, a 1 MiB limit for profiles, and a 64-level limit on nested JSON values. Records store only the fields present, so files whose rows have different columns stay proportional in memory. pakad reads no XML. | In place |
| Elevation of privilege | Input content runs as code: formula injection in CSV output, or script or markup injection in HTML and Markdown output. | Formula neutralization of every CSV cell, including full-width trigger characters. HTML escaping of every value plus a content security policy that blocks scripts, network requests, and forms. Markdown escaping of every value. No `eval`, `exec`, or `pickle`. Property-based tests cover the escaping functions. | In place |
| Elevation of privilege | A compromised dependency or build step runs with broad permissions. | Minimal runtime dependencies, locked versions, vulnerability and license scanning, least-privilege workflow tokens, and workflow security analysis with zizmor. | In place |

## Residual risks

- The tool cannot detect data that a source system never exported. Reports state this limit.
- Checksums and attestations protect users only if they verify them. [Releasing](releasing.md) shows how.
