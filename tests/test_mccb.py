import re
from pathlib import Path

import pytest
import yaml

from components.mccb.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "mccb"
RESULTS = golden.run(HERE / "golden" / "cases.yaml", select)


@pytest.mark.parametrize("case,res,diffs", RESULTS, ids=[c["id"] for c, _, _ in RESULTS])
def test_golden(case, res, diffs):
    assert not diffs, f"{case['id']} ({case['oracle']}): {diffs}\n{res.trace()}"


def test_every_rule_in_code_is_in_the_rule_sheet():
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks} - {"INPUT"}
    assert used <= set(rules), used - set(rules)


def test_every_rule_is_exercised_by_a_golden_case():
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks}
    assert set(rules) <= used, set(rules) - used


def test_every_article_has_breaking_capacity_and_trip_ratings_and_a_consistent_number():
    """Sanity: each article row joins to a breaking-capacity row and a trip-rating row, and the
    printed article number agrees with its row (frame, class digit, poles, release/neutral letters).
    The letter pattern is only a consistency check — the catalogue does not publish a number key."""
    from components.mccb.select import _articles, _breaking, _ratings
    bc = {(r["frame"], r["class"]) for r in _breaking()["rows"]}
    tr = {(r["release"], r["frame"], r["in_a"]) for r in _ratings()["rows"]}
    code = {("TM210", "none"): "ED", ("TM220", "none"): "EE", ("TM210", "100"): "GD", ("TM220", "100"): "GE"}
    cls = {"B": "2", "N": "3", "S": "4", "M": "5"}
    seen = set()
    for a in _articles()["rows"]:
        assert (a["frame"], a["class"]) in bc, a
        assert (a["release"], a["frame"], a["in_a"]) in tr, a
        m = re.fullmatch(r"3VM1(\d)(\d\d)-(\d)(\w\w)(\d)2-0AA0", a["article"])
        assert m and a["frame"] == f"3VM1{m[1]}" and m[3] == cls[a["class"]], a
        assert m[4] == code[(a["release"], str(a["neutral"]))] and int(m[5]) == a["poles"], a
        assert a["article"] not in seen, a
        seen.add(a["article"])
    assert len(seen) == 324
