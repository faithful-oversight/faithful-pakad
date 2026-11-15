# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the CSV and JSON readers, including fuzzing with arbitrary input."""

from __future__ import annotations

import contextlib
import csv
import io
import json
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from faithful_pakad.errors import InputError
from faithful_pakad.model import Side
from faithful_pakad.profile import TableSpec
from faithful_pakad.readers import read_table

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

SPEC = TableSpec(key=("id",))


def read(path: Path, spec: TableSpec = SPEC, **kwargs: int) -> list[dict[str, str | None]]:
    """Read a file and return each record with every column, absent ones as None."""
    table = read_table(path, spec, Side.EXPECTED, **kwargs)
    return [{c: r.values.get(c) for c in table.columns} for r in table.records]


def test_csv_keeps_every_value_as_text(write: Callable[[str, str | bytes], Path]) -> None:
    rows = read(write("a.csv", "id,amount,flag\n000123,1e5,TRUE\n"))
    assert rows == [{"id": "000123", "amount": "1e5", "flag": "TRUE"}]


def test_csv_metadata_and_line_numbers(write: Callable[[str, str | bytes], Path]) -> None:
    path = write("a.csv", 'id,note\n1,"two\nlines"\n\n2,x\n')
    table = read_table(path, SPEC, Side.COLLECTED)
    assert table.columns == ("id", "note")
    assert table.file == "a.csv"
    assert table.size_bytes == len(path.read_bytes())
    assert len(table.sha256) == 64
    assert [r.ref.row for r in table.records] == [2, 5]
    assert table.records[0].values["note"] == "two\nlines"
    assert table.records[0].ref.side is Side.COLLECTED


def test_csv_short_rows_are_absent_not_empty(write: Callable[[str, str | bytes], Path]) -> None:
    assert read(write("a.csv", "id,a,b\n1,\n")) == [{"id": "1", "a": "", "b": None}]


def test_csv_strips_bom_and_header_spaces(write: Callable[[str, str | bytes], Path]) -> None:
    assert read(write("a.csv", "\ufeff id ,x\n1,2\n".encode())) == [{"id": "1", "x": "2"}]


def test_tsv_and_explicit_delimiter(write: Callable[[str, str | bytes], Path]) -> None:
    assert read(write("a.tsv", "id\tx\n1\t2\n")) == [{"id": "1", "x": "2"}]
    spec = TableSpec(key=("id",), delimiter=";", format="csv")
    assert read(write("a.data", "id;x\n1;2\n"), spec) == [{"id": "1", "x": "2"}]


def test_other_encodings(write: Callable[[str, str | bytes], Path]) -> None:
    spec = TableSpec(key=("id",), encoding="cp1252")
    assert read(write("a.csv", "id\nJos\xe9\n".encode("cp1252")), spec) == [{"id": "José"}]


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("a.csv", "", "empty or has no header"),
        ("a.csv", "id,,x\n", "empty column name"),
        ("a.csv", "id,id\n", "repeats column 'id'"),
        ("a.csv", "id\n1,2\n", "line 2 has 2 fields"),
        ("a.csv", 'id\n"unterminated\n', "malformed CSV"),
        ("a.csv", b"id\n\xff\n", "not valid utf-8-sig text at byte 3"),
        ("a.xlsx", "id\n", "cannot tell the format"),
        ("a.json", "{not json", "not valid JSON"),
        ("a.json", "[NaN]", "not valid JSON"),
        ("a.json", '{"a": 1, "a": 2}', "repeats a property name"),
        ("a.json", '{"value": [], "records": []}', "or an object with"),
        ("a.json", '"text"', "expected a JSON array"),
        ("a.json", "[1]", "item 1 is not a JSON object"),
        ("a.json", '[{"": 1}]', "empty property name"),
        ("a.json", '[{"id": 1, " id": 2}]', "item 1 repeats a property name"),
        # Python 3.14 parses very deep nesting that older versions reject.
        ("a.json", "[" * 100000 + "]" * 100000, "not valid JSON|is not a JSON object"),
    ],
)
def test_malformed_inputs_are_input_errors(
    write: Callable[[str, str | bytes], Path], name: str, content: str | bytes, message: str
) -> None:
    with pytest.raises(InputError, match=message):
        read(write(name, content))


def test_unknown_encoding(write: Callable[[str, str | bytes], Path]) -> None:
    with pytest.raises(InputError, match="unknown encoding"):
        read(write("a.csv", "id\n"), TableSpec(key=("id",), encoding="no-such-codec"))


def test_size_limit(write: Callable[[str, str | bytes], Path]) -> None:
    with pytest.raises(InputError, match="over the 4-byte limit"):
        read(write("a.csv", "id\n12\n"), max_bytes=4)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"cannot read expected input .*absent\.csv") as caught:
        read(tmp_path / "absent.csv")
    assert str(tmp_path) in str(caught.value)


