from pathlib import Path

import pytest
import yaml

from components.soft_starter.select import select
from core import golden
from core.provenance import ProvenanceError, load_sourced_table

HERE = Path(__file__).resolve().parents[1] / "components" / "soft_starter"
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


def test_every_3rw52_article_is_in_the_ordering_table():
    """Each type has its 8 inline versions (Us 24 V / 110-250 V AC × Ue 480 / 600 V × analog / thermistor)."""
    from components.soft_starter.select import _ordering, _ratings
    types = {r["type"] for r in _ratings()}
    assert len(types) == 18
    for t in types:
        assert len([o for o in _ordering() if o["type"] == t]) == 8, t
