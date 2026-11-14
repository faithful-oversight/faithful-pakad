# Limitations

pakad is deliberately narrow. This page lists what it cannot do, so nobody relies on it for more than it provides.

## Out of scope

The tool will not:

- Decide whether access is authorized. Unmatched means unmatched, not unauthorized.
- Infer identity or ownership from display names.
- Connect to live systems. Inputs are exported files.

## Limits of any file-based check

- pakad sees only what the inputs contain. It cannot detect records a source system did not export.
- A clean result means no findings in the supplied inputs. It is not proof that the environment is correct.
- Results are only as current as the inputs. Freshness is checked only when the profile names a capture time column.
- The possible-truncation check has two parts. The first is a heuristic: it flags counts that are exact multiples of common page sizes, so a truncated export with any other count is not detected, and a complete export that happens to match a page size produces a warning. The second reads what a JSON file says about itself. When the file is an object with a `value` or `records` array, pakad flags a non-empty `@odata.nextLink` (also `nextLink` or `odata.nextLink`, in any letter case), which means another page exists, and an `@odata.count` or `count` that differs from the number of records in the file. Both produce a `possible-truncation` warning even when no page sizes are configured. A paged export saved as several files, or one that carries none of these properties, is not detected. Because the finding is a warning, `--fail-on error` does not fail on it.

## Matching

- Matching is exact after the profile's normalization. pakad does no fuzzy matching, by design, because fuzzy matches are hard to defend as evidence.
- Field comparisons are skipped for keys with duplicate records, because the records to compare cannot be chosen safely. Reports list how many were skipped.

## Inputs

- CSV and JSON only. Export spreadsheets to CSV first.
- Each input is read fully into memory. Memory use is several times the file size, because every value is kept with its source line. The default limit is 256 MiB per file, adjustable with `--max-bytes`; lower it on machines with little memory.
- JSON input must be an array of objects, or an object with a `value` or `records` array.