def test_json_values_become_text(write: Callable[[str, str | bytes], Path]) -> None:
    data = [
        {"id": "007", "n": 12, "f": 1.5, "b": True, "z": None, "o": {"k": [1]}},
        {"id": "8", "extra": False},
    ]
    rows = read(write("a.json", json.dumps(data)))
    assert rows[0] == {
        "id": "007",
        "n": "12",
        "f": "1.5",
        "b": "true",
        "z": None,
        "o": '{"k": [1]}',
        "extra": None,
    }
    assert rows[1]["extra"] == "false"
    assert rows[1]["n"] is None


def test_json_numbers_keep_their_exact_text(write: Callable[[str, str | bytes], Path]) -> None:
    text = '[{"id": 1.0, "big": 1e400, "n": {"b": [2.50, true, null, "s"], "a": -0}}]'
    rows = read(write("a.json", text))
    assert rows[0]["id"] == "1.0"
    assert rows[0]["big"] == "1e400"
    assert rows[0]["n"] == '{"a": -0, "b": [2.50, true, null, "s"]}'


@pytest.mark.parametrize(
    "content",
    [
        '[{"id": "x\\ud800y"}]',
        '[{"k\\udfff": "1"}]',
        '[{"id": "1", "extra": ["\\ud801"]}]',
        '[{"id": "1", "extra": {"\\udc00": 1}}]',
    ],
)
def test_json_unpaired_surrogates_are_input_errors(
    write: Callable[[str, str | bytes], Path], content: str
) -> None:
    """Replacing them would let two different invalid identifiers match silently."""
    with pytest.raises(InputError, match="unpaired surrogate"):
        read(write("a.json", content))


def test_json_valid_surrogate_pairs_still_decode(write: Callable[[str, str | bytes], Path]) -> None:
    assert read(write("a.json", '[{"id": "\\ud83d\\ude00"}]')) == [{"id": chr(0x1F600)}]


def test_json_nesting_limit_applies_after_decoding(
    write: Callable[[str, str | bytes], Path],
) -> None:
    """A value the decoder accepts but that is too deep is an input error, even if unused."""
    deep = "[" * 500 + "0" + "]" * 500
    with pytest.raises(InputError, match=r"item 1, property 'extra' is nested more than 64"):
        read(write("a.json", '[{"id": "a", "extra": ' + deep + "}]"))
    ok = "[" * 63 + "0" + "]" * 63
    assert read(write("b.json", '[{"id": "a", "extra": ' + ok + "}]"))[0]["extra"] == ok


@pytest.mark.parametrize("leaf", ["", "0", '"text"', "null", "true"])
def test_json_nesting_limit_counts_only_arrays_and_objects(
    write: Callable[[str, str | bytes], Path], leaf: str
) -> None:
    """64 levels of arrays are allowed and 65 are not, whatever the innermost value is."""
    allowed = "[" * 63 + "[" + leaf + "]" + "]" * 63
    assert read(write("ok.json", '[{"id": "a", "extra": ' + allowed + "}]"))[0]["extra"]
    deeper = "[" + allowed + "]"
    with pytest.raises(InputError, match="nested more than 64"):
        read(write("deep.json", '[{"id": "a", "extra": ' + deeper + "}]"))


def test_sparse_records_store_only_present_fields(
    write: Callable[[str, str | bytes], Path],
) -> None:
    """Memory stays linear when every record has different columns."""
    rows = 3000
    data = json.dumps([{"id": str(i), f"c{i}": "x"} for i in range(rows)])
    table = read_table(write("s.json", data), SPEC, Side.EXPECTED)
    assert len(table.columns) == rows + 1
    assert sum(len(r.values) for r in table.records) == 2 * rows
    csv_text = "id," + ",".join(f"c{i}" for i in range(rows)) + "\n" + "1\n" * rows
    table = read_table(write("s.csv", csv_text), SPEC, Side.EXPECTED)
    assert sum(len(r.values) for r in table.records) == rows
    assert table.records[0].values.get("c5") is None


def test_json_value_wrapper_and_item_refs(write: Callable[[str, str | bytes], Path]) -> None:
    path = write("a.json", json.dumps({"value": [{"id": "1"}, {"id": "2"}], "count": 2}))
    table = read_table(path, SPEC, Side.COLLECTED)
    assert [(r.ref.row, r.ref.unit) for r in table.records] == [(1, "item"), (2, "item")]


