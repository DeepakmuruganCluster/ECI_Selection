"""The client's automation / panel specification read with the RFQ (owner 2026-10-20), part 1: incoming & distribution."""
from pathlib import Path

import pytest

from core import auth, rfq, rfq_answers, rfq_bom, rfq_spec, standards

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sources" / "Sample complete" / "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf"
AUTO = ROOT / "sources" / "pdf" / "client" / "ECI-WNS2503" / "Automation_Rittal  Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf"


def test_rows_as_printed_and_what_they_decide():
    """Oracle: ECI-WNS2503-AUTO p.1, the 'requirement → value' table and the two PLC blocks."""
    d = rfq_spec.read_pdf(AUTO.read_bytes(), AUTO.name, ["BIO/UF", "RO"])
    rows = {r["label"]: r for r in d["rows"]}
    inc = rows["Main Incommer For Bio MBR Panel"]
    assert inc["panels"] == ["BIO/UF"] and inc["require"] == {"series": "3VA", "in_a": 630.0, "icu_ka": 55.0, "adjustable": True}
    assert inc["answers"] == {"incomer_series": "3VA"}               # 3VA1: TM240 adjustable by itself, no 3VM release
    assert rows["Main Incommer For RO Panel"]["panels"] == ["RO"]
    assert rows["Surge Arrester For Main Incommer"]["answers"] == {"spd": "true", "spd_make": "Phoenix"}
    assert rows["Surge Arrester For UPS Supply"]["status"] == "out of scope" and rows["UPS"]["status"] == "out of scope"
    assert rows["Energy Meter"]["answers"] == {"meter": "true", "meter_comm": "profinet"}
    assert rows["Current Transformer"]["require"] == {"makes": ["rishabh", "selec"]} and not rows["Current Transformer"]["answers"]
    assert [ln["item"] for ln in rows["Earthing"]["lines"]] == ["Earth busbar", "Analog earth bar"]
    assert rows["MCCB"]["part"] == 3 and rows["Inverter"]["part"] == 2 and rows["Relay"]["part"] == 6
    assert rows["Inverter"]["answers"] == {"duty": "normal", "line_reactor_up_to_kw": 15.0}       # part 2: 'Normal Load', 'Only 15 and Below'
    assert rows["Inverter"]["require"] == {"family": "G120", "duty": "normal", "reactor_up_to_kw": 15.0}
    assert d["plc"]["BIO/UF"]["io"]["Digital Inputs"] == {"required": 259.0, "spare": 13.0, "final": 272.0}
    assert d["plc"]["RO"]["io"]["Analog Output 4-20mA"] == {"required": 22.0, "spare": 10.0, "final": 32.0}
    with pytest.raises(ValueError):
        rfq_spec.read_pdf(b"hello", "x.pdf", ["A"])


