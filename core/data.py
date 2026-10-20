"""Where the data tables live. One table per source document, filed by who wrote it:

    data/makers/<maker>/      the maker's catalogue or manual (authority MFR)
    data/company/<group>/     company standards and databases (authority OWN): switchgear, plc, dc, propel, vfd_logic
    projects/<project>/data/  client-specific tables (read by path)
    data/catalog/             generated index (scripts/build_catalog.py), never read by a selector

Table file names are unique across data/, so a component asks for a table by name only.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
GROUPS = ("makers", "company")


@lru_cache(maxsize=None)
def _index() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for g in GROUPS:
        for p in sorted((DATA_DIR / g).glob("*/*.yaml")):
            if p.name in out:
                raise ValueError(f"table name {p.name} is used twice: {out[p.name]} and {p}")
            out[p.name] = p
    return out


def data_file(name: str) -> Path:
    """The path of a data table by its file name (fails closed if it is not filed)."""
    try:
        return _index()[name]
    except KeyError:
        raise FileNotFoundError(f"data table {name} is not in data/makers or data/company") from None


def tables() -> list[Path]:
    """Every maker and company table, then every project table."""
    return [*_index().values(), *sorted(ROOT.glob("projects/*/data/*.yaml"))]
