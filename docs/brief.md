# BRSR Disclosure Intelligence Copilot — Project Brief

**Owner:** Harsh Malik · **Started:** 14 Nov 2026 · **Target ship date:** 11 Dec 2026
**Repo:** `brsr-copilot` · **Runs on:** a laptop (no GPU), with free-tier LLMs only

---

## 1. Problem statements

### 1.1 Personal: why I'm building this
> *Draft. Rewrite it in your own words until it sounds like something you'd say out loud in an interview.*

For four years I've worked on the producing side of sustainability data: building pipelines that collect ESG data from multiple business functions for a group sustainability report. BRSR is where that kind of data ends up. Every year, India's top 1,000 listed companies publish one.

When I looked at those reports from the outside, they were surprisingly hard to use. Comparing two banks' energy use meant opening two long PDFs, finding the same table in each, checking whether one reports in GJ and the other in MWh, and whether one is standalone and the other consolidated. Then doing it again for the next company. The data is public and mandatory, but in practice nobody can compare it without a lot of manual work.

### 1.2 The user's problem
**Users:** ESG analysts, sustainability teams benchmarking against peers, investors screening companies, and consultants preparing client reports.

**Their task:** "Compare these 10 companies on emissions, energy, water, workforce and safety, and tell me what's behind the numbers."

**What gets in the way:**
1. **Finding data:** the same metric sits in a different place in each filing.
2. **Comparability:** units (GJ vs MWh, kL vs m³, ₹ lakh vs ₹ crore), reporting boundaries (standalone vs consolidated) and financial years all differ.
3. **Trust:** a number without its source page can't go into an assured report or an investment memo.
4. **Narrative context:** *why* a number moved (a new data centre, a change in methodology) is only in the free text, not in any table.

### 1.3 The industry problem it generalises to
**Turning long regulatory documents into data that can be compared and traced back to its source.** BRSR is one instance. The same pipeline applies to:
- **Value-chain (supplier) ESG data:** suppliers send disclosures as PDFs and spreadsheets, with no XBRL. This is the problem BRSR Core's value-chain requirements create for every large company.
- **Annual reports, credit documents, insurance policies and contracts:** any domain where a fixed set of fields has to be pulled out of messy documents, with an audit trail.
- **Assurance readiness:** with BRSR Core assessment or assurance reaching the top 1,000 companies in FY 2026-27, every disclosed number needs traceable evidence.

### 1.4 Why extract from PDFs if XBRL exists? (interviewers will ask)
Companies file BRSR in **both PDF and XBRL** with the exchanges. The project uses that in three ways:
- **XBRL is the answer key:** it provides free, authoritative ground-truth labels for evaluating PDF extraction. Most document-AI projects have to hand-label everything.
- **PDF extraction is the skill that generalises:** supplier disclosures, global sustainability reports and internal ESG submissions have no XBRL. A pipeline proven against BRSR's answer key can then be trusted on documents that don't have one.
- **XBRL can't answer "why":** narrative questions need RAG over the PDF text, with citations.

**Fallback:** if XBRL can't be downloaded reliably (NSE's site blocks bots), hand-label 5 filings instead. The rest of the design doesn't change.

---

## 2. Scope

| In scope | Out of scope (and why) |
|---|---|
| 10–15 companies: ~6 IT services + ~6 banks | All 1,000 companies: scale doesn't strengthen the story, the evaluations do |
| 2 financial years (FY 2024-25, FY 2025-26) | More years: two are enough for year-on-year questions |
| ~25 metrics from Section A + the BRSR Core attributes | Every one of the 130+ BRSR line items: too much labelling for little gain |
| Q&A with page-level citations over narrative sections | Financed emissions for banks: not part of BRSR |
| Routing between text-to-SQL (numbers) and RAG (narrative) | Login, multiple users, cloud deployment |
| Local Streamlit UI and a demo video | Fine-tuning: prompting + RAG is the right tool at this scale |
| Evaluation harness for extraction, retrieval and answers | Automated scraping at scale: download files by hand or with a small script |

**Why IT and banking:** both sectors are large and familiar to interviewers. They're also very different: IT has low Scope 1 and high Scope 2 from offices and data centres, while banking is dominated by branch networks. That makes comparison questions interesting and catches extraction mistakes that a single-sector set would hide.

---

## 3. Questions the system must answer (acceptance set)

