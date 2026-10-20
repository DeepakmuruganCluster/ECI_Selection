"""Interdependency audit 2026-10-17 (owner: "fix it"): a BOM or power edit reaches everything worked out from it."""
from _answers import ASK, ask
from components.requirement.select import select
from _answers import auto as _auto
select = _auto(select)    # audit 2026-10-17: per-case questions answered the old way

BASE = ask(text="crusher 160 kW star delta, conveyor 11 kW DOL, 2 x 5.5 kW pumps DOL, fan 30 kW VFD, Siemens S7-1200 PLC",
            confirmed=True, voltage_v=400, fault_ka=25, panel_internal_c=40, cable_ambient_c=40, cable_m=50, cu_encoder=False,
            cu_safety="none", cu_fieldbus="profinet", mc_copy_parameters=False, plc_make="siemens_s71200g2", spd=True,
            spd_make="siemens", pmr=True, control_supply="transformer", coil_va=10, lamp_va=1)


def run(**ch):
    r = select(**{**BASE, **ch})
    return r, r.value


def line(v, art):
    b = next(b for b in v["bom"] if b["article"] == art)
    return {"group": b["group"], "article": b["article"], "description": b["description"]}


def test_replaced_mpcb_reaches_the_power_calculation_and_the_feeder_text():
    _, b = run()
    _, v = run(edits=[{"action": "replace", "line": line(b, "3RV2011-4AA10"), "article": "3RV2011-4BA10", "description": "MPCB 14 … 20 A"}])
    prot = {r["tag"]: r["protection"] for r in v["power"]["three_phase"]}
    assert prot["M3"].startswith("3RV2011-4BA10")
    assert "3RV2011-4BA10 (edited)" in next(f["devices"] for f in v["feeders"] if f["tag"] == "M3")


def test_replaced_smps_and_incomer_reach_the_value_and_power():
    _, b = run()
    inc, sm = next(x for x in b["bom"] if x["group"] == "Incomer"), next(x for x in b["bom"] if x["group"] == "Control power")
    r, v = run(edits=[{"action": "replace", "line": line(b, inc["article"]), "article": "3VA2340-5HL32-0AA0", "description": "3VA2 400 A"},
                      {"action": "replace", "line": line(b, sm["article"]), "article": "S8VK-S12024", "description": "S8VK-S12024"}])
    assert v["incomer"] == "3VA2340-5HL32-0AA0" and v["incomer_in_a"] is None          # rating not held: never guessed
    assert any(c.verdict == "warn" and "rating is not in the held data" in c.value for c in r.checks)
    assert v["smps"] == "S8VK-S12024"
    assert (v["power"]["dc"]["supply"], v["power"]["dc"]["available_a"]) == ("S8VK-S12024", 5.0)    # rating from the held SMPS table


def test_relay_qty_edit_reaches_the_relay_count_and_the_trace():
    _, b = run()
    rel = next(x for x in b["bom"] if "relay" in x["description"].lower() and x["group"] == "Control and signalling")
    _, v = run(edits=[{"action": "qty", "line": line(b, rel["article"]), "qty": 10}])
    assert v["qty_relays"] == 10
    t = next(t for t in v["io_trace"] if t["used_in"] == "interface relays (one per output)")
    assert t["ok"] is False and "10 relay(s)" in t["value"]


def test_removed_contactor_is_flagged_and_coils_follow():
    _, b = run()
    r, v = run(edits=[{"action": "remove", "line": line(b, "3RT2027-1AP00")}])
    assert any(c.verdict == "warn" and "M2 has no contactor" in c.value for c in r.checks)
    assert "3RT2027-1AP00 (removed)" in next(f["devices"] for f in v["feeders"] if f["tag"] == "M2")


def test_power_edit_lowering_the_load_makes_the_incomer_smaller():
    _, b = run()
    _, v = run(power_edits=[{"action": "set", "key": "M1", "running": 0}])
    assert b["incomer_in_a"] == 630 and v["incomer_in_a"] < 630 and v["incomer_ib_a"] < b["incomer_ib_a"]
    assert any(x["group"] == "Incomer" and x["article"] == v["incomer"] for x in v["bom"])


def test_soft_starter_line_contactor_is_a_coil():
    r, v = select(text="75 kW crusher soft starter, Siemens S7-1200 PLC", **{k: x for k, x in BASE.items() if k != "text"},
                  ss_protection="fuse_gg"), None
    assert any(c.rule == "R-REQ-19" and c.value.startswith("1 contactor coil") for c in r.checks)
