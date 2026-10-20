"""Company standards and RFQ row rules (owner 2026-10-19): fewer inputs, every value still says where it comes from."""
from pathlib import Path

import pytest

from core import auth, rfq, rfq_answers, standards

SAMPLE = Path(__file__).resolve().parents[1] / "sources" / "Sample complete" / \
    "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf"
DESIGNER = {"name": "QA designer", "roles": ["designer"]}
APPROVER = {"name": "QA approver", "roles": ["approver"]}


@pytest.fixture
def tmp_std(tmp_path, monkeypatch):
    monkeypatch.setattr(standards, "STANDARDS", tmp_path / "standards")      # never the real standards/ folder
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    auth.set_current(DESIGNER)
    yield
    auth.set_current(None)


def _approved(values, name="Water — Siemens"):
    s = standards.save(name, values)
    auth.set_current(APPROVER)
    standards.approve(s["id"], s["version"])
    auth.set_current(DESIGNER)
    return s["id"]


def test_standard_rules(tmp_std):
    with pytest.raises(ValueError):
        standards.save("Site", {"fault_ka": 50})                     # a site question is never in a standard
    with pytest.raises(ValueError):
        standards.save("Bad", {"relay_make": "acme"})
    with pytest.raises(ValueError):
        standards.save("x", {"relay_make": "finder"})                # a name of 2 … 80 characters
    s = standards.save("Water — Siemens", {"relay_make": "finder", "plc_spare_pct": "20", "estop": "true"})
    assert s["state"] == "draft" and s["values"] == {"relay_make": "finder", "plc_spare_pct": 20.0, "estop": "true"}
    with pytest.raises(ValueError):
        standards.snapshot(s["id"])                                   # not approved: cannot be applied
    with pytest.raises(PermissionError):
        standards.approve(s["id"], 1)                                 # a designer does not approve
    auth.set_current({"name": "QA designer", "roles": ["designer", "approver"]})
    with pytest.raises(PermissionError):
        standards.approve(s["id"], 1)                                 # four eyes: not the author
    auth.set_current(APPROVER)
    a = standards.approve(s["id"], 1)
    assert a["state"] == "approved" and a["approved"]["by"] == "QA approver"
    auth.set_current(DESIGNER)
    e = standards.save("Water — Siemens", {"relay_make": "phoenix"}, sid=s["id"])   # a change is a new draft
    assert e["version"] == 2 and e["state"] == "draft"
    snap = standards.snapshot(s["id"])
    assert snap["v"] == 1 and snap["values"]["relay_make"] == "finder"   # the RFQ still gets the approved version


def test_rfq_with_a_standard_and_row_rules(tmp_std):
    sid = _approved({"relay_make": "finder", "plc_family": "s7-1500-et200sp", "io_basis": "rfq"})
    rid = rfq.save(SAMPLE.read_bytes(), SAMPLE.name, "t")["id"]
    before = rfq_answers.questions(rid)
    rfq_answers.apply_standard(rid, sid, "QA designer")
    q = rfq_answers.questions(rid)
    p = {x["key"]: x for x in q["project"]}
    assert p["relay_make"]["source"] == "standard" and p["relay_make"]["value"] == "finder" and p["relay_make"]["answer"] is None
    assert p["plc_cpu"]["relevant"]                                    # the standard's S7-1500 makes its CPU question relevant
    assert q["standard"]["name"] == "Water — Siemens" and q["standard"]["approved_by"] == "QA approver"
    rfq_answers.answer(rid, "project", "relay_make", "phoenix", "QA designer")      # an answer wins over the standard
    assert {x["key"]: x for x in rfq_answers.questions(rid)["project"]}["relay_make"]["source"] == "answered"
    assert rfq_answers.for_panel(rid, "RO")[0]["relay_make"] == "phoenix"
    rfq_answers.answer(rid, "project", "relay_make", "", "QA designer")             # cleared → the standard again
    assert rfq_answers.for_panel(rid, "RO")[0]["relay_make"] == "finder"
    assert rfq_answers.sources(rid, "RO")["relay_make"] == "standard Water — Siemens v1"
    # row rules
    with pytest.raises(ValueError):
        rfq_answers.set_rules(rid, {"running": {"2": 3}}, "QA designer")            # 3 of 2 cannot run
    with pytest.raises(ValueError):
        rfq_answers.set_rules(rid, {"feed": "somewhere"}, "QA designer")
    rows_before = sum(s_["rows_open"] for s_ in before["status"].values())
    rfq_answers.set_rules(rid, {"running": {str(g): 1 for g in before["rule_groups"]}, "feed": "outside", "flc": "rfq",
                                "units": "starters"}, "QA designer")
    q = rfq_answers.questions(rid)
    assert q["rows_by_rule"] == rows_before and all(s_["rows_open"] == 0 for s_ in q["status"].values())
    run = next(x for x in q["rows"]["BIO/UF"] if x["kind"] == "running" and x["limits"][1] == 2)
    rfq_answers.answer(rid, "row", run["key"] + "|running", 2, "QA designer")      # a row's own answer wins
    r2 = next(x for x in rfq_answers.questions(rid)["rows"]["BIO/UF"] if x["key"] == run["key"] and x["kind"] == "running")
    assert r2["value"] == 2 and r2["source"] == "answered" and r2["by_rule"] == 1
    assert rfq_answers.for_panel(rid, "BIO/UF")[1][run["key"]]["running"] == 2
    auth.set_current({"name": "QA checker", "roles": ["checker"]})
    with pytest.raises(PermissionError):
        rfq_answers.set_rules(rid, {}, "QA checker")
    with pytest.raises(PermissionError):
        rfq_answers.apply_standard(rid, None, "QA checker")


def test_bom_from_a_standard_the_site_answers_and_rules(tmp_std):
    """With a standard holding every company answer, an RFQ needs only the site questions and the row rules."""
    from tests.test_rfq import ALL
    from core import rfq_bom
    sid = _approved({k: v for k, v in ALL.items() if k not in standards.SITE})
    rid = rfq.save(SAMPLE.read_bytes(), SAMPLE.name, "t")["id"]
    rfq_answers.apply_standard(rid, sid, "QA designer")
    open_ = [x["key"] for x in rfq_answers.questions(rid)["project"] if x["relevant"] and x["value"] is None]
    assert sorted(open_) == sorted(k for k in standards.SITE)            # only the site questions are left
    for k in standards.SITE:
        rfq_answers.answer(rid, "project", k, ALL[k], "QA designer")
    g = rfq_answers.questions(rid)["rule_groups"]
    rfq_answers.set_rules(rid, {"running": {str(x): 1 for x in g}, "feed": "outside", "flc": "rfq", "units": "starters"}, "QA designer")
    assert rfq_answers.missing(rid, "BIO/UF") == []
    b = rfq_bom.build(rid, "BIO/UF")
    assert b["ready"] and b["incomer"]["article"] == "3VM1463-4ED32-0AA0"