Numbers (answered with SQL over the gold table):
1. What were Infosys's Scope 1 and Scope 2 emissions in FY 2024-25, and on which page?
2. Rank the banks by Scope 2 emissions per ₹ crore of turnover.
3. Which IT company had the largest year-on-year change in renewable energy share?
4. What is the share of women in the workforce for each company, and the sector average?
5. Which companies' BRSR Core figures were assured, and by which assurance provider?

Narrative (answered with RAG, cited):
6. What reasons did TCS give for its change in energy consumption?
7. What water-conservation initiatives do the banks describe?
8. How does HDFC Bank describe its grievance mechanism for employees?

Mixed (routed to both, then combined):
9. Which company cut emissions intensity the most, and what did it say drove the change?
10. Compare Wipro and HCLTech on waste: the numbers and their stated approach.

*(Swap in the actual company names once the filing set is fixed.)*

---

## 4. Success metrics

| Metric | Target | How it's measured |
|---|---|---|
| Field extraction accuracy | Baseline in week 2, then **+10 points** after one improvement round; aim for ≥90% | Compared against XBRL (or hand) labels; numbers within ±2% after unit normalisation |
| Unit normalisation correctness | 100% on the test set | Unit tests per unit type |
| Retrieval recall@5 | ≥ 0.85 | 30 Q&A pairs, each with a known source page |
| Answer faithfulness | ≥ 0.90 | LLM-as-judge (checked by hand on 10 samples) |
| Answers that include a citation | 100% | Rule check |
| Routing accuracy | ≥ 90% | 20 labelled questions |
| Cost to re-run | ₹0 and zero new LLM calls | Response cache keyed by file hash + prompt version |
| Query latency | < 10 seconds on a laptop | Logged per query |

---

## 5. Architecture

```
            ┌────────────── BRONZE (raw, immutable) ──────────────┐
 NSE/BSE ──▶│ filings/*.pdf   xbrl/*.xml|html  manifest.csv       │
            └──────────────┬──────────────────────┬───────────────┘
                           │ parse (Docling, D006) │ parse XBRL
            ┌──────────────▼──────────────────────▼───────────────┐
            │ SILVER: pages · tables · chunks      xbrl_facts      │
            └───────┬───────────────────────┬─────────────────────┘
       LLM extract  │ (Gemini, validated     │ embed (bge-small, CPU)
       + normalise  │  with Pydantic, cached) │ + BM25 index
            ┌───────▼────────────┐   ┌──────▼──────────────────┐
            │ GOLD: brsr_metrics │   │ Qdrant (local) + BM25   │
            │ value · unit · page│   │ hybrid → RRF → rerank   │
            │ method · confidence│   └──────┬──────────────────┘
            └───────┬────────────┘          │
                    │      ┌────────────────┴──────┐
                    └─────▶│ ROUTER: SQL │ RAG │ both│──▶ answer + citations
                           └───────────┬───────────┘
                                       ▼
                         Streamlit UI  ·  eval/ reports
```

**Stack:** Python 3.12, uv, Delta tables via `deltalake` (delta-rs) queried with DuckDB through `pyarrow` (pinned, D005), Docling for PDF parsing (PyMuPDF kept for comparison, D006), Pydantic v2, Gemini through the `google-genai` SDK behind a client that can swap providers, `sentence-transformers` (bge-small-en-v1.5), Qdrant in local mode, `bm25s`, a small cross-encoder reranker (ms-marco-MiniLM), Streamlit, pytest, ruff, GitHub Actions.

**Why Delta on a laptop:** it's the same bronze/silver/gold pattern as production Databricks, running locally. That makes the step from this project to work at Tibil or ABG obvious.

---

## 6. Data model (gold)

`brsr_metrics`, one row per company × financial year × metric:

| Column | Type | Notes |
|---|---|---|
| company_id | str | NSE symbol (e.g. `TCS`, `BANKBARODA`); see D002 |
| company_cin | str | CIN; empty for nationalised banks |
| company_name | str | |
| sector | str | `IT` or `BANK` |
| fy | str | e.g. `2024-25` |
| boundary | str | `standalone` or `consolidated` |
| metric_code | str | e.g. `ghg_scope1_tco2e` |
| value_raw | str | Exactly as written in the filing |
| unit_raw | str | |
| value_norm | float | Converted to the canonical unit |
| unit_norm | str | Canonical unit for that metric |
| source_page | int | Required |
| method | str | `xbrl`, `llm`, or `llm+xbrl_verified` |
| confidence | float | Model or rule confidence |
| prompt_version | str | For reproducibility |

