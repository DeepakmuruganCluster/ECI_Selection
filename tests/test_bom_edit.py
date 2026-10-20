import pytest
"""R-PRJ-17: designer edits are checked by the engine and applied with the original kept."""
from core import bom_edit as E

LINES = [{"group": "Feeders", "article": "3RV2021-4BA10", "description": "MPCB 13 … 20 A", "qty": 2, "unit": "no",
          "status": "engineered — awaiting sign-off", "source": "SIE-SIRIUS-CM p.28", "used_by": "P1"},
         {"group": "PLC", "article": "6ES7131-6BH01-0BA0", "description": "I/O module: DI 16x24VDC ST", "qty": 23,
          "unit": "no", "status": "engineered", "source": "SIE-ST70-2026 p.1395", "used_by": ""}]


def test_check_uses_the_catalog_and_fails_closed():
    assert E.check({"action": "replace", "article": "3RV2021-4CA10"})["verdict"] == "ok"
    assert E.check({"action": "replace", "article": "NOT-A-PART-1"})["verdict"] == "unsourced"
    assert not E.check({"action": "qty", "qty": -1})["ok"]
    assert not E.check({"action": "qty", "qty": 1.5})["ok"]
    assert not E.check({"action": "explode"})["ok"]


def test_apply_keeps_the_original_and_says_who():
    edits = [{"id": 1, "panel": "X", "line": E.line_ref(LINES[0]), "action": "replace", "article": "3RV2021-4CA10",
              "description": None, "qty": None, "proposed_by": "assistant", "check": E.check({"action": "replace", "article": "3RV2021-4CA10"})},
             {"id": 2, "panel": "X", "line": E.line_ref(LINES[1]), "action": "qty", "article": None, "qty": 24,
              "proposed_by": "designer", "check": {"verdict": "ok"}},
             {"id": 3, "panel": "X", "line": {"group": "Gone", "article": "Z", "description": "z"}, "action": "remove",
              "proposed_by": "designer", "check": {"verdict": "ok"}},
             {"id": 4, "panel": "Y", "line": E.line_ref(LINES[0]), "action": "remove", "proposed_by": "designer",
              "check": {"verdict": "ok"}}]
    out, unmatched = E.apply(LINES, edits, "X")
    assert out[0]["article"] == "3RV2021-4CA10" and out[0]["original"]["article"] == "3RV2021-4BA10"
    assert "AI-assisted" in out[0]["status"] and out[0]["source"] == edits[0]["check"]["source"]
    assert out[1]["qty"] == 24 and out[1]["original"]["qty"] == 23 and "designer" in out[1]["status"]
    assert [e["id"] for e in unmatched] == [3]          # reported, not dropped
    assert LINES[0]["article"] == "3RV2021-4BA10"         # the input BOM is not changed
    assert all(l.get("qty") != 0 for l in out)            # panel Y's removal does not touch panel X


def test_candidates_prefer_the_same_family():
    c = E.candidates(LINES[0])
    assert c and all(x["article"].startswith("3RV2") for x in c[:5])


def test_assistant_edit_proposals_are_grounded():
    """The assistant's proposal is kept only with the designer's words and an article from the prompt or the candidates."""
    from core.assistant import check_edit_proposal
    cands = [{"article": "3RV2021-4CA10", "make": "Siemens", "description": ""}]
    prompt = "use the next size up, 3RV2021-4CA10, and make it 3 off"
    ok, _ = check_edit_proposal({"action": "replace", "article": "3RV2021-4CA10", "qty": "3", "words": "make it 3 off",
                                 "reply": "r"}, prompt, cands)
    assert ok == {"action": "replace", "article": "3RV2021-4CA10", "qty": "3"}
    bad, why = check_edit_proposal({"action": "replace", "article": "3RV2031-4XX10", "qty": "", "words": "next size up",
                                    "reply": "r"}, prompt, cands)
    assert bad is None and "neither" in why
    bad, why = check_edit_proposal({"action": "qty", "article": "", "qty": "5", "words": "five please", "reply": "r"},
                                   prompt, cands)
    assert bad is None and "not in your prompt" in why
    none, why = check_edit_proposal({"action": "none", "article": "", "qty": "", "words": "", "reply": "Which size?"},
                                    prompt, cands)
    assert none is None and why == "Which size?"


@pytest.mark.parametrize("qty", ["nan", "inf", "-inf", float("nan"), "1e999"])
def test_impossible_quantities_are_invalid(qty):
    """Test-agent finding 2026-10-14: 'nan' raised ValueError, 'inf' OverflowError instead of an invalid verdict."""
    from core.bom_edit import check
    assert check({"action": "qty", "qty": qty})["verdict"] == "invalid"


def test_add_needs_at_least_one():
    """Test-agent finding 2026-10-14: an 'add' with qty 0 passed the check and was applied as 1."""
    from core.bom_edit import check
    assert check({"action": "add", "article": "3RT2027-1AP00", "qty": 0})["verdict"] == "invalid"
