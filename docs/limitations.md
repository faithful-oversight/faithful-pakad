# Limitations

pakad is deliberately narrow. This page lists what it cannot do, so nobody relies on it for more than it provides.

## Status and testing

pakad is beta software, version 0.1.2. Every test uses synthetic data. Continuous integration runs the test suite on Linux with Python 3.11 to 3.14, on Windows with Python 3.13, and on macOS with Python 3.13. No claim is made that pakad has been validated against real exports from production systems. Behavior of a redirected Windows console is tested by simulating a stream that cannot encode a character, not on a real console. Check the first reports against data you can verify by hand.

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
- Each input is read fully into memory, and every record is kept with its source line, so memory depends on the number of records far more than on the file size. Measured on Python 3.13, a whole run takes about 650 bytes per record for a one-column file of 8-byte rows, which is about 80 times the file size, and about 1,100 bytes per record for an eight-column file of roughly 80-byte rows, which is about 14 times the file size. A run of two files of 2 million narrow records needs about 2.4 GiB. Your numbers will differ with the number and width of columns and the Python version.
- `--max-bytes` limits file size, not record count. Its default is 256 MiB per file, and a file of that size made of very short rows holds tens of millions of records, which would need tens of gigabytes. Size the limit from the number of records you expect, at about 1 KiB of memory per record and per input, and lower it on machines with little memory.
- JSON input must be an array of objects, or an object with a `value` or `records` array.
