from pathlib import Path

import pytest
import yaml

from components.enclosure.select import _altitude, _formulas, _k, _products, _siemens, select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "enclosure"
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


def test_data_sanity():
    bands = sorted(_altitude()["rows"], key=lambda b: b["h_min_m"])
    assert bands[0]["h_min_m"] == 0 and bands[-1]["h_max_m"] == 1000
    for lo, hi in zip(bands, bands[1:]):
        assert lo["h_max_m"] == hi["h_min_m"], "altitude bands must be contiguous"
        assert hi["f"] > lo["f"], "f must rise with altitude"
    assert {r["k_w_m2k"] for r in _k()["rows"]} == {5.5}
    hx = [r["q_w_per_k"] for r in _products()["rows"] if r["kind"] == "heat_exchanger"]
    assert hx == sorted(hx) and min(hx) == 17.5 and max(hx) == 90     # range printed on p.24 and p.26
    ids = {r["id"] for r in _formulas()["rows"]}
    assert {"delta_t_max", "q_surface", "fan_airflow", "heat_exchanger", "cooling_unit"} <= ids
    # Rittal f at 0–100 m and the Siemens coefficient describe the same physics: agree within 1 %
    coef = next(r["value"] for r in _siemens()["rows"] if r["quantity"] == "airflow_coefficient")
    assert abs(bands[0]["f"] / 3.6 - coef) / coef < 0.01


def test_vfd_loss_feeds_the_enclosure():
    from components.vfd.select import select as vfd
    d = vfd(kw=7.5, flc_a=15.5, flc_basis="nameplate", ambient_c=40, cable_m=50, fault_ka=50, network_uk_pct=2)
    r = select(heat_loss_w=d.value["loss_w"], ambient_c=35, max_internal_c=45, altitude_m=0, siting="indoor")
    assert r.status == "ok" and r.value["fan_airflow_m3h"] == pytest.approx(3.1 * 200 / 10)
