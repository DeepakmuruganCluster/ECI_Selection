from pathlib import Path

import pytest
import yaml

from components.feeder_kit.select import select
from core import golden

HERE = Path(__file__).resolve().parents[1] / "components" / "feeder_kit"
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


SRC = Path(__file__).resolve().parents[1] / "sources" / "pdf" / "own" / "propel"


def test_kit_lines_equal_the_workbook_rows():
    """G6: article and quantity of every DOL kit line equal its workbook row (re-read here)."""
    from components.feeder_kit.select import _kits
    from core.xlsx import read_any
    book = read_any(SRC / "DOL Motors BOM 30 05 23.xlsx")
    for k in (k for k in _kits() if k["ref"] == "OWN-PROPEL-DOL"):
        rows = book[k["sheet"]]
        for it in k["items"]:
            r = rows[it["row"] - 1]
            cell = r[4]
            cell = str(int(cell)) if isinstance(cell, float) and cell.is_integer() else str(cell or "").strip()
            assert cell == it["article"] and float(r[6]) == it["qty"], (k["title"], it["row"])


def test_every_dol_kit_adds_up_to_the_sheet_total():
    from components.feeder_kit.select import _kits
    for k in (k for k in _kits() if k["ref"] == "OWN-PROPEL-DOL"):
        total = sum((i["unit_price_inr"] or 0) * (i["qty"] or 0) for i in k["items"])
        assert abs(total - k["sheet_total_inr"]) < 0.05, k["title"]


def test_costing_kit_matches_the_drawing_bom():
    """Cross-source: costing '160KW SD WITH PLC' contactors = drawing AVELCPSDL08WPLC BOM page 14 (K1, K2 200 A; K3 160 A)."""
    import pdfplumber
    from components.feeder_kit.select import select as kit
    with pdfplumber.open(SRC / "Schematic 160KW SD with PLC.pdf") as pdf:
        rows = [r for t in pdf.pages[13].extract_tables() for r in t]
    drawing = {r[8]: int(r[16]) for r in rows if len(r) > 16 and r[8] and r[8].startswith("LC1E") and r[16].isdigit()}
    k = kit(starter="SD", kw=160, application="lub with plc").value
    costing = {i["article"]: int(i["qty"]) for i in k["items"] if i["article"] in ("LC1E200M5", "LC1E160M5")}
    assert costing == {a: drawing[a] for a in costing} == {"LC1E200M5": 2, "LC1E160M5": 1}
