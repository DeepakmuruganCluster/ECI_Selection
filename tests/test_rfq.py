"""RFQ import, stage 1 (owner 2026-10-18): read the client's equipment panel specification, checked against its totals."""
from pathlib import Path

import pytest

from core import rfq

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sources" / "Sample complete" / "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf"
OTHER = ROOT / "sources" / "Sample complete" / "Schematic for 160KW with PLC.pdf"


@pytest.fixture(scope="module")
def read():
    return rfq.read_pdf(SAMPLE.read_bytes(), SAMPLE.name)


def test_panels_and_printed_totals_are_reproduced(read):
    """Oracle: the 'Panel Total' rows of the sample, pp.2-3 (BIO_Sand Filter_UF Panel Total, RO Panel Total)."""
    assert read["project_ref"] == "WNS2503" and [p["name"] for p in read["panels"]] == ["BIO/UF", "RO"]
    bio, ro = read["panels"]
    assert bio["printed"] == {"total_kw": 264.1, "inv": 22, "dol": 36, "ss": 1, "di": 259, "do": 68, "ai_420": 33, "ai_010": 1, "ao": 10}
    assert ro["printed"] == {"total_kw": 218.9, "inv": 16, "dol": 40, "ss": 2, "di": 330, "do": 83, "ai_420": 48, "ai_010": 1, "ao": 22}
    for p in read["panels"]:
        assert all(abs(p["computed"][k] - p["printed"][k]) < 0.06 for k in rfq.TOTAL_COLS)
    assert len(bio["rows"]) == 89 and len(ro["rows"]) == 109


def test_rows_copy_the_values_as_printed(read):
    bio = read["panels"][0]
    k101 = next(r for r in bio["rows"] if r["tag"] == "K101A/B")
    assert (k101["kw"], k101["amps"], k101["mpcb_rating"], k101["qty"], k101["total_kw"], k101["inv"], k101["kind"], k101["page"]) == \
        (15, 28.52, "28 - 40A", 2, 30, 2, "motor", 1)
    p102 = next(r for r in bio["rows"] if r["tag"] == "P102A/B")
    assert p102["kind"] == "motor_1ph" and p102["supply"].startswith("1PH")


def test_what_the_engine_cannot_use_is_flagged(read):
    rows = {(p["name"], r["tag"]): r for p in read["panels"] for r in p["rows"]}
    assert any("starters 2 ≠ quantity 3" in f for f in rows[("BIO/UF", "P103A/B")]["flags"])
    assert any("outside the stated setting range 1.8 … 2.5 A" in f for f in rows[("BIO/UF", "MX701")]["flags"])
    assert any("1.9 kW is not in the guide" in f for f in rows[("BIO/UF", "P104A/B")]["flags"])
    assert any("single-phase" in f for f in rows[("BIO/UF", "P102A/B")]["flags"])
    assert rows[("BIO/UF", "K101A/B")]["flags"] == []


def test_another_layout_or_file_is_refused():
    with pytest.raises(rfq.RFQError):
        rfq.read_pdf(OTHER.read_bytes(), OTHER.name)               # a drawing set, not an RFQ table
    with pytest.raises(rfq.RFQError, match="not a PDF"):
        rfq.read_pdf(b"hello", "x.pdf")
    with pytest.raises(rfq.RFQError):
        rfq.read_pdf(b"%PDF-1.4 broken", "x.pdf")


def test_range_reading():
    assert rfq._range("0.9 To 1.25A") == (0.9, 1.25) and rfq._range("28 - 40A") == (28, 40)
    assert rfq._range("1.1A To 1.6A") == (1.1, 1.6) and rfq._range("100A") == (None, 100) and rfq._range("") == (None, None)


