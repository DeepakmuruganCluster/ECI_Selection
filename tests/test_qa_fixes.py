"""Fixes from the release test of 2026-10-16 (report out/qa/test-report.html): one test per finding."""
from _answers import ASK, complete, ask, answered
import pytest

from components.control_signalling.select import select as signalling
from components.power.select import select as power
from components.project.select import select as project
from _answers import with_opts as _with_opts, OPTS
project = _with_opts(project)    # R-PRJ-20: the old options, given explicitly
from components.requirement.select import select as requirement
from _answers import auto as _auto
requirement = _auto(requirement)    # audit 2026-10-17: per-case questions answered the old way
from core import alternatives, bom_edit

PRJ = dict(panel="BIO_UF", fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, default_cable_m=50)
BASE = dict(confirmed=True, panel_internal_c=40, cable_ambient_c=40, plc_make="siemens_s71200g2", spd=False, pmr=False, control_supply="transformer", **ASK)
VFD = "75 kW conveyor with VFD, 50 m cable; 2 x 11 kW pumps DOL, 30 m cable. 400 V, 25 kA, site 35 °C, PROFINET, STO, energy meter"
VFD_IN = dict(BASE, cu_encoder="false", mc_copy_parameters="true", ct_make="rishabh")
SS45 = "45 kW fan with soft starter, 40 m cable, 400 V, 25 kA, site 40 °C"


@pytest.fixture
def overrides(tmp_path, monkeypatch):
    f = tmp_path / "overrides.yaml"
    f.write_text("edits: []\n")
    monkeypatch.setattr(bom_edit, "_file", lambda project: f)
    return f


# H1 — duty / standby per tag group
def test_h1_standby_per_group_lowers_the_running_load():
    all_run = project(**PRJ).value
    sb = project(**PRJ, standby={"K102A/B": 1, "P201A/B/C": 1}).value
    assert sb["power_calc"]["ac3"]["i_l1_a"] < all_run["power_calc"]["ac3"]["i_l1_a"] - 90
    g = {x["tag"]: x for x in sb["standby_groups"]}
    assert g["K102A/B"]["standby"] == 1 and g["K102A/B"]["set"] and not g["P101A/B"]["set"]


def test_h1_standby_refused_for_unknown_group_or_all_units():
    assert project(**PRJ, standby={"NOPE": 1}).status == "invalid"
    assert project(**PRJ, standby={"K102A/B": 2}).status == "invalid"


def test_h1_standby_saved_kept_and_cleared(overrides):
    bom_edit.standby_save(None, "BIO_UF", "K102A/B", 1)
    assert bom_edit.load_standby(None, "BIO_UF") == {"K102A/B": 1}
    assert project(**PRJ).value["power_calc"]["ac3"]["i_l1_a"] < project(**PRJ, standby={"K102A/B": 0}).value["power_calc"]["ac3"]["i_l1_a"]
    bom_edit._save(None, [])                       # saving BOM edits keeps the standby units
    assert bom_edit.load_standby(None, "BIO_UF") == {"K102A/B": 1}
    bom_edit.standby_save(None, "BIO_UF", "K102A/B", None)
    assert bom_edit.load_standby(None, "BIO_UF") == {}
    with pytest.raises(ValueError):
        bom_edit.standby_save(None, "BIO_UF", "K102A/B", True)


# H2 — soft starter protection asked when the breaker is not tested up to the fault level
def test_h2_soft_starter_protection_asked_then_selected():
    v = requirement(text=SS45, **BASE).value
    assert not v["selected"] and [q["input"] for q in v["questions"]] == ["ss_protection"]
    v = requirement(text=SS45, ss_protection="fuse_gg", **BASE).value
    assert v["selected"] and not v["incomplete"]
    assert any(b["article"].startswith("3NA3") for b in v["bom"])


