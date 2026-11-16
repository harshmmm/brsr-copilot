"""Docling parser: layout model + TableFormer table structure, OCR off (the PDFs are digital)."""

from functools import cache
from importlib.metadata import version as pkg_version
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from brsr.parse.records import PageRecord, ParsedDoc, TableRecord, clean_cell

NAME = "docling"


def version() -> str:
    # Options are part of the version: changing them must invalidate cached silver output.
    return f"docling-{pkg_version('docling')}-noocr-tableformer-accurate"


@cache
def _converter() -> DocumentConverter:
    # Loading the models takes seconds, so build the converter once per process.
    opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    pdf = PdfFormatOption(pipeline_options=opts)
    return DocumentConverter(format_options={InputFormat.PDF: pdf})


def warmup() -> None:
    """Load the models up front so per-filing timings measure parsing, not model loading."""
    _converter()


def parse(path: Path) -> ParsedDoc:
    doc = _converter().convert(path).document
    out = ParsedDoc(parser=NAME, parser_version=version())
    for page_no in sorted(doc.pages):
        out.pages.append(PageRecord(page_no, doc.export_to_markdown(page_no=page_no)))

    per_page: dict[int, int] = {}
    for table in doc.tables:
        page_no = table.prov[0].page_no if table.prov else 0  # first page if it spans several
        idx = per_page.get(page_no, 0)
        per_page[page_no] = idx + 1
        rows = [[clean_cell(cell.text) for cell in row] for row in table.data.grid]
        out.tables.append(TableRecord(page_no, idx, rows))
    return out
