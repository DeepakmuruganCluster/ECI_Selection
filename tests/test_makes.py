"""Every BOM line names its make (owner request 2026-10-15), and the BOM is organised the same way on the page and in Excel."""
from _answers import ASK, ask, answered
from components.requirement.select import select as requirement
from _answers import auto as _auto
requirement = _auto(requirement)    # audit 2026-10-17: per-case questions answered the old way
from core import project as P
from core.bom_layout import SECTIONS, ordered, section_of
from core.bom_edit import search
from core.makes import make_of

MULTI = ("75 kW conveyor with VFD, 50 m cable; 2 x 11 kW pumps DOL, 30 m cable; 160 kW crusher with star delta starter, "
         "50 m cable. 400 V, 25 kA, site 35 °C, PROFINET, STO, energy meter, surge arrester, phase monitoring relay")


def test_every_engineered_line_of_a_machine_has_a_make():
    r = answered(requirement, text=MULTI, panel_internal_c=40, cu_encoder=False, mc_copy_parameters=True, ct_make="rishabh",
                    plc_make="siemens_s71200g2", spd_make="siemens", control_supply="transformer", confirmed=True)
    missing = [b["article"] for b in r.value["bom"] if b["article"] and not b.get("make")]
    # the company sheets' unpriced 'wiring accessories' lines name no make: shown as "—", never guessed
    assert all(a.startswith("Wiring accessories") for a in missing), missing
    makes = {b["article"]: b["make"] for b in r.value["bom"] if b["article"]}
    assert makes["6SL3210-1PE31-8UL0"] == "Siemens" and makes["38.61.7.024.0050"] == "Finder"
    assert makes["Lapp H07V-K 4 mm²"] == "Lapp" and makes["Emergency Stop Hood"] == "Not fixed (any reputed make)"
    assert any(v == "Polycab" for k, v in makes.items() if "XLPE" in k) and makes["2ASDT0"] == "GIC"


def test_every_engineered_line_of_a_project_has_a_make():
    from components.project.select import select
    for panel in P.panels():
        r = select(panel=panel, **(P.load().get("design_inputs") or {}))
        missing = [b for b in r.value["bom"] if b["article"] and not b.get("make")]
        # only the client's own items without a stated make (busbars, UPS, network items, plinth)
        assert all(b["group"].startswith(("Client spec", "Out of scope")) for b in missing), [b["article"] for b in missing]


def test_make_is_never_guessed():
    assert make_of({"article": "XYZ-123 unknown", "description": "something"}) is None
    assert make_of({"article": "3RT2027-1AP00"}) == "Siemens"
    assert make_of({"article": "X", "description": "Lamp (REPUTED)"}) == "Not fixed (any reputed make)"


def test_sections_in_build_order():
    bom = [{"group": g} for g in ("Not selected", "PLC", "Feeders", "Client spec (RO)", "Incomer", "Motor cables")]
    assert [b["group"] for b in ordered(bom)] == ["Incomer", "Feeders", "Motor cables", "PLC", "Client spec (RO)", "Not selected"]
    assert section_of("Client spec (RO)") == "Client and project items" and SECTIONS[0][0].startswith("Incoming")


def test_catalog_search_for_adding_a_component():
    hits = search("3RT2027")
    assert hits and hits[0]["article"].startswith("3RT2027") and hits[0]["make"] == "Siemens"
    assert search("x") == []
