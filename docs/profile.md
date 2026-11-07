# Profile reference

A profile is a [TOML](https://toml.io/) file that tells pakad how to read the two inputs, how to match records, and which checks to run. Print a commented starting point with `pakad example-profile`.

Validation is strict. A setting pakad does not recognize is an error, so a typo can never silently switch a check off. Check a profile with `pakad check-profile`.

## Complete example

```toml
version = 1
name = "HR roster vs directory export"

[expected]
key = ["employee_id"]

[collected]
key = ["employeeID"]

[match]
normalize = ["strip", "casefold"]

[[compare]]
expected = "status"
collected = "accountEnabled"
normalize = ["strip", "casefold"]
equivalents = { "true" = "active", "false" = "terminated" }

[collection]
source_column = "domain"
expected_sources = ["corp.example", "eu.corp.example", "apac.corp.example"]
captured_at_column = "collectedAt"
max_age_hours = 24
naive_timestamps = "reject"
page_sizes = [1000, 1500, 5000]
```

## Top level

| Setting | Required | Meaning |
| --- | --- | --- |
| `version` | Yes | Profile format version. Must be `1`. |
| `name` | No | Shown in report titles. Default: `unnamed profile`. |

## `[expected]` and `[collected]`

Both tables take the same settings and both are required.

| Setting | Default | Meaning |
| --- | --- | --- |
| `key` | required | Column, or list of columns, that identify a record. Both tables must name the same number of columns. The first expected column is matched with the first collected column, and so on. |
| `format` | `auto` | `auto` picks from the file extension. Or `csv` or `json`. |
| `delimiter` | `,` | CSV delimiter, one character other than a quote or line break. Files ending in `.tsv` default to a tab. |
| `encoding` | `utf-8-sig` | Text encoding. The default reads UTF-8 with or without a byte order mark. Use, for example, `cp1252` for older Windows exports. Checked when the profile loads. |

## `[match]`

| Setting | Default | Meaning |
| --- | --- | --- |
| `normalize` | `["strip"]` | Steps applied to key values before matching, in order. |

Available normalization steps:

| Step | Effect |
| --- | --- |
| `strip` | Removes spaces, tabs, and line breaks at the start and end. |
| `casefold` | Ignores letter case, including for non-English letters. |
| `collapse-whitespace` | Turns every run of whitespace inside the value into one space. |
| `nfkc` | Applies Unicode NFKC normalization, so look-alike forms such as full-width digits compare as plain digits. |

Choose steps deliberately. If two different raw keys become identical after normalization, pakad reports an `ambiguous-key` finding rather than silently merging them.

## `[[compare]]`

Optional. Repeat the table once for each field to compare on matched records.

| Setting | Default | Meaning |
| --- | --- | --- |
| `expected` | required | Column in the expected input. |
| `collected` | required | Column in the collected input. |
| `normalize` | `["strip"]` | Steps applied to both values before comparing. |
| `equivalents` | none | Table mapping a collected value to the expected value it counts as. Keys and values are normalized with the same steps, and two keys that normalize to the same text are an error. |

An absent value never equals anything, including another absent value, so missing data always shows up as a `field-mismatch`.

Fields are compared only when each side has exactly one record for the key. When duplicates make the pairing unclear, pakad skips the comparison for that key and says so under **Not verified**.

## `[collection]`

Optional checks on the collected export as a whole.

| Setting | Default | Meaning |
| --- | --- | --- |
| `source_column` | none | Collected column that names where each record came from, for example its domain. |
| `expected_sources` | none | Sources that must each contribute at least one record. Needs `source_column`. Compared ignoring case and surrounding spaces. |
| `captured_at_column` | none | Collected column holding each record's capture time, in ISO 8601. Set together with `max_age_hours`. |
| `max_age_hours` | none | Records captured longer ago than this, measured from the reference time, are reported as stale. Between 0 and 87600 (ten years). Capture times more than five minutes after the reference time are reported as invalid, because they usually mean a clock or typing error. |
| `naive_timestamps` | `reject` | How to treat capture times without a time zone: `reject` reports them as invalid, `utc` treats them as UTC. |
| `page_sizes` | `[1000, 1500, 5000]` | Warn when the collected record count, overall or for any source, is an exact multiple of one of these numbers. Use `[]` to switch the check off. |

Checks that are not configured are listed under **Not verified** in every report, so a reader can see what was not checked.
