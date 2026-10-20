"""The drawing set (owner 2026-10-17: better than the company sample AVELCPSDL08WPLC, OWN-PROPEL-SCH160)."""
from _answers import ASK, ask, answered
import html
import re

import pytest

from components.requirement.select import select
from _answers import auto as _auto
select = _auto(select)    # audit 2026-10-17: per-case questions answered the old way
from core import templates as T
from core.drawing_tags import plan, _compact
from core.sld import build_sld

DEMO = dict(text="crusher 160 kW star delta, conveyor 11 kW DOL, 2 x 5.5 kW pumps DOL, fan 30 kW VFD, Siemens S7-1200 PLC",
            confirmed=True, voltage_v=415, fault_ka=25, panel_internal_c=40, cable_ambient_c=40, cable_m=50, cu_encoder=False,
            cu_safety="none", cu_fieldbus="profinet", mc_copy_parameters=False, plc_make="siemens_s71200g2", spd=True,
            spd_make="siemens", pmr=True, control_supply="transformer", **ASK)


def _text(svg):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", svg)))


def _titles(sheets):
    return [html.unescape(re.search(r'data-title="([^"]+)"', s).group(1)) for s in sheets]


def _tpl(sheet):
    t = next(x for x in T.catalogue() if x["sheet"] == sheet)
    return select(text=T.text(t["id"]), template=t["id"], confirmed=True, **{k: int(v) for k, v in T.answers(t["id"]).items()}).value


@pytest.fixture(scope="module")
def demo():
    v = select(**DEMO).value
    return v, build_sld(v, "Demo")


def test_company_sheet_order_and_index(demo):
    v, sheets = demo
    titles = _titles(sheets)
    assert titles[:5] == ["COVER SHEET", "INDEX SHEET", "LEGENDS, ABBREVIATIONS & SYMBOLS", "TECHNICAL DETAILS", "SINGLE LINE DIAGRAM"]
    order = ["POWER WIRING", "CONTROL SUPPLY", "CONTROL WIRING", "DIGITAL INPUT", "TERMINAL DETAILS", "BILL OF MATERIAL"]
    firsts = [next(i for i, t in enumerate(titles) if t.startswith(o)) for o in order]
    assert firsts == sorted(firsts)
    idx = _text(sheets[1])
    for i, t in enumerate(titles, 1):           # the index gives every sheet its real number
        base = re.sub(r"-\d+$", "", t)
        assert base in idx
    assert "not made by the tool" in idx     # GA and block diagram: listed, not pretended


def test_every_bom_tag_is_on_a_drawing_and_every_part_listed(demo):
    v, sheets = demo
    p = plan(v)
    drawings = " ".join(_text(s) for s in sheets if not _titles([s])[0].startswith(("BILL OF", "LEGENDS")))
    bom = " ".join(_text(s) for s in sheets if _titles([s])[0].startswith("BILL OF"))
    for i, b in enumerate(v["bom"]):
        if b["group"] == "Not selected":
            continue
        assert str(b["article"])[:30] in bom, b["article"]
        tag = p["line_tags"].get(i, "")
        if tag and tag != "—" and " " not in tag and "," not in tag:      # a device tag (not 'M1 kit', 'aux K1', lists)
            first = re.split(r"-(?=[A-Z])", tag)[0]
            assert re.search(rf"\b{re.escape(first)}\b", drawings), (tag, b["article"])


def test_tags_follow_the_company_legend(demo):
    v, sheets = demo
    p = plan(v)
    m1 = next(u for u in p["units"] if u["tag"] == "M1")
    assert m1["dev"]["k"] == ["K1", "K2", "K3"]                 # main, delta, star (p.6)
    assert [p["devices"][k]["role"] for k in m1["dev"]["k"]] == ["main", "delta", "star"]
    assert p["devices"]["1SQ1"]["kind"] == "incomer" and "R-PHASE" in p["devices"] and "SMPS" in p["devices"]
    assert _compact(["1F1", "1F2", "1F3", "K1", "K2", "H4"]) == "1F1-1F3, K1-K2, H4"


def test_cross_references_resolve(demo):
    v, sheets = demo
    allt = " ".join(sheets)
    assert "\x00" not in allt
    titles = _titles(sheets)
    lad = titles.index("CONTROL WIRING DIAGRAM-1") + 1
    power = next(s for s in sheets if 'data-title="POWER WIRING DIAGRAM-1' in s)
    assert re.search(rf"coil: {lad}\.\d[A-D]", power)            # motor → its coil on the ladder
    ladder = sheets[lad - 1]
    pw = titles.index("POWER WIRING DIAGRAM-1") + 1
    assert re.search(rf"main {pw}\.\d[A-D]", ladder)              # coil → its main contacts on the power sheet


