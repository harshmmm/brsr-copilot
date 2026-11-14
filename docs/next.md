# Ideas parked for later

Things that are out of scope for the current milestone. Not commitments.

## Open questions for later milestones
- **Boundary default (M2).** The brief says to default comparisons to standalone. But TCS, Infosys, Tech Mahindra, Persistent and LTIMindtree report only on a consolidated basis, while all banks and Coforge report standalone. A "standalone by default" rule would drop most of the IT sector. Decide once extraction shows which filings give both.
- **Where the BRSR starts (M1).** Some PDFs carry other content first: Bank of Baroda FY 2024-25 Section A starts on page 106 of 187; Indian Bank puts a Hindi version before the English one; several NSE copies have a cover letter on page 1.
- **Source URLs to replace with NSE originals:** Federal Bank FY 2024-25 (Business Standard copy). Infosys FY 2024-25 URL could not be verified (site returns 403 to scripts).
- **XBRL taxonomy versions differ (M2).** Three `in-capmkt-ent` versions in the corpus: 2024-04-30 (Indian Bank and Bank of Baroda FY 2024-25), 2025-05-31 (other FY 2024-25 filings) and 2026-02-28 (all FY 2025-26). The XBRL parser must map element names across versions; `NSESymbol` exists only in 2026-02-28.
- **XBRL source URLs are the NSE listing page**, not per-file links, because NSE's archive path for XBRL files wasn't confirmed. Replace them if direct links turn up.
- **One XBRL file is Inline XBRL (M2).** `xbrl/ltimindtree_2024-25.html` (from BSE) tags facts as `ix:nonFraction` / `ix:nonNumeric` inside XHTML, with `format` (e.g. `ixt2:datedaymonthyear`) and `scale` attributes. The XBRL parser needs an iXBRL path that applies those transforms; see D004.
