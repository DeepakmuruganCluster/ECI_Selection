from _answers import ASK, complete, ask, answered
from pathlib import Path

import pytest
import yaml

from components.requirement.select import select
from _answers import auto as _auto
_plain = select
select = _auto(select)    # audit 2026-10-17: per-case questions answered the old way
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "requirement"
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


TEXT = ("I need a control panel for a 75kW special purpose conveyor system, IP54, outdoor installation in Germany, "
        "budget under €8,000.")


def test_every_fact_points_at_its_words():
    """R-REQ-01: the highlighted words are exactly what the fact was read from."""
    r = select(text=TEXT)
    for f in r.value["facts"]:
        if f["how"] in ("read", "suggested"):
            assert TEXT[f["start"]:f["end"]].strip() == f["from"], f


def test_nothing_runs_without_confirmation():
    full = dict(text=TEXT, starter="VFD", voltage_v=400, fault_ka=25, panel_internal_c=40, cable_ambient_c=30,
                motor_pf=0.86, cable_m=50, cu_encoder=False, cu_safety="sto", cu_fieldbus="profinet",
                mc_copy_parameters=True, plc_make="other", plc_24v_a=2, spd=False, pmr=False, control_supply="transformer", **ASK)
    assert not select(**full).value["selected"]
    r = select(**full, confirmed=True)
    assert r.value["selected"] and [x["category"] for x in r.value["vfd_bom"]][:4] == [
        "Power Module", "Control Unit", "Memory Card", "Operator Panel"]


def test_confirmed_with_questions_left_does_not_run():
    r = select(text=TEXT, confirmed=True)
    assert not r.value["selected"] and r.value["n_questions"] == 20   # power factor no longer asked (R-REQ-20); control supply (CC-1), the R-REQ-32 questions and the incomer series (R-REQ-34) asked


def test_budget_and_enclosure_are_recorded_not_used():
    uses = {x["fact"]: x["use"] for x in select(text=TEXT).value["recorded"]}
    assert "price" in uses["Budget"] and "out of scope" in uses["IP rating"] and "voltage" in uses["Country"]


def test_document_pack_has_every_step():
    """Documents step: requirement, BOM, VFD BOM, I/O list, design logic, open points and the sources cited."""
    from core.bom_export import build_requirement
    from core.xlsx import read_any
    import tempfile
    inputs = dict(text=TEXT, starter="VFD", voltage_v=400, fault_ka=25, panel_internal_c=40, cable_ambient_c=30,
                  motor_pf=0.86, cable_m=50, cu_encoder=False, cu_safety="sto", cu_fieldbus="profinet",
                  mc_copy_parameters=True, plc_make="other", plc_24v_a=2, spd=False, pmr=False, control_supply="transformer", **ASK, confirmed=True)
    data, stats = build_requirement(inputs)
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        f.write(data)
        f.flush()
        book = read_any(f.name)
    assert list(book) == ["Requirement", "Drawing index", "BOM (drawing format)", "BOM", "VFD BOM", "Power", "Inputs", "Outputs",
                          "Bus and STO", "I-O trace", "Design logic", "Not selected", "Open points", "Wiring conventions", "Sources"]
    assert [r[1] for r in book["Inputs"][1:]] == ["I_EmergencyStop", "I_Reset"]          # VFD on the bus: panel signals only
    assert [r[1] for r in book["Outputs"][1:]] == ["O_GeneralTrip", "O_GeneralWarning"]
    assert [r[1] for r in book["Bus and STO"][1:]] == ["PN_M1", "O_M1_STO"]
    assert all(r[4] == "yes" for r in book["I-O trace"][1:])
    refs = [row[0] for row in book["Sources"][1:]]
    assert "SIE-PM240-2" in refs and "SIE-G120-PROT" in refs
    assert [row[3] for row in book["VFD BOM"][1:5]] == ["6SL3210-1PE31-8UL0", "6SL3244-0BB12-1FA0",
                                                         "6SL3054-4AG00-2AA0", "6SL3255-0AA00-4CA1"]


def test_document_pack_refuses_before_confirmation():
    from core.bom_export import build_requirement
    with pytest.raises(ValueError):
        build_requirement(dict(text=TEXT))


