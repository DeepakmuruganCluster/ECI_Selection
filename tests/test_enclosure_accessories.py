from pathlib import Path

import pytest
import yaml

from components.enclosure_accessories.select import _table, fans, select, size_in
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "enclosure_accessories"
RESULTS = golden.run(HERE / "golden" / "cases.yaml", select)


@pytest.mark.parametrize("case,res,diffs", RESULTS, ids=[c["id"] for c, _, _ in RESULTS])
def test_golden(case, res, diffs):
    assert not diffs, f"{case['id']} ({case['oracle']}): {diffs}\n{res.trace()}"


def test_golden_case_count():
    assert 15 <= len(RESULTS) <= 30


def test_every_rule_in_code_is_in_the_rule_sheet():
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks} - {"INPUT"}
    assert used <= set(rules), used - set(rules)


def test_every_rule_is_exercised_by_a_golden_case():
    rules = yaml.safe_load((HERE / "rules.yaml").read_text())["rules"]
    used = {c.rule for _, r, _ in RESULTS for c in r.checks}
    assert set(rules) <= used, set(rules) - used


def test_data_sanity():
    for f in fans():
        for hz in (50, 60):
            one = next(r["value"] for r in f["rows"] if r["quantity"] == "airflow_outlet_m3h"
                       and r["hz"] == hz and r["outlet_filters"] == 1)
            two = next(r["value"] for r in f["rows"] if r["quantity"] == "airflow_outlet_m3h"
                       and r["hz"] == hz and r["outlet_filters"] == 2)
            free = next(r["value"] for r in f["rows"] if r["quantity"] == "airflow_free_m3h"
                        and r["hz"] == hz and r["filter"] == "chopped_fibre")
            # an outlet filter can only reduce the airflow; a second one less than the first
            assert one < two < free
    assert sorted(size_in(f) for f in fans()) == [8, 10]
    assert {_table(t)["rows"][0]["value"] for t in ("rittal_ts8601060.yaml", "rittal_ts8602060.yaml")} == {100, 200}


def test_enclosure_airflow_feeds_the_fan_count():
    from components.enclosure.select import select as enc
    e = enc(heat_loss_w=1000, ambient_c=35, max_internal_c=45, altitude_m=0, siting="indoor")
    r = select(required_airflow_m3h=e.value["fan_airflow_m3h"], doors=5, fan_size_in=8, supply_v=230, frequency_hz=50)
    assert r.value["fan_qty"] == 5 and r.value["delivered_airflow_m3h"] >= 310       # 310 / 74 = 4.2 → 5
