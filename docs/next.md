# Ideas parked for later

Things that are out of scope for the current milestone. Not commitments.

## Open questions for later milestones
- **Boundary default (M2).** The brief says to default comparisons to standalone. But TCS, Infosys, Tech Mahindra, Persistent and LTIMindtree report only on a consolidated basis, while all banks and Coforge report standalone. A "standalone by default" rule would drop most of the IT sector. Decide once extraction shows which filings give both.
- **Where the BRSR starts (M1).** Some PDFs carry other content first: Bank of Baroda FY 2024-25 Section A starts on page 106 of 187; Indian Bank puts a Hindi version before the English one; several NSE copies have a cover letter on page 1.
- **Source URLs to replace with NSE originals:** Federal Bank FY 2024-25 (Business Standard copy). Infosys FY 2024-25 URL could not be verified (site returns 403 to scripts).
- **XBRL taxonomy versions differ (M2).** Three `in-capmkt-ent` versions in the corpus: 2024-04-30 (Indian Bank and Bank of Baroda FY 2024-25), 2025-05-31 (other FY 2024-25 filings) and 2026-02-28 (all FY 2025-26). The XBRL parser must map element names across versions; `NSESymbol` exists only in 2026-02-28.
- **XBRL source URLs are the NSE listing page**, not per-file links, because NSE's archive path for XBRL files wasn't confirmed. Replace them if direct links turn up.
- **One XBRL file is Inline XBRL (M2).** `xbrl/ltimindtree_2024-25.html` (from BSE) tags facts as `ix:nonFraction` / `ix:nonNumeric` inside XHTML, with `format` (e.g. `ixt2:datedaymonthyear`) and `scale` attributes. The XBRL parser needs an iXBRL path that applies those transforms; see D004.
- **PDF vs XBRL disagreements found during M1 (M3).** Hand-checked, not parser errors:
  TCS FY 2023-24 total energy prints 1,70,91,82,976 MJ vs XBRL 1709182975 (off by 1);
  Bank of Baroda FY 2023-24 non-renewable and total energy print …922.96 / …233.46 vs XBRL …922.95 / …233.45;
  Axis FY 2025-26 never prints the Scope 1 total (only CO2/CH4/N2O, which sum to the XBRL's 11,644.43).
  The ±2% extraction tolerance absorbs the first two; the Axis case means some XBRL totals must be derived, not found.
- **BRSR section detection (M2).** Tag each silver page with its BRSR section/principle so extraction can run per section (brief decision 2). Deferred from M1.
