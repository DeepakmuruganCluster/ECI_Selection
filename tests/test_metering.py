import re
from pathlib import Path

import pytest
import yaml

from components.metering.select import _ct_rows, _designation, _ltrp, _selec, _tw, select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "metering"
RESULTS = golden.run(HERE / "golden" / "cases.yaml", select)
RULES = yaml.safe_load((HERE / "rules.yaml").read_text())


@pytest.mark.parametrize("case,res,diffs", RESULTS, ids=[c["id"] for c, _, _ in RESULTS])
def test_golden(case, res, diffs):
    assert not diffs, f"{case['id']} ({case['oracle']}): {diffs}\n{res.trace()}"


def test_every_rule_in_code_is_in_the_rule_sheet():
    used = {c.rule for _, r, _ in RESULTS for c in r.checks} - {"INPUT"}
    assert used <= set(RULES["rules"]), used - set(RULES["rules"])


def test_every_rule_is_exercised_by_a_golden_case():
    used = {c.rule for _, r, _ in RESULTS for c in r.checks}
    assert set(RULES["rules"]) <= used, set(RULES["rules"]) - used


def test_every_rule_has_an_authority():
    assert {r["authority"] for r in RULES["rules"].values()} <= {"MFR", "PHYS", "RULE", "CLIENT"}


def test_ct_rows_are_consistent():
    """Every CT row has a known class, a positive VA and a window; sizes keep one window each."""
    order = RULES["params"]["class_order"]
    for make, rows in _ct_rows().items():
        windows = {}
        for r in rows:
            assert r["class"] in order and r["va"] > 0 and r["primary_a"] > 0, r
            w = (r["window"], r.get("window_d_mm"), r.get("window_w_mm"), r.get("window_h_mm"))
            assert windows.setdefault((r["family"], r["size"]), w) == w, r
    assert (len(_ltrp()["rows"]), len(_tw()["rows"]), len(_selec()["rows"])) == (72, 146, 65)


def test_selec_type_codes_reproduce_the_printed_examples():
    """The type code is assembled from the nomenclature: it must give back the codes printed as table titles."""
    printed = {"SPCT-100/60-500/5A-VA5-CL1-CE", "SPCT-140/100-800/5A-VA15-CL0.5-CE", "SPCT-62/40-100/5A-VA1-CL1-CE",
               "SPCT-50/30-60/5A-VA1-CL5-CE", "TWCT-T-D110-800/5A-VA10-CL0.5", "TWCT-T-D65-500/5A-VA5-CL1",
               "TWCT-T-D120-1000/5A-VA10-CL0.5", "TWCT-T-D35-30/5A-VA1.5-CL5", "TWCT-T-D55-150/5A-VA5-CL1"}
    made = {_designation(r) for r in _ct_rows()["selec"]}
    assert printed <= made, printed - made


def test_lead_burden_hand_calculation():
    r = select(circuit_a=630, ct_make="rishabh", busbar_w_mm=60, busbar_t_mm=10, lead_length_m=5, lead_mm2=2.5,
               lead_temp_c=20, ambient_c=35)
    assert r.value["lead_burden_va"] == pytest.approx(2 * 5 * 25 / 58 / 2.5, abs=1e-3)   # 0.862 VA at 20 °C


def test_wns2503_incomer_meter_and_module():
    r = select(circuit_a=630, ct_make="rishabh")
    assert r.value["meter"] == "SENTRON PAC3220" and r.value["comm_module"] == "7KM9300-0AE02-0AA0"
    assert re.fullmatch(r"7KM3220-\w+-\w+", r.value["meter_article_example"])