**Metrics (~25):** Scope 1, Scope 2, GHG intensity per ₹ crore of turnover; total energy (GJ), % renewable, energy intensity; water withdrawal, consumption, discharge (kL), water intensity; waste generated, recovered, disposed (t); permanent employees (male/female/total), % women, % differently abled; employee turnover rate; LTIFR, fatalities; consumer complaints received/pending; CSR spend; assurance provider and assurance type.

---

## 7. Milestones

| # | Week | Milestone | Done when |
|---|---|---|---|
| M0 | 1 (Sat) | Repo scaffold, brief, filing manifest | CI runs lint; manifest lists every file |
| M1 | 1 (Sun) | PDF parsing to silver; parser comparison | Pages and tables per filing; result written in `decisions.md` |
| M2 | 2 (Sat) | XBRL parsing to `xbrl_facts`; LLM extraction to gold with cache | Gold table filled; a re-run makes zero LLM calls |
| M3 | 2 (Sun) | Extraction evaluation against XBRL; one improvement round | Accuracy per field before and after, recorded |
| M4 | 3 (Sat) | Chunking, embeddings, hybrid search, reranking, citations | Top 5 results include source pages |
| M5 | 3 (Sun) | Q&A test set; router; retrieval and answer evaluation | recall@5, faithfulness and routing accuracy reported |
| M6 | 4 (Sat–Sun) | Streamlit UI, README, demo video | Runs with one command; README reviewed |

---

## 8. Key decisions (to record in `docs/decisions.md` as you make them)

1. **Parser:** PyMuPDF vs Docling on BRSR tables. Measure on 3 filings; don't assume. *Decided 2026-11-24: Docling (D006): equal recall, 17/19 vs 10/19 table rows intact, ~9× slower.*
2. **Granularity:** extract per section (e.g. the Principle 6 environment section), not the whole document at once. Smaller context gives better accuracy and costs less.
3. **Unit normalisation is done in code, not by the LLM.** The LLM returns the raw value and unit; deterministic rules convert them. *(Same principle as the Safety platform: the LLM extracts, rules decide, so the result is auditable.)*
4. **Boundary:** extract both standalone and consolidated figures when present, and default comparisons to standalone. *Open: most IT filings report only consolidated (see `next.md`); decide in M2.*
5. **Provider abstraction:** Gemini by default; Ollama (local) or Bedrock as fallbacks through one interface.
6. **When XBRL and the LLM disagree:** treat XBRL as the truth for evaluation; log the disagreement as an evaluation finding, don't hide it.

## 9. Risks

| Risk | Mitigation |
|---|---|
| NSE blocks automated downloads | Download the filings and their XBRL by hand (24 + 24 in the corpus); keep URLs in the manifest |
| Gemini free-tier rate limits | Cache responses, process in batches with backoff, extract per section |
| Docling is slow on CPU | Run it once, keep silver output in Delta, never parse the same file twice. *Measured: 2.08 h for 24 filings / 1,688 pages; re-run is a no-op.* |
| BRSR table layouts differ between companies | Evaluation per field shows where; add few-shot examples for the worst fields |
| Scope creeps past 4 weeks | This brief's out-of-scope list is binding; new ideas go in `docs/next.md` |

## 10. The 30-second pitch
> "India's top 1,000 companies file BRSR sustainability reports every year, and they're nearly impossible to compare. I built a copilot that turns them into a comparable table where every number cites its source page, and answers questions with citations. I used the companies' own XBRL filings as an answer key, so I can tell you exactly how accurate the PDF extraction is: it went from X% to Y%. That pipeline then works on documents with no XBRL, like supplier ESG disclosures."

---

## References
- NSE circular NSE/CML/2024/11 (10 May 2024), BRSR FAQs: BRSR is filed in PDF and XBRL on the same day as the annual report — https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_Circular_10052024_3.pdf
- NSE BRSR XBRL taxonomy (XBRL information page) — https://www.nseindia.com/static/companies-listing/xbrl-information
- NSE corporate filings, BRSR listing — https://www.nseindia.com/companies-listing/corporate-filings-annual-reports-xbrl
- BRSR Core assurance glide path (top 150 → top 1,000 by FY 2026-27) — https://taxguru.in/?p=955846