MULTI = "75 kW conveyor with VFD, 50 m cable; 2 x 11 kW pumps DOL, 30 m cable. 400 V, 25 kA, PROFINET, STO, energy meter"


def test_whole_panel_uses_every_built_component():
    """R-REQ-07 … 13: feeders, I/O list, relays, terminals, internal wiring, incomer, metering, blocked list."""
    r = answered(select, text=MULTI, panel_internal_c=40, cable_ambient_c=30, motor_pf=0.86, cu_encoder=False,
               mc_copy_parameters=True, ct_make="rishabh", plc_make="other", plc_24v_a=2, spd=True, spd_make="Phoenix", pmr=True, control_supply="transformer",
               confirmed=True)
    groups = {b["group"] for b in r.value["bom"]}
    assert groups == {"Feeders", "Motor cables", "Control and signalling", "Internal wiring", "Incomer", "Metering",
                      "Control power", "Auxiliary switchgear", "Feeder accessories", "Control circuit",
                      "Not selected"}  # PLC: 'other' make
    comps = {d["component"] for d in r.value["design_logic"]}
    assert {"motor_flc", "vfd", "dol_starter", "cable", "io_list", "control_signalling", "internal_wiring", "mccb",
            "metering", "control_power", "aux_switchgear", "control_circuit"} <= comps
    assert len([b for b in r.value["bom"] if b["group"] == "Not selected"]) == 4   # soft starter built 2026-10-14


def test_motor_answers_apply_to_their_motor_only():
    r = select(text="75 kW conveyor with VFD; 2 x 11 kW pumps DOL. 400 V, 25 kA",
               motors=[{"cable_m": 50}, {"cable_m": 30}])
    assert [m["cable_m"] for m in r.value["motors"]] == [50, 30]


def test_shared_fact_applies_to_every_motor():
    """R-REQ-09: 'All with VFD' in a part without kW applies to both motors."""
    r = select(text="A 75 kW conveyor and a 90 kW pump. All with VFD.")
    assert [m["starter"] for m in r.value["motors"]] == ["VFD", "VFD"]


def test_word_quantity_is_read():
    r = select(text="two 11 kW pumps with DOL")
    assert r.value["qty"] == 2


def test_multi_motor_document_pack_has_a_block_per_drive():
    from core.bom_export import build_requirement
    from core.xlsx import read_any
    import tempfile
    data, _ = build_requirement(dict(text="2 x 15 kW pumps VFD, 40 m cable; 37 kW fan VFD, 60 m cable. 400 V, 25 kA, "
                                          "PROFINET, STO", panel_internal_c=40, cable_ambient_c=30, motor_pf=0.86,
                                     cu_encoder=False, mc_copy_parameters=True, plc_make="other", plc_24v_a=2, spd=False, pmr=False, control_supply="transformer", **ASK,
                                     confirmed=True))
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        f.write(data)
        f.flush()
        vfd = read_any(f.name)["VFD BOM"]
    assert [row[0] for row in vfd[1:] if row[0]] == ["M1", "M2"]


def test_design_log_becomes_a_sheet():
    from core.bom_export import build_requirement
    from core.xlsx import read_any
    import tempfile
    log = [{"when": "2026-10-12 09:18", "step": "Whole panel · 24 V DC supply", "action": "changed 24 V supply make = Weidmueller",
            "detail": "added Weidmueller 2838500000; removed Omron S8VK-G01524"}]
    data, _ = build_requirement(complete(text="2 x 11 kW pumps DOL, 30 m cable, 400 V, 25 kA", panel_internal_c=40,
                                     cable_ambient_c=30, motor_pf=0.85, plc_make="omron", spd=False, pmr=False, control_supply="transformer", **ASK,
                                     confirmed=True), design_log=log)
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        f.write(data)
        f.flush()
        book = read_any(f.name)
    assert list(book)[1] == "Design log" and book["Design log"][1][2] == "changed 24 V supply make = Weidmueller"
    dbom = book["BOM (drawing format)"]
    assert dbom[0][:8] == ["S.NO", "DESCRIPTION", "TAG NAME", "PART NO.", "SAP PART CODE", "MAKE", "QTY", "UOM"]
    assert any(r[2] == "Q1-Q2" and r[3].startswith("3RV") for r in dbom[1:])          # 2 MPCBs → Q1-Q2
    assert any(r[3] == "XB7EV03MPN" and r[4] == "AVELCAILGREEN" for r in dbom[1:])       # SAP code from the sample
    assert any(r[1] == "PLC" and r[2] == "CP2E-N20DT1-D" and r[4] == "Omron" for r in book["BOM"][1:])   # section, group, article, description, make


