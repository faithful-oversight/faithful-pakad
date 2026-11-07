# Reports and findings

Every run produces one report document, and every output format is rendered from it, so the formats always agree.

## Report sections

| Section | What it holds |
| --- | --- |
| Summary | Record counts, matched keys, and the number of errors and warnings. A result with no findings still says how many checks did not run, so it is never read as a full pass. |
| Not verified | Checks that did not run, and why. |
| Findings | Each discrepancy, grouped by kind, with a plain-language explanation and a next step. |
| Evidence | The SHA-256 hash of each input and of the profile, the rules applied, and how to verify the hashes. |

The report also records the reference time used for freshness checks, the time it was generated, and the pakad version.

## Finding kinds

| Kind | Severity | Meaning |
| --- | --- | --- |
| `missing` | error | An expected record has no match in the collected export. |
| `unexpected` | error | A collected record matches nothing in the expected population. |
| `duplicate-key` | error | The same key appears in more than one record of one input. |
| `ambiguous-key` | error | Different raw keys become identical after normalization. |
| `blank-key` | error | A record's key is absent or empty, so it cannot be matched. |
| `field-mismatch` | error | A matched pair has different values in a compared field. |
| `missing-source` | error | An expected source contributed no collected records. |
| `stale-record` | warning | A capture time is older than the profile allows. |
| `invalid-timestamp` | warning | A capture time is absent, unusable, or more than five minutes after the reference time. |
| `possible-truncation` | warning | A record count is an exact multiple of a common page size. |
| `empty-input` | warning | An input has a header but no records, which would otherwise look like a clean result. |

A finding is a fact about the inputs, not a judgment. For example, `unexpected` means the record is unmatched, not that the access is unauthorized.

## Source references

Each finding points to the records that show it:

- **CSV:** the physical line where the record starts, counting the header as line 1. A record with a quoted line break starts on the line shown.
- **JSON:** the record's position in the array, starting at 1.

In people-facing reports, each reference starts with its input, for example `collected: users.csv line 7`, so inputs with the same filename stay distinct.

Keys in findings are shown after normalization, which is the form pakad matched on. Missing and unexpected findings also show the `raw_key` as written in the file, and duplicate and ambiguous findings list every raw value.

## JSON report

`pakad-report.json` follows a published JSON Schema. `pakad schema` prints the schema for the installed version, with no network access. The schema's identifier, `https://faithful-oversight.github.io/faithful-pakad/schema/report-v1.schema.json`, is also where the documentation site serves it once the project is public.

```json
{
  "schema_version": "1.0",
  "tool": {"name": "pakad", "version": "0.1.0"},
  "summary": {"expected_records": 9, "collected_records": 12, "matched_keys": 8,
              "errors": 7, "warnings": 2, "findings_by_kind": {"missing": 1, "...": 0}},
  "findings": [
    {
      "id": "F00001",
      "kind": "missing",
      "severity": "error",
      "message": "Expected record has no match in the collected export.",
      "key": ["000106"],
      "refs": [{"input": "expected", "file": "expected.csv", "row": 7, "unit": "line"}],
      "details": {"key_columns": "employee_id"}
    }
  ]
}
```

Compatibility promise:

- Within major version 1, a release may add optional properties or new finding kinds. Each such change raises the minor `schema_version`, for example from `1.0` to `1.1`, and ships the matching schema.
- Existing properties and finding kinds are never removed or renamed within a major version. A breaking change gets a new major schema version and a new major pakad release.
- The schema is strict, so a `1.0` validator rejects a `1.1` report's new fields. Validate each report with the schema for its `schema_version`, which `pakad schema` from the same pakad version prints. Consumers that read reports without validating should ignore properties and finding kinds they do not know.

The report records the profile's SHA-256 and lists its rules, including equivalent values. The hash identifies the profile; it does not contain it. Keep the profile with the inputs if the report may need to be reproduced.

Every report also has a `run_id`, shared by all files from the same run.

## Invisible characters

Input values can contain characters that change how text looks rather than what it says, such as terminal escape sequences or right-to-left override marks that make `exe.txt` display as `txt.exe`. The HTML, Markdown, and CSV reports and the terminal show these as visible escapes like `\u202e`. The JSON report keeps the exact values.

## Composite keys and display

People-facing reports join composite keys with ` | `. A key value that itself contains ` | ` can look like two values there. The JSON report keeps each part separately and is the authoritative form.

## Large reports

The HTML and Markdown reports show at most 500 findings of each kind, and say how many more there are. The JSON and CSV outputs always hold every finding.

## CSV findings

`pakad-findings.csv` has one row per finding, with the columns `id`, `kind`, `severity`, `key`, `source`, `message`, `details`, and `run_id`. Any cell that starts with a character a spreadsheet could treat as a formula gets a leading apostrophe, so opening the file cannot run anything.

## HTML report

`pakad-report.html` is a single file with no external resources. It works offline, follows the system's light or dark setting, and prints cleanly to paper or PDF. Its content security policy blocks scripts, network requests, and form submission, and every value from the inputs is escaped.

## Markdown report

`pakad-report.md` holds the same content in GitHub-flavored Markdown, ready to paste into a pull request, ticket, or change record. Input values are escaped so they cannot break the table layout or inject HTML.
