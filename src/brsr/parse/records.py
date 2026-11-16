"""Parser-independent records: every PDF parser returns a ParsedDoc built from these."""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageRecord:
    page_no: int  # 1-based, as shown in a PDF viewer, so it can be cited directly
    text: str


@dataclass(frozen=True)
class TableRecord:
    page_no: int
    table_idx: int  # order of the table on its page, from 0
    rows: list[list[str]]


@dataclass
class ParsedDoc:
    parser: str
    parser_version: str
    pages: list[PageRecord] = field(default_factory=list)
    tables: list[TableRecord] = field(default_factory=list)


def clean_cell(value: str | None) -> str:
    """Normalise a table cell: None becomes "", internal whitespace and newlines collapse."""
    return re.sub(r"\s+", " ", value or "").strip()


def devanagari_ratio(text: str) -> float:
    """Share of letters in the Devanagari block, used to flag Hindi pages in bilingual filings."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum("ऀ" <= c <= "ॿ" for c in letters) / len(letters)


def table_markdown(rows: list[list[str]]) -> str:
    """Render rows as a markdown table, first row as header. Ragged rows are padded."""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    padded = [[c.replace("|", "\\|") for c in r] + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
    return "\n".join(lines)