def test_save_get_list_and_tamper_check(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    data = SAMPLE.read_bytes()
    s = rfq.save(data, SAMPLE.name, "Asha")
    assert s["id"] == rfq.rfq_id(rfq.hashlib.sha256(data).hexdigest()) and s["uploaded_by"] == "Asha"
    assert rfq.save(data, "again.pdf", "Ben")["uploaded_by"] == "Asha"        # the same file: the first upload kept
    g = rfq.get(s["id"])
    assert [p["name"] for p in g["panels"]] == ["BIO/UF", "RO"] and rfq.listing()[0]["id"] == s["id"]
    (tmp_path / "rfq" / s["id"] / "source.pdf").write_bytes(data + b"x")
    with pytest.raises(rfq.RFQError, match="changed"):
        rfq.get(s["id"])
    with pytest.raises(rfq.RFQError):
        rfq.get("../etc")


def test_mpcb_rating_against_the_engine(read):
    """Owner 2026-10-18: a colour per row. Oracle: guide FLC 1.5 kW = 3.6 A → 3RV2011-1FA10, printed 3.5 … 5 A (SIE-SIRIUS-CM
    p.28, same at 10 … 100 kA); MX701 states 1.8 … 2.5 A → unsafe; S102 (1.5 kW) 2.8 … 4 A contains 3.6 A → differs (above the
    3RV2011-1EA10's IE3 usable 3.5 A: confirm the IE class); a drive is not checked."""
    rows = {(p["name"], r["tag"], r["sno"]): r for p in rfq._annotate(read)["panels"] for r in p["rows"]}
    mx = rows[("BIO/UF", "MX701", 1)]["mpcb_check"]
    assert mx["state"] == "unsafe" and mx["flc_a"] == 3.6 and mx["engine_range"] == [3.5, 5.0]
    s102 = rows[("BIO/UF", "S102", 2)]["mpcb_check"]
    assert s102["state"] == "differs" and s102["rfq_mpcb"] == "3RV2011-1EA10" and "IE class" in s102["why"]
    assert rows[("BIO/UF", "K101A/B", 3)]["mpcb_check"]["state"] == "unchecked"
    assert "not in the guide table" in rows[("BIO/UF", "P104A/B", 11)]["mpcb_check"]["why"]
    assert {s for r in rows.values() for s in [(r.get("mpcb_check") or {}).get("state")] if s} <= {"match", "differs", "unsafe", "unchecked"}


def test_current_io_and_signal_checks(read):
    """Owner 2026-10-18: more checks per row. Oracles: guide FLC 1.5 kW 3.6 A vs RFQ 2.71 A = −24.7 % (differs);
    a DOL motor 2 DI + 1 DO per unit = the engine (R-IO-02, slim relay); a VFD with no hardwired I/O = on the fieldbus (R-IO-04);
    the dosing pumps' AO and 1.5 DO per unit differ; LT701 (4-20 mA) has no AI → differs."""
    rows = {(p["name"], r["tag"], r["sno"]): r for p in rfq._annotate(read)["panels"] for r in p["rows"]}
    c = rows[("BIO/UF", "MX701", 1)]["current_check"]
    assert c["state"] == "differs" and c["guide_a"] == 3.6 and c["diff_pct"] == -24.7
    io = rows[("BIO/UF", "MX701", 1)]["io_check"]
    assert io["state"] == "match" and io["variant"] == "slim relay"
    assert rows[("BIO/UF", "K101A/B", 3)]["io_check"]["variant"] == "on the fieldbus"
    assert rows[("BIO/UF", "P407A/B", 15)]["io_check"]["state"] == "differs"
    lt = next(r for (pn, t, _), r in rows.items() if pn == "BIO/UF" and t == "LT701")
    assert lt["signal_check"]["state"] == "differs" and "analog input" in lt["signal_check"]["why"]


def test_panel_checks(read):
    pc = rfq._annotate(read)["panel_checks"]
    bio = {c["check"]: c for c in pc["BIO/UF"]}
    assert "S102" in bio["tags unique in the panel"]["text"] and bio["tags unique in the panel"]["state"] == "differs"
    assert "P412A/B" in bio["tags only in this panel"]["text"]
    assert "S102" in bio["every DOL / soft-starter motor has I/O"]["text"] and "K101A/B" not in bio["every DOL / soft-starter motor has I/O"]["text"]


# owner 2026-10-18: the panel by functional section, and a trial selection one panel at a time
def test_partition_puts_every_row_in_one_section(read):
    from core.rfq_trial import partition, SECTIONS
    for p in read["panels"]:
        part = partition(p)
        assert [s["section"] for s in part] == SECTIONS
        keys = [k for s in part for k in s["rows"]]
        assert len(keys) == len(set(keys)) == len(p["rows"])                  # each row exactly once
        sec = {s["section"]: s for s in part}
        assert sec["VFD section"]["totals"]["inv"] == p["printed"]["inv"]      # the drives add up to the printed count
        assert sec["DOL / MCC section"]["totals"]["dol"] == p["printed"]["dol"]
        assert sec["Soft starter section"]["totals"]["ss"] == p["printed"]["ss"]


def test_trial_runs_one_panel_and_marks_its_values(tmp_path, monkeypatch):
    from core import rfq_trial
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    s = rfq.save(SAMPLE.read_bytes(), SAMPLE.name, "t")
    t = rfq_trial.trial(s["id"], "BIO/UF")
    assert t["trial"] is True and t["values"]["fault_ka"] == 50 and t["value_labels"]["fault_ka"]
    rows = {x["tag"]: x for x in t["rows"]}
    assert rows["K101A/B"]["verdict"] == "pass" and "6SL3210" in rows["K101A/B"]["devices"]
    assert rows["P102A/B"]["verdict"] == "fail" and "single-phase" in rows["P102A/B"]["why"]
    assert rows["MX701"]["verdict"] == "warning"                               # MPCB outside (unsafe)
    assert rows["P104A/B"]["flc_from_rfq"]                                     # 1.9 kW: the RFQ's current, said so
    inc = next(x for x in t["sections"] if x["section"] == "Incoming & distribution")
    assert inc["verdict"] == "fail" and "running units" in inc["result"]       # 991 A > 630 A until the running units are answered
    assert rfq_trial.trial(s["id"], "BIO/UF", {"fault_ka": "25"})["values"]["fault_ka"] == 25
    import pytest
    with pytest.raises(ValueError):
        rfq_trial.trial(s["id"], "BIO/UF", {"nope": 1})
    with pytest.raises(ValueError):
        rfq_trial.trial(s["id"], "XX")


# stage 2 (owner 2026-10-18): the questions the RFQ does not answer — asked once per project, overridable per panel, per row
@pytest.fixture
def saved(tmp_path, monkeypatch):
    from core import auth
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")                         # never the real rfq/ folder
    auth.set_current({"name": "QA designer", "roles": ["designer"]})
    yield rfq.save(SAMPLE.read_bytes(), SAMPLE.name, "t")["id"]
    auth.set_current(None)


def test_questions_start_open_and_nothing_is_assumed(saved):
    from core import rfq_answers
    q = rfq_answers.questions(saved)
    assert q["complete"] is False and all(x["answer"] is None for x in q["project"])
    rel = {x["key"] for x in q["project"] if x["relevant"]}
    rel_open = {x["key"] for x in q["project"] if x["relevant"] and x["value"] is None}
    assert q["project_open"] == len(rel_open) and "spd_make" not in rel and "meter_comm" not in rel   # asked only with a surge arrester / meter
    assert {x["key"]: x["source"] for x in q["project"] if x["value"] is not None} == {"ss_protection": "client spec"}  # the RFQ's protection column
    assert {"cu_encoder", "ss_line_contactor", "io_basis", "voltage_v"} <= rel                   # BIO/UF has drives and a soft starter
    kinds = {k: sum(1 for x in q["rows"]["BIO/UF"] if x["kind"] == k) for k in ("running", "feed", "flc", "units")}
    assert kinds == {"running": 22, "feed": 6, "flc": 2, "units": 1}
    assert len(q["rows"]["RO"]) == 33 and q["status"]["BIO/UF"]["rows_open"] == 31
    flc = next(x for x in q["rows"]["BIO/UF"] if x["kind"] == "flc")
    assert flc["pick"]                                                         # the RFQ's amps offered, not filled in


def test_answers_are_checked_scoped_and_recorded(saved):
    from core import auth, rfq_answers
    with pytest.raises(ValueError):
        rfq_answers.answer(saved, "project", "fault_ka", "abc", "QA designer")
    with pytest.raises(ValueError):
        rfq_answers.answer(saved, "project", "nope", 1, "QA designer")
    with pytest.raises(ValueError):
        rfq_answers.answer(saved, "panel:XX", "fault_ka", 50, "QA designer")
    with pytest.raises(ValueError):
        rfq_answers.answer(saved, "elsewhere", "fault_ka", 50, "QA designer")
    rfq_answers.answer(saved, "project", "fault_ka", "50", "QA designer")
    rfq_answers.answer(saved, "panel:RO", "fault_ka", 36, "QA designer")
    run = next(x for x in rfq_answers.questions(saved)["rows"]["BIO/UF"] if x["kind"] == "running")
    with pytest.raises(ValueError):
        rfq_answers.answer(saved, "row", run["key"] + "|running", run["limits"][1] + 1, "QA designer")
    with pytest.raises(ValueError):
        rfq_answers.answer(saved, "row", run["key"] + "|running", 1.5, "QA designer")
    rfq_answers.answer(saved, "row", run["key"] + "|running", 1, "QA designer")
    assert rfq_answers.for_panel(saved, "BIO/UF")[0]["fault_ka"] == 50 and rfq_answers.for_panel(saved, "RO")[0]["fault_ka"] == 36
    q = rfq_answers.questions(saved)
    n_rel = sum(1 for x in q["project"] if x["relevant"] and (x["value"] is None or x["key"] == "fault_ka"))
    assert q["project_open"] == n_rel - 1 and q["status"]["BIO/UF"]["rows_open"] == 30
    assert [h["by"] for h in q["history"]] == ["QA designer"] * 3 and q["history"][0]["from"] is None
    rfq_answers.answer(saved, "project", "fault_ka", "", "QA designer")       # clears
    assert rfq_answers.questions(saved)["project_open"] == n_rel
    rfq_answers.answer(saved, "project", "spd", "true", "QA designer")         # a surge arrester → its make is asked
    assert {"spd_make", "spd_config", "spd_signalling"} <= {x["key"] for x in rfq_answers.questions(saved)["project"] if x["relevant"]}
    auth.set_current({"name": "QA checker", "roles": ["checker"]})
    with pytest.raises(PermissionError):
        rfq_answers.answer(saved, "project", "fault_ka", 50, "QA checker")


def test_answers_feed_the_trial(saved):
    """Answered: 1 running in every group, single-phase motors fed from outside → the incomer is selected (630 A frame)."""
    from core import rfq_answers, rfq_trial
    for x in rfq_answers.questions(saved)["rows"]["BIO/UF"]:
        if x["kind"] == "running":
            rfq_answers.answer(saved, "row", x["key"] + "|running", 1, "QA designer")
        if x["kind"] == "feed":
            rfq_answers.answer(saved, "row", x["key"] + "|feed", "outside", "QA designer")
    rfq_answers.answer(saved, "project", "fault_ka", 36, "QA designer")
    t = rfq_trial.trial(saved, "BIO/UF")
    assert t["sources"]["fault_ka"] == "answered" and t["values"]["fault_ka"] == 36
    rows = {x["tag"]: x for x in t["rows"]}
    assert rows["P102A/B"]["verdict"] == "outside" and t["verdicts"]["outside"] >= 1 and t["verdicts"].get("fail", 0) == 0
    inc = next(x for x in t["sections"] if x["section"] == "Incoming & distribution")
    assert inc["verdict"] != "fail" and "3VM1463" in str(inc["result"])


# stage 3 (owner 2026-10-18): the full BOM of each panel from the answers, with the panel break
ALL = dict(voltage_v=400, fault_ka=36, panel_internal_c=40, cable_ambient_c=40, cable_m=50, incomer_factor=1.5, incomer_series="3VM", incomer_release="TM210",
           breaking_basis="icu", spd="true", pmr="true", spd_make="Siemens", spd_config="3Ph+N+PE", spd_signalling="true", meter="true",
           meter_comm="profinet", meter_supply="ac_dc", ct_make="rishabh", vfd_protection="fuse", cu_fieldbus="profinet", cu_safety="none", cu_encoder="false",
           duty="normal", emc_filter="none", mc_copy_parameters="false", ss_protection="fuse_gg", ss_line_contactor="false",
           ss_thermistor="false", plc_family="s7-1500-et200sp", plc_cpu="CPU 1513-1 PN", plc_mc_mb=12, io_basis="rfq", plc_spare_pct=20,
           panel_signals="true", relay_make="finder", terminal_make="phoenix", io_conductor_mm2=1, control_supply="transformer",
           estop="true", reset_pb="true", phase_lamps="true", lamp_va=1, smps_input="1P+N", wire_insulation="70", wire_circuits=6,
           cable_other=0, cable_make="polycab", fuse_holder="switch_disconnector", line_reactor_up_to_kw=0,
           contactor_suppressor="varistor", ss_comm="profinet", ss_hmi="standard", ss_hmi_mounting="door", ss_hmi_cable_m="2.5")


def _answer_all(rid):
    from core import rfq_answers
    for k, v in ALL.items():
        rfq_answers.answer(rid, "project", k, v, "QA designer")
    for qs in rfq_answers.questions(rid)["rows"].values():
        for x in qs:      # 1 running per group, single-phase fed from outside, the RFQ's current where asked, every unit fed
            v = {"running": 1, "feed": "outside", "flc": x.get("pick"), "units": (x.get("limits") or [0, 0])[1]}[x["kind"]]
            rfq_answers.answer(rid, "row", x["key"] + "|" + x["kind"], v, "QA designer")


def test_bom_waits_for_every_answer(saved):
    from core import rfq_bom
    b = rfq_bom.build(saved, "BIO/UF")
    assert b["ready"] is False and "project: io_basis" in b["missing"] and any(m.endswith(": running") for m in b["missing"])
    with pytest.raises(ValueError):
        rfq_bom.build(saved, "XX")


def test_bom_panel_by_panel_with_its_sections(saved):
    """Oracle (sample, answered as ALL): BIO/UF Ib 335.39 A × 1.5 → 3VM1463 In 630 A (SIE-3VM-LV31); PLC DI = the RFQ's 259 +
    the 3 panel signals (E-stop, reset, phase failure, R-IO-10); the 6 single-phase pumps answered 'outside' are not in the BOM;
    MX701 keeps the RFQ's 1.8 … 2.5 A MPCB (3RV2011-1CA10, R-DOL-14) and is flagged (3.6 A outside it)."""
    from core import rfq_bom
    _answer_all(saved)
    b = rfq_bom.build(saved, "BIO/UF")
    assert b["ready"] and b["incomer"] == {"article": "3VM1463-4ED32-0AA0", "in_a": 630.0, "ib_a": 335.39}
    assert b["io"]["engine"]["di"] == 259 + 3 and b["io"]["rfq"]["di"] == 259
    assert {x["tag"] for x in b["outside"]} == {"P102A/B", "P407A/B", "P411A/B", "P412A/B", "P419A/B", "P704A/B"}
    assert all(x["section"] in rfq_bom.SECTIONS for x in b["bom"])
    secs = [x["section"] for x in b["sections"]]
    assert secs[:4] == ["Incoming & distribution", "VFD section", "DOL / MCC section", "Soft starter section"]
    assert sum(x["n_lines"] for x in b["sections"]) == b["n_bom_lines"]
    f = {x["tag"]: x for x in b["feeders"]}
    assert f["MX701"]["devices"].startswith("3RV2011-1CA10") and "MX701" in b["rfq_mpcb_flags"]
    assert f["K101A/B"]["running"] == 1 and all(x["status"] == "selected" for x in b["feeders"])
    vfd = [x for x in b["bom"] if x["section"] == "VFD section"]
    assert vfd and all(x["article"].startswith(("6SL", "3NA", "3NP")) for x in vfd if x["group"] == "Feeders" and "Control Unit" not in x["description"] and "BOP" not in x["description"])


def test_bom_workbook_has_every_panel(saved):
    import zipfile, io as io_
    from core import rfq_bom
    _answer_all(saved)
    data, info = rfq_bom.export(saved)
    assert info == {"panels": 2, "built": 2}
    wb = zipfile.ZipFile(io_.BytesIO(data)).read("xl/workbook.xml").decode()
    for n in ("Summary", "BIO_UF BOM", "BIO_UF feeders", "RO BOM", "RO open points", "Not in a BOM", "All panels"):
        assert f'name="{n}"' in wb
