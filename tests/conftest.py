from pathlib import Path

import pymupdf
import pytest

TABLE = [
    ["Parameter", "FY 2025", "FY 2024"],
    ["Total Scope 1 emissions", "20,494.8", "21,949.0"],
    ["Total Scope 2 emissions", "55,599.0", "73,722.0"],
]


def write_sample_pdf(path: Path) -> Path:
    """Two pages: plain text on page 1, a ruled 3x3 table on page 2."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "SECTION A: GENERAL DISCLOSURES")
    page = doc.new_page()
    x0, y0, col_w, row_h = 72, 100, 160, 24
    for r, row in enumerate(TABLE):
        for c, text in enumerate(row):
            rect = pymupdf.Rect(
                x0 + c * col_w, y0 + r * row_h, x0 + (c + 1) * col_w, y0 + (r + 1) * row_h
            )
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y1 - 8), text, fontsize=9)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return write_sample_pdf(tmp_path / "sample.pdf")
