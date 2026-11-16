from pathlib import Path

import pyarrow as pa
import pytest

from brsr.storage.delta import query, replace_partition, table_exists


def rows(company: str, n: int) -> pa.Table:
    return pa.table(
        {
            "company_id": [company] * n,
            "fy": ["2024-25"] * n,
            "page_no": list(range(1, n + 1)),
        }
    )


PART = ["company_id", "fy"]


def part(company: str) -> dict[str, str]:
    return {"company_id": company, "fy": "2024-25"}


def count(path: Path) -> dict[str, int]:
    t = query("SELECT company_id, count(*) AS n FROM t GROUP BY 1 ORDER BY 1", t=path)
    return dict(zip(t["company_id"].to_pylist(), t["n"].to_pylist(), strict=True))


def test_rewrite_same_partition_does_not_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "pages"
    replace_partition(path, rows("TCS", 3), part("TCS"))
    replace_partition(path, rows("TCS", 3), part("TCS"))
    assert table_exists(path)
    assert count(path) == {"TCS": 3}


def test_replacing_one_partition_leaves_others(tmp_path: Path) -> None:
    path = tmp_path / "pages"
    replace_partition(path, rows("TCS", 3), part("TCS"))
    replace_partition(path, rows("INFY", 2), part("INFY"))
    replace_partition(path, rows("TCS", 5), part("TCS"))
    assert count(path) == {"INFY": 2, "TCS": 5}


def test_empty_data_clears_partition(tmp_path: Path) -> None:
    path = tmp_path / "pages"
    replace_partition(path, rows("TCS", 3), part("TCS"))
    replace_partition(path, rows("INFY", 2), part("INFY"))
    replace_partition(path, rows("TCS", 0), part("TCS"))
    assert count(path) == {"INFY": 2}


def test_rows_outside_partition_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="company_id"):
        replace_partition(tmp_path / "pages", rows("INFY", 1), part("TCS"))
