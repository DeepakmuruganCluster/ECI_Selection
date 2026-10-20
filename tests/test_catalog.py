"""The generated catalog must match the tables (rebuild = file) and every part must trace to a registered document."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_is_current():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_catalog import build
    cat = build()
    on_disk = yaml.safe_load((ROOT / "data" / "catalog" / "parts.yaml").read_text())
    assert on_disk == cat["parts"], "run scripts/build_catalog.py"


def test_every_part_traces_to_a_registered_document():
    from core.provenance import register
    reg = register()
    parts = yaml.safe_load((ROOT / "data" / "catalog" / "parts.yaml").read_text())
    for k, p in parts.items():
        assert all(s["ref"] in reg for s in p["sources"]), k


def test_no_component_keeps_its_own_data():
    """Tables live in data/makers, data/company or projects/*/data — never inside a component."""
    assert not list(ROOT.glob("components/*/data")), "move the table to data/makers or data/company"


def test_no_client_table_in_the_generic_engine():
    """Client-specific tables live in projects/, not in data/makers or data/company."""
    from core.data import _index
    for f in _index().values():
        ref = (yaml.safe_load(f.read_text()).get("source") or {}).get("ref", "")
        assert not ref.startswith("ECI-"), f


def test_maker_and_company_tables_have_the_right_authority():
    """data/makers holds maker documents; data/company holds own data (refs OWN-*)."""
    from core.data import _index
    for f in _index().values():
        ref = yaml.safe_load(f.read_text())["source"]["ref"]
        assert ref.startswith("OWN-") == (f.parts[-3] == "company"), (f, ref)


def test_every_table_is_read_by_a_component_and_every_listed_file_exists():
    from core.data import tables
    listed = set()
    for rv in ROOT.glob("components/*/review.yaml"):
        for f in yaml.safe_load(rv.read_text()).get("data_files") or []:
            assert (ROOT / f).is_file(), (rv, f)
            listed.add(f)
    pending = (yaml.safe_load((ROOT / "data" / "pending.yaml").read_text()) or {}).get("tables") or {}
    unread = [str(f.relative_to(ROOT)) for f in tables() if str(f.relative_to(ROOT)) not in listed | set(pending)]
    assert not unread, unread
    assert not (set(pending) & listed), "a pending table is now read: remove it from data/pending.yaml"
    assert all((ROOT / f).is_file() for f in pending), pending