def test_star_delta_ladder_from_the_company_sequence(demo):
    v, sheets = demo
    ladder = _text(next(s for s in sheets if 'data-title="CONTROL WIRING DIAGRAM-1' in s))
    for s in ("TIMER", "STAR", "DELTA", "MAIN", "T1", "IR3", "O_M1_Run", "AVELCPSDL08WPLC p.11"):
        assert s in ladder, s
    assert "PROFINET" in ladder                                    # the drive: no hardwired control


def test_io_sheet_names_and_relays(demo):
    v, sheets = demo
    io = _text(next(s for s in sheets if 'data-title="DIGITAL INPUT' in s))
    for r in v["io_list"]:
        if r["type"] in ("DI", "DO"):
            assert r["name"] in io and r["channel"] in io
    assert "IR1" in io and "X2:1" in io


def test_title_block_from_the_versions(demo):
    v, _ = demo
    meta = {"version": {"v": 4, "state": "approved", "by": "Asha", "at": "2026-10-17T10:00:00", "checked_by": "Ben",
                        "checked_at": "2026-10-17T11:00:00", "approved_by": "Ravi", "approved_at": "2026-10-17T12:00:00"},
            "revisions": [{"v": 4, "state": "approved", "summary": "BOM: replace K1", "by": "Asha", "at": "2026-10-17T10:00:00"}],
            "project": "Plant X", "panel": "MCC-1", "client": "Client Y"}
    s = _text(build_sld(v, "MCC-1", meta=meta)[5])
    for x in ("Asha", "Ben", "Ravi", "APPROVED", "v4", "BOM: replace K1", "CLIENT Y", "04"):
        assert x in s, x
    d = _text(build_sld(v, "MCC-1")[5])
    assert "DRAFT — not for construction" in d and "no version yet" in d


def test_template_auxiliary_feeders_are_not_given_to_the_motor():
    """160KW SD WITH PLC: the 3 star-delta contactors are the motor's; the smaller contactors are auxiliary drives whose
    motors the template does not state; overload relays whose range does not cover the motor current are not its own."""
    v = _tpl("160KW SD WITH PLC")
    p = plan(v)
    m1 = next(u for u in p["units"] if u["tag"] == "M1")
    assert [p["devices"][k]["line"]["article"] for k in m1["dev"]["k"]] == ["LC1E200M5", "LC1E200M5", "LC1E160M5"]
    assert "olr" not in m1["dev"] and m1["dev"]["mpr"] == ["MPR1"] and len(m1["aux_prot"]) == 4
    aux = [u for u in p["units"] if u["status"] == "template-aux"]
    assert len(aux) == 5 and all(u["kw"] is None for u in aux)
    power = " ".join(_text(s) for s in build_sld(v, "t") if 'data-title="POWER WIRING' in s)
    assert "motor not stated" in power and "without the motor each protects" in power


def test_template_gaps_are_flagged_not_drawn():
    sheets = build_sld(_tpl("VSI 300"), "VSI 300")
    allt = " ".join(_text(s) for s in sheets)
    assert "the template lists only K4 for this motor" in allt and "star-delta incomplete in the template" in allt
    assert "NO PLC IN THIS PANEL" in allt and "1F1-1F25" in allt


@pytest.mark.parametrize("t", list(T.catalogue()), ids=lambda t: f"{t['sheet']}|{t['row']}")
def test_every_template_draws(t):
    v = select(text=T.text(t["id"]), template=t["id"], confirmed=True, **{k: int(x) for k, x in T.answers(t["id"]).items()}).value
    sheets = build_sld(v, t["title"])
    assert len(sheets) >= 9 and "\x00" not in "".join(sheets)
    if v["scope"].get("plc") is False:
        assert "NO PLC IN THIS PANEL" in " ".join(sheets)
    if v["scope"].get("incomer") is False:
        assert "NO INCOMER" in " ".join(sheets)


def test_single_line_agrees_with_the_power_sheet():
    """The overview is drawn from the same plan: the 160 kW motor keeps K1-K3 and MPR1; K4-K8 are auxiliary feeders."""
    sheets = build_sld(_tpl("160KW SD WITH PLC"), "t")
    sld = _text(next(s for s in sheets if 'data-title="SINGLE LINE' in s))
    assert "K1-K3" in sld and "K1-K8" not in sld and "MPR1" in sld and "OLR1" not in sld.split("AUXILIARY FEEDERS")[0]
    for k in range(1, 6):
        assert f"M1-AUX{k}" in sld
    assert "motor not stated in the template" in sld and "AUXILIARY FEEDERS" in sld


