from pathlib import Path

import pytest
import yaml

from components.internal_wiring.select import _data, select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "internal_wiring"
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


def test_ratings_increase_with_size():
    rows = _data()["ratings"]
    for col in ("A", "C"):
        rs = sorted((r for r in rows if r["column"] == col and r["amps"] is not None), key=lambda r: r["size"])
        for a, b in zip(rs, rs[1:]):
            assert b["amps"] > a["amps"], (col, a["size"], b["size"])


def test_temperature_factors_fall_with_temperature():
    for ins, row in _data()["temp"].items():
        f = [row["factors"][t] for t in sorted(row["factors"])]
        assert f == sorted(f, reverse=True), ins
        if row["kind"] == "temp":
            assert row["factors"][30] == 1.0, ins


def test_group_and_core_factors_fall_with_number():
    for method, g in _data()["group"].items():
        f = [g[n][0] for n in sorted(g)]
        assert f == sorted(f, reverse=True), method
    c = [r["free_air"] for r in _data()["cores"]]
    assert c == sorted(c, reverse=True)


def test_hotter_panel_never_gives_a_smaller_wire():
    for ib, inn in ((2, 2), (15.5, 16), (70, 100), (200, 250)):
        sizes = [select(ib_a=ib, in_a=inn, ambient_c=t, insulation="70", installation="duct", circuits=3).value
                 .get("size_mm2", 1e9) for t in range(10, 66, 5)]
        assert sizes == sorted(sizes), (ib, sizes)


def test_more_circuits_never_gives_a_smaller_wire():
    sizes = [select(ib_a=10, in_a=10, ambient_c=40, insulation="70", installation="duct", circuits=n).value
             .get("size_mm2", 1e9) for n in range(1, 21)]
    assert sizes == sorted(sizes)


def test_every_answer_cites_lapp_and_reports_what_is_not_checked():
    for case, res, _ in RESULTS:
        if res.status == "ok":
            assert any("LAPP-POWER" in c.source for c in res.checks), case["id"]
            assert any(c.rule == "R-WIR-13" for c in res.checks), case["id"]
