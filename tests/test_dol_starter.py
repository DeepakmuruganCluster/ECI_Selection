from pathlib import Path

import pytest
import yaml

from components.dol_starter.select import select
from core import golden
from core.provenance import ProvenanceError, load_sourced_table

HERE = Path(__file__).resolve().parents[1] / "components" / "dol_starter"
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


def test_ranges_are_valid():
    from components.dol_starter.select import _table
    for r in _table()["rows"]:
        a, b = r["range"]; c, d = r["range_ie3"]
        assert a < b and c < d and a == c and d <= b, r

