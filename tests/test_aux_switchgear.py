from pathlib import Path

import pytest
import yaml

from components.aux_switchgear.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "aux_switchgear"
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


SRC = Path(__file__).resolve().parents[1] / "sources" / "pdf" / "own" / "switchgears"


def _csv(name):
    import csv
    with open(SRC / name, encoding="utf-8-sig", newline="") as f:
        return {i: r for i, r in enumerate(csv.DictReader(f), 2)}


def test_data_files_equal_the_database_line_by_line():
    """G6: every generated row equals its CSV line (re-read here independently of the import script)."""
    from components.aux_switchgear.select import _db
    for kind, name, art in (("mcb", "MCB.csv", "Part number"), ("rccb", "RCCB.csv", "Part number"),
                            ("isolator", "isolator.csv", "Part number"), ("sa", "sa.csv", "Part number"),
                            ("pmr", "pmr.csv", "Part number")):
        lines = _csv(name)
        rows = _db(kind)["rows"]
        assert len(rows) == sum(1 for r in lines.values() if r[art].strip()), kind
        for r in rows:
            line = lines[r["row"]]
            assert r["article"] == line[art].strip() and r["make"] == line["Make"].strip(), (kind, r["row"])
            if "in_a" in r and r["in_a"] is not None:
                assert float(r["in_a"]) == float(line["Rated Current, In"]), (kind, r["row"])


def test_mcb_trip_bands_are_curve_multiples():
    """Data quality: B = 3 … 5 × In, C = 5 … 10 × In, D = 10 … 20 × In or 10 … 14 × In (maker-specific D band)."""
    from components.aux_switchgear.select import _db
    allowed = {"B": {(3, 5)}, "C": {(5, 10)}, "D": {(10, 20), (10, 14)}}
    for r in _db("mcb")["rows"]:
        k = (round(r["trip_lo_a"] / r["in_a"], 2), round(r["trip_hi_a"] / r["in_a"], 2))
        assert k in allowed[r["curve"]], (r["row"], r["article"], k)


def test_siemens_mpcb_rows_match_the_siemens_manual():
    """G6 cross-check of the own database: the 21 Siemens 3RV rows equal the SIRIUS table (SIE-SIRIUS-CM)."""
    import yaml as _y
    sirius = {}
    for r in _y.safe_load((Path(__file__).resolve().parents[1] / "data" / "makers" / "siemens" /
                           "siemens_type2_400v.yaml").read_text())["rows"]:
        sirius.setdefault(r["mpcb"], tuple(float(x) for x in r["range"]))
    rows = [r for r in _csv("MPCB.csv").values() if r["Make"] == "Siemens"]
    assert len(rows) == 21
    for r in rows:
        assert sirius[r["Part number"]] == (float(r["Low Amps"]), float(r["High Amps"])), r["Part number"]
