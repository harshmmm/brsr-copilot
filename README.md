# brsr-copilot

A local copilot over SEBI BRSR sustainability filings: PDF and XBRL → bronze/silver/gold Delta tables → LLM extraction with source pages → cited Q&A. See [docs/brief.md](docs/brief.md).

## Setup

```sh
uv sync
cp .env.example .env   # add your GEMINI_API_KEY
```

## Adding filings

1. Save PDFs to `data/bronze/filings/` and XBRL files to `data/bronze/xbrl/`.
2. Add one row per file to `data/bronze/manifest.csv` (leave `sha256` empty).
3. `uv run brsr ingest --fill-hashes --check`

## Pipeline

```sh
uv run brsr parse --parser docling   # PDFs -> data/silver/{pages,tables,parse_runs}
```

## Latest evaluation

**PDF parser comparison** (2026-11-16, [report](eval/reports/parser_compare_20261116-192521.md), decision [D006](docs/decisions.md)): scored against each filing's own XBRL.

| | XBRL values found | P6 table rows intact | s/filing |
|---|---|---|---|
| TCS + Axis, PyMuPDF | 75/78 (96%) | 10/19 (53%) | 32 |
| TCS + Axis, **Docling** | 75/78 (96%) | **17/19 (89%)** | 290 |
| Bank of Baroda, PyMuPDF | 27/29 (93%) | 6/8 (75%) | 87 |
| Bank of Baroda, Docling | 27/29 (93%) | 6/8 (75%) | 835 |

All misses shared by both parsers are PDF/XBRL disagreements, verified by hand. Full corpus parsed with Docling: 24 filings, 1,688 pages, 2,812 tables, 2.1 h on a laptop CPU.

Build history and every decision: [docs/build_log.md](docs/build_log.md).

## Development

```sh
uv run pytest
uv run ruff check . && uv run ruff format .
```
