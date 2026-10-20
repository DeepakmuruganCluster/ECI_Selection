"""Loading data with mandatory provenance.

Rule of the project: no source, no data. A data file must name a reference in
sources/register.yaml, that reference's file must be present with the recorded
SHA-256, and every row must carry the page it was read from. Anything else is a
hard error, not a warning.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"


class ProvenanceError(Exception):
    pass


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def register() -> dict:
    return load_yaml(SOURCES / "register.yaml")["references"]


@lru_cache(maxsize=None)
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_reference(ref_id: str) -> dict:
    refs = register()
    if ref_id not in refs:
        raise ProvenanceError(f"reference {ref_id!r} is not in sources/register.yaml")
    ref = refs[ref_id]
    if ref.get("access") == "stored":
        path = SOURCES / ref["file"]
        if not path.exists():
            raise ProvenanceError(f"{ref_id}: source file missing: sources/{ref['file']}")
        if ref.get("sha256") and _sha256(path) != ref["sha256"]:
            raise ProvenanceError(f"{ref_id}: sources/{ref['file']} differs from the registered SHA-256 "
                                  "(different edition?) — re-verify the data before updating the hash")
    return ref


def load_sourced_table(path: Path, row_fields: tuple[str, ...]) -> dict:
    """Load a data file and refuse it unless every row is traceable."""
    d = load_yaml(path)
    name = path.name
    src = d.get("source") or {}
    if not src.get("ref"):
        raise ProvenanceError(f"{name}: no source.ref")
    d["reference"] = check_reference(src["ref"])
    rows = d.get("rows") or []
    if not rows:
        raise ProvenanceError(f"{name}: no rows")
    for i, r in enumerate(rows):
        # a PDF row cites its page; a spreadsheet row cites its sheet row instead
        locator = "row" if str(d["reference"].get("file", "")).endswith((".xlsx", ".xls", ".csv")) else "page"
        missing = [k for k in (*row_fields, locator) if r.get(k) is None]
        if missing:
            raise ProvenanceError(f"{name}: row {i + 1} missing {', '.join(missing)}")
    return d
