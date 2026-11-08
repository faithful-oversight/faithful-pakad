# Reconciliation report: HR roster vs directory export

**7 errors and 2 warnings need review.**

Reference time 2026-11-07T12:00:00+00:00. Generated 2026-11-07T23:24:18+00:00 by pakad 0.1.0. Run ID `7054929deee74c35b006ab44605a4654`.

> This report covers only what the input files contain. It cannot detect records a source system never exported, and a clean result is not proof that the environment is correct.

## Summary

| Measure | Value |
| --- | --- |
| Expected records | 9 |
| Collected records | 12 |
| Matched keys | 8 |
| Errors | 7 |
| Warnings | 2 |

## Not verified

- **field comparison:** Skipped for 2 matched keys with duplicate records, because the records to compare cannot be chosen safely.

## Findings

### Missing from the collected export (1)

`missing`, error. A record in the expected population has no matching record in the collected export.

**What to do:** Confirm whether the record should exist in the source system. If it should, check whether the export filtered it out or stopped early before treating it as absent.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00001 | 000106 | expected: expected.csv line 7 | key columns: employee\_id; raw key: 000106 |

### Not in the expected population (1)

`unexpected`, error. A collected record matches nothing in the expected population.

**What to do:** Confirm whether the expected population is complete. If it is, the record may be an orphaned, test, or unapproved account. Unmatched does not by itself mean unauthorized.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00002 | 000110 | collected: collected.csv line 12 | key columns: employeeID; raw key: 000110 |

### Duplicate keys (1)

`duplicate-key`, error. The same key appears in more than one record of the same input.

**What to do:** Find out why the source has two records for one key. Field comparisons are skipped for these keys, because the right record cannot be chosen safely.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00003 | 000105 | collected: collected.csv line 6; collected: collected.csv line 7 | raw values: 000105 |

### Keys that collide after normalization (1)

`ambiguous-key`, error. Different raw key values become identical after the profile's normalization, for example two values that differ only in letter case.

**What to do:** Decide whether these are truly the same identity. If not, remove the normalization step that merges them from the profile.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00004 | a0108 | collected: collected.csv line 9; collected: collected.csv line 10 | raw values:  A0108; a0108 |

### Records without a usable key (1)

`blank-key`, error. A record's key is absent or empty, so it cannot be matched to anything.

**What to do:** Fix the record in the source, or confirm it is outside the scope of the review.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00005 | — | collected: collected.csv line 13 | key columns: employeeID |

### Field values that disagree (1)

`field-mismatch`, error. A matched pair of records has different values in a compared field.

**What to do:** Check which value is correct. If the values mean the same thing but are written differently, add them to the profile's equivalents.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00006 | 000104 | expected: expected.csv line 5; collected: collected.csv line 5 | field: status / accountEnabled; expected value: terminated; collected value: TRUE |

### Expected sources with no records (1)

`missing-source`, error. The profile lists a source, such as a domain or tenant, that contributed no records to the collected export.

**What to do:** Check whether collection ran against that source and finished successfully.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00007 | — | — | source column: domain; source: apac.corp.example |

### Stale records (1)

`stale-record`, warning. A collected record's capture time is older than the profile allows.

**What to do:** Collect a fresh export, or confirm the older capture is acceptable for this review.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00008 | — | collected: collected.csv line 8 | column: collectedAt; captured at: 2026-11-04T06:00:00+00:00; max age hours: 24 |

### Unusable capture times (1)

`invalid-timestamp`, warning. A capture time is absent, is not ISO 8601, or has no time zone while the profile rejects timestamps without one.

**What to do:** Export timestamps in ISO 8601 with a time zone, or set naive\_timestamps to utc if the source writes UTC without saying so.

| ID | Key | Source | Details |
| --- | --- | --- | --- |
| F00009 | — | collected: collected.csv line 11 | column: collectedAt; value: 2026-11-07 06:00:00 |

## Evidence

| Input | File | Records | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| Expected | expected.csv | 9 | 390 | a44a4f07a0d3a27d9eeb1d95736fbd7b92bb21bb006d122af89cb4bde836b2d8 |
| Collected | collected.csv | 12 | 793 | 8e7cf644a6c61b4b433b323cace116fe78d2504f70001fb29dcddbfc919e9aa7 |
| Profile | profile.toml | — | — | 285f99b876116a207b924538fa817ee973d076e8d8068fa4ce48c8abbf7f7b81 |

Rules applied:

- Match expected \[employee\_id\] to collected \[employeeID\] after normalization: strip, casefold.
- Compare status with accountEnabled after normalization: strip, casefold; equivalents: true = active, false = terminated.
- Every expected source must appear in domain: corp.example, eu.corp.example, apac.corp.example.
- Records in collectedAt must be at most 24 hours old (naive timestamps: reject).
- Warn when record counts are exact multiples of 1000, 1500, 5000.

To confirm this report describes the files you hold, compute each file's SHA-256 hash and compare it with the value above.

- Linux: `sha256sum FILE`
- macOS: `shasum -a 256 FILE`
- Windows PowerShell: `Get-FileHash -Algorithm SHA256 FILE`
