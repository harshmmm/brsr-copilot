# Build log

What has been built, milestone by milestone, with every decision and the reason for it.
Full reasoning and measurements for each decision are in [decisions.md](decisions.md) (D001…);
ideas and open questions are in [next.md](next.md). Update this file at the end of each step.

**Status (2026-11-24):** M0 and M1 done. Next: M2 plan.

| Milestone | Scope | Status |
|---|---|---|
| M0 | Scaffold, filing manifest, CI, corpus | ✅ Done |
| M1 | PDF parsing → silver, parser comparison | ✅ Done |
| M2 | XBRL → `xbrl_facts`; LLM extraction → gold, with cache | ⏳ |
| M3 | Extraction evaluation against XBRL | ⏳ |
| M4 | Chunking, embeddings, hybrid search, reranking, citations | ⏳ |
| M5 | Q&A test set, router, retrieval and answer evaluation | ⏳ |
| M6 | Streamlit UI, README, demo video | ⏳ |

---

## M0 — Scaffold, manifest, corpus (2026-11-13 → 14)

### Built
- **Project skeleton**: `uv` project (Python 3.12), Typer CLI `brsr`, ruff (line length 100;
  rules E, F, I, UP, B), pytest, GitHub Actions CI (`uv sync --locked`, ruff check, ruff format
  --check, pytest). `.env.example` for `GEMINI_API_KEY`; `.gitattributes` forces LF endings.
- **Filing manifest** `data/bronze/manifest.csv` — one row per file: company_id, company_cin,
  name, sector, fy, doc_type (pdf/xbrl), file path, source URL, sha256, download date.
- **`src/brsr/ingest/manifest.py`** — Pydantic `ManifestRow` validates every row;
  `check_manifest` reports duplicates, missing files, missing or mismatched sha256 and files on
  disk that the manifest doesn't list; `fill_hashes` fills empty hashes but never overwrites one.
- **`brsr ingest --check / --fill-hashes`.**
- **Corpus**: 12 companies × FY 2024-25 and FY 2025-26 = 24 PDFs + 24 XBRL. IT: TCS, Infosys,
  Tech Mahindra, Persistent, LTM (formerly LTIMindtree), Coforge. Banks: SBI, Axis, Federal,
  IndusInd, Bank of Baroda, Indian Bank. `brsr ingest --check` → "Manifest OK: 48 file(s)".

### Decisions
| ID | Decision | Reason |
|---|---|---|
| D001 | Commit the manifest (URL + sha256), not the filings | Repo stays small; corpus is rebuildable; sha256 makes a silently changed file fail the check instead of shifting eval results |
| D002 | Key companies by NSE symbol; CIN optional | Nationalised banks have no CIN, and bank XBRL holds placeholder CINs, so a CIN join would silently mismatch. Caveat: symbols change on renames (LTIM → LTM); we use the current symbol |
| D003 | Target FY 2024-25 and FY 2025-26 (brief said 23-24 / 24-25) | FY26 BRSRs were filed by Nov 2026; analysts ask about the latest year first. Boundaries recorded: 5 IT companies consolidated; Coforge and all banks standalone |
| D004 | Keep LTM FY25 Inline XBRL (`.html`) as downloaded | Bronze is raw and its sha256 must match the source; converting is parsing, which belongs in silver where it can be tested |

### Problems and how they were handled
- Wrong files received and excluded: a Fedbank Financial Services BRSR (not Federal Bank), annual-
  report XBRL (`in-ci-ent`, not BRSR), an out-of-scope FY24 file, a one-page SBI stub.
- LTM FY25 XBRL isn't on NSE under the new symbol → used BSE's Inline XBRL (D004).
- NSE blocks scripted downloads; filings were downloaded by hand rather than working around it.

---

## M1 — PDF parsing to silver + parser comparison (2026-11-16 → 24)

Plan approved with three conditions: pin pyarrow and record why; compare on TCS FY25, Axis FY26
and Bank of Baroda FY25 (stop if any XBRL is missing; report Bank of Baroda separately); in the
full run, parse only PDFs present on disk and list missing ones instead of failing.

### Step 1 — Dependencies and storage helpers
- Added deltalake, duckdb, pymupdf, docling and `pyarrow==26.0.1`.
- **`src/brsr/storage/delta.py`**: `replace_partition` overwrites one partition with a predicate
  (creates the table on first write) — this is what makes every stage idempotent; `query` runs
  DuckDB SQL over Delta tables via Arrow datasets.
- **D005 — pin pyarrow exactly.** We build Arrow tables ourselves and DuckDB reads Delta back
  through Arrow, so it's a direct dependency. An unpinned upgrade can change the Arrow → Delta
  type mapping (`string` / `large_string` / `string_view`) and break overwrites with a schema
  mismatch.

