from pathlib import Path

import pytest
import yaml

from components.panel.select import select
from core import golden
from core.provenance import ProvenanceError, load_sourced_table

HERE = Path(__file__).resolve().parents[1] / "components" / "panel"
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


def test_bom_comes_only_from_component_results():
    """Every BOM article must be an article some component returned (the assembly adds no data)."""
    from components.panel.select import select
    r = select(load_list="M1 7.5 DOL flc=15.5 cable=50\nF1 37 VFD flc=66 cable=250 qty=2 standby=1",
               fault_ka=50, panel_internal_c=45, motor_pf=0.85, cable_ambient_c=40, site_ambient_c=35)
    arts = {b["article"]: b["qty"] for b in r.value["bom"]}
    assert arts["3RV2021-4BA10"] == 1 and arts["3RT2027-1AP00"] == 1
    assert arts["6SL3210-1PE27-5UL0"] == 2
    assert arts["6SE6400-3TC07-5ED0"] == 4          # 2 drives × 2 output reactors in series (250 m)
    assert arts["3NA3830"] == 6          # owner 2026-10-20, R-VFD-17: a fuse in each line conductor (SIE-PM240-2 Fig. 4-5) × 2 drives



def test_control_unit_bop_and_memory_card_reach_the_bom():
    from components.panel.select import select
    r = select(load_list="F1 37 VFD flc=66 cable=50 qty=2 standby=1", fault_ka=50, panel_internal_c=45, motor_pf=0.85,
               cable_ambient_c=40, cu_encoder=False, cu_safety="sto", cu_fieldbus="profinet", mc_copy_parameters=True)
    arts = {b["article"]: b["qty"] for b in r.value["bom"]}
    assert arts["6SL3244-0BB12-1FA0"] == 2 and arts["6SL3255-0AA00-4CA1"] == 2 and arts["6SL3054-4AG00-2AA0"] == 2
    assert not any("Control Unit" in n for n in r.value["not_selected"])


def test_heavy_duty_line_gets_the_ho_rating():
    """R-PNL-11: duty=heavy → HO 75 kW 6SL3210-1PE31-8UL0 (SIE-PM240-2 p.105); default → LO 75 kW 6SL3210-1PE31-5UL0."""
    base = dict(fault_ka=25, panel_internal_c=40, motor_pf=0.86, cable_ambient_c=30)
    heavy = select(load_list="C1 75 VFD cable=50 duty=heavy", **base)
    normal = select(load_list="C1 75 VFD cable=50", **base)
    assert "6SL3210-1PE31-8UL0" in [b["article"] for b in heavy.value["bom"]]
    assert "6SL3210-1PE31-5UL0" in [b["article"] for b in normal.value["bom"]]


def test_design_logic_holds_every_component_check():
    r = select(load_list="M1 7.5 DOL flc=15.5 cable=50\nF1 37 VFD flc=66 cable=50", fault_ka=50, panel_internal_c=45,
               motor_pf=0.85, cable_ambient_c=40)
    comps = {(d["tag"], d["component"]) for d in r.value["design_logic"]}
    assert {("M1", "motor_flc"), ("M1", "dol_starter"), ("M1", "cable"), ("F1", "vfd"), ("F1", "cable")} <= comps


def test_star_delta_line_uses_the_company_kit():
    r = select(load_list="C1 30 SD", fault_ka=25, panel_internal_c=40, motor_pf=0.86, cable_ambient_c=30)
    arts = {b["article"]: b["qty"] for b in r.value["bom"]}
    assert arts == {"LC1E50": 2, "LC1E40M7": 1, "LRE32": 1, "2ASDT0": 1, "LAEN22": 3}
    assert any(o["rule"] == "R-PNL-12" for o in r.value["open_points"])


def test_company_dol_kit_replaces_the_siemens_starter():
    r = select(load_list="M1 5.5 DOL cable=30", fault_ka=25, panel_internal_c=40, motor_pf=0.86, cable_ambient_c=30,
               dol_source="company")
    arts = {b["article"] for b in r.value["bom"]}
    assert {"GZ1E16", "LC1E18", "GZ1AN11", "LAEN22"} <= arts and not any(a.startswith("3RV") for a in arts)


def test_kit_accessories_with_siemens_starter():
    r = select(load_list="M1 5.5 DOL cable=30 qty=2", fault_ka=25, panel_internal_c=40, motor_pf=0.86, cable_ambient_c=30,
               kit_accessories=True)
    arts = {b["article"]: b for b in r.value["bom"]}
    assert any(a.startswith("3RV") for a in arts) and "GZ1AN11" not in arts and "LAEN22" not in arts
    assert arts["XB7EV03MPN"]["qty"] == 2 and arts["XB7EV03MPN"]["unit_price_inr"] == 127.93935
    assert arts["KUT4"]["qty"] == 2 * (3 + 10)   # power 3 + control 10 per feeder
    assert any(o["rule"] == "R-PNL-14" and "auxiliary contacts" in o["point"] for o in r.value["open_points"])
    assert not any(o["rule"] == "R-KIT-03" for o in r.value["open_points"])
