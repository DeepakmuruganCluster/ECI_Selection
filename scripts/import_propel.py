"""Import the company (Propel) BOM structures into traceable data files.

    .venv/bin/python scripts/import_propel.py

DOL Motors BOM (OWN-PROPEL-DOL): one kit per block (title row → item rows → total row), every item with sheet + row.
Costing sheet (OWN-PROPEL-COST): one kit per sheet (star-delta panels and machine panels).
Values are copied as written; prices are the sheet's cached values (indicative, INR).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.xlsx import read_any  # noqa: E402

SRC = ROOT / "sources" / "pdf" / "own" / "propel"
SKIP_SHEETS = {"Consolidated", "Elmex Price", "Sheet1", "NOT REQ DEWATERING "}  # summary, price list, empty, marked not required


def text(v) -> str:
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


def parse_title(title: str, sheet: str | None = None) -> dict:
    """The company naming convention (owner 2026-10-16): '<kW>KW <starter> [WITH PLC]' — '55KW SD' = 55 kW star-delta,
    '110KW SD WITH PLC' = with PLC, 'BELT CONVEYOR 7.5KW DOL', 'PAN FEEDER 1.13kw X 2 DOL' = two motors,
    'BELT CONVEYOR 30KW SDL' = star-delta, 'BELT CONVEYOR 7.5KW F/R' = forward / reverse, '2.2KW / 3.2 X 2' = two kW options,
    'DUAL MOTOR' = two motors. The costing sheet's sheet name follows the convention and is read first; then the title.
    The word STARTER alone says nothing about the starter."""
    names = [n for n in (sheet, title) if n]
    out = {"kw": None, "kw_options": [], "motors": 1, "starter": "", "plc": False, "name_basis": ""}
    for n in names:
        t = re.sub(r"\s+", " ", n.upper())
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:K\s*W)?\s*/\s*(\d+(?:\.\d+)?)\s*K\s*W", t) or \
            re.search(r"(\d+(?:\.\d+)?)\s*K\s*W(?:\s*/\s*(\d+(?:\.\d+)?))?", t)
        if m:                                    # kW options from every name (title '160/187KW' + sheet '187KW SD')
            opts = {float(m.group(1)), float(m.group(2) or m.group(1))}
            out["kw_options"] = sorted(set(out["kw_options"]) | opts)
            if out["kw"] is None:
                out.update(kw=max(opts), name_basis=n)
        if re.search(r"X\s*2(?!\d)|DUAL\s*MOTOR", t):
            out["motors"] = 2
        if not out["starter"]:
            out["starter"] = ("SD" if re.search(r"K\s*W\s*SDL?\b|\bSDL?\b|S/D|STAR[- ]?DELTA", t) else "DOL_FR" if "F/R" in t
                              else "DOL" if re.search(r"\bDOL\b|KW\s*X?\s*2?\s*DOL|\dDOL", t) else "")
        if "PLC" in t:
            out["plc"] = True
    if sheet and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*KW\s+SD(\s+WITH\s+PLC)?\s*", sheet.upper()):
        out["kw"] = float(re.match(r"\s*(\d+(?:\.\d+)?)", sheet).group(1))     # the sheet name is the panel's rating
    out["application"] = re.split(r"\(|\d", title, maxsplit=1)[0].strip().lower()
    return out


def role(desc: str) -> str:
    d = desc.upper().replace(" ", "").replace("-", "")
    for key, r in (("EARTHTERMIANL", "earth_terminal"), ("DELAY", "timer"), ("SPREADER", "accessory"), ("RELAYBASE", "relay"),
                   ("RELAY", "relay"), ("ENDCLAMP", "end_clamp"), ("MPCB", "mpcb"), ("POWERCONTACTOR", "contactor"), ("AUXILIARYCONTACT", "aux_contact"),
                   ("ADDONBLOCK", "aux_contact"), ("ADDONBLOCK", "aux_contact"), ("LAMP", "pilot_lamp"),
                   ("PUSHBUTTON", "push_button"), ("POWERTERMINAL", "power_terminal"), ("CONTROLTERMINAL", "control_terminal"),
                   ("EARTHTERMINAL", "earth_terminal"), ("ENDPLATE", "end_plate"), ("ENDCLAMP", "end_clamp"),
                   ("POWERCOPPERCABLE", "power_wire"), ("COPPERCABLE", "control_wire"), ("WIRINGACC", "wiring_accessories"),
                   ("OLR", "overload_relay"), ("TIMER", "timer"), ("MCCB", "mccb"), ("MCB", "mcb")):
        if key in d:
            return r
    return "other"


def dol_kits() -> dict:
    book = read_any(SRC / "DOL Motors BOM 30 05 23.xlsx")
    kits, skipped = [], []
    for sheet, rows in book.items():
        if sheet in SKIP_SHEETS:
            continue
        head_i = next((i for i, r in enumerate(rows) if any(text(c).upper() == "DESCRIPTION" for c in r)), None)
        if head_i is None:
            skipped.append(f"{sheet}: no header row")
            continue
        head = [text(c).upper() for c in rows[head_i]]
        col = {k: next((j for j, h in enumerate(head) if h.startswith(p)), None) for k, p in
               (("desc", "DESCRIPTION"), ("rating", "RATING"), ("make", "MAKE"), ("part", "PART"), ("price", "UNIT PRICE"),
                ("qty", "BOM QTY"))}
        kit = None
        for i, r in enumerate(rows[head_i + 1:], head_i + 2):
            r = list(r) + [None] * 30
            first, desc = text(r[0]), text(r[col["desc"]])
            if not first and desc and not text(r[col["part"]]) and num(r[col["qty"]]) is None:
                kit = {"title": desc, **parse_title(desc), "sheet": sheet, "row": i, "items": []}
                kits.append(kit)
            elif kit is not None and not first and not desc and num(r[col["price"] + 2]) is not None and "sheet_total_inr" not in kit:
                kit["sheet_total_inr"] = num(r[col["price"] + 2])
                kit["sheet_total_revised_inr"] = num(r[col["price"] + 3])
            elif kit is not None and desc and (num(r[0]) is not None or (text(r[col["part"]]) and num(r[col["qty"]]))):
                kit["items"].append({"role": role(desc), "description": desc, "rating": text(r[col["rating"]]),
                                     "make": text(r[col["make"]]), "article": text(r[col["part"]]),
                                     "unit_price_inr": num(r[col["price"]]), "qty": num(r[col["qty"]]), "row": i})
    kits = [k for k in kits if k["items"]]
    for k in kits:
        if k["kw"] is None:
            skipped.append(f"{k['sheet']} row {k['row']} '{k['title']}': no kW in the title")
    return {"source": {"ref": "OWN-PROPEL-DOL", "note": "one kit per block; 'row' = sheet row; prices INR as cached in the sheet"},
            "rows": [k for k in kits if k["kw"] is not None], "skipped": skipped}


def costing_kits() -> dict:
    book = read_any(SRC / "PIP STANDARD PANEL COSTING SHEET R0.xlsx")
    kits, skipped = [], []
    for sheet, rows in book.items():
        title = text(rows[0][0]) if rows and rows[0] else ""
        head_i = next((i for i, r in enumerate(rows[:6]) if any(text(c).upper() == "DESCRIPTION" for c in r)), None)
        if not title or head_i is None:
            skipped.append(f"{sheet}: no title or header")
            continue
        head = [text(c).upper() for c in rows[head_i]]
        c = {k: next((j for j, h in enumerate(head) if h.startswith(p)), None) for k, p in
             (("desc", "DESCRIPTION"), ("rating", "RATING"), ("part", "PART"), ("make", "MAKE"), ("remarks", "REMARKS"))}
        # current BOM = the second (new) price / quantity pair: J = NEW PRICE, L = QTY ('REMOVED' lines have no qty)
        jp = [j for j, h in enumerate(head) if "PRICE" in h and "TOTAL" not in h]
        jq = [j for j, h in enumerate(head) if h == "QTY"]
        items = []
        for i, r in enumerate(rows[head_i + 1:], head_i + 2):
            r = list(r) + [None] * 30
            desc = text(r[c["desc"]])
            if num(r[0]) is None or not desc:
                continue
            qty = num(r[jq[-1]]) if jq else None
            items.append({"role": role(desc), "description": desc, "rating": text(r[c["rating"]]), "make": text(r[c["make"]]),
                          "article": text(r[c["part"]]), "unit_price_inr": num(r[jp[-1]]) if jp else None, "qty": qty,
                          "remark": text(r[c["remarks"]]) if c["remarks"] is not None else "", "row": i})
        meta = parse_title(title, sheet)
        if not meta["starter"]:                    # the name is silent: the sheet's own lines may show a star-delta timer
            sd = next((x for x in items if x["qty"] and "STAR DELTA TIMER" in x["description"].upper()), None)
            if sd:
                meta.update(starter="SD", starter_basis=f"sheet line {sd['row']}: {sd['description']}")
            else:
                meta["starter_basis"] = "not in the name or the sheet's lines (asked)"
        kits.append({"title": title, **meta, "sheet": sheet, "row": 1,
                     "items": [x for x in items if x["qty"]], "removed": [x["article"] or x["description"] for x in items
                                                                          if not x["qty"]]})
    return {"source": {"ref": "OWN-PROPEL-COST", "note": "one kit per sheet; current quantities and new prices (columns J / L)"},
            "rows": kits, "skipped": skipped}


if __name__ == "__main__":
    head = ("# Generated by scripts/import_propel.py from the company (Propel) BOM structures — do not edit by hand.\n"
            "# Authority OWN: company standard kits and indicative prices (INR); confirm before ordering.\n")
    out = ROOT / "data" / "company" / "propel"
    out.mkdir(parents=True, exist_ok=True)
    for name, d in (("propel_dol_kits.yaml", dol_kits()), ("propel_panel_kits.yaml", costing_kits())):
        (out / name).write_text(head + yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=200))
        print(f"{name}: {len(d['rows'])} kits, {len(d['skipped'])} skipped")
