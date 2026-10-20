"""Alternatives for a machine BOM line (rule R-REQ-22): change the design choice behind the line, never the part alone.

A part in the BOM is the result of design choices (the motor's starter and duty, the drive protection, the cable make,
the PLC family …). An alternative is one of those choices set differently: the requirement is selected again with it,
so every linked part follows — a heavier drive brings its own fuse, reactor, cable, wiring and incomer current. Each
option is shown with every line it changes and the indicative cost difference; options that do not select fully are
not offered. Ranking by the designer's prompt is a convenience (words → options); it never changes a selection.
"""
from __future__ import annotations

import json
import re

from components.requirement.select import select as requirement

# design choices: key → (scope, label, [(value, label, words)])
KNOBS = {
    "starter": ("motor", "Starter", [("VFD", "VFD (variable speed drive)", "vfd drive inverter variable speed"),
                                     ("DOL", "DOL starter", "dol direct on line contactor mpcb"),
                                     ("SD", "Star-delta (company kit)", "star delta sd y-d"),
                                     ("SS", "Soft starter (3RW52)", "soft starter soft start 3rw")]),
    "duty": ("motor", "Duty", [("normal", "Normal duty (LO rating)", "normal light lo smaller"),
                               ("heavy", "Heavy duty (HO rating)", "heavy ho bigger larger upsize higher overload")]),
    "vfd_protection": ("panel", "Drive protection", [("fuse", "Fuses (Siemens-listed)", "fuse fuses 3na"),
                                                     ("msp", "Motor starter protector", "msp mpcb 3rv starter protector"),
                                                     ("breaker", "Circuit breaker", "breaker mccb 3va")]),
    "cu_encoder": ("panel", "Motor encoder", [("true", "With encoder feedback", "encoder feedback closed loop"),
                                               ("false", "No encoder", "no encoder open loop")]),
    "cu_safety": ("panel", "Drive safety", [("sto", "Safe torque off (STO)", "sto safety safe torque"),
                                            ("none", "No safety function", "no safety")]),
    "cu_fieldbus": ("panel", "Drive fieldbus", [("profinet", "PROFINET", "profinet pn"), ("ethernet_ip", "EtherNet/IP", "ethernet ip eip"),
                                                ("profibus", "PROFIBUS", "profibus dp"), ("modbus", "Modbus", "modbus rtu"),
                                                ("none", "Hardwired (no fieldbus)", "hardwired analog no fieldbus")]),
    "mc_copy_parameters": ("panel", "Drive memory card", [("true", "With memory card", "memory card copy"),
                                                           ("false", "No memory card", "no memory card")]),
    "ss_protection": ("panel", "Soft starter protection", [("mpcb", "Breaker (Siemens type 1, printed kA)", "breaker mpcb 3rv 3va"),
                                                          ("fuse_gg", "gG fuses (type 1)", "fuse fuses gg 3na"),
                                                          ("fuse_semi", "Semiconductor fuses (type 2)", "semiconductor fuse type 2 3ne")]),
    "dol_source": ("panel", "DOL starters from", [("siemens", "Siemens Type 2 (3RV + 3RT)", "siemens type 2 3rv 3rt"),
                                                  ("company", "Company kit (Schneider)", "company kit schneider gz1e lc1e")]),
    "kit_accessories": ("panel", "Feeder accessories", [("true", "Company kit accessories", "accessories lamps terminals kit"),
                                                         ("false", "No kit accessories", "no accessories remove")]),
    "cable_make": ("panel", "Cable make", [("polycab", "Polycab", "polycab"), ("kei", "KEI", "kei")]),
    "cable_installation": ("panel", "Cable installation", [("air", "In air (tray)", "air tray"),
                                                           ("ground", "Buried in the ground", "buried ground underground"),
                                                           ("duct", "In a buried duct", "duct")]),
    "plc_make": ("panel", "PLC", [("siemens_s7200smart", "Siemens S7-200 SMART", "siemens s7-200 smart small"),
                                  ("siemens_s71200g2", "Siemens S7-1200 G2", "siemens s7-1200 1200 g2"),
                                  ("siemens_s71500", "Siemens S7-1500 + ET 200SP", "siemens s7-1500 1500 et200sp remote io"),
                                  ("omron", "Omron CP2E", "omron cp2e")]),
    "smps_brand": ("panel", "24 V supply make", [("Omron", "Omron", "omron"), ("Phoenix Contact", "Phoenix Contact", "phoenix"),
                                                 ("Mean well", "Mean Well", "mean well meanwell"), ("Weidmueller", "Weidmüller", "weidmuller weidmueller")]),
    "spd_make": ("panel", "Surge arrester make", [("Siemens", "Siemens 5SD7", "siemens 5sd"), ("Phoenix", "Phoenix Contact", "phoenix"),
                                                  ("OBO", "OBO Bettermann", "obo")]),
    "ct_make": ("panel", "CT make", [("rishabh", "Rishabh", "rishabh"), ("selec", "Selec", "selec")]),
    "control_supply": ("panel", "Control supply", [("transformer", "Control transformer", "transformer"),
                                                   ("phase_neutral", "Phase-neutral 230 V (no transformer)", "phase neutral no transformer")]),
    "panel_internal_c": ("panel", "Temperature inside the panel", [(35, "35 °C", "35 cooler"), (40, "40 °C", "40"), (45, "45 °C", "45"),
                                                                   (50, "50 °C", "50 hotter")]),
}
DEFAULTS = {"ss_protection": "mpcb", "vfd_protection": "fuse", "dol_source": "siemens", "kit_accessories": "true", "cable_make": "polycab",
            "cable_installation": "air", "smps_brand": "Omron", "control_supply": "transformer"}