# H3 — a malformed BOM edit is refused, and a stored one is set aside
@pytest.mark.parametrize("edit", [
    {"action": "add", "article": "X1", "description": {"a": 1}, "qty": 1},
    {"action": "add", "article": ["X1"], "qty": 1},
    {"action": "qty", "qty": True},
    {"action": "qty", "qty": 1e308},
    {"action": "add", "article": "X1", "group": ["g"], "qty": 1}])
def test_h3_bad_edit_refused(edit):
    assert not bom_edit.check(edit)["ok"]


def test_h3_unknown_panel_refused(overrides):
    with pytest.raises(ValueError):
        bom_edit.save(None, "../../etc/passwd", {"group": "Feeders"}, {"action": "add", "article": "X1", "qty": 1})
    with pytest.raises(ValueError):
        bom_edit.save(None, "RO", {"description": {"a": [1]}}, {"action": "remove"})


def test_h3_stored_bad_edit_does_not_break_the_panel(overrides):
    overrides.write_text("edits:\n- {id: 3, panel: RO, action: add, article: X1, description: {a: 1}, qty: 1, group: [g],\n"
                         "   line: {}, check: {verdict: ok}, proposed_by: designer}\n")
    r = project(**{**PRJ, "panel": "RO"})
    assert r.status != "invalid"
    assert any("set aside as unusable" in c.value for c in r.checks if c.rule == "R-PRJ-17")


# H4 / L6 / M1 — incomer against the feeders, the largest phase and the template basis
def test_h4_incomer_below_an_outgoing_device_is_flagged():
    r = requirement(text=VFD, incomer_factor=1, **VFD_IN)          # factor 1: 200 A incomer under M1's 224 A fuse
    c = next(c for c in r.checks if c.rule == "R-REQ-25")
    assert c.verdict == "warn" and "224 A" in c.value
    r = requirement(text=VFD, **VFD_IN)                            # factor 1.5 (default): 320 A, above every device
    assert next(c for c in r.checks if c.rule == "R-REQ-25").verdict == "info"


def test_l6_incomer_current_includes_single_phase_loads():
    v = requirement(text=VFD, **VFD_IN).value
    p = v["power"]
    assert v["incomer_ib_a"] == pytest.approx(max(p["i_l1_a"], p["i_l2_a"], p["i_l3_a"]), abs=0.01)


def test_m1_incomer_factor_is_an_input_with_15_default():
    v = requirement(text=VFD, **VFD_IN).value
    top = max(v["power"]["i_l1_a"], v["power"]["i_l2_a"], v["power"]["i_l3_a"])
    assert v["incomer_in_a"] >= top * 1.5 and v["power"]["main_fos"] == 1.5
    v = requirement(text=VFD, incomer_factor=1.25, **VFD_IN).value
    assert v["power"]["main_fos"] == 1.25 and v["incomer_in_a"] >= top * 1.25


# M2 — an incomplete design says so
def test_m2_incomplete_design_listed():
    v = requirement(text=SS45, ss_protection="mpcb", **BASE).value
    assert v["selected"] and [x["tag"] for x in v["incomplete"]] == ["M1"]
    assert "15 kA" in v["incomplete"][0]["reason"]


# M3 — minimum power wire, soft-starter wiring, CT loading
def test_m3_small_motor_gets_075_and_soft_starter_gets_a_wire():
    v = requirement(text="0.37 kW agitator DOL 10 m cable 400 V 10 kA", **BASE).value
    assert [b["article"] for b in v["bom"] if b["group"] == "Internal wiring"] == ["Lapp H07V-K 0.75 mm²"]
    v = requirement(text=SS45, ss_protection="fuse_gg", **BASE).value
    assert [b["article"] for b in v["bom"] if b["group"] == "Internal wiring"]


def test_m3_ct_loading_shown():
    r = requirement(text="0.37 kW agitator DOL 10 m cable 400 V 10 kA, energy meter", ct_make="rishabh", **BASE)
    c = next(c for c in r.checks if "CT loading" in c.requirement)
    assert c.verdict == "warn" and "%" in c.value


