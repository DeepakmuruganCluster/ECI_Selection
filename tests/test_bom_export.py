from core.bom_export import build
from core.xlsx import read_back

INPUTS = {"load_list": "M1 7.5 DOL flc=15.5 cable=50\nF1 37 VFD flc=66 cable=50\nM3 3.7 DOL cable=30",
          "fault_ka": 50, "panel_internal_c": 45, "motor_pf": 0.85, "cable_ambient_c": 40, "site_ambient_c": 35}


def test_workbook_has_all_sheets_and_traceable_lines():
    data, info = build(INPUTS, client_panel="RO", title="test")
    wb = read_back(data)
    assert list(wb) == ["Summary", "BOM", "Feeders", "Open points", "Sources"]
    bom = wb["BOM"]
    assert bom[0][:5] == ["Group", "Article / model", "Description", "Make", "Qty"]
    arts = {r[1]: r for r in bom[1:]}
    assert arts["3RV2021-4BA10"][4] == "1" and arts["6SL3210-1PE27-5UL0"][4] == "1"
    assert arts["3RV2021-4BA10"][3] == "Siemens"                      # the make column (2026-10-15)
    # every line has a status; client lines cite the spec page
    assert all(r[6] for r in bom[1:])
    assert any(r[7].startswith("ECI-WNS2503-AUTO p.") for r in bom[1:])
    # the RO section-width finding and the 3.7 kW refusal are open points
    text = "\n".join(" ".join(r) for r in wb["Open points"])
    assert "7400" in text and "M3" in text
    assert info["bom_lines"] == len(bom) - 1


def test_invalid_input_raises():
    import pytest
    with pytest.raises(ValueError):
        build({**INPUTS, "motor_pf": 1.5})   # out of range (a missing power factor is allowed since 2026-10-14)
