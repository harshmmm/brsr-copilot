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

## Development

```sh
uv run pytest
uv run ruff check . && uv run ruff format .
```
