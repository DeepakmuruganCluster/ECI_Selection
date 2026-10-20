import json

import pytest

from core import review


@pytest.fixture
def tmp_signoff(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "signoff_path", lambda name: tmp_path / f"{name}.json")
    return tmp_path


def _recommended(name):
    return {d["id"]: d["recommended"] for d in review.review(name)["decisions"]}


@pytest.mark.parametrize("name", review.components())
def test_review_runs_every_case_and_shows_pages(name):
    r = review.review(name)
    assert r["total"] > 0 and r["passed"] == r["total"]
    has_data = bool(review.data_files(name))
    if has_data:   # composition-only components (panel) cite no pages of their own
        assert r["pages"] and all(p["image"] or p.get("link") for p in r["pages"]), "run scripts/render_source_pages.py"
    else:
        assert not r["pages"]
    for d in r["decisions"]:
        assert d["recommended"] in d["options"]


@pytest.mark.parametrize("name", review.components())
def test_spot_checks_give_an_answer_or_a_stated_refusal(name):
    import importlib
    select = importlib.import_module(f"components.{name}.select").select
    for s in review.review(name)["spot_checks"]:
        assert select(**{"fault_ka": 50, **s["inputs"]} if name == "dol_starter" else s["inputs"]).status != "invalid"


def test_sign_off_needs_name_confirmation_and_all_decisions(tmp_signoff):
    with pytest.raises(ValueError, match="name"):
        review.sign_off("motor_flc", {"name": " ", "compared": True, "decisions": _recommended("motor_flc")})
    with pytest.raises(ValueError, match="compared"):
        review.sign_off("motor_flc", {"name": "A", "compared": False, "decisions": _recommended("motor_flc")})
    with pytest.raises(ValueError, match="Choose"):
        review.sign_off("motor_flc", {"name": "A", "compared": True, "decisions": {}})


def test_sign_off_record_and_change_detection(tmp_signoff, monkeypatch):
    dec = {**_recommended("dol_starter"), "E-1": "smallest"}
    rec = review.sign_off("dol_starter", {"name": "Reviewer", "compared": True, "decisions": dec})
    assert rec["changes_needed"] == ["E-1"]
    assert json.loads((tmp_signoff / "dol_starter.json").read_text())["signed_by"] == "Reviewer"
    assert review.review("dol_starter")["signoff"]["still_valid"] is True
    monkeypatch.setattr(review, "data_hashes", lambda name: {"changed": "x"})
    assert review.review("dol_starter")["signoff"]["still_valid"] is False
