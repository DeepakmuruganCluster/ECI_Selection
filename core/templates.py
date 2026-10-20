"""ECI templates (owner 2026-10-16): the company's standard panels, from the two company sheets already held as sources —
PIP standard panel costing sheet (OWN-PROPEL-COST, one panel per sheet) and DOL motors BOM (OWN-PROPEL-DOL, one feeder
kit per block). A template is copied into the designer's own project; its lines become that panel's BOM (with the
sheet's makes and prices), and the engine works out power, I/O, cables and the diagram from the template's motor and
checks the template against the rules (decision of the owner: "template BOM, engine checks it").

Only what the sheets print is used: a template without a motor kW (washing plants, VSI, lube panels) asks for it.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache

from .data import data_file
from .provenance import load_sourced_table

SHEETS = (("propel_panel_kits.yaml", "OWN-PROPEL-COST", "Standard panels"), ("propel_dol_kits.yaml", "OWN-PROPEL-DOL", "DOL feeder kits"))
FEEDER_ROLES = {"contactor", "timer", "aux_contact", "overload_relay", "mpcb"}
KEYWORDS = [  # (words in the description, BOM group) — the template line's place in the BOM sections
    (("INCOMER", "ISOLATOR", "SWITCH DISCONNECTOR", "CHANGEOVER"), "Incomer"),
    (("PLC", "SIMATIC", "CPU", "HMI", "ANALOG MODULE", "DIGITAL MODULE", "HUB SWITCH", "ETH", "PEN DRIVE"), "PLC"),
    (("SMPS",), "Control power"),
    (("MFM", "METER WITH", "CURRENT TRANSFORMER", "CURRENT SENSOR"), "Metering"),
    (("UV/OV", "PHASE", "SURGE"), "Auxiliary switchgear"),
    (("MOTOR PROTECTION", "MOTOR PORTECTION"), "Feeders"),
    (("CONTROL TRANSFORMER", "HOUR METER", "EMERGENCY", "HOOD"), "Control circuit"),
    (("TERMINAL", "RELAY BOARD", "RELAY 2CO", "RELAY", "END PLATE", "END CLAMP", "SPREADER", "DISTRIBUTION"), "Control and signalling"),
    (("CABLE",), "Internal wiring"),
    (("ROTARY HANDLE",), "Incomer"),
]
ROLE_GROUP = {"mccb": "Incomer", "mcb": "Control circuit", "push_button": "Control circuit", "pilot_lamp": "Control circuit",
              "earth_terminal": "Control and signalling", "end_plate": "Control and signalling", "end_clamp": "Control and signalling",
              "accessory": "Control and signalling", "wiring_accessories": "Feeder accessories"}


@lru_cache(maxsize=None)
def catalogue() -> tuple:
    out = []
    for fname, ref, family in SHEETS:
        for r in load_sourced_table(data_file(fname), ("title", "sheet", "items"))["rows"]:
            tid = f"{ref}|{r['sheet'].strip()}|{r.get('row') or 0}"
            priced = [i for i in r["items"] if i.get("unit_price_inr") is not None and isinstance(i.get("qty"), (int, float))]
            st = r.get("starter") or ""
            out.append({"id": tid, "ref": ref, "family": family, "title": r["title"].strip(), "sheet": r["sheet"].strip(),
                        "row": r.get("row"), "kw": r.get("kw"), "kw_options": r.get("kw_options") or [],
                        "motors": int(r.get("motors") or 1), "starter": st, "starter_basis": r.get("starter_basis") or "the name",
                        "application": re.sub(r"\s+", " ", (r.get("application") or "")).strip(),
                        "plc": bool(r.get("plc")) or any("SIMATIC" in str(i.get("description", "")).upper() for i in r["items"]),
                        "spec": spec(r.get("kw_options") or ([r["kw"]] if r.get("kw") else []), int(r.get("motors") or 1), st,
                                     bool(r.get("plc")), capacity(r["sheet"])),
                        "n_items": len(r["items"]), "price_inr": round(sum(i["unit_price_inr"] * i["qty"] for i in priced), 2),
                        "unpriced": len(r["items"]) - len(priced), "_items": r["items"]})
    return tuple(out)


STARTER_WORDS = {"SD": "star-delta", "DOL": "DOL", "DOL_FR": "DOL forward / reverse", "SS": "soft starter", "VFD": "VFD", "": "starter not stated"}


def capacity(sheet: str) -> str | None:
    """Owner 2026-10-16: PROWASH 100 = a 100 TPH washing plant (each one an independent client order)."""
    m = re.match(r"\s*(PROWASH|ECOWASH)\s+(\d+(?:\s*OR\s*\d+)?)", sheet.upper())
    return f"{m.group(2).lower()} TPH" if m else None


def spec(kws: list, motors: int, starter: str, plc: bool, cap: str | None = None) -> str:
    """The naming convention, decoded: '55KW SD' → '55 kW · star-delta'; '4.3 KW X 2 DOL' → '2 × 4.3 kW · DOL'."""
    kw = " / ".join(f"{k:g}" for k in kws) + " kW" if kws else (f"{cap} · client order" if cap else "client order")
    count = (f"{motors} × " if kws else f"{motors} motors · ") if motors > 1 else ""
    head = f"{count}{kw}" if kws else f"{kw}{' · ' + count.rstrip(' · ') if count else ''}"
    return f"{head} · {STARTER_WORDS.get(starter, starter)}{' · with PLC' if plc else ''}"


def listing() -> list[dict]:
    return [{k: v for k, v in t.items() if not k.startswith("_")} for t in catalogue()]


def get(tid: str) -> dict:
    t = next((t for t in catalogue() if t["id"] == tid), None)
    if t is None:
        raise ValueError(f"no template {tid!r}")
    return t


def _group(item: dict) -> str:
    role, desc = item.get("role", ""), str(item.get("description", "")).upper()
    if role in FEEDER_ROLES:
        return "Feeders"
    if role in ROLE_GROUP:
        return ROLE_GROUP[role]
    if role == "relay" and ("MOTOR PROT" in desc or "MOTOR PORT" in desc):
        return "Feeders"
    for words, g in KEYWORDS:
        if any(w in desc for w in words):
            return g
    return "Template items"


def bom(tid: str, motor_tag: str = "M1") -> list[dict]:
    """The template's lines as BOM lines (group, article, description with rating, qty, make, price, source)."""
    t = get(tid)
    out = []
    for i in t["_items"]:
        q = i.get("qty")
        if not isinstance(q, (int, float)) or q <= 0:
            continue
        g = _group(i)
        mk = str(i.get("make") or "").strip()
        out.append({"group": g, "article": str(i.get("article") or "").strip(),
                    "description": html.unescape(" ".join(x for x in (str(i.get("description") or "").strip().capitalize(),
                                                                      str(i.get("rating") or "").strip()) if x)),
                    "qty": int(q) if float(q).is_integer() else q, "unit": "no",
                    "used_by": motor_tag if g == "Feeders" else "panel",
                    "source": f"{t['ref']} sheet '{t['sheet']}' row {i.get('row')}",
                    "unit_price_inr": i.get("unit_price_inr"), "make": mk.title() if len(mk) > 3 else (mk or None),
                    "status": "template"})
    return out


