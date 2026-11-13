"""`brsr` command-line entry point. One command per pipeline stage."""

from pathlib import Path
from typing import Annotated

import typer

from brsr.ingest.manifest import check_manifest, fill_hashes, read_manifest

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_MANIFEST = Path("data/bronze/manifest.csv")


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
