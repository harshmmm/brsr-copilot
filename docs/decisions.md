# Decisions

One entry per design choice: context, options, choice, and why. Include measured numbers when options were compared.

---

## D001 — Version the manifest, not the filings (M0, 2026-11-13)

**Context.** Filings are downloaded by hand from NSE/BSE. `data/bronze/manifest.csv` is the source of truth for what's in the corpus, but the PDFs and XBRL files are large and freely re-downloadable.

**Options.**
1. Commit the filings to git (or Git LFS).
2. Commit nothing under `data/`.
3. Commit only the manifest, with a source URL and sha256 per file.

**Choice.** Option 3. `.gitignore` excludes `data/**` except `data/bronze/manifest.csv`.

**Why.** The repo stays small, and anyone can rebuild the corpus from the URLs. The sha256 makes the corpus reproducible: `brsr ingest --check` fails if a file is missing, unlisted, or has changed since it was recorded, so a silently re-downloaded filing can't shift evaluation results. `--fill-hashes` never overwrites an existing hash, so a mismatch has to be investigated rather than papered over.

---

## D002 — Key companies by NSE symbol, not CIN (M0, 2026-11-13)

**Context.** The brief keyed companies by CIN. Bank of Baroda and Indian Bank are nationalised banks, constituted by statute rather than registered under the Companies Act, so their BRSRs state the CIN as "Not Applicable". (The Indian Bank PDF does contain a CIN, but it belongs to its share registrar, which is the kind of mistake a regex-based extractor would make.)

**Options.**
1. Keep CIN and invent a placeholder for the two banks.
2. Key by NSE symbol and keep CIN as an optional column.
3. Key by ISIN.

**Choice.** Option 2. `company_id` is the NSE symbol (`TCS`, `INFY`, `BANKBARODA`); `company_cin` is empty when the filing says "Not Applicable".

**Why.** Every company in scope is listed on NSE, so the symbol always exists and is unique. It's also what an analyst types, and what NSE's XBRL listing is filtered by. A made-up CIN would be a fabricated value in a project whose whole point is traceability. ISIN works too but is unreadable in a query.

**Evidence from the XBRL (2026-11-14).** The BRSR XBRL files confirm that CIN is unreliable for these banks: the "CIN" fields hold placeholders such as `X00000XX0000XXX000000` (Indian Bank FY25), `A00000AA0000AAA000000` (SBI) and well-formed but fictitious values like `L01234KA2023PTC567891` (Bank of Baroda). Code that joined on CIN would silently mismatch. `NSESymbol` is a fact in the FY 2025-26 taxonomy, which also makes the symbol the natural join key with XBRL.

**Caveat: symbols change on renames.** LTIMindtree became LTM Limited in FY 2025-26 and its NSE symbol changed from `LTIM` to `LTM`. We use the *current* symbol for both years, and the manifest keeps each filing's own `company_name`.

---

## D003 — Target FY 2024-25 and FY 2025-26 (M0, 2026-11-13)

**Context.** The brief said FY 2023-24 and FY 2024-25. By November 2026 the FY 2025-26 BRSRs have been filed (May–August 2026).

**Choice.** Use FY 2024-25 and FY 2025-26: the two most recent years.

**Why.** An analyst would ask about the latest filing first. Year-on-year questions still need exactly two years.

**Corpus (updated 2026-11-14).** Complete: 12 companies × 2 years, 24 PDFs and 24 XBRL files (one Inline XBRL, see D004). IT: TCS, Infosys, Tech Mahindra, Persistent, LTM (formerly LTIMindtree), Coforge. Banks: SBI, Axis, Federal, IndusInd, Bank of Baroda, Indian Bank. Boundary: TCS, Infosys, Tech Mahindra, Persistent and LTM report consolidated; Coforge and all banks report standalone.

---

## D004 — Keep Inline XBRL as downloaded (M0, 2026-11-14)

**Context.** LTIMindtree's FY 2024-25 BRSR XBRL isn't on NSE under the new `LTM` symbol, and BSE offers it only as Inline XBRL (`.html`): the same `in-capmkt` facts embedded in XHTML. The other 23 XBRL files are plain `.xml` instances.

**Options.** (1) Convert it to a plain `.xml` instance before storing it in bronze. (2) Store the `.html` file unchanged and parse both formats into the same `xbrl_facts` table.

**Choice.** Option 2. The manifest accepts `.xml` or `.html` for `doc_type = xbrl`.

**Why.** Bronze is raw and immutable: its sha256 must match what the exchange served. The conversion is parsing, so it belongs in the silver step, where it can be tested. Cross-check: this file's Scope 1 (1,542 tCO2e) and Scope 2 (18,239 tCO2e) match the prior-year values in LTM's FY 2025-26 XBRL exactly.

---

## D005 — Add pyarrow, pinned to an exact version (M1, 2026-11-16)

**Context.** Silver and gold are Delta tables written with `deltalake` and queried with DuckDB. Both libraries exchange data as Arrow tables. `pyarrow` was not in the brief's stack.

**Options.** (1) Rely on whatever Arrow implementation `deltalake` pulls in transitively. (2) Add `pyarrow` as a direct dependency with a range. (3) Add it pinned to one version.

**Choice.** Option 3: `pyarrow==26.0.1`.

**Why.** We build Arrow tables ourselves before writing to Delta, and DuckDB reads Delta back through Arrow, so `pyarrow` is a direct dependency, not an incidental one. Pinning it exactly keeps the Arrow-to-Delta type mapping stable between runs (e.g. `string` vs `large_string` vs `string_view`). A silent change there alters the Delta table schema and makes a later overwrite fail with a schema mismatch, or worse, makes two runs produce different files. Upgrades will be deliberate: bump the pin, rerun the tests and one parse, and commit.
