import json
from datetime import date
from pathlib import Path

import pytest
from conftest import TABLE, write_sample_pdf

from brsr.ingest.manifest import ManifestRow, sha256_file
from brsr.parse import pdf_pymupdf
from brsr.parse.records import clean_cell, devanagari_ratio, table_markdown
from brsr.parse.silver import parse_filings
from brsr.storage.delta import query

# --- records -----------------------------------------------------------------


def test_clean_cell() -> None:
    assert clean_cell(None) == ""
    assert clean_cell("  Total\nScope 1 \t emissions ") == "Total Scope 1 emissions"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", 0.0), ("1,234 ₹", 0.0), ("Energy", 0.0), ("ऊर्जा", 1.0), ("ab कख", 0.5)],
)
def test_devanagari_ratio(text: str, expected: float) -> None:
    assert devanagari_ratio(text) == pytest.approx(expected)


def test_table_markdown_pads_ragged_rows_and_escapes_pipes() -> None:
    md = table_markdown([["a", "b"], ["x|y"]])
    assert md.splitlines() == ["| a | b |", "| --- | --- |", "| x\\|y |  |"]


# --- pymupdf parser ------------------------------------------------------------


def test_pymupdf_pages_are_one_based(sample_pdf: Path) -> None:
    doc = pdf_pymupdf.parse(sample_pdf)
    assert [p.page_no for p in doc.pages] == [1, 2]
    assert "SECTION A" in doc.pages[0].text


def test_pymupdf_extracts_ruled_table_intact(sample_pdf: Path) -> None:
    doc = pdf_pymupdf.parse(sample_pdf)
    assert len(doc.tables) == 1
    t = doc.tables[0]
    assert (t.page_no, t.table_idx) == (2, 0)
    assert t.rows == TABLE


# --- silver writer -------------------------------------------------------------


def manifest_row(bronze: Path, name: str = "tcs_2024-25.pdf") -> ManifestRow:
    path = bronze / "filings" / name
    return ManifestRow(
        company_id="TCS",
        company_name="Tata Consultancy Services Limited",
        sector="IT",
        fy="2024-25",
        doc_type="pdf",
        file_path=f"filings/{name}",
        source_url="https://example.com/x.pdf",
        sha256=sha256_file(path) if path.exists() else "",
        downloaded_on=date(2026, 11, 14),
    )


def run(bronze: Path, silver: Path, rows: list[ManifestRow], force: bool = False):
    return parse_filings(
        rows,
        bronze,
        silver,
        pdf_pymupdf.parse,
        pdf_pymupdf.NAME,
        pdf_pymupdf.version(),
        force,
        log=lambda _: None,
    )


@pytest.fixture
def bronze(tmp_path: Path) -> Path:
    (tmp_path / "bronze" / "filings").mkdir(parents=True)
    write_sample_pdf(tmp_path / "bronze" / "filings" / "tcs_2024-25.pdf")
    return tmp_path / "bronze"


def test_parse_writes_pages_tables_and_run(bronze: Path, tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    report = run(bronze, silver, [manifest_row(bronze)])
    assert report.parsed == ["TCS 2024-25"]
    pages = query("SELECT page_no, n_chars FROM p ORDER BY page_no", p=silver / "pages")
    assert pages["page_no"].to_pylist() == [1, 2]
    tables = query("SELECT page_no, n_rows, n_cols, cells_json FROM t", t=silver / "tables")
    assert tables.to_pylist()[0]["n_rows"] == 3
    assert json.loads(tables["cells_json"][0].as_py()) == TABLE
    runs = query("SELECT n_pages, n_tables FROM r", r=silver / "parse_runs").to_pylist()
    assert runs == [{"n_pages": 2, "n_tables": 1}]


def test_second_run_is_skipped_and_force_does_not_duplicate(bronze: Path, tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    rows = [manifest_row(bronze)]
    run(bronze, silver, rows)
    assert run(bronze, silver, rows).skipped == ["TCS 2024-25"]
    assert run(bronze, silver, rows, force=True).parsed == ["TCS 2024-25"]
    n = query("SELECT count(*) AS n FROM p", p=silver / "pages")["n"][0].as_py()
    assert n == 2


def test_missing_and_changed_files_are_listed_not_fatal(bronze: Path, tmp_path: Path) -> None:
    ok = manifest_row(bronze)
    missing = manifest_row(bronze, "absent.pdf")
    changed = manifest_row(bronze).model_copy(update={"sha256": "0" * 64, "fy": "2025-26"})
    report = run(bronze, tmp_path / "silver", [missing, changed, ok])
    assert report.parsed == ["TCS 2024-25"]
    assert report.missing == ["TCS 2024-25: filings/absent.pdf"]
    assert report.changed == ["TCS 2025-26: filings/tcs_2024-25.pdf"]


def test_done_is_called_once_per_row_whatever_the_outcome(bronze: Path, tmp_path: Path) -> None:
    ok = manifest_row(bronze)
    missing = manifest_row(bronze, "absent.pdf")
    seen: list[str] = []
    silver = tmp_path / "silver"
    for _ in range(2):  # second pass: `ok` is skipped as already parsed
        parse_filings(
            [missing, ok],
            bronze,
            silver,
            pdf_pymupdf.parse,
            pdf_pymupdf.NAME,
            pdf_pymupdf.version(),
            log=lambda _: None,
            done=lambda r: seen.append(r.file_path),
        )
    assert seen == ["filings/absent.pdf", "filings/tcs_2024-25.pdf"] * 2
