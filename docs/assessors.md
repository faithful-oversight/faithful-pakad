# Guide for assessors

This page explains how to read a pakad report as audit evidence: what it proves, what it does not, and how to confirm it describes the files you were given.

## What a report shows

A pakad report compares two files under a stated set of rules:

- the **expected population**, such as an HR roster or an approved access list, and
- the **collected export**, for example a directory's user export.

It lists every record that is missing, unexpected, duplicated, ambiguous, or mismatched, and every collection problem the profile asked it to check. Each finding names the file and the line or position of the records involved.

## What a report does not show

- It does not prove the collected export is complete. pakad cannot see records a source system never exported. The **possible-truncation** and **missing-source** checks catch common causes of incomplete exports, but not all of them.
- It does not judge authorization. An unexpected record is unmatched, not necessarily unauthorized.
- It does not verify where the files came from. That is part of your evidence chain, not pakad's.

Every report states this limit near the top.

## Confirm the report matches your files

The **Evidence** section lists the SHA-256 hash of each input and of the profile. Compute the hash of the files you received and compare:

| System | Command |
| --- | --- |
| Linux | `sha256sum FILE` |
| macOS | `shasum -a 256 FILE` |
| Windows PowerShell | `Get-FileHash -Algorithm SHA256 FILE` |

If any hash differs, the report was not produced from those files.

To reproduce the report yourself, run the same pakad version with the same profile and inputs, keeping the same file names, and pass the report's `as_of` value with `--as-of`. The reference time is recorded at full precision, so the findings will be identical. Only the generation time and run ID change. The report records the profile's hash, not the profile itself, so the profile must be kept with the inputs.

All files from one run share a run ID. If the HTML, JSON, CSV, and Markdown files you received show different run IDs, they did not come from the same run.

Ask for `pakad-manifest.json` with the reports. It lists every report file from the run with its SHA-256, which you can check with the commands in the preceding table. A matching hash shows the file is complete and unchanged since pakad wrote it. This covers a findings CSV with no rows, which has no other place to record its run. The manifest itself is not signed, so it detects accidents and partial copies; protect the set in your evidence system if you need to detect deliberate edits.

## Check the scope of the review

Read three sections before relying on the findings:

1. **Rules applied.** The key columns, the normalization, and the fields compared. Normalization that is too broad can merge distinct identities. pakad reports those cases as `ambiguous-key`, but check that the rules suit the population.
2. **Not verified.** Checks that did not run. A check that did not run is never reported as passed.
3. **Summary counts.** Expected and collected counts should agree with what the system owner reports.

## Sample

The repository includes a [complete sample report](https://github.com/faithful-oversight/faithful-pakad/tree/main/examples/roster-vs-directory/sample-report) built from synthetic data, with every finding kind.
