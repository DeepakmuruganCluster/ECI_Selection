from pathlib import Path

import pytest
import yaml

from components.plc.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "plc"
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


def test_data_equals_the_workbooks():
    """G6: every CPU and module row equals its workbook row (re-read here, independently of the import script)."""
    import re
    from components.plc.select import _cpus, _modules
    from core.xlsx import read_any
    src = Path(__file__).resolve().parents[1] / "sources" / "pdf" / "own" / "autobom"
    amp = lambda v: float(re.search(r"[\d.]+", str(v)).group())
    db = read_any(src / "PLC db.xlsx")["db"]
    head = [str(h).strip() if h else "" for h in db[0]]
    for r in _cpus()["rows"]:
        line = dict(zip(head, db[r["row"] - 1]))
        assert line["Model Number"] == r["model"] and float(line["Digital Inputs"]) == r["di"]
        assert amp(line["Current Consumption, 5VDC"]) == r["i5_a"] and float(line["Max Ext Mod"]) == r["max_ext"]
    dio = read_any(src / "PLC IO_db.xlsx")["db_DIO"]
    head = [str(h).strip() if h else "" for h in dio[0]]
    for m in _modules()["rows"]:
        line = dict(zip(head, dio[m["row"] - 1]))
        assert line["Model Number"] == m["model"] and amp(line["Current Consumption, 5VDC"]) == m["i5_a"]


def test_every_module_is_cp2e_compatible_as_recorded():
    from components.plc.select import _modules
    assert all("CP2E" in m["series_ok"] for m in _modules()["rows"])
