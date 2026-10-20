from pathlib import Path

import pytest
import yaml

from components.io_list.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "io_list"
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


def test_every_signal_row_names_its_rule():
    r = select(load_list="K1 11 DOL\nP1 7.5 VFD qty=2\nE1 7.5 SS", vfd_control="hardwired", vfd_sto=True)
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    assert all(row["rule"] in rules for row in r.value["io_list"])
    assert r.value["n_signals"] == len(r.value["io_list"])


def test_counts_match_the_eci_load_lists():
    """BIO_UF: 36 DOL, 1 SS, 22 VFD units; RO: 39 DOL, 2 SS, 16 VFD (component 14); latching relays, STO."""
    from components.load_list.select import select as load_list
    for panel, (di, do, pn) in {"BIO_UF": (36 * 2 + 2, 36 * 2 + 1, 22), "RO": (39 * 2 + 4, 39 * 2 + 2, 16)}.items():
        text = load_list(panel=panel, default_cable_m=50).value["load_list"]
        r = select(load_list=text, dol_relays="latching", vfd_sto=True)
        assert (r.value["io_di"], r.value["io_do"], r.value["io_pn"], r.value["io_safety"]) == (di, do, pn, pn), panel