def test_drawing_bom_tags_follow_the_company_legend():
    """160 kW star-delta with the company kit: contactors K1-K2 / K3, MCCB 1SQ1 (legend p.3; sample BOM p.14)."""
    from core.bom_export import drawing_bom
    bom = [{"group": "Incomer", "article": "LV540306", "description": "Incomer MCCB 3VM", "qty": 1, "unit": "no", "source": "x"},
           {"group": "Feeders", "article": "LC1E250M5", "description": "Power Contactor 250A (SCHNEIDER, company kit)", "qty": 2,
            "unit": "no", "source": "company kit (feeder_kit)"},
           {"group": "Feeders", "article": "LC1E200M5", "description": "Power Contactor 200A (SCHNEIDER, company kit)", "qty": 1,
            "unit": "no", "source": "company kit (feeder_kit)"}]
    rows = drawing_bom(bom)
    assert [r[2] for r in rows[1:]] == ["1SQ1", "K1-K2", "K3"]
    assert rows[1][4] == "AVELCAMCCB3614" and rows[3][4] == "AVELCAPCTR200A"


def test_not_selected_is_one_complete_list():
    r = answered(select, text=MULTI, panel_internal_c=40, cable_ambient_c=30, motor_pf=0.86, cu_encoder=False,
               mc_copy_parameters=True, ct_make="rishabh", plc_make="other", plc_24v_a=2, spd=True, spd_make="Phoenix",
               pmr=True, control_supply="transformer", confirmed=True)
    cats = {x["category"] for x in r.value["not_selected_detail"]}
    assert cats == {"component not built", "not selected for this panel", "in the company drawing, no selection component yet",
                    "out of scope"}
    items = " ".join(x["item"] for x in r.value["not_selected_detail"])
    assert "Busbar" in items and "VAF meter" in items and "M2" in items   # M2: Siemens auxiliary contacts
    assert "Control transformer" not in items   # selected now (control circuit, component 25)


def test_single_line_diagram_draws_every_feeder():
    from core.sld import build_sld
    r = answered(select, text=MULTI, panel_internal_c=40, cable_ambient_c=30, motor_pf=0.86, cu_encoder=False,
               mc_copy_parameters=True, ct_make="rishabh", plc_make="other", plc_24v_a=2, spd=True, spd_make="Phoenix",
               pmr=True, control_supply="transformer", confirmed=True)
    sheets = build_sld(r.value, "test")
    svg = next(x for x in sheets if 'data-title="SINGLE LINE DIAGRAM' in x)          # the single line overview
    for s in ("1SQ1", "M1", "M2 × 2", "U1", "Q1-Q2", "K1-K2", "6SL3210-1PE31-8UL0", "3VM1332-4ED32-0AA0", "SURGE ARRESTER",
              "PHASE MONITORING", "ENERGY METER", "NOT SELECTED"):
        assert s in svg, s
    power = " ".join(x for x in sheets if 'data-title="POWER WIRING' in x)            # power wiring, every motor drawn
    for s in ("1SQ1", "M1", "M2.1", "M2.2", "U1", "Q1", "Q2", "K1", "K2", "1X1"):
        assert f">{s}<" in power, s


