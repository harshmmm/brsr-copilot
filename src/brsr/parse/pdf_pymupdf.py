"""PyMuPDF parser: embedded text per page, plus ruled tables via find_tables()."""

from pathlib import Path

import pymupdf

from brsr.parse.records import PageRecord, ParsedDoc, TableRecord, clean_cell

NAME = "pymupdf"


def version() -> str:
    # "cellclip": cell text comes from get_text(clip=cell), not Table.extract(); see D006.
    return f"pymupdf-{pymupdf.__version__}-cellclip"


def _table_rows(page: pymupdf.Page, table: pymupdf.table.Table) -> list[list[str]]:
    # Table.extract() drops spaces and moves punctuation to the end of BRSR cells
    # ("20,494.8" -> "204948 , ."). The cell grid is right, so read each cell's text
    # with the normal extractor clipped to the cell rectangle. None = merged-away cell.
    return [
        [clean_cell(page.get_text("text", clip=cell)) if cell else "" for cell in row.cells]
        for row in table.rows
    ]


def parse(path: Path) -> ParsedDoc:
    out = ParsedDoc(parser=NAME, parser_version=version())
    with pymupdf.open(path) as doc:
        for page_no, page in enumerate(doc, start=1):
            out.pages.append(PageRecord(page_no, page.get_text()))
            # Default "lines" strategy: BRSR tables are ruled, so cell borders define the grid.
            for idx, table in enumerate(page.find_tables().tables):
                out.tables.append(TableRecord(page_no, idx, _table_rows(page, table)))
    return out
