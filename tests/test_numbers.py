import re
from decimal import Decimal as D

import pytest

from brsr.parse.numbers import (
    cell_has_value,
    number_tokens,
    row_has_values,
    same_number,
    significant_digits,
)


def test_number_tokens_handles_indian_and_western_grouping() -> None:
    text = "Total (A) 1,53,74,95,415 and 1,537,495,415; Scope 1: 20,494.8 in FY 2024-25."
    assert number_tokens(text) == [
        D("1537495415"),
        D("1537495415"),
        D("1"),
        D("20494.8"),
        D("2024"),
        D("25"),
    ]


def test_trailing_full_stop_is_not_a_decimal_point() -> None:
    assert number_tokens("was 642.") == [D("642")]


@pytest.mark.parametrize(
    ("value", "n"), [("0", 0), ("5.6", 2), ("0.0123", 3), ("20494.8", 6), ("100", 3)]
)
def test_significant_digits(value: str, n: int) -> None:
    assert significant_digits(D(value)) == n


@pytest.mark.parametrize(
    ("printed", "reported", "match"),
    [
        ("20494.8", "20494.8", True),
        ("20494.80", "20494.8", True),  # trailing zero
        ("587.91", "587.907", True),  # rounded to printed decimals
        ("1542", "1541.6", True),
        ("1537", "1537495415", False),  # truncated, not rounded: different number
        ("587.90", "587.907", False),
        ("204948", "20494.8", False),  # lost decimal point
    ],
)
def test_same_number(printed: str, reported: str, match: bool) -> None:
    assert same_number(D(printed), D(reported)) is match


@pytest.mark.parametrize("cell", ["0", "Nil", "NIL", "-", "NA", "0.00"])
def test_zero_can_be_printed_as_words(cell: str) -> None:
    assert cell_has_value(cell, D("0"))


def test_zero_does_not_match_empty_or_nonzero() -> None:
    assert not cell_has_value("", D("0"))
    assert not cell_has_value("12", D("0"))
    assert not cell_has_value("Total Scope 1 emissions", D("0"))  # text without numbers


SCOPE1 = re.compile(r"scope\s*1", re.I)


def test_row_intact_in_order_across_cells() -> None:
    row = ["Total Scope 1 emissions", "tCO2e", "20,494.8", "21,949.0"]
    assert row_has_values(row, SCOPE1, D("20494.8"), D("21949"))


def test_row_broken_if_years_merged_into_one_cell() -> None:
    row = ["Total Scope 1 emissions", "tCO2e", "20,494.8 21,949.0"]
    assert not row_has_values(row, SCOPE1, D("20494.8"), D("21949"))


def test_row_broken_if_years_swapped_or_label_missing() -> None:
    assert not row_has_values(["Scope 1", "21,949.0", "20,494.8"], SCOPE1, D("20494.8"), D("21949"))
    assert not row_has_values(["Scope 2", "20,494.8", "21,949.0"], SCOPE1, D("20494.8"), D("21949"))
