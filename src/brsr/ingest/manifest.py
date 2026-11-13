"""Filing manifest: the source of truth for which files are in the bronze layer."""

import csv
import hashlib
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator, model_validator

COLUMNS = [
    "company_id",
    "company_cin",
    "company_name",
    "sector",
    "fy",
    "doc_type",
    "file_path",
    "source_url",
    "sha256",
    "downloaded_on",
]
EXTENSIONS = {"pdf": ".pdf", "xbrl": ".xml"}
DATA_DIRS = ("filings", "xbrl")


class ManifestRow(BaseModel):
    company_id: str  # NSE symbol, e.g. TCS, BANKBARODA
    company_cin: str = ""  # empty for nationalised banks, which have no CIN
    company_name: str
    sector: Literal["IT", "BANK"]
    fy: str
    doc_type: Literal["pdf", "xbrl"]
    file_path: str  # relative to the bronze directory, forward slashes
    source_url: str
    sha256: str = ""  # empty until `brsr ingest --fill-hashes`
    downloaded_on: date

    @field_validator("company_id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        # NSE symbols are upper-case letters and digits, sometimes with & or -.
        if not v or v != v.upper() or not all(c.isalnum() or c in "&-" for c in v):
            raise ValueError(f"company_id must be an upper-case NSE symbol, got {v!r}")
        return v

    @field_validator("company_cin")
    @classmethod
    def _cin_format(cls, v: str) -> str:
        # CIN: listing status (L/U), 5-digit industry code, state, year, ownership, 6-digit reg no.
        if not v:
            return v
        if len(v) != 21 or v[0] not in "LU" or not v[1:6].isdigit() or not v[-6:].isdigit():
            raise ValueError(f"not a valid 21-character CIN: {v!r}")
        return v

    @field_validator("fy")
    @classmethod
    def _fy_format(cls, v: str) -> str:
        start, _, end = v.partition("-")
        if not (len(start) == 4 and start.isdigit() and len(end) == 2 and end.isdigit()):
            raise ValueError(f"fy must look like '2024-25', got {v!r}")
        if (int(start) + 1) % 100 != int(end):
            raise ValueError(f"fy years are not consecutive: {v!r}")
        return v

    @field_validator("source_url")
    @classmethod
    def _url_format(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"source_url must be an http(s) URL, got {v!r}")
        return v

    @field_validator("sha256")
    @classmethod
    def _sha_format(cls, v: str) -> str:
        if v and (len(v) != 64 or any(c not in "0123456789abcdef" for c in v)):
            raise ValueError("sha256 must be 64 lowercase hex characters or empty")
        return v

    @model_validator(mode="after")
    def _extension_matches_type(self) -> "ManifestRow":
        expected = EXTENSIONS[self.doc_type]
        if not self.file_path.lower().endswith(expected):
            raise ValueError(f"{self.doc_type} file must end in {expected}: {self.file_path}")
        return self


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_manifest(manifest_path: Path) -> tuple[list[ManifestRow], list[str]]:
    """Parse every row; return the valid rows and one message per invalid row."""
    rows: list[ManifestRow] = []
    problems: list[str] = []
    with manifest_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            return [], [f"header must be exactly: {','.join(COLUMNS)}"]
        for line_no, record in enumerate(reader, start=2):  # line 1 is the header
            try:
                rows.append(ManifestRow.model_validate(record))
            except ValidationError as e:
                for err in e.errors():
                    field = ".".join(str(p) for p in err["loc"]) or "row"
                    problems.append(f"line {line_no}: {field}: {err['msg']}")
    return rows, problems


def check_manifest(rows: list[ManifestRow], bronze_dir: Path) -> list[str]:
    """Cross-check manifest rows against the files on disk. Empty list means OK."""
    problems: list[str] = []

    seen: dict[tuple[str, str, str], str] = {}
    for r in rows:
        key = (r.company_id, r.fy, r.doc_type)
        if key in seen:
            problems.append(f"duplicate {key}: {seen[key]} and {r.file_path}")
        seen[key] = r.file_path

    listed = set()
    for r in rows:
        path = bronze_dir / r.file_path
        listed.add(path.resolve())
        if not path.is_file():
            problems.append(f"missing file: {r.file_path}")
        elif not r.sha256:
            problems.append(f"no sha256 (run --fill-hashes): {r.file_path}")
        elif sha256_file(path) != r.sha256:
            problems.append(f"sha256 mismatch (file changed?): {r.file_path}")

    for sub in DATA_DIRS:
        for path in sorted((bronze_dir / sub).rglob("*")):
            if path.is_file() and path.resolve() not in listed:
                rel = path.relative_to(bronze_dir).as_posix()
                problems.append(f"file not in manifest: {rel}")

    return problems


def fill_hashes(manifest_path: Path, bronze_dir: Path) -> int:
    """Write sha256 for rows that have none and whose file exists. Returns rows updated.

    Existing hashes are never overwritten: a mismatch must be investigated, not hidden.
    """
    with manifest_path.open(newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))

    updated = 0
    for rec in records:
        path = bronze_dir / rec["file_path"]
        if not rec["sha256"] and path.is_file():
            rec["sha256"] = sha256_file(path)
            updated += 1

    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    return updated