def test_single_line_diagram_has_every_selected_part():
    """Owner 2026-10-14: every component is on the drawing — power sheets, control and automation sheet, schedule."""
    import html
    import re
    from core.sld import build_sld
    r = answered(select, text=MULTI, panel_internal_c=40, cable_ambient_c=30, cu_encoder=False, mc_copy_parameters=True,
               ct_make="rishabh", plc_make="siemens_s71200g2", spd=True, spd_make="siemens", pmr=True, control_supply="transformer", confirmed=True)
    sheets = build_sld(r.value, "test")
    text = html.unescape(" ".join(re.sub(r"<[^>]+>", " ", s) for s in sheets))
    missing = [b["article"] for b in r.value["bom"] if b["group"] != "Not selected" and str(b["article"])[:40] not in text]
    assert not missing, missing
    titles = [re.search(r'data-title="([^"]+)"', x).group(1) for x in sheets]
    assert titles[:4] == ["COVER SHEET", "INDEX SHEET", "LEGENDS, ABBREVIATIONS &amp; SYMBOLS", "TECHNICAL DETAILS"]
    assert "CONTROL SUPPLY 230 V AC / 24 V DC" in titles and "DIGITAL INPUT &amp; OUTPUT" in titles and titles[-1].startswith("BILL OF MATERIAL")
    assert "24 V DC" in text and "INTERFACE RELAYS" in text and "PLC FIELD TERMINALS" in text
    io = next(x for x in sheets if 'data-title="DIGITAL INPUT' in x)
    assert re.search(r"A1 6ES7", io), "PLC tagged A1"


def test_plc_is_sized_on_analog_signals_too():
    """Test-agent finding 2026-10-14 (CRITICAL): the PLC was sized on DI / DO only; a hardwired drive has AI + AO."""
    r = answered(select, text="7.5 kW pump VFD normal duty 30 m cable, 400 V, 25 kA", panel_internal_c=40, cable_ambient_c=30,
               cu_encoder=False, cu_safety="none", cu_fieldbus="none", mc_copy_parameters=True,
               plc_make="siemens_s71200g2", spd=False, pmr=False, control_supply="transformer", confirmed=True)
    v = r.value
    assert v["io_ai"] >= 1 and v["io_ao"] >= 1
    plc = [b for b in v["bom"] if b["group"] == "PLC"]
    assert any("AI" in b["description"] or "AQ" in b["description"] for b in plc), plc


@pytest.mark.parametrize("text", ["1" * 5000, "1 " * 2500, "1." * 2500, "1,1" * 1600, "-1" * 2500, "€1" * 2500, "2x" * 2500])
def test_reading_is_fast_on_hostile_text(text):
    """Security test 2026-10-14 (HIGH): 100 000 digits froze the server (quadratic regex). Every pattern now starts only
    at the beginning of a number, and texts are capped at 5 000 characters."""
    import time
    t = time.perf_counter()
    select(text=text)
    assert time.perf_counter() - t < 0.5


def test_overlong_text_is_refused():
    assert select(text="11 kW pump DOL. " + "x" * 5000).status == "invalid"


def test_plc_is_sized_to_the_clients_final_io_count():
    """Owner 2026-10-20 (RFQ part 6, R-REQ-36 / R-PLC-25): the client's final I/O per type (spare included) is a minimum;
    a higher spare % still wins."""
    kw = dict(text="2 x 11 kW pumps DOL, 30 m cable. 400 V, 25 kA", panel_internal_c=40, cable_ambient_c=30,
              plc_make="siemens_s71500", plc_cpu="CPU 1513-1 PN", plc_mc_mb=12, spd=False, pmr=False,
              control_supply="phase_neutral", confirmed=True)
    mods = lambda r: {b["article"]: b["qty"] for b in r.value["bom"] if b["group"] == "PLC" and "I/O module" in b["description"]}
    r = answered(select, plc_spare_pct=0, plc_io_min={"di": 32, "do": 16, "ai": 8, "ao": 4}, **kw)
    assert mods(r) == {"6ES7131-6BH01-0BA0": 2, "6ES7132-6BH01-0BA0": 1, "6ES7134-6HD01-0BA1": 2, "6ES7135-6HD00-0BA1": 1}, mods(r)
    assert any(c.rule == "R-REQ-36" for c in r.checks)
    big = answered(select, plc_spare_pct=0, plc_io_min={"di": 1}, **kw)
    assert mods(big)["6ES7131-6BH01-0BA0"] >= 1 and "6ES7135-6HD00-0BA1" not in mods(big)
