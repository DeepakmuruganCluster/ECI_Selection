"""The assistant's guard: proposals must quote the designer's own words and name a known input (no API call)."""
from core.assistant import check_proposals


def test_proposal_kept_only_with_the_designers_words():
    msg = "It's about 40 degrees inside the panel and the cables are 50 m long"
    kept, dropped = check_proposals([
        {"input": "panel_internal_c", "value": "40", "words": "about 40 degrees inside the panel"},
        {"input": "cable_m", "value": "50", "words": "cables are 50 m"},
        {"input": "voltage_v", "value": "400", "words": "Germany"},            # invented: not in the message
        {"input": "price_inr", "value": "5000", "words": "50 m"},              # not an input the tool asks for
    ], msg, motors=1)
    assert [k["input"] for k in kept] == ["panel_internal_c", "cable_m"]
    assert len(dropped) == 2


def test_motor_prefix_must_exist():
    kept, dropped = check_proposals([{"input": "M3.cable_m", "value": "30", "words": "30 m"}], "M3 has 30 m", motors=2)
    assert not kept and "no such motor" in dropped[0]
