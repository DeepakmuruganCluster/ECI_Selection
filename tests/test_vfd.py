from pathlib import Path

import pytest
import yaml

from components.vfd.select import select
from core import golden
from core.provenance import ProvenanceError, load_sourced_table

HERE = Path(__file__).resolve().parents[1] / "components" / "vfd"
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


def test_every_module_has_reactor_assignments():
    from components.vfd.select import _modules, _reactors, _stem
    rx = _reactors()["rows"]
    for m in _modules()["rows"]:
        assert any(r["kind"] == "output" and r["module"] == _stem(m["order_no"]) for r in rx), m["order_no"]
        if m["frame"] in ("FSA", "FSB", "FSC"):
            assert any(r["kind"] == "line" and r["module"] == _stem(m["order_no"]) for r in rx), m["order_no"]



def test_fuse_in_manual_matches_protective_devices_document():
    """Two Siemens documents must agree: PM240-2 manual fuse = Protective Devices fuse, for every module."""
    from components.vfd.select import _modules, _protection, _stem
    fuses = {r["module"]: r for r in _protection()["rows"] if r["type"] == "fuse"}
    for m in _modules()["rows"]:
        f = fuses[_stem(m["order_no"])]
        assert (f["article"], f["max_a"]) == (m["fuse"], m["fuse_a"]), m["order_no"]


def test_company_database_matches_the_siemens_manual():
    """ECI-VFD-Selection database.xlsx (own) vs PM240-2 manual data (Siemens): every 400 V FSA–FSF module."""
    from components.vfd.select import _modules
    from core.provenance import SOURCES, register
    from core.xlsx import read_any
    rows = read_any(SOURCES / register()["OWN-VFD-DB"]["file"])["Power module"]
    head = rows[0]
    col = {h: i for i, h in enumerate(head)}
    num = lambda s: float(str(s).split()[0])
    db = {}
    for r in rows[1:]:
        if r and r[col["Child part series"]] == "PM240-2" and r[col["Voltage min"]] == "380 V":
            db[str(r[col["Part number"]]).replace(" ", "")] = r
    checked = 0
    for m in _modules()["rows"]:
        for art in (m["order_no"], m["order_no_c2"]):
            r = db[art]
            assert (num(r[col["Rated power LO"]]), num(r[col["Output current LO"]]),
                    num(r[col["Rated power HO"]]), num(r[col["Output current HO"]]), r[col["Frame size"]]) == \
                   (m["lo_kw"], m["lo_out"], m["ho_kw"], m["ho_out"], m["frame"]), art
            checked += 1
    assert checked == 42


def test_company_control_unit_data_matches_the_database_file():
    from components.vfd.select import _own_cu
    from core.provenance import SOURCES, register
    from core.xlsx import read_any
    rows = read_any(SOURCES / register()["OWN-VFD-DB"]["file"])["Control Unit"]
    by_row = {i + 1: r for i, r in enumerate(rows)}
    for cu in _own_cu()["rows"]:
        r = by_row[cu["row"]]
        assert (r[3], r[4]) == (cu["series"], cu["article"]), cu["row"]


def test_bom_follows_the_vfd_selector_structure():
    """Same order and categories as ECI-VFD-Selection: Power Module → Control Unit → Memory Card → Operator Panel."""
    from components.vfd.select import select
    r = select(kw=37, flc_a=66, flc_basis="nameplate", ambient_c=45, cable_m=250, fault_ka=50, cu_encoder=False,
               cu_safety="sto", cu_fieldbus="profinet", mc_copy_parameters=True)
    b = r.value["vfd_bom"]
    assert [x["category"] for x in b[:4]] == ["Power Module", "Control Unit", "Memory Card", "Operator Panel"]
    assert [x["part_number"] for x in b[:4]] == ["6SL3210-1PE27-5UL0", "6SL3244-0BB12-1FA0", "6SL3054-4AG00-2AA0",
                                                 "6SL3255-0AA00-4CA1"]
    assert all(x["qty"] == 1 for x in b[:4])
    assert b[-1]["category"] == "Output reactor" and b[-1]["qty"] == 2
