"""Delta Lake helpers: partition-replacing writes, and DuckDB queries over Delta tables."""

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable, write_deltalake


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def table_exists(path: Path) -> bool:
    return DeltaTable.is_deltatable(str(path))


def replace_partition(path: Path, data: pa.Table, partition: dict[str, str]) -> None:
    """Make `data` the complete contents of one partition, leaving other partitions alone.

    `partition` maps partition columns to values, e.g. {"company_id": "TCS", "fy": "2024-25"}.
    Rows that previously matched are deleted, so re-running a stage never duplicates rows.
    An empty `data` simply clears the partition.
    """
    for col, val in partition.items():
        if data.num_rows and not pc.all(pc.equal(data[col], val)).as_py():
            raise ValueError(f"every row must have {col} == {val!r}")

    if table_exists(path):
        predicate = " AND ".join(f"{c} = {_sql_literal(v)}" for c, v in partition.items())
        write_deltalake(str(path), data, mode="overwrite", predicate=predicate)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_deltalake(str(path), data, partition_by=list(partition))


def query(sql: str, **tables: Path) -> pa.Table:
    """Run DuckDB SQL where each keyword argument names a Delta table, e.g. pages=Path(...)."""
    con = duckdb.connect()
    for name, path in tables.items():
        con.register(name, DeltaTable(str(path)).to_pyarrow_dataset())
    return con.sql(sql).to_arrow_table()