# M4 — alternatives that need answers are offered, the rest explained
def test_m4_vfd_offered_with_its_questions():
    inp = complete(text="11 kW pump, DOL, 400 V, 25 kA, 30 m cable", **{k: v for k, v in BASE.items() if k != "confirmed"})
    v = requirement(**inp, confirmed=True).value
    line = next(b for b in v["bom"] if b["article"] == "3RV2021-4DA10")
    a = alternatives.alternatives(inp, line)
    vfd = next(o for o in a["options"] if o["value"] == "VFD")
    assert vfd["needs"] and vfd["n_changes"] == 0
    assert any(s["label"].startswith("Star-delta") for s in a["skipped"])


# M6 — impossible counts refused
def test_m6_counts_bounded():
    assert signalling(other_outputs=5000).status == "invalid"
    assert signalling(io_terminals=100, jumper_groups=[2] * 600).status == "invalid"


# L2 — power edit numbers within reason
@pytest.mark.parametrize("bad", [{"i_a": 1e308}, {"i_a": True}, {"running": 1.5}, {"va": -1}, {"connection": "XY"}])
def test_l2_power_edit_values(bad):
    r = power(voltage_v=400, three_phase=[], single_phase=[{"key": "x", "name": "x", "va": 100}],
              edits=[{"action": "set", "key": "x", **bad}])
    assert r.status == "invalid"


# L5 — a bare length is offered, a pump head is not
def test_l5_bare_length_offered_head_not():
    v = requirement(text="3 x 7.5 kW mixers VFD 20 m cable, 2 x 2.2 kW pumps DOL 15 m, 400 V 36 kA, Modbus",
                    panel_internal_c=40, cable_ambient_c=40).value
    q = next(q for q in v["questions"] if q["input"] == "M2.cable_m")
    assert q["help"]["picks"][0] == 15.0
    v = requirement(text="5.5 kW pump DOL 30 m head, 400 V 25 kA").value
    assert "suggest" not in next(q for q in v["questions"] if q["input"] == "cable_m")


# L7 — a load given in VA counts its VA
def test_l7_va_counted_as_given():
    r = power(voltage_v=400, three_phase=[], single_phase=[{"name": "x", "va": 230, "u_v": 230}])
    assert r.value["s_kva"] == pytest.approx(0.230, abs=1e-6)


# L8 — kit wiring accessories carry a 'not fixed' make
def test_l8_kit_wiring_accessories_make():
    v = requirement(text="11 kW pump, DOL, 400 V, 25 kA, 30 m cable", **BASE).value
    acc = [b for b in v["bom"] if str(b["article"]).startswith("Wiring accessories")]
    assert acc and all(b["make"].startswith("Not fixed") for b in acc)


# owner 2026-10-16: named I/O, inputs / outputs apart, traced into the calculations and drawn on the SLD
def test_io_named_split_traced_and_drawn():
    from core.sld import build_sld
    v = answered(requirement, text=VFD, **{**VFD_IN, "pmr": True, "control_supply": "transformer"}).value
    assert [r["name"] for r in v["io_inputs"]][:3] == ["I_EmergencyStop", "I_Reset", "I_PhaseFailure"]
    assert all(r["name"].startswith("I_") for r in v["io_inputs"]) and all(r["name"].startswith("O_") for r in v["io_outputs"])
    assert v["io_trace"] and all(t["ok"] for t in v["io_trace"])
    di = next(t for t in v["io_trace"] if t["used_in"].startswith("24 V DC load: digital"))
    assert di["count"] == v["io_di"] == len([r for r in v["io_inputs"] if r["type"] == "DI"])
    sheets = build_sld(v, "test")
    sld = next(x for x in sheets if 'data-title="SINGLE LINE' in x)
    io = next(x for x in sheets if 'data-title="DIGITAL INPUT' in x)
    assert "I_M2_1_Running" in sld and "I_M2_1_Running" in io and "O_GeneralTrip" in io


