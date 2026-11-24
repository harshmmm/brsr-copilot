# CLAUDE.md — brsr-copilot

Context for Claude Code. Read `docs/brief.md` first: it has the problem, scope, metrics and milestones.

## What this is
A local, free-to-run copilot over SEBI BRSR sustainability filings (IT and banking companies, FY 2024-25 and 2025-26):
PDF and XBRL → bronze/silver/gold Delta tables → LLM extraction of ~25 metrics, each with its source page → hybrid RAG with citations → a router that sends questions to SQL, RAG or both → Streamlit UI. Every stage has an evaluation.

This is a **portfolio project for Data+AI engineering interviews**. Code quality, measured results and clearly recorded decisions matter more than feature count.

## Constraints
- Runs on a laptop CPU. No GPU, no paid APIs, no Docker requirement.
- Default LLM: Gemini free tier via `google-genai`. Every LLM call goes through `src/brsr/llm/client.py`.
- Ask before adding a dependency that isn't listed in the brief's stack.

## Layout (target)
```
src/brsr/
  ingest/       # manifest, PDF + XBRL loading → bronze
  parse/        # pages, tables, chunks → silver; xbrl_facts
  extract/      # schema.py (Pydantic), prompts/, extractor.py, units.py → gold
  retrieve/     # embed, bm25, hybrid (RRF), rerank
  answer/       # router, text2sql, rag, compose (citations)
  llm/          # client.py (provider abstraction, cache, retry, token/latency log)
  storage/      # delta + duckdb helpers
app/            # streamlit_app.py
eval/           # gold_labels/, qa_set.jsonl, routing_set.jsonl, run_*.py, reports/
data/           # bronze/ silver/ gold/  (gitignored)
docs/           # brief.md, decisions.md, next.md
tests/
```

## Commands (once set up)
- On Harsh's laptop `uv` isn't on PATH: use `python -m uv …` in place of `uv …`.
- `uv sync` · `uv run pytest` · `uv run ruff check . && uv run ruff format .`
- `uv run brsr ingest|parse|extract|index` — pipeline stages (Typer CLI); parse with `--parser docling` (D006)
- `uv run python eval/run_extraction.py` · `eval/run_retrieval.py` · `eval/run_router.py`
- `uv run streamlit run app/streamlit_app.py`

## How to work with me (Harsh)
1. **One milestone at a time** (M0–M6 in the brief). Before writing code, propose a short plan for that milestone and wait for my OK.
2. Don't build things I haven't asked for. Put ideas in `docs/next.md` instead.
3. When we make a design choice, add an entry to `docs/decisions.md`: the context, the options, what we chose and why. Include measured numbers whenever we compared options.
4. Keep changes small and reviewable. Run tests and ruff before saying a task is done.
5. Explain non-obvious code in your reply, not in long comments. I want to be able to defend every line in an interview.
6. At the end of each step, update `docs/build_log.md` (what was built, decisions with reasons, problems, results) and any other doc the step makes stale.

## Engineering rules
- **The LLM extracts; code decides.** The LLM returns `value_raw`, `unit_raw` and `source_page`. Unit conversion and derived values (intensities, percentages) happen in `units.py` with unit tests.
- **Every gold value has a `source_page`.** No page, no row.
- **Validate all LLM output with Pydantic.** On failure, retry once with the validation error included in the prompt, then log the failure and move on.
- **Cache LLM responses** keyed by (file hash, section, prompt_version, model). Re-running the pipeline must make zero new calls.
- **Version prompts** as files in `extract/prompts/` with a `prompt_version` constant; store the version on every gold row.
- **Make every stage idempotent:** re-running a stage overwrites its own output partition and never duplicates rows.
- **Never edit `eval/gold_labels/` or test sets to make a score go up.** If a label is wrong, fix it in a separate commit with a reason.
- **Store evaluation reports** under `eval/reports/` with a timestamp, and put the latest summary in the README.
- No secrets in code. Use `.env` (gitignored) and keep `.env.example` up to date.
- **Long-running commands show a terminal progress bar with ETA** (`typer.progressbar`, weighted by the real unit of work, e.g. pages).
- Type hints everywhere; small pure functions; pytest for parsers, units, router and the cache.

## Data notes
- BRSR is filed with the exchanges in **both PDF and XBRL**. XBRL facts are the answer key for evaluating extraction, not an input to it.
- Watch for: GJ vs MWh vs kWh, kL vs m³, ₹ lakh vs crore, standalone vs consolidated boundaries, "NA" or "Nil" vs 0, and figures split across pages.
- Filings are downloaded by hand; `data/bronze/manifest.csv` is the source of truth for what's in the corpus.
