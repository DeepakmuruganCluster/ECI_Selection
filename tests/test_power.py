from _answers import ASK, complete
from pathlib import Path

import pytest
import yaml

from components.power.select import select
from core import golden
from core.provenance import ProvenanceError, load_sourced_table

HERE = Path(__file__).resolve().parents[1] / "components" / "power"
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
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks}
    assert set(rules) <= used, set(rules) - used


def test_exports_follow_the_company_template():
    """Owner 2026-10-15: power in the layout of Switchgear_Selection_Calculation.xls (OWN-SWG-CALC)."""
    import tempfile
    from core.bom_export import build_requirement
    from core.xlsx import read_any
    data, _ = build_requirement(complete(text="2 x 11 kW pumps DOL, 30 m cable, 400 V, 25 kA", panel_internal_c=40, cable_ambient_c=30,
                                     plc_make="siemens_s71200g2", spd=False, pmr=False, control_supply="transformer", **ASK, confirmed=True))
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        f.write(data)
        f.flush()
        sheet = read_any(f.name)["Power"]
    flat = [" ".join(map(str, r)) for r in sheet]
    assert any("Power calculation and main switchgear selection" in x for x in flat)
    head = next(r for r in sheet if r and r[0] == "Sl.no" and "AC load" in r)
    assert head[:8] == ["Sl.no", "AC load", "Description", "Phase", "Min voltage", "Max voltage", "Power (kW)", "Current (A)"]
    assert head[10:13] == ["L1 (A)", "L2 (A)", "L3 (A)"]
    assert any("Load current with FOS 1.5" in x for x in flat) and any("SMPS selection" in x for x in flat)
    assert any("Grand total (A) with FOS 1.25" in x for x in flat) and any(x.startswith("Power requirement") for x in flat)
    assert any("3RV2021-4DA10" in x for x in flat)          # the pumps' MPCB as their protection device