### Step 2 — PyMuPDF parser, silver tables, `brsr parse`
- **`parse/records.py`**: parser-neutral `PageRecord`, `TableRecord`, `ParsedDoc`, so both
  parsers write the same silver schema. Each page gets a `devanagari_ratio` (share of Hindi
  letters) to spot bilingual pages later.
- **`parse/pdf_pymupdf.py`**: page text plus `find_tables` (ruling-line strategy).
- **`parse/silver.py`**: three Delta tables partitioned by company_id / fy / parser —
  `pages`, `tables` (cells as JSON plus markdown), `parse_runs` (pages, tables, seconds,
  timestamp). Explicit Arrow schemas. A filing is skipped when the same sha256 + parser_version
  is already in `parse_runs`; `parse_runs` is written last, so a crash mid-filing leaves it
  "not parsed" and it is redone next time.
- **`brsr parse --parser --company --fy --force`**: missing files and files whose hash changed
  are listed, not fatal.
- Finding: PyMuPDF's `Table.extract()` garbles BRSR cells ("20,494.8" → "204948 , ."). Fixed
  by reading each cell's text with `page.get_text(clip=cell)`; the version string carries
  `-cellclip` so output from the old method can't be mistaken for the new.

### Step 3 — Docling parser
- **`parse/pdf_docling.py`**: Docling with OCR off (the PDFs are digital) and TableFormer in
  ACCURATE mode. The converter is built once per process; `warmup()` loads the models before
  timing so per-filing seconds measure parsing only. The options are part of `parser_version`,
  so changing them invalidates silver output.

### Step 4 — Comparison (report: `eval/reports/parser_compare_20261116-192521.md`)
- **`parse/numbers.py`**: reads numbers as filings print them — Indian (1,53,74,95,415) and
  Western grouping; a printed value matches XBRL if equal after rounding XBRL to the printed
  decimals; zero may be printed as Nil, -, NA or 0. Unit-tested.
- **`eval/run_parser_compare.py`**: scores both parsers against each filing's own XBRL on
  (a) recall of XBRL values in the parsed text, (b) Principle 6 energy/emissions rows kept
  intact (label, current year, previous year in separate cells, in order), (c) seconds per
  filing. Stops if any XBRL file is missing or a filing hasn't been parsed by both parsers.

| | Recall | Rows intact | s/filing |
|---|---|---|---|
| TCS + Axis, PyMuPDF | 75/78 (96%) | 10/19 (53%) | 32 |
| TCS + Axis, Docling | 75/78 (96%) | 17/19 (89%) | 290 |
| Bank of Baroda, PyMuPDF | 27/29 (93%) | 6/8 (75%) | 87 |
| Bank of Baroda, Docling | 27/29 (93%) | 6/8 (75%) | 835 |

- Every miss shared by both parsers was checked by hand and is a PDF/XBRL disagreement, not a
  parse error (TCS total off by 1; two Bank of Baroda values off by 0.01; Axis never prints its
  Scope 1 total). Logged in `next.md`.
- The real difference is Axis: its tables have almost no ruling lines, so PyMuPDF merges cells
  (1/8 rows intact) while Docling gets 8/8.
- **D006 — use Docling.** Row integrity is what extraction depends on, and PyMuPDF fails
  silently. Docling costs ~9× the CPU time, but parsing happens once per file version thanks to
  the sha256 + parser_version skip. A PyMuPDF-with-Docling-fallback hybrid is in `next.md`.

### Step 5 — Full corpus parse
- `brsr parse --parser docling` over the 24 manifest PDFs. No files missing or changed. The 3
  comparison filings were already parsed with the same parser version and were skipped.
- **Result:** 24 filings, 1,688 pages, 2,812 tables in silver; 2.08 h of parsing (4.44 s/page;
  model loading excluded). Slowest: SBI FY26 (168 pages, 670 s).
- **Checks:** no duplicate pages or tables; a second run reports "Parsed 0, already up to date
  24" (idempotent); 332 pages are mostly Hindi (devanagari_ratio > 0.3) and 29 pages are nearly
  empty (< 50 characters, e.g. cover or image pages).
- **Docling warnings to watch in M2:** 4 table structures discarded at the decode limit (text
  kept as a single cell) and 84 warnings about cells that fit no row or column and were dropped.
  Extraction keeps `source_page`, so any wrong value can be traced back to its page.

### Other problems fixed in M1
- Ruff B008 on Typer defaults → `Annotated[...]` options.
- DuckDB 2.0 renamed `fetch_arrow_table` → `to_arrow_table`.
- `cell_has_value` matched zero in cells with no numbers at all → now requires a numeric token;
  test added.
- Windows console (cp1252) couldn't print "≥" → eval script reconfigures stdout to UTF-8.

---

## Test and lint status
64 tests pass; `ruff check` and `ruff format --check` are clean (end of M1).