def _knobs_for(line: dict, motors: dict) -> list[str]:
    """The design choices that produce this line."""
    g, art = line.get("group", ""), str(line.get("article") or "").upper()
    tags = [t for t in str(line.get("used_by") or "").split(", ") if t in motors]
    starter = motors[tags[0]].get("starter") if tags else None
    if g == "Feeders":
        if starter == "VFD":
            if art.startswith(("6SL3244", "6SL3246", "6SL3243")):
                return ["cu_fieldbus", "cu_safety", "cu_encoder", "starter"]
            if art.startswith("6SL3054"):
                return ["mc_copy_parameters", "starter"]
            return ["duty", "vfd_protection", "starter"]
        if starter == "SS":
            return ["duty", "ss_protection", "starter"]
        if starter == "DOL":
            return ["dol_source", "starter"]
        return ["starter"]
    return {"Feeder accessories": ["kit_accessories", "dol_source"], "Motor cables": ["cable_make", "cable_installation", "starter"],
            "Internal wiring": ["panel_internal_c"], "Incomer": ["panel_internal_c"], "PLC": ["plc_make"],
            "Control power": ["smps_brand", "plc_make"], "Auxiliary switchgear": ["spd_make"], "Metering": ["ct_make"],
            "Control circuit": ["control_supply"], "Control and signalling": ["plc_make"]}.get(g, [])


def _diff(a: list[dict], b: list[dict]) -> list[dict]:
    """Lines that differ between two BOMs (by group and article), with quantities."""
    key = lambda l: (l["group"], str(l["article"]))
    ia = {key(l): l for l in a if l["group"] != "Not selected" and l["article"]}
    ib = {key(l): l for l in b if l["group"] != "Not selected" and l["article"]}
    out = []
    for k in sorted(set(ia) | set(ib)):
        x, y = ia.get(k), ib.get(k)
        if x and y and x["qty"] == y["qty"]:
            continue
        l = y or x
        out.append({"group": l["group"], "article": l["article"], "description": l["description"], "make": l.get("make"),
                    "from_qty": x["qty"] if x else 0, "to_qty": y["qty"] if y else 0,
                    "kind": "added" if not x else "removed" if not y else "quantity", "unit_price_inr": l.get("unit_price_inr")})
    return out


def _cost(lines: list[dict]) -> tuple[float, int]:
    """Indicative cost of the changed lines (priced lines only) and how many changed lines carry no price."""
    total, unpriced = 0.0, 0
    for c in lines:
        p = c.get("unit_price_inr")
        dq = (c["to_qty"] if isinstance(c["to_qty"], (int, float)) else 0) - (c["from_qty"] if isinstance(c["from_qty"], (int, float)) else 0)
        if p is None:
            unpriced += 1
        else:
            total += p * dq
    return round(total, 2), unpriced


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9.\-]+", s.lower()) if len(w) > 1}


