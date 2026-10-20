from pathlib import Path

import pytest
import yaml

from components.control_power.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "control_power"
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


def test_smps_data_equals_the_workbook():
    """G6: every supply row equals its workbook row (re-read here independently of the import script)."""
    import re
    from components.control_power.select import _smps
    from core.xlsx import read_any
    book = read_any(Path(__file__).resolve().parents[1] / "sources" / "pdf" / "own" / "autobom" / "SMPS db.xlsx")
    rows = _smps()["rows"]
    assert len(rows) == 197
    for r in rows:
        sheet = book[r["sheet"]]
        head = [str(h).strip() if h else "" for h in sheet[0]]
        line = dict(zip(head, sheet[r["row"] - 1]))
        cell = line["Model Number"]
        cell = str(int(cell)) if isinstance(cell, float) and cell.is_integer() else str(cell).strip()
        assert cell == r["model"], (r["sheet"], r["row"])  # numeric order numbers (Phoenix, Weidmueller) kept whole
        assert float(re.search(r"[\d.]+", str(line["Secondary rated current"])).group()) == r["i_out_a"], r["model"]