def test_control_supply_follows_the_choice():
    """CC-1 (owner 2026-10-17): asked every time. Phase-neutral: no transformer drawn; transformer without coil VA: 'not sized'."""
    b = dict(text="11 kW pump DOL, 400 V, 25 kA, 30 m cable", confirmed=True, panel_internal_c=40, cable_ambient_c=30,
             plc_make="siemens_s71200g2", spd=False, pmr=False)
    asked = select(**b).value
    assert not asked["selected"] and any(q["input"] == "control_supply" for q in asked["questions"])
    sheet = lambda v: _text(next(s for s in build_sld(v, "t") if 'data-title="CONTROL SUPPLY' in s))
    pn = select(**b, control_supply="phase_neutral").value
    assert pn["control_supply"] == "phase_neutral" and "PRIMARY" not in sheet(pn) and "PHASE-NEUTRAL 230 V" in sheet(pn)
    d = answered(select, **b, control_supply="transformer").value
    assert d["control_supply"] == "transformer" and d["control_supply_how"] == "given"
    assert "PRIMARY" in sheet(d) and "NOT SIZED" not in sheet(d)     # lamp VA is asked now (R-REQ-32): the transformer is sized
    sized = select(**ask(**b, control_supply="transformer", coil_va=10, lamp_va=2)).value
    assert "PRIMARY" in sheet(sized) and "TRA1" in sheet(sized)


def test_template_control_supply_from_its_lines():
    """A template is not asked (R-REQ-30): its transformer line decides."""
    v = _tpl("160KW SD WITH PLC")
    assert v["control_supply"] == "transformer" and v["control_supply_how"] == "template"


# --- interdependency audit 2026-10-17: the drawing set follows every edit and every line ---------------------------------
AUD = ask(confirmed=True, voltage_v=400, fault_ka=25, panel_internal_c=40, cable_ambient_c=40, cable_m=50, cu_encoder=False,
           cu_safety="none", cu_fieldbus="profinet", mc_copy_parameters=False, plc_make="siemens_s71200g2", spd=True,
           spd_make="siemens", pmr=True, control_supply="transformer", coil_va=10, lamp_va=1)


def test_a_line_shared_by_two_motors_is_split_not_repeated():
    v = select(text="pump 5.5 kW DOL; pump 5.5 kW DOL; Siemens S7-1200 PLC", **AUD).value
    p = plan(v)
    assert [(u["tag"], u["dev"].get("mpcb"), u["dev"].get("k")) for u in p["units"]] == [("M1", ["Q1"], ["K1"]), ("M2", ["Q2"], ["K2"])]
    allt = " ".join(_text(s) for s in build_sld(v, "t"))
    assert "AUX" not in allt and "Q3" not in allt and "K3" not in allt


def test_removed_lines_are_not_drawn_and_control_mcbs_are_mcbs():
    base = select(text=DEMO["text"], **AUD).value
    p = plan(base)
    tags = {b["article"]: p["line_tags"].get(i) for i, b in enumerate(base["bom"])}
    assert tags["5SY72058CC"] == "2Q1" and tags["5SL42027RC"] == "2Q2" and tags["Control transformer 150 VA"] == "TRA1"
    for art in ("5SD7464-1", "Control transformer 150 VA"):
        b = next(x for x in base["bom"] if x["article"] == art)
        v = select(text=DEMO["text"], **AUD, edits=[{"action": "remove", "line": {k: b[k] for k in ("group", "article", "description")}}]).value
        assert art not in {d["line"]["article"] for d in plan(v)["devices"].values()}
    cs = _text(next(s for s in build_sld(v, "t") if 'data-title="CONTROL SUPPLY' in s))
    assert "REMOVED by a BOM edit" in cs and "PRIMARY" not in cs


def test_drive_breaker_is_the_drives_protection():
    v = select(text=DEMO["text"], **{**AUD, "vfd_protection": "breaker"}).value
    m4 = next(u for u in plan(v)["units"] if u["tag"] == "M4")
    assert m4["dev"].get("mpcb") and "3VA" in plan(v)["devices"][m4["dev"]["mpcb"][0]]["line"]["article"]


def test_template_control_supply_conflict_is_flagged():
    t = next(x for x in T.catalogue() if x["sheet"] == "160KW SD WITH PLC")
    r = select(text=T.text(t["id"]), template=t["id"], confirmed=True, control_supply="phase_neutral")
    assert any(c.verdict == "warn" and "control supply phase_neutral chosen" in c.value for c in r.checks)
