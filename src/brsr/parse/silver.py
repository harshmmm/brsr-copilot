"""Write parsed PDFs to the silver Delta tables: pages, tables and parse_runs."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa

from brsr.ingest.manifest import ManifestRow, sha256_file
from brsr.parse.records import ParsedDoc, devanagari_ratio, table_markdown
from brsr.storage.delta import query, replace_partition, table_exists

PARTITION = ("company_id", "fy", "parser")

# Explicit schemas so the Delta schema never depends on type inference (see D005).
_KEYS = [
    ("company_id", pa.string()),
    ("fy", pa.string()),
    ("parser", pa.string()),
    ("parser_version", pa.string()),
    ("file_sha256", pa.string()),
]
PAGES_SCHEMA = pa.schema(
    [
        *_KEYS,
        ("page_no", pa.int32()),
        ("text", pa.string()),
        ("n_chars", pa.int32()),
        ("devanagari_ratio", pa.float32()),
    ]
)
TABLES_SCHEMA = pa.schema(
    [
        *_KEYS,
        ("page_no", pa.int32()),
        ("table_idx", pa.int32()),
        ("n_rows", pa.int32()),
        ("n_cols", pa.int32()),
        ("cells_json", pa.string()),
        ("markdown", pa.string()),
    ]
)
RUNS_SCHEMA = pa.schema(
    [
        *_KEYS,
        ("n_pages", pa.int32()),
        ("n_tables", pa.int32()),
        ("seconds", pa.float64()),
        ("parsed_at", pa.timestamp("us", tz="UTC")),
    ]
)


@dataclass(frozen=True)
class Filing:
    company_id: str
    fy: str
    file_sha256: str


def _keys(f: Filing, doc: ParsedDoc, n: int) -> dict[str, list[str]]:
    return {
        "company_id": [f.company_id] * n,
        "fy": [f.fy] * n,
        "parser": [doc.parser] * n,
        "parser_version": [doc.parser_version] * n,
        "file_sha256": [f.file_sha256] * n,
    }


def pages_table(f: Filing, doc: ParsedDoc) -> pa.Table:
    p = doc.pages
    return pa.table(
        {
            **_keys(f, doc, len(p)),
            "page_no": [r.page_no for r in p],
            "text": [r.text for r in p],
            "n_chars": [len(r.text) for r in p],
            "devanagari_ratio": [devanagari_ratio(r.text) for r in p],
        },
        schema=PAGES_SCHEMA,
    )


def tables_table(f: Filing, doc: ParsedDoc) -> pa.Table:
    t = doc.tables
    return pa.table(
        {
            **_keys(f, doc, len(t)),
            "page_no": [r.page_no for r in t],
            "table_idx": [r.table_idx for r in t],
            "n_rows": [len(r.rows) for r in t],
            "n_cols": [max((len(row) for row in r.rows), default=0) for r in t],
            "cells_json": [json.dumps(r.rows, ensure_ascii=False) for r in t],
            "markdown": [table_markdown(r.rows) for r in t],
        },
        schema=TABLES_SCHEMA,
    )


def runs_table(f: Filing, doc: ParsedDoc, seconds: float) -> pa.Table:
    return pa.table(
        {
            **_keys(f, doc, 1),
            "n_pages": [len(doc.pages)],
            "n_tables": [len(doc.tables)],
            "seconds": [seconds],
            "parsed_at": [datetime.now(UTC)],
        },
        schema=RUNS_SCHEMA,
    )


def already_parsed(silver: Path, f: Filing, parser: str, parser_version: str) -> bool:
    """True if this exact file was parsed by this exact parser version."""
    runs = silver / "parse_runs"
    if not table_exists(runs):
        return False
    # parse_runs holds one row per (filing, parser), so comparing in Python is cheap.
    t = query("SELECT company_id, fy, parser, parser_version, file_sha256 FROM r", r=runs)
    wanted = {
        "company_id": f.company_id,
        "fy": f.fy,
        "parser": parser,
        "parser_version": parser_version,
        "file_sha256": f.file_sha256,
    }
    return any(row == wanted for row in t.to_pylist())


def write_filing(silver: Path, f: Filing, doc: ParsedDoc, seconds: float) -> None:
    part = {"company_id": f.company_id, "fy": f.fy, "parser": doc.parser}
    replace_partition(silver / "pages", pages_table(f, doc), part)
    replace_partition(silver / "tables", tables_table(f, doc), part)
    # Written last: a parse_runs row means pages and tables for this run are complete.
    replace_partition(silver / "parse_runs", runs_table(f, doc, seconds), part)


@dataclass
class ParseReport:
    parsed: list[str]
    skipped: list[str]
    missing: list[str]
    changed: list[str]


def parse_filings(
    rows: list[ManifestRow],
    bronze: Path,
    silver: Path,
    parse_fn: Callable[[Path], ParsedDoc],
    parser: str,
    parser_version: str,
    force: bool = False,
    log: Callable[[str], None] = print,
    done: Callable[[ManifestRow], None] = lambda row: None,
) -> ParseReport:
    """Parse every PDF row whose file is present and unchanged; report the rest.

    `done(row)` is called once per row, whatever happened to it (for progress display).
    """
    report = ParseReport([], [], [], [])
    for row in rows:
        _parse_one(row, bronze, silver, parse_fn, parser, parser_version, force, log, report)
        done(row)
    return report


def _parse_one(
    row: ManifestRow,
    bronze: Path,
    silver: Path,
    parse_fn: Callable[[Path], ParsedDoc],
    parser: str,
    parser_version: str,
    force: bool,
    log: Callable[[str], None],
    report: ParseReport,
) -> None:
    label = f"{row.company_id} {row.fy}"
    path = bronze / row.file_path
    if not path.is_file():
        report.missing.append(f"{label}: {row.file_path}")
        return
    sha = sha256_file(path)
    if sha != row.sha256:
        report.changed.append(f"{label}: {row.file_path}")
        return
    f = Filing(row.company_id, row.fy, sha)
    if not force and already_parsed(silver, f, parser, parser_version):
        report.skipped.append(label)
        return
    start = time.perf_counter()
    doc = parse_fn(path)
    seconds = time.perf_counter() - start
    write_filing(silver, f, doc, seconds)
    log(f"  {label}: {len(doc.pages)} pages, {len(doc.tables)} tables, {seconds:.1f}s")
    report.parsed.append(label)