def text(tid: str, kw: float | None = None) -> str:
    """The description a template stands for (what the requirement reads): motor kW, application, starter."""
    t = get(tid)
    kw = kw if kw is not None else t["kw"]
    # F/R is read as DOL by the rules (no reversing starter is selected; the template's lines hold the reversing pair)
    starter = {"SD": "star delta starter", "DOL": "DOL", "DOL_FR": "DOL", "SS": "soft starter", "VFD": "VFD"}.get(t["starter"], "")
    app = t["application"] or "motor"
    qty = f"{t['motors']} x " if t["motors"] > 1 else ""
    if kw is None:   # the name does not give the kW: the tool asks for it (the motor count goes in as an answer, answers())
        return f"{t['title'].title()} ({app}){', ' + starter if starter else ''}"
    return f"{qty}{kw:g} kW {app} with {starter}" if starter == "star delta starter" else (f"{qty}{kw:g} kW {app} {starter}" if starter else f"{qty}{kw:g} kW {app}")


def answers(tid: str) -> dict:
    """What a template copy starts with as answers: the motor count when the name gives no kW (e.g. VSI 'DUAL MOTOR')."""
    t = get(tid)
    return {"qty": str(t["motors"])} if t["kw"] is None and t["motors"] > 1 else {}


FULL_SCOPE = {"plc": True, "smps": True, "incomer": True, "control_transformer": True}


def scope(tid: str) -> dict:
    """R-REQ-31: what the template lists, so only that is selected — plc, smps (24 V supply), incomer, control transformer;
    with the template's own 24 V supply rating (A) and line, when listed."""
    lines = bom(tid)
    sm = next((l for l in lines if l["group"] == "Control power"), None)
    return {"plc": any(l["group"] == "PLC" and re.search(r"CPU|SIMATIC|CP2E|\bPLC\b", l["description"].upper()) for l in lines),
            "smps": sm is not None, "incomer": any(l["group"] == "Incomer" for l in lines),
            "control_transformer": any("control transformer" in l["description"].lower() for l in lines),
            "smps_a": rating_a(sm) if sm else None, "smps_line": f"{sm['description']} ({sm['source']})" if sm else None}


def defaults(tid: str, prm: dict) -> dict:
    """R-REQ-30: the inputs a template copy runs with when its words do not give them: {input: (value, where it comes from)}.
    From the template's own lines first, then the owner's template defaults (prm = requirement params.template_defaults)."""
    t = get(tid)
    lines = bom(tid)
    out = {}
    tr = next((l for l in lines if "control transformer" in l["description"].lower()), None)
    m = re.search(r"(\d{3})\s*/\s*\d{3}\s*V", tr["description"].upper()) if tr else None
    out["voltage_v"] = (float(m.group(1)), f"template line: {tr['description']} ({tr['source']})") if m \
        else (float(prm["voltage_v"]), "template default")
    cpu = next((l for l in lines if l["group"] == "PLC" and re.search(r"CPU|SIMATIC|CP2E", l["description"].upper())), None)
    if cpu:
        d = cpu["description"].upper()
        fam = "siemens_s7200smart" if "200 SMART" in d or "S7-200" in d else "siemens_s71200g2" if "1200" in d \
            else "siemens_s71500" if "1500" in d else "omron" if "CP2E" in d else "other"
        out["plc_make"] = (fam, f"template line: {cpu['description']} ({cpu['source']})")
    else:
        out["plc_make"] = ("none", "the template lists no PLC")
    out["control_supply"] = ("transformer", f"template line: {tr['description']} ({tr['source']})") if tr \
        else ("phase_neutral", "the template lists no control transformer")
    for k, x in prm.items():                 # every other template default (R-REQ-30; audit 2026-10-17: the asked choices too)
        if k not in out and k not in ("voltage_v", "cable_m"):
            out[k] = (x, "template default")
    return out


def rating_a(line: dict) -> float | None:
    """The current rating printed in a template line's description ('400A,3POLE' → 400)."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*A\b", str(line.get("description") or ""))
    return float(m.group(1)) if m else None
