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
- The possible-truncation check is a heuristic. It flags counts that are exact multiples of common page sizes. A truncated export with any other count is not detected, and a complete export that happens to match a page size produces a warning.

## Matching

- Matching is exact after the profile's normalization. pakad does no fuzzy matching, by design, because fuzzy matches are hard to defend as evidence.
- Field comparisons are skipped for keys with duplicate records, because the records to compare cannot be chosen safely. Reports list how many were skipped.

## Inputs

- CSV and JSON only. Export spreadsheets to CSV first.
- Each input is read fully into memory. Memory use is several times the file size, because every value is kept with its source line. The default limit is 256 MiB per file, adjustable with `--max-bytes`; lower it on machines with little memory.
- JSON input must be an array of objects, or an object with a `value` or `records` array.