# owner 2026-10-16: every output editable, assistant per page
def test_io_edits_flow_into_every_count():
    base = requirement(text="11 kW pump, DOL, 400 V, 25 kA, 30 m cable", **BASE).value
    v = requirement(text="11 kW pump, DOL, 400 V, 25 kA, 30 m cable",
                    io_edits=[{"action": "add", "type": "DI", "name": "I_DoorOpen", "signal": "door"},
                              {"action": "add", "type": "DO", "name": "O_Horn", "signal": "horn"}], **BASE).value
    assert v["io_di"] == base["io_di"] + 1 and v["io_do"] == base["io_do"] + 1
    assert v["qty_relays"] == base["qty_relays"] + 1 and v["qty_io_terminals"] == base["qty_io_terminals"] + 2
    assert v["power"]["dc"]["rows"][0]["qty"] == v["io_di"] and all(t["ok"] for t in v["io_trace"])
    assert requirement(text="11 kW pump, DOL, 400 V, 25 kA, 30 m cable", io_edits=[{"action": "remove", "name": "I_Nope"}],
                       **BASE).status == "invalid"


def test_dc_override_shows_as_mismatch_in_the_trace():
    v = requirement(text="11 kW pump, DOL, 400 V, 25 kA, 30 m cable",
                    power_edits=[{"action": "set", "key": "relays", "qty": 9, "dc": True}], **BASE).value
    t = next(t for t in v["io_trace"] if t["used_in"].endswith("relay coils"))
    assert not t["ok"] and "your power edit" in t["value"]


def test_project_io_edits_saved_and_undone(overrides):
    rec = bom_edit.io_save(None, "RO", {"action": "add", "type": "DI", "name": "I_DoorOpen", "signal": "door"})
    v = project(**{**PRJ, "panel": "RO"}).value
    assert any(r.get("name") == "I_DoorOpen" for r in v["io_list"]) and v["io_error"] is None
    assert bom_edit.io_undo(None, rec["id"]) and not bom_edit.io_list(None)


def test_page_assistant_proposals_are_checked():
    from core.assistant import check_page_proposal as chk
    ctx = {"ac": [{"key": "control"}], "dc": [{"key": "di"}], "signals": [{"name": "I_K1_Running"}]}
    ok, _ = chk("power", {"action": "set", "key": "control", "connection": "LN", "phase": "L2", "words": "transformer to L2"},
                "move the transformer to L2", ctx)
    assert ok == [{"action": "set", "key": "control", "connection": "LN", "phase": "L2"}]
    assert chk("power", {"action": "set", "key": "ghost", "words": "x"}, "x", ctx)[0] == []
    assert chk("power", {"action": "set", "key": "control", "words": "not said"}, "move it", ctx)[0] == []
    assert chk("io", {"edits": [{"action": "remove", "name": "I_Ghost"}], "words": "remove"}, "remove it", ctx)[0] == []


# owner 2026-10-16: project version history and the impact of a change
def test_every_project_change_is_a_version_and_restorable(overrides):
    from core import versions
    bom_edit.power_save(None, "RO", {"action": "set", "key": "control", "connection": "LN", "phase": "L2"})
    bom_edit.standby_save(None, "RO", "P302A/B", 1)
    rec = bom_edit.io_save(None, "RO", {"action": "add", "type": "DI", "name": "I_DoorOpen", "signal": "door"})
    bom_edit.io_undo(None, rec["id"])
    vs = versions.listing(overrides)
    assert [v["v"] for v in vs] == [5, 4, 3, 2, 1]
    assert "starting point" in vs[-1]["summary"] and "Power: set control" in vs[-2]["summary"]
    assert "Standby RO" in vs[-3]["summary"] and "took back" in vs[0]["summary"]
    bom_edit.restore(None, 2)                    # back to: power edit only
    now = versions.listing(overrides)[0]
    assert now["v"] == 6 and now["summary"].startswith("restored version 2") and now["standby"] == 0
    assert bom_edit.load_standby(None, "RO") == {} and bom_edit.load_power(None, "RO")


