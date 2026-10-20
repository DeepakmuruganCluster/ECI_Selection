from pathlib import Path

import pytest
import yaml

from components.motor_flc.select import select
from core import golden
from core.provenance import ProvenanceError, load_sourced_table
from core.data import data_file

HERE = Path(__file__).resolve().parents[1] / "components" / "motor_flc"
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


def test_guide_table_is_monotonic():
    rows = load_sourced_table(data_file("siemens_guide_400v_4p.yaml"), ("kw", "flc_a"))["rows"]
    assert all(a["kw"] < b["kw"] and a["flc_a"] < b["flc_a"] for a, b in zip(rows, rows[1:]))


def test_row_without_page_is_refused(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("source: {ref: SIE-SIRIUS-CM}\nrows:\n  - {kw: 1, flc_a: 2}\n")
    with pytest.raises(ProvenanceError, match="page"):
        load_sourced_table(bad, ("kw", "flc_a"))


def test_unknown_reference_is_refused(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("source: {ref: NOWHERE}\nrows:\n  - {kw: 1, flc_a: 2, page: 1}\n")
    with pytest.raises(ProvenanceError, match="not in sources/register.yaml"):
        load_sourced_table(bad, ("kw", "flc_a"))
