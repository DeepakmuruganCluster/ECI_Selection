"""Alternatives for a BOM line change the design choice behind it, so linked parts follow (R-REQ-22, 2026-10-15)."""
from _answers import ASK, complete
import json

from components.requirement.select import select as requirement
from _answers import auto as _auto
requirement = _auto(requirement)    # audit 2026-10-17: per-case questions answered the old way
from core.alternatives import alternatives, _diff

INP = complete(text="75 kW conveyor with VFD, 50 m cable; 2 x 11 kW pumps DOL, 30 m cable. 400 V, 25 kA, site 35 °C, PROFINET, STO, energy meter",
           panel_internal_c=40, cu_encoder=False, mc_copy_parameters=True, ct_make="rishabh", plc_make="siemens_s71200g2", spd=False, pmr=False, control_supply="transformer", **ASK)
DRIVE = {"group": "Feeders", "article": "6SL3210-1PE31-8UL0", "description": "SINAMICS PM240-2 HO 75 kW", "used_by": "M1"}


def _apply(answer):
    inp = dict(INP)
    for k, v in answer.items():
        if "." in k:
            tag, key = k.split(".")
            ms = [{} for _ in range(2)]
            ms[int(tag[1:]) - 1][key] = v
            inp["motors"] = ms
        else:
            inp[k] = v
    return requirement(**inp, confirmed=True)


def test_drive_alternatives_change_the_linked_parts():
    r = alternatives(INP, DRIVE)
    normal = next(o for o in r["options"] if o["knob"] == "duty")
    arts = {(c["article"], c["kind"]) for c in normal["changes"]}
    # LO 75 kW: a smaller power module AND its own Siemens-listed fuse AND the wiring follow (not the module alone)
    assert ("6SL3210-1PE31-8UL0", "removed") in arts and ("3NA3142", "removed") in arts
    assert any(a.startswith("6SL3210") and k == "added" for a, k in arts) and any(a.startswith("3NA") and k == "added" for a, k in arts)
    assert any("Lapp" in a for a, _ in arts)


def test_applying_an_option_gives_exactly_the_bom_it_showed():
    base = requirement(**INP, confirmed=True)
    for o in alternatives(INP, DRIVE)["options"]:
        if o.get("needs"):          # an option that needs answers first (e.g. the kit, R-REQ-32) shows no BOM until answered
            continue
        after = _apply(o["answer"])
        assert _diff(base.value["bom"], after.value["bom"]) == o["changes"], o["label"]


def test_no_option_leaves_a_feeder_unselected():
    base = {f["tag"] for f in requirement(**INP, confirmed=True).value["feeders"] if f["status"] == "selected"}
    for o in alternatives(INP, DRIVE)["options"]:
        after = {f["tag"] for f in _apply(o["answer"]).value["feeders"] if f["status"] == "selected"}
        assert base <= after, o["label"]


def test_prompt_ranks_but_never_claims_unpriced_savings():
    r = alternatives(INP, {"group": "Feeders", "article": "3RV2021-4DA10", "used_by": "M2"}, "cheaper")
    assert all(o["score"] == 0 for o in r["options"] if o["unpriced_changes"])          # no price, no 'cheaper'
    r = alternatives(INP, DRIVE, "use a circuit breaker for the drive")
    assert r["options"][0]["value"] == "breaker"


def test_needs_a_selected_machine():
    import pytest
    with pytest.raises(ValueError):
        alternatives({"text": "11 kW pump"}, DRIVE)