def test_impact_lists_what_follows():
    from core import impact
    base = complete(text=VFD, **{k: v for k, v in VFD_IN.items() if k != "confirmed"})
    r = impact.machine(base, {"motors": [{"removed": True}]})
    assert any(d["what"] == "Incomer" for d in r["devices"]) and any(c["article"] == "6SL3210-1PE31-8UL0" and c["kind"] == "removed"
                                                                     for c in r["bom"])
    assert impact.machine(base, {"io_edits": [{"action": "remove", "name": "I_Nope"}]})["refused"]
    r = impact.project(None, "RO", dict(fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, default_cable_m=50, **OPTS),
                       {"standby": {"P302A/B": 1}})
    assert any(p["what"] == "L1 current" and p["to"] < p["from"] for p in r["power"])


# owner 2026-10-16: design projects (Project → panels → design → versions), saved on disk
def test_design_projects_save_version_restore_label(tmp_path, monkeypatch):
    from core import designs
    monkeypatch.setattr(designs, "DESIGNS", tmp_path / "designs")
    p = designs.create("Crusher plant 7", client="ACME", location="Coimbatore")
    d = {"text": "11 kW pump DOL, 400 V, 25 kA, 30 m cable", "answers": {"panel_internal_c": "40"}}
    assert designs.save(p["id"], "MCC-1", d)["version"]["v"] == 1
    assert designs.save(p["id"], "MCC-1", d)["saved"] is False                     # unchanged: no new version
    d2 = {**d, "answers": {**d["answers"], "cable_ambient_c": "40"}, "io_edits": [{"action": "add", "type": "DI", "name": "I_Door"}]}
    v2 = designs.save(p["id"], "MCC-1", d2)["version"]
    assert v2["v"] == 2 and "cable_ambient_c" in v2["summary"] and "I/O: add I_Door" in v2["summary"]
    designs.label(p["id"], "MCC-1", 2, "Issued to client, rev A")
    assert designs.history(p["id"], "MCC-1")[0]["label"] == "Issued to client, rev A"
    r = designs.restore(p["id"], "MCC-1", 1)
    assert r["version"]["v"] == 3 and r["version"]["summary"].startswith("restored version 1")
    assert designs.load(p["id"], "MCC-1")["design"]["answers"] == {"panel_internal_c": "40"}
    assert [x["name"] for x in designs.listing()[0]["panels"]] == ["MCC-1"]
    for bad in ("../x", "", "a/b"):
        with pytest.raises(ValueError):
            designs.save(p["id"], bad, d)
    with pytest.raises(ValueError):
        designs.create("Crusher plant 7")


# owner 2026-10-16: versions record who; Draft → Checked → Approved, four eyes
def test_version_states_four_eyes(tmp_path, monkeypatch):
    from core import auth, designs
    monkeypatch.setattr(designs, "DESIGNS", tmp_path / "designs")
    d = designs.create("Plant X")
    auth.set_current({"name": "Asha", "roles": ["designer"]})
    designs.save(d["id"], "P1", {"text": "11 kW pump DOL", "answers": {}})
    designs.save(d["id"], "P1", {"text": "11 kW pump DOL", "answers": {"cable_m": "30"}})
    h = designs.history(d["id"], "P1")
    assert h[0]["by"] == "Asha" and h[0]["state"] == "draft"
    with pytest.raises(PermissionError):                        # a designer cannot check
        designs.set_state(d["id"], "P1", 2, "checked")
    auth.set_current({"name": "Asha", "roles": ["designer", "checker"]})
    with pytest.raises(PermissionError):                        # nor check her own version
        designs.set_state(d["id"], "P1", 2, "checked")
    auth.set_current({"name": "Ravi", "roles": ["approver"]})
    with pytest.raises(ValueError):                             # approve before check
        designs.set_state(d["id"], "P1", 2, "approved")
    auth.set_current({"name": "Ben", "roles": ["checker", "approver"]})
    designs.set_state(d["id"], "P1", 2, "checked")
    with pytest.raises(PermissionError):                        # the checker does not also approve
        designs.set_state(d["id"], "P1", 2, "approved")
    auth.set_current({"name": "Ravi", "roles": ["approver"]})
    designs.set_state(d["id"], "P1", 2, "approved")
    h = designs.history(d["id"], "P1")[0]
    assert (h["state"], h["checked_by"], h["approved_by"]) == ("approved", "Ben", "Ravi")
    auth.set_current(None)


