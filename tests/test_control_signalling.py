"""Component 16: control and signalling (interface relays, terminal blocks, Rittal door switch and light)."""
from pathlib import Path

import pytest
import yaml

from components.control_signalling.select import _data, _rows, exact_pieces, overlap_pieces, select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "control_signalling"
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


def test_every_data_file_loads_with_its_registered_source():
    for key in ("s38", "s39", "s13", "s40", "s20", "cwes", "cwtb", "door", "light"):
        d = _data(key)
        assert d["rows"] and d["reference"]["access"] == "stored"


def test_module_codes_agree_with_their_relay_and_socket():
    """Finder: the printed module code carries the socket's coil code; one relay type for all 24 V modules."""
    for key in ("s38", "s39"):
        for m in _rows(key, kind="module"):
            assert m["article"].startswith(m["series"] + ".")
            assert m["article"].split(".")[2] + "." + m["article"].split(".")[3] == m["coil_code"], m
            assert m["relay"] == "34.51.7.024.0010", m
            assert _rows(key, kind="coil", coil_code=m["coil_code"]), m


def test_every_terminal_has_its_end_plate_marker_card_and_jumper_series():
    tb = _rows("cwtb", kind="terminal")
    cards = {r["article"] for r in _rows("cwtb", kind="marker")}
    series = {r["series"] for r in _rows("cwtb", kind="jumper")}
    for t in tb:
        assert t["marker"] in cards and t["jumper_series"] in series and t["end_plate"].startswith("EP"), t
        assert t["ferrule_min"] <= t["ferrule_max"] <= t["size_mm2"], t


@pytest.mark.parametrize("n", range(2, 120))
def test_jumper_arithmetic(n):
    ex = exact_pieces(n, [2, 3, 4, 5, 8, 10, 16])
    assert sum(ex) == n and list(ex) == sorted(ex, reverse=True)
    ov = overlap_pieces(n, [2, 3, 4, 5, 6, 7, 8, 10, 20])
    assert sum(ov) - (len(ov) - 1) == n


def test_no_latching_relay_is_offered_by_connectwell_or_finder_38_39():
    assert not _rows("cwes", kind="latching") and not _rows("s38", kind="latching") and not _rows("s39", kind="latching")
    assert [r["article"] for r in _rows("s13", kind="latching")] == ["13.12.0.024.0000"]
