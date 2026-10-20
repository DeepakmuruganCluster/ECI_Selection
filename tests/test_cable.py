from pathlib import Path

import pytest
import yaml

from components.cable.select import _data, select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "cable"
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


@pytest.mark.parametrize("make", ["polycab", "kei"])
def test_ratings_increase_and_resistance_decreases_with_size(make):
    rows = _data(make)["rows"]
    for cores in sorted({r["cores"] for r in rows}):
        rs = sorted((r for r in rows if r["cores"] == cores), key=lambda r: r["size"])
        for a, b in zip(rs, rs[1:]):
            for col in ("ground", "duct", "air", "isc1"):
                assert b[col] > a[col], (make, cores, col, a["size"], b["size"])
            assert b["r"] < a["r"], (make, cores, "r", a["size"], b["size"])


@pytest.mark.parametrize("make", ["polycab", "kei"])
def test_temperature_factors_fall_with_temperature_and_are_1_at_the_basis(make):
    d = _data(make)
    for kind, row in d["temp"].items():
        f = [row["factors"][t] for t in sorted(row["factors"])]
        assert f == sorted(f, reverse=True), (make, kind)
        base = d["basis"]["air_c" if kind == "air" else "ground_c"]
        assert row["factors"][base] == 1.0, (make, kind)


def test_makes_are_never_mixed():
    """Every page a selection cites belongs to the make that was asked for."""
    for case, res, _ in RESULTS:
        make = case["in"].get("make", "polycab")
        other = "KEI-TH-2023" if make == "polycab" else "POLYCAB-LT-V9"
        assert not any(other in c.source for c in res.checks), case["id"]
