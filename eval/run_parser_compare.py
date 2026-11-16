"""Compare PDF parsers on three filings, scored against each filing's own XBRL.

(a) recall: share of selected XBRL values found anywhere in the parser's page text
(b) table integrity: Principle 6 energy/emissions rows whose label, current-year value and
    previous-year value sit in separate cells of one extracted table row, in that order
(c) seconds per filing, from silver.parse_runs

Bank of Baroda is reported separately: its Hindi/English pages would skew the averages.
Run after `brsr parse` for both parsers:
    uv run python eval/run_parser_compare.py
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from brsr.ingest.manifest import read_manifest
from brsr.parse.numbers import number_tokens, row_has_values, same_number, significant_digits
from brsr.storage.delta import query

MANIFEST = Path("data/bronze/manifest.csv")
SILVER = Path("data/silver")
REPORTS = Path("eval/reports")
PARSERS = ("pymupdf", "docling")
FILINGS = [("TCS", "2024-25"), ("AXISBANK", "2025-26"), ("BANKBARODA", "2024-25")]
SEPARATE = {"BANKBARODA"}  # bilingual; reported on its own

ENERGY = [
    "TotalElectricityConsumptionFromRenewableSources",
    "TotalFuelConsumptionFromRenewableSources",
    "EnergyConsumptionThroughOtherSourcesFromRenewableSources",
    "TotalEnergyConsumedFromRenewableSources",
    "TotalElectricityConsumptionFromNonRenewableSources",
    "TotalFuelConsumptionFromNonRenewableSources",
    "EnergyConsumptionThroughOtherSourcesFromNonRenewableSources",
    "TotalEnergyConsumedFromNonRenewableSources",
    "TotalEnergyConsumedFromRenewableAndNonRenewableSources",
]
EMISSIONS = ["TotalScope1Emissions", "TotalScope2Emissions", "TotalScope3Emissions"]
WATER = [
    "WaterWithdrawalBySurfaceWater",
    "WaterWithdrawalByGroundwater",
    "WaterWithdrawalByThirdPartyWater",
    "WaterWithdrawalBySeawaterOrDesalinatedWater",
    "WaterWithdrawalByOthers",
    "TotalVolumeOfWaterWithdrawal",
    "TotalVolumeOfWaterConsumption",
]
WASTE = ["TotalWasteGenerated", "TotalWasteRecovered", "TotalWasteDisposed"]
WORKFORCE = ["NumberOfEmployeesOrWorkersIncludingDifferentlyAbled"]
RECALL_ELEMENTS = ENERGY + EMISSIONS + WATER + WASTE + WORKFORCE

# Row labels in the Principle 6 tables. Several rows share a label pattern (e.g. renewable
# and non-renewable "Total electricity consumption"); the expected values disambiguate.
ROW_LABELS = {
    **{e: r"electricity\s*consum" for e in ENERGY if "Electricity" in e},
    **{e: r"fuel\s*consum" for e in ENERGY if "Fuel" in e},
    **{e: r"other\s*sources" for e in ENERGY if "OtherSources" in e},
    **{e: r"total\s*energy\s*consum" for e in ENERGY if e.startswith("TotalEnergyConsumed")},
    "TotalScope1Emissions": r"scope\s*1",
    "TotalScope2Emissions": r"scope\s*2",
    "TotalScope3Emissions": r"scope\s*3",
}
MIN_SIGNIFICANT_DIGITS = 3  # values like 0, 1 or 12 would be "found" by chance


# --- XBRL: just enough to read the facts above (the full parser is M2) -------------


@dataclass(frozen=True)
class Fact:
    element: str
    period_end: str
    dims: tuple[str, ...]
    value: Decimal


def read_facts(path: Path, elements: set[str]) -> list[Fact]:
    xbrli = "{http://www.xbrl.org/2003/instance}"
    root = ET.parse(path).getroot()
    contexts = {}
    for c in root.iter(xbrli + "context"):
        end = [x.text.strip() for x in c.find(xbrli + "period")][-1]
        dims = tuple(
            (m.text or "").split(":")[-1] for m in c.iter() if m.tag.endswith("explicitMember")
        )
        contexts[c.get("id")] = (end, dims)
    facts = []
    for e in root:
        name = e.tag.rsplit("}", 1)[-1]
        if name in elements and e.get("unitRef") and (e.text or "").strip():
            end, dims = contexts[e.get("contextRef")]
            facts.append(Fact(name, end, dims, Decimal(e.text.strip())))
    return facts


def fy_ends(fy: str) -> tuple[str, str]:
    start = int(fy[:4])
    return f"{start + 1}-03-31", f"{start}-03-31"


# --- scoring -----------------------------------------------------------------------


def recall_targets(facts: list[Fact], fy: str) -> list[Fact]:
    """Distinct non-trivial values for the current and previous year."""
    seen, out = set(), []
    for f in facts:
        if f.period_end in fy_ends(fy) and significant_digits(f.value) >= MIN_SIGNIFICANT_DIGITS:
            if f.value not in seen:
                seen.add(f.value)
                out.append(f)
    return out


def score_recall(targets: list[Fact], text: str) -> list[tuple[Fact, bool]]:
    tokens = set(number_tokens(text))
    return [(f, any(same_number(t, f.value) for t in tokens)) for f in targets]


@dataclass(frozen=True)
class ExpectedRow:
    element: str
    current: Decimal
    previous: Decimal


def expected_rows(facts: list[Fact], fy: str) -> list[ExpectedRow]:
    cur_end, prev_end = fy_ends(fy)
    by = {(f.element, f.period_end): f.value for f in facts if not f.dims}
    out = []
    for element in ROW_LABELS:
        cur, prev = by.get((element, cur_end)), by.get((element, prev_end))
        if cur is None or prev is None or (cur == 0 and prev == 0):
            continue  # an all-zero row is printed as Nil/-, which can't show structure
        out.append(ExpectedRow(element, cur, prev))
    return out


def score_rows(
    expected: list[ExpectedRow], tables: list[list[list[str]]]
) -> list[tuple[ExpectedRow, bool]]:
    rows = [row for t in tables for row in t]
    out = []
    for e in expected:
        label = re.compile(ROW_LABELS[e.element], re.I)
        out.append((e, any(row_has_values(r, label, e.current, e.previous) for r in rows)))
    return out


# --- data access ---------------------------------------------------------------------


def silver_text(company: str, fy: str, parser: str) -> str:
    t = query(
        f"SELECT text FROM p WHERE company_id = '{company}' AND fy = '{fy}' "
        f"AND parser = '{parser}' ORDER BY page_no",
        p=SILVER / "pages",
    )
    return "\n".join(t["text"].to_pylist())


def silver_tables(company: str, fy: str, parser: str) -> list[list[list[str]]]:
    t = query(
        f"SELECT cells_json FROM t WHERE company_id = '{company}' AND fy = '{fy}' "
        f"AND parser = '{parser}' ORDER BY page_no, table_idx",
        t=SILVER / "tables",
    )
    return [json.loads(c) for c in t["cells_json"].to_pylist()]


def silver_run(company: str, fy: str, parser: str) -> dict | None:
    t = query(
        f"SELECT parser_version, n_pages, n_tables, seconds FROM r WHERE company_id = '{company}' "
        f"AND fy = '{fy}' AND parser = '{parser}'",
        r=SILVER / "parse_runs",
    ).to_pylist()
    return t[0] if t else None


# --- report --------------------------------------------------------------------------


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console defaults to cp1252
    rows, problems = read_manifest(MANIFEST)
    if problems:
        print("Manifest invalid; run `brsr ingest --check`.", file=sys.stderr)
        return 1
    xbrl = {(r.company_id, r.fy): r for r in rows if r.doc_type == "xbrl"}

    # Hard requirement: every comparison filing has its XBRL in bronze. No substitutes.
    missing = [
        f"{c} {fy}"
        for c, fy in FILINGS
        if (c, fy) not in xbrl or not (MANIFEST.parent / xbrl[(c, fy)].file_path).is_file()
    ]
    if missing:
        print(f"STOP: XBRL missing for {', '.join(missing)}. Not substituting.", file=sys.stderr)
        return 1
    not_parsed = [
        f"{c} {fy} ({p})" for c, fy in FILINGS for p in PARSERS if silver_run(c, fy, p) is None
    ]
    if not_parsed:
        print(f"STOP: not parsed yet: {', '.join(not_parsed)}", file=sys.stderr)
        return 1

    results = {}
    for company, fy in FILINGS:
        facts = read_facts(MANIFEST.parent / xbrl[(company, fy)].file_path, set(RECALL_ELEMENTS))
        targets, expected = recall_targets(facts, fy), expected_rows(facts, fy)
        for parser in PARSERS:
            results[(company, fy, parser)] = {
                "recall": score_recall(targets, silver_text(company, fy, parser)),
                "rows": score_rows(expected, silver_tables(company, fy, parser)),
                "run": silver_run(company, fy, parser),
            }

    lines = render(results)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"parser_compare_{datetime.now():%Y%m%d-%H%M%S}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[: lines.index("## Details")]))
    print(f"Report: {out}")
    return 0


def render(results: dict) -> list[str]:
    def summary(group: list[tuple[str, str]], title: str) -> list[str]:
        out = [
            f"### {title}",
            "",
            "| Parser | (a) XBRL value recall | (b) P6 rows intact | (c) seconds/filing | s/page |",
            "|---|---|---|---|---|",
        ]
        for p in PARSERS:
            rec = [ok for c, fy in group for _, ok in results[(c, fy, p)]["recall"]]
            rws = [ok for c, fy in group for _, ok in results[(c, fy, p)]["rows"]]
            secs = [results[(c, fy, p)]["run"]["seconds"] for c, fy in group]
            pages = sum(results[(c, fy, p)]["run"]["n_pages"] for c, fy in group)
            out.append(
                f"| {p} | {pct(sum(rec), len(rec))} | {pct(sum(rws), len(rws))} "
                f"| {sum(secs) / len(secs):.1f} | {sum(secs) / pages:.2f} |"
            )
        return [*out, ""]

    main_group = [f for f in FILINGS if f[0] not in SEPARATE]
    sep_group = [f for f in FILINGS if f[0] in SEPARATE]
    lines = [
        f"# Parser comparison — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Scored against each filing's XBRL. "
        f"Recall uses values with ≥{MIN_SIGNIFICANT_DIGITS} significant digits, current and "
        "previous FY, deduplicated. Row integrity: label, current-year value and previous-year "
        "value in separate cells of one table row, in order.",
        "",
        "## Summary",
        "",
        *summary(main_group, " + ".join(f"{c} {fy}" for c, fy in main_group)),
        *summary(sep_group, " + ".join(f"{c} {fy}" for c, fy in sep_group) + " (separate)"),
        "Parser versions: "
        + ", ".join(sorted({r["run"]["parser_version"] for r in results.values()})),
        "",
        "## Details",
        "",
    ]
    for company, fy in FILINGS:
        lines += [f"### {company} {fy}", ""]
        for p in PARSERS:
            r = results[(company, fy, p)]
            run = r["run"]
            recall = pct(sum(ok for _, ok in r["recall"]), len(r["recall"]))
            rows_ok = pct(sum(ok for _, ok in r["rows"]), len(r["rows"]))
            lines.append(
                f"**{p}**: {run['n_pages']} pages, {run['n_tables']} tables, "
                f"{run['seconds']:.1f}s; recall {recall}; rows {rows_ok}"
            )
        lines.append("")
        other = {p: dict((f, ok) for f, ok in results[(company, fy, p)]["recall"]) for p in PARSERS}
        missed = [f for f in other[PARSERS[0]] if not all(other[p][f] for p in PARSERS)]
        if missed:
            lines += [
                "Recall misses (✗ = not found):",
                "",
                "| element | dims | period | value | " + " | ".join(PARSERS) + " |",
                "|---|---|---|---|" + "---|" * len(PARSERS),
            ]
            for f in missed:
                marks = " | ".join("✓" if other[p][f] else "✗" for p in PARSERS)
                lines.append(
                    f"| {f.element} | {'/'.join(f.dims)} | {f.period_end} | {f.value} | {marks} |"
                )
            lines.append("")
        rows = {p: dict((e, ok) for e, ok in results[(company, fy, p)]["rows"]) for p in PARSERS}
        lines += [
            "P6 rows:",
            "",
            "| element | current | previous | " + " | ".join(PARSERS) + " |",
            "|---|---|---|" + "---|" * len(PARSERS),
        ]
        for e in rows[PARSERS[0]]:
            marks = " | ".join("✓" if rows[p][e] else "✗" for p in PARSERS)
            lines.append(f"| {e.element} | {e.current} | {e.previous} | {marks} |")
        lines.append("")
    return lines


if __name__ == "__main__":
    sys.exit(main())
