from pathlib import Path

import pytest
import yaml

from components.instruments.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "instruments"
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


def test_import_reproduces_the_client_io_table():
    """G6: motor + field-device I/O read from the specification = the client's required I/O, both panels."""
    for panel in ("BIO_UF", "RO"):
        assert select(panel=panel).value["io_matches"], panel
