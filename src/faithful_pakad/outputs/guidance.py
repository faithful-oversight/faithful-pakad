# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Plain-language titles and next steps for each finding kind.

Reports show this text next to each group of findings, so a reader knows what a
finding means and what to check without opening the documentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from faithful_pakad.model import Kind


@dataclass(frozen=True, slots=True)
class Guidance:
    """How a finding kind is presented to readers."""

    title: str
    meaning: str
    next_step: str


GUIDANCE: dict[Kind, Guidance] = {
    Kind.MISSING: Guidance(
        "Missing from the collected export",
        "A record in the expected population has no matching record in the collected export.",
        "Confirm whether the record should exist in the source system. If it should, check "
        "whether the export filtered it out or stopped early before treating it as absent.",
    ),
    Kind.UNEXPECTED: Guidance(
        "Not in the expected population",
        "A collected record matches nothing in the expected population.",
        "Confirm whether the expected population is complete. If it is, the record may be "
        "an orphaned, test, or unapproved account. Unmatched does not by itself mean "
        "unauthorized.",
    ),
    Kind.DUPLICATE_KEY: Guidance(
        "Duplicate keys",
        "The same key appears in more than one record of the same input.",
        "Find out why the source has two records for one key. Field comparisons are "
        "skipped for these keys, because the right record cannot be chosen safely.",
    ),
    Kind.AMBIGUOUS_KEY: Guidance(
        "Keys that collide after normalization",
        "Different raw key values become identical after the profile's normalization, "
        "for example two values that differ only in letter case.",
        "Decide whether these are truly the same identity. If not, remove the "
        "normalization step that merges them from the profile.",
    ),
    Kind.BLANK_KEY: Guidance(
        "Records without a usable key",
        "A record's key is absent or empty, so it cannot be matched to anything.",
        "Fix the record in the source, or confirm it is outside the scope of the review.",
    ),
    Kind.FIELD_MISMATCH: Guidance(
        "Field values that disagree",
        "A matched pair of records has different values in a compared field.",
        "Check which value is correct. If the values mean the same thing but are written "
        "differently, add them to the profile's equivalents.",
    ),
    Kind.MISSING_SOURCE: Guidance(
        "Expected sources with no records",
        "The profile lists a source, such as a domain or tenant, that contributed no "
        "records to the collected export.",
        "Check whether collection ran against that source and finished successfully.",
    ),
    Kind.STALE_RECORD: Guidance(
        "Stale records",
        "A collected record's capture time is older than the profile allows.",
        "Collect a fresh export, or confirm the older capture is acceptable for this review.",
    ),
    Kind.INVALID_TIMESTAMP: Guidance(
        "Unusable capture times",
        "A capture time is absent, is not ISO 8601, or has no time zone while the profile "
        "rejects timestamps without one.",
        "Export timestamps in ISO 8601 with a time zone, or set naive_timestamps to utc if "
        "the source writes UTC without saying so.",
    ),
    Kind.POSSIBLE_TRUNCATION: Guidance(
        "Possible paging truncation",
        "A record count is an exact multiple of a common page size, or the file itself says "
        "it is one page of a larger result, such as a Microsoft Graph page with an "
        "@odata.nextLink. Paged exports that stop early often look like this.",
        "Export every page and run again. For a count that only matches a page size, compare "
        "it with the source system's own total; if they match, the warning can be ignored.",
    ),
    Kind.EMPTY_INPUT: Guidance(
        "Empty inputs",
        "An input file has a header but no records. Comparing against an empty file "
        "finds nothing, which can look like a clean result.",
        "Confirm the export ran and the population really is empty before relying on "
        "the rest of the report.",
    ),
}
