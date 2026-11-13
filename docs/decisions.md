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

---

## D003 — Target FY 2024-25 and FY 2025-26 (M0, 2026-11-13)

**Context.** The brief said FY 2023-24 and FY 2024-25. By November 2026 the FY 2025-26 BRSRs have been filed (May–August 2026).

**Choice.** Use FY 2024-25 and FY 2025-26: the two most recent years.

**Why.** An analyst would ask about the latest filing first. Year-on-year questions still need exactly two years.

**Corpus as of this decision.** 11 companies, 21 PDFs. IT: TCS, Infosys, Tech Mahindra, Persistent, LTIMindtree (renamed LTM Limited in FY26), Coforge (FY 2024-25 only so far). Banks: Axis, Federal, IndusInd, Bank of Baroda, Indian Bank. SBI is in the target list but not yet downloaded. No XBRL yet.
