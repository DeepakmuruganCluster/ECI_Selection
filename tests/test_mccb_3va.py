import re
from pathlib import Path

import pytest
import yaml

from components.mccb_3va.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "mccb_3va"
RESULTS = golden.run(HERE / "golden" / "cases.yaml", select)


@pytest.mark.parametrize("case,res,diffs", RESULTS, ids=[c["id"] for c, _, _ in RESULTS])
def test_golden(case, res, diffs):
    assert not diffs, f"{case['id']} ({case['oracle']}): {diffs}\n{res.trace()}"


def test_every_rule_in_code_is_in_the_rule_sheet():
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks} - {"INPUT"}
    assert used <= set(rules), used - set(rules)


def test_every_rule_is_exercised_by_a_golden_case():
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks}
    assert set(rules) <= used, set(rules) - used


def test_every_held_data_sheet_agrees_with_the_catalogue_structure():
    """Each held 3VA1 data sheet: the structure (LV 10 · 2026 pp.2/26-2/27) builds the same article from the sheet's frame,
    In and Icu, and the sheet's Icu / Ics are the catalogue's for that class (p.2/9)."""
    from components.mccb_3va.select import _datasheets, _structure
    st = _structure()
    assert _datasheets(), "no 3VA1 data sheet held"
    for art, ds in _datasheets().items():
        row = next(r for r in st["rows"] if r["frame"] == ds["frame"])
        cls = next(c for c in row["classes"] if c["class"] == ds["class"])
        assert (cls["icu_ka"], cls["ics_ka"]) == (ds["icu_ka"], ds["ics_ka"]), art
        r = select(ib_a=ds["in_a"], fault_ka=ds["icu_ka"], ambient_c=40, frame=ds["frame"])
        assert r.value["article_no"] == art and r.value["confirmed"] is True, (art, r.value["article_no"])
