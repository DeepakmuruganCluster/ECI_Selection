from pathlib import Path

import pytest
import yaml

from components.project.select import select
from _answers import with_opts as _with_opts, OPTS
_plain = select
select = _with_opts(select)    # R-PRJ-20: the old options, given explicitly
from core import golden
from core.provenance import ProvenanceError, load_sourced_table

HERE = Path(__file__).resolve().parents[1] / "components" / "project"
RESULTS = golden.run(HERE / "golden" / "cases.yaml", _plain)


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


def test_every_decision_option_runs():
    from components.project.select import DECISIONS, select
    base = dict(panel="RO", fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, default_cable_m=50)
    for key, (_, opts) in DECISIONS.items():
        for val, _label in opts:
            r = select(**base, **{key: val})
            assert r.status != "invalid", (key, val)


def test_cu_option_swaps_the_control_unit():
    from components.project.select import select
    base = dict(panel="BIO_UF", fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, default_cable_m=50,
                **{k: v for k, v in OPTS.items() if k != "cu_safety"})
    a = {l["article"] for l in select(**base, cu_safety="sto").value["bom"]}
    b = {l["article"] for l in select(**base, cu_safety="none").value["bom"]}
    assert "6SL3244-0BB12-1FA0" in a and "6SL3243-0BB30-1FA0" in b and "6SL3244-0BB12-1FA0" not in b



def test_power_calculation_section_adds_up():
    """R-PRJ-15: the power calculation lines sum to the 24 V load the BOM check uses; open lines stay open."""
    from components.project.select import select
    for panel in ("BIO_UF", "RO"):
        v = select(panel=panel, fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40,
                   default_cable_m=50, **OPTS).value
        d = v["power_calc"]["dc24"]
        assert abs(sum(r["total"] for r in d["rows"] if r["total"] is not None) - d["subtotal_a"]) < 1e-6
        assert abs(d["subtotal_a"] - v["load_24v_a"]) < 1e-3
        assert abs(d["required_a"] - round(d["subtotal_a"] * d["factor"], 3)) < 1e-6
        assert all(r["source"] for r in d["rows"])
        assert all((r["total"] is None) == (r["per_unit"] is None) for r in d["rows"] if r["qty"] is not None)


@pytest.mark.parametrize("family", ["s7-200smart", "s7-1200g2"])
def test_project_plc_works_for_every_siemens_family(monkeypatch, family):
    """Test-agent finding 2026-10-14 (HIGH): only ET 200SP parts carry 'qty' and 'i24_a'; with a compact family the
    project BOM crashed (KeyError) or took 0 A. A compact PLC that fits (20 DI / 10 DO) must give its parts and 24 V."""
    from core import project as P
    import components.project.select as prj
    from components.plc.select import select as plc
    monkeypatch.setattr(prj, "plc_select", lambda **k: plc(di=20, do=10, make="siemens", family=family))
    proj = P.names()[0]
    r = prj.select(project=proj, panel=P.panels(proj)[0], **(P.load(proj).get("design_inputs") or {}),
                   fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, default_cable_m=50, **OPTS)
    assert r.status in ("ok", "warning"), r.trace()
    assert r.value["plc_i24_a"] > 0
    assert any(b["group"] == "PLC" for b in r.value["bom"])