def alternatives(inputs: dict, line: dict, prompt: str = "") -> dict:
    """{options: [...], knobs: [...]} for one line of a confirmed machine (inputs = the requirement's inputs)."""
    base_in = {**inputs, "confirmed": True}
    base = requirement(**base_in)
    if base.status == "invalid" or not (base.value or {}).get("selected"):
        raise ValueError("confirm the machine first: alternatives are worked out on a selected design")
    v = base.value
    motors = {m["tag"]: m for m in v.get("motors") or []}
    multi = len(motors) > 1
    tags = [t for t in str(line.get("used_by") or "").split(", ") if t in motors]
    pw = _words(prompt)
    options, skipped = [], []
    for k in _knobs_for(line, motors):
        scope, klabel, opts = KNOBS[k]
        if scope == "motor":
            if not tags:
                continue
            tag = tags[0]
            cur = str(motors[tag].get(k))
        else:
            cur = v.get(k)
            cur = DEFAULTS.get(k) if cur is None else cur
            cur = str(cur).lower() if isinstance(cur, bool) else str(cur)
        for val, label, words in opts:
            if str(val).lower() == str(cur).lower():
                continue
            var = dict(base_in)
            if scope == "motor" and multi:
                ms = json.loads(var["motors"]) if isinstance(var.get("motors"), str) else [dict(m) for m in var.get("motors") or []]
                idx = int(tag[1:]) - 1
                while len(ms) <= idx:
                    ms.append({})
                ms[idx] = {**ms[idx], k: val}
                var["motors"] = ms
                answer = {f"{tag}.{k}": val}
            else:
                var[k] = val
                answer = {k: val}
            r = requirement(**var)
            score = len(pw & _words(f"{label} {words}")) * 3
            if r.status == "invalid":
                skipped.append({"label": label, "knob_label": klabel, "why": next((c.value for c in r.checks if c.verdict == "fail"), "not usable")})
                continue
            if not (r.value or {}).get("selected"):
                qs = (r.value or {}).get("questions") or []
                if qs:   # QA 2026-10-16 (M4): offered, with the questions it brings, instead of silently left out
                    options.append({"knob": k, "knob_label": klabel, "value": val, "label": label,
                                    "scope": f"{tag}" if scope == "motor" else "whole panel", "answer": answer,
                                    "changes": [], "n_changes": 0, "cost_delta_inr": 0, "unpriced_changes": 0,
                                    "status": r.status, "refusals": 0, "score": score, "needs": [q["question"] for q in qs]})
                else:
                    skipped.append({"label": label, "knob_label": klabel, "why": "does not select"})
                continue
            # a choice that leaves a selected feeder unselected is not an alternative (nothing is half-done)
            was = {f["tag"] for f in v["feeders"] if f["status"] == "selected"}
            lost = was - {f["tag"] for f in r.value["feeders"] if f["status"] == "selected"}
            if lost:
                skipped.append({"label": label, "knob_label": klabel, "why": f"{', '.join(sorted(lost))} could not be selected with it"})
                continue
            changes = _diff(v["bom"], r.value["bom"])
            if not changes:
                continue
            cost, unpriced = _cost(changes)
            fails = [o for o in r.value.get("open_points", []) if o.get("kind") == "refused"]
            score += (2 if re.search(r"\bcheap|\bcost|\bprice", prompt.lower()) and cost < 0 and not unpriced else 0)
            options.append({"knob": k, "knob_label": klabel, "value": val, "label": label,
                            "scope": f"{tag}" if scope == "motor" else "whole panel", "answer": answer,
                            "changes": changes, "n_changes": len(changes), "cost_delta_inr": cost, "unpriced_changes": unpriced,
                            "status": r.status, "refusals": len(fails), "score": score})
    options.sort(key=lambda o: (-o["score"], bool(o.get("needs")), o["refusals"], o["n_changes"]))
    return {"line": {k: line.get(k) for k in ("group", "article", "description", "used_by")},
            "knobs": [KNOBS[k][1] for k in _knobs_for(line, motors)], "options": options, "skipped": skipped,
            "matched": bool(pw) and any(o["score"] for o in options)}