def test_auth_store_hashes_and_locks(tmp_path, monkeypatch):
    from core import auth
    monkeypatch.setattr(auth, "USERS", tmp_path / "users.yaml")
    monkeypatch.setattr(auth, "_fails", {})
    import secrets
    pw = secrets.token_urlsafe(12)
    auth.setup("Owner", pw)
    assert pw not in (tmp_path / "users.yaml").read_text() and "scrypt$" in (tmp_path / "users.yaml").read_text()
    with pytest.raises(PermissionError):
        auth.setup("Other", pw)                                  # setup only once
    assert auth.session(auth.login("Owner", pw))["roles"] == list(auth.ROLES)
    for _ in range(5):
        with pytest.raises(PermissionError):
            auth.login("Owner", "wrong-password")
    with pytest.raises(PermissionError, match="wait"):
        auth.login("Owner", pw)                                  # locked for a minute
    with pytest.raises(ValueError):
        auth.remove_user("Owner")                                # the last admin stays


# owner 2026-10-16: the company naming convention — '55KW SD' = 55 kW star-delta; it holds for every template
@pytest.mark.parametrize("sheet,title,want", [
    ("55KW SD", "55KW STAR-DELTA STARTER PANEL", (55, [55], 1, "SD", False)),
    ("110KW SD WITH PLC", "AVCONE 110KW S/D LUB WITH PLC OPTION", (110, [110], 1, "SD", True)),
    ("187KW SD", "160/187KW STAR-DELTA STARTER PANEL", (187, [160, 187], 1, "SD", False)),
    ("PROWASH 100", "PROWASH 100 STARTER PANEL", (None, [], 1, "", False)),            # 'STARTER' says nothing
    ("VSI 250", "VSI 250 DUAL MOTOR STARTER PANEL", (None, [], 2, "", False)),
    (None, "BELT CONVEYOR 30KW SDL - Prowash", (30, [30], 1, "SD", False)),
    (None, "BELT CONVEYOR 7.5KW F/R", (7.5, [7.5], 1, "DOL_FR", False)),
    (None, "GRIZZLY FEEDER 4.3 KW X 2 DOL", (4.3, [4.3], 2, "DOL", False)),
    (None, "ECO WASH FEEDER 2.2KW / 3.2 X 2 DOL DEWATERING", (3.2, [2.2, 3.2], 2, "DOL", False)),
    (None, "PROWASHFEEDER6.2KWX2DOLDEWATERING", (6.2, [6.2], 2, "DOL", False)),
])
def test_naming_convention(sheet, title, want):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("imp", Path(__file__).resolve().parents[1] / "scripts" / "import_propel.py")
    imp = importlib.util.module_from_spec(spec); spec.loader.exec_module(imp)
    d = imp.parse_title(title, sheet)
    assert (d["kw"], d["kw_options"], d["motors"], d["starter"], d["plc"]) == want


def test_every_template_reads_back_as_its_name_says():
    from core import templates as T
    for t in T.listing():
        v = requirement(text=T.text(t["id"]), **{k: v_ for k, v_ in T.answers(t["id"]).items()}).value
        m = v["motors"]
        assert len(m) == 1, t["title"]
        assert (m[0]["kw"], m[0]["qty"], m[0]["starter"]) == (t["kw"], t["motors"], {"DOL_FR": "DOL"}.get(t["starter"], t["starter"]) or None), t["title"]


