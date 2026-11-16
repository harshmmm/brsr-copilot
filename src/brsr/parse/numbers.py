"""Read numbers as BRSR filings print them, and match them against reported (XBRL) values."""

import re
from decimal import ROUND_HALF_UP, Decimal

# Digits with optional thousands separators in Western (1,537,495) or Indian (15,37,495)
# grouping, and an optional decimal part. Commas are dropped before conversion.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ZERO_WORDS = {"0", "nil", "-", "–", "—", "na", "n.a.", "not applicable"}


def number_tokens(text: str) -> list[Decimal]:
    out = []
    for tok in _NUMBER.findall(text):
        digits = tok.replace(",", "").rstrip(".")
        if digits:
            out.append(Decimal(digits))
    return out


def significant_digits(value: Decimal) -> int:
    """Digits after stripping leading zeros: 0 -> 0, 5.6 -> 2, 0.0123 -> 3, 20494.8 -> 6."""
    return len(str(abs(value)).replace(".", "").lstrip("0"))


def same_number(printed: Decimal, reported: Decimal) -> bool:
    """True if `printed` is `reported`, possibly rounded to the decimals actually printed.

    A filing may print 587.91 where XBRL has 587.907; it must not match 1,537 to 1537495415.
    """
    if printed == reported:
        return True
    decimals = max(0, -int(printed.as_tuple().exponent))
    step = Decimal(1).scaleb(-decimals)
    return reported.quantize(step, rounding=ROUND_HALF_UP) == printed


def cell_has_value(cell: str, value: Decimal) -> bool:
    """Does a table cell show `value`? Zero may be printed as 0, Nil, - or NA."""
    if value == 0:
        text = cell.strip().lower()
        tokens = number_tokens(text)
        return text in _ZERO_WORDS or (bool(tokens) and all(t == 0 for t in tokens))
    return any(same_number(t, value) for t in number_tokens(cell))


def row_has_values(
    row: list[str], label: re.Pattern[str], current: Decimal, previous: Decimal
) -> bool:
    """A row is intact if a label cell is followed by the current-year value and then the
    previous-year value, each in its own cell (BRSR prints current year first)."""
    for i, cell in enumerate(row):
        if not label.search(cell):
            continue
        cur = [j for j in range(i + 1, len(row)) if cell_has_value(row[j], current)]
        if any(cell_has_value(row[k], previous) for j in cur for k in range(j + 1, len(row))):
            return True
    return False