@pytest.fixture
def rid(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    monkeypatch.setattr(standards, "STANDARDS", tmp_path / "standards")
    auth.set_current({"name": "QA designer", "roles": ["designer"]})
    r = rfq.save(SAMPLE.read_bytes(), SAMPLE.name, "t")["id"]
    rfq_spec.save(r, AUTO.read_bytes(), AUTO.name, "QA designer")
    yield r
    auth.set_current(None)


def test_spec_answers_between_the_standard_and_your_answer(rid):
    s = standards.save("Std", {"spd_make": "Siemens", "relay_make": "finder"})
    auth.set_current({"name": "QA approver", "roles": ["approver"]})
    standards.approve(s["id"], 1)
    auth.set_current({"name": "QA designer", "roles": ["designer"]})
    rfq_answers.apply_standard(rid, s["id"], "QA designer")
    p = {x["key"]: x for x in rfq_answers.questions(rid)["project"]}
    assert p["spd_make"]["value"] == "Phoenix" and p["spd_make"]["source"] == "client spec"   # the client wins over the standard
    assert p["relay_make"]["source"] == "standard"
    assert p["meter_supply"]["relevant"] and p["meter_supply"]["value"] is None             # the client's meter → its supply asked
    rfq_answers.answer(rid, "project", "spd_make", "OBO", "QA designer")                    # your answer wins over both
    assert rfq_answers.for_panel(rid, "BIO/UF")[0]["spd_make"] == "OBO"
    assert rfq_answers.sources(rid, "RO")["incomer_series"].startswith("client spec p.1: Main Incommer For RO Panel")


def test_part1_bom_lines_and_client_checks(rid):
    """BIO/UF at 55 kA (owner 2026-10-20), no phase relay: the client's 3VA → 3VA1463-5EF32-0AA0 (smallest frame with
    630 A, TM240, class M 55 kA; LV 10 · 2026) complies; Phoenix surge arrester, PAC3220 7KM3220-0BA01-1DA0 + PROFINET
    module, Rishabh CTs comply; the busbar and both earth bars are client lines, not engine-checked."""
    from tests.test_rfq import ALL
    for k, v in {**{k: v for k, v in ALL.items() if k not in ("spd_make", "meter", "meter_comm", "incomer_release", "incomer_series",
                                                              "duty", "line_reactor_up_to_kw")},
                 "fault_ka": 55, "pmr": "false", "smps_input": "3P"}.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    b = rfq_bom.build(rid, "BIO/UF")
    inc = next(x for x in b["bom"] if x["group"] == "Incomer")
    assert inc["article"] == "3VA1463-5EF32-0AA0" and "TM240" in inc["description"] and "Icu 55 kA" in inc["description"]
    assert not any(x["group"] == "Auxiliary switchgear" and "PMR" in x["description"] for x in b["bom"])
    assert any(x["article"] == "7KM3220-0BA01-1DA0" for x in b["bom"])
    client = [x for x in b["bom"] if x["group"] == "Client-specified" and x["section"] == "Incoming & distribution"]
    assert len(client) == 3 and all("not engine-checked" in x["source"] for x in client)        # busbar, earth bar, analog earth bar
    v = {c["requirement"].split(":")[0]: c for c in b["client_checks"]}
    assert v["Main Incommer For Bio MBR Panel"]["verdict"] == "complies"
    assert {k: v[k]["verdict"] for k in ("Surge Arrester For Main Incommer", "Energy Meter", "Current Transformer")} == \
        {"Surge Arrester For Main Incommer": "complies", "Energy Meter": "complies", "Current Transformer": "complies"}


def test_part2_drives_fuses_holders_and_line_reactors(rid):
    """Part 2 (owner 2026-10-20), BIO/UF: 22 drives (10 rows). Client: 'G120 VFD Normal Load and Input Choke … Only 15 and
    Below 15KW'. Three fuses per drive (SIE-PM240-2 Fig. 4-5) = 66, each drive's fuses in a 3NP1123-1CA20 (all size 000,
    LV 10 · 2026 pp.7/46, 8/87); line reactors on the 20 drives ≤ 15 kW (K102A/B 37 kW: none); the check complies."""
    from tests.test_rfq import ALL
    for k, v in {**{k: v for k, v in ALL.items() if k not in ("spd_make", "meter", "meter_comm", "incomer_release", "incomer_series",
                                                              "duty", "line_reactor_up_to_kw")},
                 "fault_ka": 55, "pmr": "false", "smps_input": "3P"}.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    b = rfq_bom.build(rid, "BIO/UF")
    vfd = [x for x in b["bom"] if x["section"] == "VFD section"]
    n_drives = sum(x["qty"] for x in vfd if x["article"].startswith("6SL3210"))
    fuses = sum(x["qty"] for x in vfd if x["article"].startswith("3NA"))
    holders = sum(x["qty"] for x in vfd if x["article"] == "3NP1123-1CA20")
    reactors = [x for x in vfd if x["article"].startswith("6SL3203") and x["description"] == "Line reactor"]
    assert n_drives == 22 and fuses == 66 and holders == 22
    assert sum(x["qty"] for x in reactors) == 20 and not any("K102A/B" in x["used_by"] for x in reactors)
    assert not any(o["rule"] == "R-VFD-08" for o in b["open_points"])
    chk = next(c for c in b["client_checks"] if c["requirement"].startswith("Inverter"))
    assert chk["verdict"] == "complies" and "≤ 15 kW" in chk["detail"]


def test_part3_drive_mpcbs_dol_suppressors_and_link_modules(rid):
    """Part 3 (owner 2026-10-20), BIO/UF. The RFQ's protection column ('MPCB-3RV' on every drive row) answers the drive
    protection: each drive gets a Siemens-listed 3RV rated ≥ its input current (R-VFD-19) — the client's 100 A on the 37 kW
    drive fits (input 70 A), the other drive ranges are below the input current and are warnings. DOL: a varistor per
    contactor by size — 3RT2916-1JL00 (S00, the client's), 3RT2926-1JL00 (S0) — IC 10 p.3/96; K202 and P204A/B are
    Siemens' S00 + S0 pair without a link module: wired, listed as a deviation."""
    from tests.test_rfq import ALL
    skip = ("spd_make", "meter", "meter_comm", "incomer_release", "incomer_series", "duty", "line_reactor_up_to_kw",
            "vfd_protection", "fuse_holder", "contactor_suppressor")
    for k, v in {**{k: v for k, v in ALL.items() if k not in skip}, "fault_ka": 55, "pmr": "false", "smps_input": "3P"}.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    assert rfq_answers.sources(rid, "BIO/UF")["vfd_protection"].startswith("RFQ BIO/UF: protection column")
    b = rfq_bom.build(rid, "BIO/UF")
    assert b["answers"]["vfd_protection"] == "msp" and b["answers"]["contactor_suppressor"] == "varistor"
    f = {x["tag"]: x for x in b["feeders"]}
    assert f["K102A/B"]["devices"].endswith("3RV2041-4MA10") and f["P101A/B"]["devices"].endswith("3RV2021-4AA10")
    flagged = {o["tag"] for o in b["open_points"] if o["rule"] == "R-VFD-19"}
    assert "K102A/B" not in flagged and {"P101A/B", "P201A/B/C", "P205A/B"} <= flagged
    assert not any(x["article"].startswith(("3NA", "3NP")) for x in b["bom"] if x["section"] == "VFD section")   # MSP: no drive fuses
    sup = {x["article"]: x["qty"] for x in b["bom"] if "surge suppressor" in x["description"].lower()}
    assert sup == {"3RT2916-1JL00": 21, "3RT2926-1JL00": 3}
    chk = next(c for c in b["client_checks"] if c["requirement"].startswith("DOL"))
    assert chk["verdict"] == "deviation" and "K202, P204A/B" in chk["detail"] and "no surge suppressor" not in chk["detail"]


def test_part4_soft_starter_display_profinet_and_protection(rid):
    """Part 4 (owner 2026-10-20), BIO/UF E101 7.5 kW (15.5 A). Client: '3RW-52 Softstarter with Display and Profinet
    Communication' → ss_comm profinet from the spec; the RFQ's protection column ('MPCB-3RV') → ss_protection mpcb; owner:
    Standard HMI on the door. 3RW5214-1AC14 + Siemens' tested 3RV2032-4DA10 (not the RFQ's 11-16 A: a deviation), PROFINET
    3RW5980-0CS00, HMI 3RW5980-0HS00, IP65 door kit 3RW5980-0HD00, 2.5 m cable 3UF7933-0BA00-0 (IC 10 6/75-6/76)."""
    from tests.test_rfq import ALL
    skip = ("spd_make", "meter", "meter_comm", "incomer_release", "incomer_series", "duty", "line_reactor_up_to_kw",
            "vfd_protection", "fuse_holder", "contactor_suppressor", "ss_protection", "ss_comm")
    for k, v in {**{k: v for k, v in ALL.items() if k not in skip}, "fault_ka": 55, "pmr": "false", "smps_input": "3P"}.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    b = rfq_bom.build(rid, "BIO/UF")
    assert b["answers"]["ss_comm"] == "profinet" and b["answers"]["ss_protection"] == "mpcb"
    ss = {x["article"] for x in b["bom"] if x["section"] == "Soft starter section"}
    assert {"3RW5214-1AC14", "3RV2032-4DA10", "3RW5980-0CS00", "3RW5980-0HS00", "3RW5980-0HD00", "3UF7933-0BA00-0"} <= ss
    chk = next(c for c in b["client_checks"] if c["requirement"].startswith("Soft Starer"))
    assert chk["verdict"] == "deviation" and "3RV2032-4DA10" in chk["detail"] and "11 - 16A" in chk["detail"]
    assert "communication module on" not in chk["detail"] and "display" not in chk["detail"].split("E101")[0]


def test_part5_sitop_per_panel_and_tower_lamps(rid):
    """Part 5 (owner 2026-10-20). Client (AUTO p.1): 'Separate Power supply for PLC/ CPU and Every ET I/O's - Sitop … (BIO Panel
    10A-1No, 20A-1No) (RO Panel - 20A -1 NO)'; owner: the client's numbers, 10 A for the CPU, 20 A for the I/O, family PSU6200.
    BIO/UF (3-phase input): 6EP3434-7SB00-3AX0 10 A for the CPU (0.56 A × 1.25) + 6EP3436-7SB00-3AX0 20 A for the I/O (KT 10.1
    p.3/21). Tower lamps (plant item, 3 Schneider) → the panel holding the CPU 1513 (the client's PLC block) = BIO/UF."""
    from tests.test_rfq import ALL
    d = rfq_spec.get(rid)
    smps = next(r for r in d["rows"] if r["kind"] == "smps")
    assert smps["panel_answers"] == {"BIO/UF": {"smps_split": "cpu_io", "smps_cpu_min_a": 10.0, "smps_io_min_a": 20.0},
                                     "RO": {"smps_split": "single", "smps_min_a": 20.0}}
    assert next(r for r in d["rows"] if r["kind"] == "tower_lamp")["panels"] == ["BIO/UF"]
    skip = ("spd_make", "meter", "meter_comm", "incomer_release", "incomer_series", "duty", "line_reactor_up_to_kw",
            "vfd_protection", "fuse_holder", "contactor_suppressor", "ss_protection", "ss_comm")
    for k, v in {**{k: v for k, v in ALL.items() if k not in skip}, "fault_ka": 55, "pmr": "false", "smps_input": "3P"}.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    b = rfq_bom.build(rid, "BIO/UF")
    ps = {x["article"]: x["description"] for x in b["bom"] if x["group"] == "Control power"}
    assert set(ps) == {"Siemens 6EP3434-7SB00-3AX0", "Siemens 6EP3436-7SB00-3AX0"} and "for the CPU" in ps["Siemens 6EP3434-7SB00-3AX0"]
    lamp = next(x for x in b["bom"] if x["description"].startswith("Tower lamp"))
    assert lamp["qty"] == 3 and lamp["section"] == "Control supply & control circuit"
    chk = next(c for c in b["client_checks"] if c["requirement"].startswith("Power Supply"))
    assert chk["verdict"] == "complies"


def test_part6_plc_io_at_the_clients_final_count(rid):
    """Part 6 (owner 2026-10-20). Client (AUTO p.1) 'BIO_UF Panel Requirements': final I/O incl. spare DI 272, DO 80,
    AI 40 (4-20 mA) + 4 (0-10 V / 4-20 mA), AO 16. The PLC is sized to at least those counts, no spare % on top (the client's
    spare is in them; a designer's answer still wins): 17 × DI16, 5 × DQ16, 11 × AI4, 4 × AQ4; the check complies."""
    from tests.test_rfq import ALL
    assert rfq_spec.io_final(rfq_spec.get(rid)["plc"]["BIO/UF"]) == {"di": 272, "do": 80, "ai": 44, "ao": 16}
    assert rfq_spec.io_final(rfq_spec.get(rid)["plc"]["RO"]) == {"di": 336, "do": 96, "ai": 60, "ao": 32}
    sp = rfq_spec.answers_for(rid, "BIO/UF")
    assert sp["plc_io_min"][0] == {"di": 272, "do": 80, "ai": 44, "ao": 16} and sp["plc_spare_pct"][0] == 0
    skip = ("spd_make", "meter", "meter_comm", "incomer_release", "incomer_series", "duty", "line_reactor_up_to_kw",
            "vfd_protection", "fuse_holder", "contactor_suppressor", "ss_protection", "ss_comm", "plc_spare_pct")
    for k, v in {**{k: v for k, v in ALL.items() if k not in skip}, "fault_ka": 55, "pmr": "false", "smps_input": "3P"}.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    b = rfq_bom.build(rid, "BIO/UF")
    mods = {x["article"]: x["qty"] for x in b["bom"] if x["group"] == "PLC" and "I/O module" in x["description"]}
    assert mods == {"6ES7131-6BH01-0BA0": 17, "6ES7132-6BH01-0BA0": 5, "6ES7134-6HD01-0BA1": 11, "6ES7135-6HD00-0BA1": 4}, mods
    chk = next(c for c in b["client_checks"] if c["requirement"].startswith("BIO_UF Panel Requirements"))
    assert chk["verdict"] == "complies" and chk["part"] == "PLC & I/O"
    rfq_answers.answer(rid, "project", "plc_spare_pct", 20, "QA designer")           # the designer's spare wins where it gives more
    mods = {x["article"]: x["qty"] for x in rfq_bom.build(rid, "BIO/UF")["bom"] if x["group"] == "PLC" and "I/O module" in x["description"]}
    assert mods["6ES7131-6BH01-0BA0"] == 20 and mods["6ES7135-6HD00-0BA1"] == 4


def test_plc_io_check_reports_a_shortfall():
    reqs = [{"label": "X Panel Requirements", "value": "", "page": 1, "kind": "plc_io", "part_name": "PLC & I/O",
             "require": {"final": {"di": 32, "ao": 8}}}]
    bom = [{"group": "PLC", "article": "6ES7131-6BH01-0BA0", "description": "I/O module: DI 16x24VDC ST", "qty": 2},
           {"group": "PLC", "article": "6ES7135-6HD00-0BA1", "description": "I/O module: AQ 4xU/I ST", "qty": 1}]
    c = rfq_bom.client_checks(reqs, bom)[0]
    assert c["verdict"] == "deviation" and "AO 4 < 8" in c["detail"]
    assert rfq_bom.client_checks(reqs, [])[0]["verdict"] == "not built"