def test_template_sld_draws_its_own_feeder_protection():
    """VSI 300 (no kW in the name): the diagram shows the template's overload relay and MPR, not 'protection not selected'."""
    from components.requirement.select import select
    from core import templates as T
    from core.sld import build_sld
    t = next(x for x in T.catalogue() if "VSI 300" in x["sheet"])
    r = select(text=T.text(t["id"]), template=t["id"], confirmed=True, qty=2)
    s = "".join(build_sld(r.value, "VSI 300"))
    assert "OLR1 LRE487" in s and "MPR1" in s and "PROTECTION NOT SELECTED" not in s
    assert "kW not stated" in s and "NO PLC IN THIS PANEL" in s and ("Busbar &amp; accessories" in s or "Busbar & accessories" in s)


# owner 2026-10-17: delete a project or a panel — to Recently deleted, restorable; approved work only by an admin
def test_delete_and_restore_project_and_panel(tmp_path, monkeypatch):
    from core import auth, designs
    monkeypatch.setattr(designs, "DESIGNS", tmp_path / "designs")
    d = designs.create("Plant Y")
    auth.set_current({"name": "Asha", "roles": ["designer"]})
    designs.save(d["id"], "P1", {"text": "11 kW pump DOL", "answers": {}})
    designs.save(d["id"], "P2", {"text": "15 kW fan DOL", "answers": {}})
    # a panel: gone from the project, in the bin, back on restore with its versions
    designs.delete_panel(d["id"], "P2")
    assert [p["name"] for p in designs.listing()[0]["panels"]] == ["P1"]
    b = designs.deleted()
    assert b[0]["kind"] == "panel" and b[0]["name"] == "P2" and b[0]["deleted_by"] == "Asha"
    designs.undelete(b[0]["id"])
    assert [p["name"] for p in designs.listing()[0]["panels"]] == ["P1", "P2"] and designs.history(d["id"], "P2")
    assert designs.deleted() == []
    # the project: gone from the list, restorable whole
    r = designs.delete_project(d["id"])
    assert r["panels"] == 2 and designs.listing() == []
    with pytest.raises(ValueError):
        designs.load(d["id"], "P1")
    designs.undelete(designs.deleted()[0]["id"])
    assert designs.listing()[0]["name"] == "Plant Y" and designs.load(d["id"], "P1")["design"]["text"] == "11 kW pump DOL"
    assert "deleted_at" not in (tmp_path / "designs" / d["id"] / "design.yaml").read_text()
    # a restore never overwrites: a new project of the same name blocks it
    designs.delete_project(d["id"])
    designs.create("Plant Y")
    with pytest.raises(ValueError):
        designs.undelete(designs.deleted()[0]["id"])
    with pytest.raises(ValueError):
        designs.undelete("../x")
    auth.set_current(None)


def test_delete_needs_designer_and_admin_for_approved(tmp_path, monkeypatch):
    from core import auth, designs
    monkeypatch.setattr(designs, "DESIGNS", tmp_path / "designs")
    d = designs.create("Plant Z")
    auth.set_current({"name": "Asha", "roles": ["designer"]})
    designs.save(d["id"], "P1", {"text": "11 kW pump DOL", "answers": {}})
    designs.save(d["id"], "P1", {"text": "11 kW pump DOL", "answers": {"cable_m": "30"}})
    auth.set_current({"name": "Ben", "roles": ["checker"]})
    with pytest.raises(PermissionError):                        # a checker does not delete
        designs.delete_project(d["id"])
    designs.set_state(d["id"], "P1", 2, "checked")
    auth.set_current({"name": "Ravi", "roles": ["approver"]})
    designs.set_state(d["id"], "P1", 2, "approved")
    auth.set_current({"name": "Asha", "roles": ["designer"]})
    with pytest.raises(PermissionError):                        # approved work: an admin only
        designs.delete_panel(d["id"], "P1")
    with pytest.raises(PermissionError):
        designs.delete_project(d["id"])
    auth.set_current({"name": "Deepak", "roles": ["designer", "admin"]})
    designs.delete_project(d["id"])
    assert designs.listing() == [] and designs.deleted()[0]["deleted_by"] == "Deepak"
    auth.set_current(None)
