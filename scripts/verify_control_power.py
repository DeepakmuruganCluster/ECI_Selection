"""G6 for control_power: the template values in own_calc_method.yaml equal the .xls cells.

Needs xlrd; with the v2 environment it re-runs itself with the v1 one (~/Documents/panel-selector/.venv), which has it.
"""
import os
import sys
from pathlib import Path

try:
    import xlrd
except ImportError:   # the v2 environment has no xlrd: run again with the v1 one, which has it (QA 2026-10-16, M5)
    v1 = Path.home() / "Documents/panel-selector/.venv/bin/python"
    if v1.exists() and Path(sys.prefix).resolve() != v1.parents[1].resolve():
        os.execv(str(v1), [str(v1), *sys.argv])
    sys.exit("needs xlrd: run with ~/Documents/panel-selector/.venv/bin/python")
import yaml

ROOT = Path(__file__).resolve().parents[1]
d = yaml.safe_load((ROOT / "data/company/switchgear/own_calc_method.yaml").read_text())
wb = xlrd.open_workbook(ROOT / "sources/pdf/own/switchgears/Switchgear_Selection_Calculation.xls")
bad = 0
for r in d["rows"]:
    sh = wb.sheet_by_name(r["sheet"])
    col = ord(r["cell"][0]) - ord("A")
    got = sh.cell_value(r["row"] - 1, col)
    ok = abs(float(got) - float(r["value"])) < 1e-9
    bad += not ok
    print(f"{'OK ' if ok else 'BAD'} {r['item']}: {r['sheet']}!{r['cell']} = {got} (data {r['value']})")
print("all match" if not bad else f"{bad} mismatch(es)")
raise SystemExit(bad)
