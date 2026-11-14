from pathlib import Path

import pytest

from brsr.ingest.manifest import (
    COLUMNS,
    check_manifest,
    fill_hashes,
    read_manifest,
    sha256_file,
)

CIN = "L85110KA1981PLC013115"
URL = "https://example.com/brsr.pdf"


def make_row(**overrides: str) -> dict[str, str]:
    row = {
        "company_id": "INFY",
        "company_cin": CIN,
        "company_name": "Infosys Limited",
        "sector": "IT",
        "fy": "2024-25",
        "doc_type": "pdf",
        "file_path": "filings/infosys_2024-25.pdf",
        "source_url": URL,
        "sha256": "",
        "downloaded_on": "2026-11-14",
    }
    row.update(overrides)
    return row


def write_manifest(bronze: Path, rows: list[dict[str, str]]) -> Path:
    path = bronze / "manifest.csv"
    lines = [",".join(COLUMNS)] + [",".join(r[c] for c in COLUMNS) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def add_file(bronze: Path, rel: str, content: bytes = b"%PDF-1.7 test") -> Path:
    path = bronze / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def bronze(tmp_path: Path) -> Path:
    (tmp_path / "filings").mkdir()
    (tmp_path / "xbrl").mkdir()
    return tmp_path


def test_valid_manifest_passes(bronze: Path) -> None:
    f = add_file(bronze, "filings/infosys_2024-25.pdf")
    m = write_manifest(bronze, [make_row(sha256=sha256_file(f))])
    rows, problems = read_manifest(m)
    assert problems == []
    assert check_manifest(rows, bronze) == []


def test_empty_manifest_with_no_files_passes(bronze: Path) -> None:
    rows, problems = read_manifest(write_manifest(bronze, []))
    assert (rows, problems) == ([], [])
    assert check_manifest(rows, bronze) == []


def test_wrong_header_is_rejected(bronze: Path) -> None:
    m = bronze / "manifest.csv"
    m.write_text("cin,name\n", encoding="utf-8")
    _, problems = read_manifest(m)
    assert len(problems) == 1 and "header" in problems[0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company_id", ""),
        ("company_id", "infy"),  # NSE symbols are upper case
        ("company_cin", "L85110KA1981"),  # too short
        ("sector", "PHARMA"),
        ("fy", "2024-2025"),
        ("fy", "2024-26"),  # not consecutive
        ("doc_type", "html"),
        ("source_url", "nseindia.com/file.pdf"),
        ("sha256", "abc"),
        ("downloaded_on", "14/11/2026"),
        ("file_path", "filings/infosys_2024-25.xml"),  # extension doesn't match pdf
    ],
)
def test_invalid_fields_are_reported_with_line_number(bronze: Path, field: str, value: str) -> None:
    m = write_manifest(bronze, [make_row(), make_row(**{field: value})])
    rows, problems = read_manifest(m)
    assert len(rows) == 1
    assert problems and all(p.startswith("line 3:") for p in problems)


def test_empty_cin_is_allowed_for_nationalised_banks(bronze: Path) -> None:
    row = make_row(company_id="BANKBARODA", company_cin="", sector="BANK")
    rows, problems = read_manifest(write_manifest(bronze, [row]))
    assert problems == [] and rows[0].company_cin == ""


@pytest.mark.parametrize("path", ["xbrl/ltm_2024-25.xml", "xbrl/ltm_2024-25.html"])
def test_xbrl_accepts_plain_and_inline(bronze: Path, path: str) -> None:
    row = make_row(doc_type="xbrl", file_path=path)
    rows, problems = read_manifest(write_manifest(bronze, [row]))
    assert problems == [] and len(rows) == 1


def test_pdf_rejects_html(bronze: Path) -> None:
    _, problems = read_manifest(write_manifest(bronze, [make_row(file_path="filings/x.html")]))
    assert len(problems) == 1 and ".pdf" in problems[0]


def test_missing_file(bronze: Path) -> None:
    rows, _ = read_manifest(write_manifest(bronze, [make_row()]))
    assert check_manifest(rows, bronze) == ["missing file: filings/infosys_2024-25.pdf"]


def test_missing_hash(bronze: Path) -> None:
    add_file(bronze, "filings/infosys_2024-25.pdf")
    rows, _ = read_manifest(write_manifest(bronze, [make_row()]))
    assert check_manifest(rows, bronze)[0].startswith("no sha256")


def test_hash_mismatch(bronze: Path) -> None:
    f = add_file(bronze, "filings/infosys_2024-25.pdf")
    rows, _ = read_manifest(write_manifest(bronze, [make_row(sha256=sha256_file(f))]))
    f.write_bytes(b"changed")
    assert check_manifest(rows, bronze)[0].startswith("sha256 mismatch")


def test_unlisted_file_is_reported(bronze: Path) -> None:
    add_file(bronze, "xbrl/tcs_2024-25.xml")
    rows, _ = read_manifest(write_manifest(bronze, []))
    assert check_manifest(rows, bronze) == ["file not in manifest: xbrl/tcs_2024-25.xml"]


def test_duplicate_company_year_type(bronze: Path) -> None:
    a = add_file(bronze, "filings/a.pdf")
    b = add_file(bronze, "filings/b.pdf", b"other")
    rows, _ = read_manifest(
        write_manifest(
            bronze,
            [
                make_row(file_path="filings/a.pdf", sha256=sha256_file(a)),
                make_row(file_path="filings/b.pdf", sha256=sha256_file(b)),
            ],
        )
    )
    problems = check_manifest(rows, bronze)
    assert len(problems) == 1 and problems[0].startswith("duplicate")


def test_fill_hashes_fills_only_empty_and_existing(bronze: Path) -> None:
    f = add_file(bronze, "filings/infosys_2024-25.pdf")
    stale = "0" * 64
    m = write_manifest(
        bronze,
        [
            make_row(),  # file exists, no hash -> filled
            make_row(fy="2023-24", file_path="filings/missing.pdf"),  # no file -> left empty
            make_row(doc_type="xbrl", file_path="xbrl/x.xml", sha256=stale),  # kept as is
        ],
    )
    assert fill_hashes(m, bronze) == 1
    rows, problems = read_manifest(m)
    assert problems == []
    assert [r.sha256 for r in rows] == [sha256_file(f), "", stale]
