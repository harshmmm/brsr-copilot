"""`brsr` command-line entry point. One command per pipeline stage."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from brsr.ingest.manifest import check_manifest, fill_hashes, read_manifest

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_MANIFEST = Path("data/bronze/manifest.csv")
DEFAULT_SILVER = Path("data/silver")


class Parser(StrEnum):
    pymupdf = "pymupdf"
    docling = "docling"


@app.callback()
def main() -> None:
    """BRSR copilot pipeline."""


@app.command()
def ingest(
    manifest: Annotated[Path, typer.Option(help="Path to manifest.csv.")] = DEFAULT_MANIFEST,
    check: Annotated[bool, typer.Option("--check", help="Validate against files.")] = False,
    hashes: Annotated[bool, typer.Option("--fill-hashes", help="Fill missing sha256.")] = False,
) -> None:
    """Validate the filing manifest (bronze loading arrives in a later milestone)."""
    if not (check or hashes):
        typer.echo("Nothing to do: pass --check and/or --fill-hashes.")
        raise typer.Exit(2)

    bronze_dir = manifest.parent
    if hashes:
        n = fill_hashes(manifest, bronze_dir)
        typer.echo(f"Filled sha256 for {n} row(s).")

    if check:
        rows, problems = read_manifest(manifest)
        if not problems:
            problems = check_manifest(rows, bronze_dir)
        for p in problems:
            typer.echo(f"  - {p}", err=True)
        if problems:
            typer.echo(f"Manifest check FAILED: {len(problems)} problem(s).", err=True)
            raise typer.Exit(1)
        typer.echo(f"Manifest OK: {len(rows)} file(s).")


@app.command()
def parse(
    parser: Annotated[Parser, typer.Option(help="PDF parser.")] = Parser.pymupdf,
    company: Annotated[str | None, typer.Option(help="Only this NSE symbol.")] = None,
    fy: Annotated[str | None, typer.Option(help="Only this financial year, e.g. 2024-25.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Reparse even if unchanged.")] = False,
    manifest: Annotated[Path, typer.Option(help="Path to manifest.csv.")] = DEFAULT_MANIFEST,
    silver: Annotated[Path, typer.Option(help="Silver directory.")] = DEFAULT_SILVER,
) -> None:
    """Parse manifest PDFs into silver pages/tables. Missing files are listed, not fatal."""
    from brsr.parse.silver import parse_filings

    if parser is Parser.docling:
        from brsr.parse import pdf_docling as mod
    else:
        from brsr.parse import pdf_pymupdf as mod

    rows, problems = read_manifest(manifest)
    if problems:
        for p in problems:
            typer.echo(f"  - {p}", err=True)
        raise typer.Exit(1)
    rows = [
        r
        for r in rows
        if r.doc_type == "pdf" and company in (None, r.company_id) and fy in (None, r.fy)
    ]
    if not rows:
        typer.echo("No PDF rows match the filters.", err=True)
        raise typer.Exit(2)

    typer.echo(f"Parsing {len(rows)} PDF(s) with {mod.version()}")
    if hasattr(mod, "warmup"):
        mod.warmup()  # keep one-off model loading out of the per-filing timings
    report = parse_filings(
        rows, manifest.parent, silver, mod.parse, mod.NAME, mod.version(), force, typer.echo
    )
    typer.echo(f"Parsed {len(report.parsed)}, already up to date {len(report.skipped)}.")
    for title, items in (("Missing", report.missing), ("Changed since hashed", report.changed)):
        if items:
            typer.echo(f"{title} ({len(items)}), not parsed:")
            for item in items:
                typer.echo(f"  - {item}")
