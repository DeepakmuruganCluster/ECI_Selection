"""Power edits wired through the requirement and the project (R-PWR-11, R-REQ-23, R-PRJ-15) — audit 2026-10-15."""
from _answers import ASK
from components.project.select import select as project
from _answers import with_opts as _with_opts, OPTS
project = _with_opts(project)    # R-PRJ-20: the old options, given explicitly
from components.requirement.select import select as requirement
from _answers import auto as _auto
requirement = _auto(requirement)    # audit 2026-10-17: per-case questions answered the old way
from core import bom_edit

TEXT = "75 kW conveyor with VFD, 50 m cable; 2 x 11 kW pumps DOL, 30 m cable. 400 V, 25 kA, site 35 °C, PROFINET, STO, energy meter"
KW = dict(text=TEXT, confirmed=True, panel_internal_c=40, cu_encoder="false", mc_copy_parameters="true", ct_make="rishabh",
          plc_make="siemens_s71200g2", spd=False, pmr=False, control_supply="transformer", **ASK)
PRJ = dict(panel="BIO_UF", fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, default_cable_m=50)


def rows(p):
    return {r["key"]: r for r in p["ac_rows"]}


def test_machine_control_circuit_is_line_to_line_on_two_lines():
    p = requirement(**KW).value["power"]
    c = rows(p)["control"]
    assert c["connection"] == "LL" and c["lines"].count("L") == 2
    assert sum(c[k] is not None for k in ("l1", "l2", "l3")) == 2
    assert "transformer losses not included" in c["description"]


def test_machine_edit_moves_control_circuit_to_l2_and_adds_a_load():
    edits = [{"action": "set", "key": "control", "connection": "LN", "phase": "L2"},
             {"action": "add", "key": "fan", "name": "panel fan", "va": 60, "connection": "LN", "phase": "L1"}]
    r = requirement(**KW, power_edits=edits)
    p = r.value["power"]
    c, fan = rows(p)["control"], rows(p)["fan"]
    assert c["lines"] == "L2" and c["l1"] is None and c["l3"] is None
    assert fan["added"] and fan["lines"] == "L1"
    assert p["edits_applied"]
    assert any(o["rule"] == "R-PWR-11" for o in r.value["open_points"])
    assert edits[0]["phase"] == "L2"            # the caller's edit is not changed


def test_machine_edit_naming_no_load_keeps_the_design():
    r = requirement(**KW, power_edits=[{"action": "set", "key": "nope", "i_a": 1}])
    assert r.status != "invalid" and r.value["selected"]
    assert r.value["power"] is None and "nope" in r.value["power_error"]


def test_machine_remove_and_running_units():
    base = requirement(**KW).value["power"]
    p = requirement(**KW, power_edits=[{"action": "remove", "key": "smps"}, {"action": "set", "key": "M2", "running": 1}]).value["power"]
    assert "smps" not in rows(p)
    assert rows(p)["M2"]["current_a"] < rows(base)["M2"]["current_a"]


def test_project_unselected_feeders_are_listed_not_hidden():
    p = project(**PRJ).value["power_calc"]["ac3"]
    assert any("no current to count" in x for x in p["not_counted"])
    assert not any("see the 230 V AC rows" in x for x in p["not_counted"])


def test_project_power_edits_saved_and_undone(tmp_path, monkeypatch):
    f = tmp_path / "overrides.yaml"
    f.write_text("edits: []\n")
    monkeypatch.setattr(bom_edit, "_file", lambda project: f)
    rec = bom_edit.power_save(None, "BIO_UF", {"action": "set", "key": "control", "connection": "LN", "phase": "L3"})
    assert bom_edit.load_power(None, "BIO_UF") == [{"action": "set", "key": "control", "connection": "LN", "phase": "L3"}]
    p = project(**PRJ).value["power_calc"]["ac3"]
    assert rows(p)["control"]["lines"] == "L3"
    bom_edit._save(None, [])                      # BOM edits saved later keep the power edits
    assert bom_edit.power_list(None)
    assert bom_edit.power_undo(None, rec["id"]) and not bom_edit.power_list(None)


def test_project_bad_power_edit_is_reported_not_crashed():
    v = project(**PRJ, power_edits=[{"action": "set", "key": "nope", "i_a": 1}]).value["power_calc"]
    assert v["ac3"] is None and "nope" in v["ac3_error"]