@settings(max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(content=st.binary(max_size=400), suffix=st.sampled_from([".csv", ".json"]))
def test_arbitrary_bytes_never_crash(
    write: Callable[[str, str | bytes], Path], content: bytes, suffix: str
) -> None:
    """Fuzz: any input either reads cleanly or raises InputError, never anything else."""
    with contextlib.suppress(InputError):
        read(write("fuzz" + suffix, content))


TEXT = st.text(st.characters(codec="utf-8"), max_size=20)


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(rows=st.lists(st.tuples(TEXT, TEXT), min_size=1, max_size=20))
def test_csv_round_trip_preserves_values(
    write: Callable[[str, str | bytes], Path], rows: list[tuple[str, str]]
) -> None:
    """Whatever a standard CSV writer produces, the reader returns unchanged."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["id", "value"])
    writer.writerows(rows)
    result = read(write("rt.csv", buffer.getvalue()))
    assert result == [{"id": a, "value": b} for a, b in rows]


GRAPH_PAGE = (
    '{"@odata.context": "https://graph.example/v1.0/$metadata#users", %s, "value": [{"id": "A1"}]}'
)


@pytest.mark.parametrize(
    ("extras", "expected"),
    [
        ('"@odata.nextLink": "https://graph.example/v1.0/users?$skiptoken=abc"', "@odata.nextLink"),
        ('"nextLink": "https://example.test/next"', "nextLink"),
        ('"@ODATA.NEXTLINK": "https://example.test/next"', "@ODATA.NEXTLINK"),
    ],
)
def test_a_next_page_link_marks_the_input_incomplete(
    write: Callable[[str, str | bytes], Path], extras: str, expected: str
) -> None:
    """PAKAD-C02: a paged Graph export is not a complete population."""
    table = read_table(write("graph.json", GRAPH_PAGE % extras), SPEC, Side.COLLECTED)
    assert len(table.incomplete_signals) == 1
    assert expected in table.incomplete_signals[0]
    assert table.paging_signals == ()
    assert [r.values.get("id") for r in table.records] == ["A1"]


@pytest.mark.parametrize(
    ("extras", "expected"),
    [
        ('"@odata.count": 250', "@odata.count is 250, but the file holds 1 records"),
        ('"count": 12', "count is 12, but the file holds 1 records"),
    ],
)
def test_a_differing_total_is_only_a_possible_truncation_signal(
    write: Callable[[str, str | bytes], Path], extras: str, expected: str
) -> None:
    table = read_table(write("graph.json", GRAPH_PAGE % extras), SPEC, Side.COLLECTED)
    assert table.incomplete_signals == ()
    assert len(table.paging_signals) == 1
    assert expected in table.paging_signals[0]


@pytest.mark.parametrize(
    "extras",
    [
        '"@odata.nextLink": null',
        '"@odata.nextLink": ""',
        '"@odata.nextLink": 5',
        '"@odata.count": 1',
        '"count": "7"',
        '"count": 1.5',
        '"@odata.deltaLink": "https://graph.example/v1.0/users/delta?$deltatoken=x"',
    ],
)
def test_a_json_wrapper_that_does_not_say_more_exists_is_not_flagged(
    write: Callable[[str, str | bytes], Path], extras: str
) -> None:
    path = write("graph.json", GRAPH_PAGE % extras)
    table = read_table(path, SPEC, Side.COLLECTED)
    assert table.paging_signals == ()
    assert table.incomplete_signals == ()


def test_a_huge_count_is_a_different_total_and_does_not_crash(
    write: Callable[[str, str | bytes], Path],
) -> None:
    path = write("graph.json", GRAPH_PAGE % ('"count": ' + "9" * 5000))
    assert len(read_table(path, SPEC, Side.COLLECTED).paging_signals) == 1


def test_plain_arrays_and_csv_have_no_paging_signals(
    write: Callable[[str, str | bytes], Path],
) -> None:
    assert read_table(write("a.json", '[{"id": "1"}]'), SPEC, Side.EXPECTED).paging_signals == ()
    assert read_table(write("a.csv", "id\n1\n"), SPEC, Side.EXPECTED).paging_signals == ()


@pytest.mark.parametrize("limit", [2**36, 2**40, 2**63 - 1, 2**63, 2**200])
def test_a_huge_size_limit_does_not_fail_on_a_tiny_file(
    write: Callable[[str, str | bytes], Path], limit: int
) -> None:
    """PAKAD-C06: the limit is a ceiling, not an amount of memory to reserve."""
    assert read(write("a.csv", "id\nA1\n"), max_bytes=limit) == [{"id": "A1"}]


def test_the_limit_is_exact_across_read_blocks(
    write: Callable[[str, str | bytes], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("faithful_pakad.readers.READ_BLOCK_BYTES", 3)
    path = write("a.csv", "id\n1234567\n")  # 11 bytes
    assert len(read(path, max_bytes=11)) == 1
    with pytest.raises(InputError, match="over the 10-byte limit"):
        read(path, max_bytes=10)
