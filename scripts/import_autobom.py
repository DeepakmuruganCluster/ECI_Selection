"""Import the AutoBOM databases (OWN-AB-*) into traceable data files: one row per sheet row, with sheet and row.

    .venv/bin/python scripts/import_autobom.py

Values are copied as written ("1.3 A" → 1.3); incomplete rows are skipped and listed in the data file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.xlsx import read_any  # noqa: E402

SRC = ROOT / "sources" / "pdf" / "own" / "autobom"


def amps(v):
    """'1.3 A' / '0.018 A' / 1.3 → float; '', '-', None → None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"(\d+(?:\.\d+)?)", str(v))
    return float(m.group(1)) if m else None


def text(v):
    """Cell → text; whole numbers stored as numbers (Weidmueller / Phoenix order numbers) without '.0'."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def table(book, sheet):
    rows = book[sheet]
    head = [text(h) for h in rows[0]]
    for i, r in enumerate(rows[1:], 2):
        r = list(r) + [None] * (len(head) - len(r))
        yield i, {h: r[j] for j, h in enumerate(head) if h}


def smps():
    book = read_any(SRC / "SMPS db.xlsx")
    rows, skipped = [], []
    for sheet in ("db1", "Phoenix", "Omron", "Meanwell", "Weidmueller"):
        for i, r in table(book, sheet):
            model = text(r.get("Model Number"))
            if not model:
                continue
            brand = text(r.get("Manufacturer") or r.get("Brand"))
            row = {"brand": brand, "series": text(r.get("Series")), "model": model,
                   "input": text(r.get("Primary Voltage Type")), "network": text(r.get("Primary Network")),
                   "vin_min": num(r.get("Primary Voltage min")), "vin_max": num(r.get("Primary Voltage max")),
                   "vout_min": amps(r.get("Secondary Voltage min, VDC") or r.get("Secondary Voltage min")),
                   "vout_max": amps(r.get("Secondary Voltage max, VDC") or r.get("Secondary Voltage max")),
                   "i_out_a": amps(r.get("Secondary rated current")), "efficiency": num(r.get("Efficiency")),
                   "sheet": sheet, "row": i}
            if None in (row["i_out_a"], row["vout_min"], row["vout_max"]) or not row["network"]:
                skipped.append(f"{sheet} row {i} {model}: rated current, output voltage or input network missing")
                continue
            rows.append(row)
    verified = {}
    log = book["Logsheet"]
    for i, r in enumerate(log[2:], 3):
        r = list(r) + [None] * 6
        if text(r[0]) == "Issues to address":
            break  # below this line the sheet lists open data issues, not series
        if text(r[0]) and text(r[1]):
            verified[f"{text(r[0])}|{text(r[1])}"] = {"entered_by": text(r[2]), "verified": text(r[4]), "link": text(r[5]),
                                                     "row": i}
    return {"source": {"ref": "OWN-AB-SMPS", "note": "sheets db1, Phoenix, Omron, Meanwell, Weidmueller; 'row' = sheet row"},
            "rows": rows, "skipped": skipped, "logsheet": verified}


def plc():
    book = read_any(SRC / "PLC db.xlsx")
    rows, skipped = [], []
    for i, r in table(book, "db"):
        model = text(r.get("Model Number"))
        if not model:
            continue
        row = {"brand": text(r.get("Manufacturer")), "series": text(r.get("Series")), "model": model,
               "max_io": num(r.get("Max Total I/Os")), "di": num(r.get("Digital Inputs")),
               "do": num(r.get("Digital Outputs")), "do_type": text(r.get("DO direction")).lower(),
               "max_ext": num(r.get("Max Ext Mod")), "i24_a": amps(r.get("Current consumption, 24VDC")),
               "i5_a": amps(r.get("Current Consumption, 5VDC")), "eff_5v": num(r.get("Efficiency 24V to 5VDC")),
               "fieldbus": sorted(h.replace("Fieldbus ", "") for h, v in r.items()
                                  if h.startswith("Fieldbus") and text(v).lower() in ("yes", "y")),
               "sheet": "db", "row": i}
        if model.endswith(("DR-D",)) or "R-D" in model[-4:]:
            row["do_type"] = "relay"
        if None in (row["max_io"], row["di"], row["do"], row["i24_a"], row["i5_a"], row["eff_5v"]) or row["max_ext"] is None:
            skipped.append(f"db row {i} {model}: I/O count, expansion limit or current missing")
            continue
        rows.append(row)
    return {"source": {"ref": "OWN-AB-PLC", "note": "sheet db; 'row' = sheet row"}, "rows": rows, "skipped": skipped}


def plcio():
    book = read_any(SRC / "PLC IO_db.xlsx")
    compat = {}
    for i, r in table(book, "db1"):
        m = text(r.get("Model Number"))
        if m:
            compat[m] = {s: text(r.get(f"{s} compatible")).lower() == "yes" for s in ("CP2E", "CP1E", "CP1L", "CP1H", "NX1P")}
    rows, skipped = [], []
    for i, r in table(book, "db_DIO"):
        m = text(r.get("Model Number"))
        if not m:
            continue
        di, do = num(r.get("Digital Inputs")) or 0.0, num(r.get("Digital Outputs")) or 0.0
        i5 = amps(r.get("Current Consumption, 5VDC"))
        eff = num(r.get("Efficiency 24V to 5VDC"))
        row = {"model": m, "di": di, "do": do, "do_type": text(r.get("DO Type")).lower().replace("-", ""),
               "i24_a": amps(r.get("Current consumption, 24VDC")), "i5_a": i5, "eff_5v": eff,
               "series_ok": [s for s, ok in compat.get(m, {}).items() if ok], "sheet": "db_DIO", "row": i}
        if i5 is None or eff is None:
            skipped.append(f"db_DIO row {i} {m}: current not in the database")
            continue
        rows.append(row)
    return {"source": {"ref": "OWN-AB-PLCIO", "note": "sheet db_DIO (+ compatibility from db1); 'row' = sheet row"},
            "rows": rows, "skipped": skipped}


if __name__ == "__main__":
    head = ("# Generated by scripts/import_autobom.py from the AutoBOM databases — do not edit by hand.\n"
            "# Authority OWN: entered by the AutoBOM team from maker data sheets (not held); confirm before ordering.\n")
    for rel, d in {"dc/ab_smps.yaml": smps(), "plc/ab_plc.yaml": plc(),
                   "plc/ab_plc_io.yaml": plcio()}.items():
        p = ROOT / "data" / "company" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(head + yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=200))
        print(f"{rel}: {len(d['rows'])} rows, {len(d['skipped'])} skipped")
