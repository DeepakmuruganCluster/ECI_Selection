from pathlib import Path

import pytest
import yaml

from components.load_list.select import select
from components.panel.select import parse
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "load_list"
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


@pytest.mark.parametrize("panel", ["all", "BIO_UF", "RO"])
@pytest.mark.parametrize("kw", [{}, {"default_cable_m": 50, "standby_per_group": 1}])
def test_load_list_parses_in_the_panel_format(panel, kw):
    r = select(panel=panel, **kw)
    loads = parse(r.value["load_list"])
    assert len(loads) == r.value["n_rows"]
    assert sum(ld["qty"] for ld in loads) == r.value["n_units"]
    assert all(ld["flc"] is None for ld in loads)                    # R-LL-06: client Amps never passed as flc=
    assert all((ld["cable_m"] is not None) == ("default_cable_m" in kw) for ld in loads)   # R-LL-07
    for p, text in r.value["load_lists"].items():
        assert len(parse(text)) == sum(1 for o in r.value["rows"] if o["panel"] == p)


def test_every_row_cites_a_table_and_row():
    rows = select(panel="all").value["rows"]
    assert all(o["source"].startswith("table ") and " row " in o["source"] for o in rows)
    assert len({o["tag"] for o in rows}) == len(rows)
