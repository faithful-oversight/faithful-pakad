# 3. Exact, explicit matching

- Status: accepted
- Date: 2026-11-07

## Context

Reconciliation results are used as audit evidence. A result that depends on guesswork, such as fuzzy name matching or automatic type conversion, is hard to defend and easy to get wrong. Common spreadsheet failures include dropped leading zeros, silently merged duplicates, and blanks treated as matches.

## Decision

- Every input value stays text. pakad never converts values to numbers or dates.
- Records match only when their keys are equal after the normalization steps the profile names. pakad does no fuzzy matching.
- An absent value differs from an empty value, and an absent value never equals anything.
- Duplicate keys and keys that collide only after normalization are findings, not merges.
- Field comparison runs only for keys with exactly one record on each side. Other keys are counted under **Not verified**.
- Checks that are not configured are reported as not verified, never as passed.

## Consequences

Results are reproducible and explainable: each finding follows from a stated rule and points to its source records. Users must state normalization explicitly, so a profile can need small adjustments before a first clean run. That cost is intended, because every adjustment is visible in the report's rules.
