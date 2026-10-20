"""One device tag per BOM line, shared by every drawing sheet and the drawing-format BOM (owner 2026-10-17: the drawing
set must be better than the company sample AVELCPSDL08WPLC, where the BOM tags are typed by hand and can drift).

Letters follow the company legend (OWN-PROPEL-SCH160 p.3 and BOM pages 14-15): 1SQ incomer MCCB, Q motor protection
circuit breaker, K power contactor, 2Q miniature circuit breaker, CT current transformer, CTS current sensor, PB push
button, IPB illuminated push button, EPB emergency stop, H indication lamp (R / Y / B-PHASE for the phase lamps), HM hour
meter, VAF meter, TRA control transformer, T timer, MPR motor protection relay, UV/OV relay, SMPS, IR interface relays
(24 V relay board), 1F fuses, X terminals. Where the company legend has no letter the tool uses: F drive fuse, U drive
(power module + control unit + operator panel), SS soft starter, OLR overload relay, SPD surge arrester, PMR phase
monitoring relay, A1… PLC CPU and modules. A device of a feeder with several motors gets a tag per motor.

plan(v) → {"units": [...], "line_tags": {bom index: "K1-K3"}, "devices": {tag: {...}}}
"""
from __future__ import annotations

import re

# feeder device roles from the article / description (makes used by the selection and the company kits)
def role_of(article: str, desc: str) -> str | None:
    a, d = str(article).upper(), str(desc).lower()
    if a.startswith("3RW5") or "soft starter" in d:
        return "ss"
    if a.startswith(("3RV", "GZ1E", "GV2", "GV3", "GV7")) or "motor protection circuit breaker" in d or "mpcb" in d:
        return "mpcb"
    if a.startswith("3VA") or "breaker for the drive" in d:
        return "mpcb"                              # a circuit breaker protecting a feeder (vfd_protection = breaker)
    if a.startswith(("LAEN", "LADN", "3RH", "3RA19")) or "add on block" in d or "add-on block" in d or "auxiliary contact" in d:
        return "aux"
    if a.startswith(("3RT", "LC1E", "LC1D")) or "contactor" in d:
        return "contactor"
    if a.startswith("3NA") or ("fuse" in d and "terminal" not in d):
        return "fuse"
    if a.startswith("6SL3210") or "power module" in d:
        return "pm"
    if a.startswith(("6SL3243", "6SL3244", "6SL3246")) or "control unit" in d:
        return "cu"
    if a.startswith(("6SL3054", "6SL3255")) or "operator panel" in d or "memory card" in d:
        return "drive_acc"
    if a.startswith("6SL3203") or "reactor" in d:
        return "reactor"
    if a.startswith("LRE") or d.startswith("olr") or "overload" in d:
        return "olr"
    if "motor protection relay" in d:
        return "mpr"
    if "timer" in d:
        return "timer"
    return None


def _range_a(desc: str) -> tuple[float, float] | None:
    """A setting range printed in a description ('Olr 5.5-8A', 'GZ1E 6-10A') → (5.5, 8.0)."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|…|\.\.\.|to)\s*(\d+(?:\.\d+)?)\s*A", str(desc))
    return (float(m.group(1)), float(m.group(2))) if m else None


def _contactor_a(desc: str, article: str) -> float:
    m = re.search(r"(\d+)\s*A\b", desc) or re.search(r"LC1E(\d+)", article.upper())
    return float(m.group(1)) if m else 0.0


def _panel_tag(b: dict) -> tuple[str, str] | None:
    """(letter, kind) of a panel-level line; kind names the device on the sheets."""
    g, a, d = b["group"], str(b["article"]).upper(), str(b.get("description") or "").lower()
    if g == "Incomer":
        return ("1SQ", "incomer")
    if g == "Metering":
        if "module" in d and "meter" in d:
            return ("VAF", "meter_acc")          # the meter's communication module: part of the meter
        if "sensor" in d:
            return ("CTS", "ct_sensor")
        if "current transformer" in d or a.startswith(("CT", "4NC")) or " ct" in f" {d}":
            return ("CT", "ct")
        return ("VAF", "meter")
    if g == "Auxiliary switchgear":
        if "surge" in d:
            return ("SPD", "spd")
        if "uv/ov" in d or "uv / ov" in d:
            return ("UV/OV", "uvov")
        return ("PMR", "pmr")
    if g == "Control power":
        return ("SMPS", "smps")
    if g == "PLC":
        if "hmi" in d or a.startswith("6AV"):
            return ("HMI", "hmi")
        if any(w in d for w in ("switch", "pen drive", "cable", "connector")):
            return None                              # network and accessories: listed in the BOM, not PLC modules
        return ("A", "plc")
    if g == "Control circuit":
        if "mcb" in d or a.startswith(("5SL", "5SY", "A9K", "A9F")):
            return ("2Q", "mcb")                 # before 'transformer': 'MCB … control transformer primary' is an MCB
        if "transformer" in d:
            return ("TRA", "transformer")
        if a.startswith("ZBE") or ("element" in d and "push" not in d):
            return ("PB", "element")             # NO / NC contact element: part of the push button before it
        if "emergency" in d or "mushroom" in d or "hood" in d:
            return ("EPB", "estop")
        if "lamp" in d:
            return ("H", "lamp")
        if "hour meter" in d:
            return ("HM", "hour_meter")
        if "illuminated" in d:
            return ("IPB", "ipb")
        if "push" in d or a in ("ZBE101N",):
            return ("PB", "pb")
        return None
    if g == "Control and signalling":
        if "relay" in d and "terminal" not in d:
            return ("RLB", "relay230") if "230" in d else ("IR", "relay")      # company: RLB 230 V boards, IR 24 V (p.14)
        if "terminal" in d and "end" not in d:
            return ("X", "terminal")
        return None
    if g.startswith("Client spec") and "(plant)" not in g:     # the client's own items of this panel
        if "surge arrester" in d:                 # before 'main incomer': 'Surge arrester, main incomer'
            return ("SPD", "spd")
        if "main incomer" in d:
            return ("1SQ", "incomer")
        if "24 v dc power supply" in d or a.startswith("SITOP"):
            return ("SMPS", "smps_n")
        if "energy meter" in d:
            return ("VAF", "meter")
        if "hmi" in d:
            return ("HMI", "hmi")
        return None
    if g == "Template items":
        if "selector" in d:
            return ("SS", "selector")
        if "vaf" in d or "meter" in d:
            return ("VAF", "meter")
        if "fuse" in d:
            return ("1F", "fuse")
        return None
    return None


LAMP_COLOUR = {"XB7EV04MPN": "red", "XB7EV05MPN": "yellow", "XB7EV06MPN": "blue", "XB7EV03MPN": "green"}


def _colour(b: dict) -> str | None:
    a, d = str(b["article"]).upper(), str(b.get("description") or "").lower()
    return LAMP_COLOUR.get(a) or next((c for c in ("red", "yellow", "blue", "green", "white", "amber") if c in d), None)


def plan(v: dict) -> dict:
    bom = v.get("bom") or []
    feeders = [f for f in v.get("feeders") or [] if f.get("status") != "excluded"]
    counters: dict[str, int] = {}
    line_tags: dict[int, list[str]] = {}
    devices: dict[str, dict] = {}

    def nxt(letter: str) -> str:
        counters[letter] = counters.get(letter, 0) + 1
        return f"{letter}{counters[letter]}"

    def give(i: int, tag: str, kind: str, unit: str | None = None, **kw):
        line_tags.setdefault(i, []).append(tag)
        devices.setdefault(tag, {"tag": tag, "kind": kind, "unit": unit, "line": bom[i], "index": i, **kw})
        return tag

    # feeder units: one per motor (a feeder of 2 motors → M3.1, M3.2), devices split per motor
    units = []
    by_tag = {}
    apps = {m.get("tag"): m.get("application") for m in v.get("motors") or []}
    fq = {f["tag"]: int(f.get("qty") or 1) for f in feeders}
    share = {i: sum(fq.get(t, 0) for t in str(b.get("used_by") or "").split(", ")) or 1 for i, b in enumerate(bom)}
    seen_units: dict[int, int] = {}                 # line → units already given their share
    for i, b in enumerate(bom):
        for t in str(b.get("used_by") or "").split(", "):
            by_tag.setdefault(t, []).append(i)
    for f in feeders:
        q = int(f.get("qty") or 1)
        idx = [i for i in by_tag.get(f["tag"], []) if bom[i]["group"] in ("Feeders", "Feeder accessories", "Motor cables", "Internal wiring")]
        for n in range(q):
            uid = f["tag"] if q == 1 else f"{f['tag']}.{n + 1}"
            u = {"tag": uid, "feeder": f, "app": apps.get(f["tag"]) or "", "kw": f.get("kw"), "starter": f.get("starter") or "", "flc_a": f.get("flc_a"),
                 "cable": f.get("cable") or "", "status": f.get("status"), "dev": {}, "kit": [], "wire": None}
            units.append(u)
            # contactors: star-delta = main, delta (the larger pair), star (company p.6: K1 main, K2 delta, K3 star)
            cts, prot = [], []
            for i in idx:
                b = bom[i]
                r = role_of(b["article"], b.get("description", ""))
                qty = b["qty"] if isinstance(b["qty"], (int, float)) else 0
                k_ = seen_units.get(i, 0)              # this unit's place among all units sharing the line (audit 2026-10-17)
                seen_units[i] = k_ + 1
                per = int(qty) // share[i] + (1 if k_ < int(qty) % share[i] else 0) if qty else 0
                if b["group"] == "Motor cables":
                    give(i, f"{uid} cable", "cable", uid)
                    continue
                if b["group"] == "Internal wiring":
                    u["wire"] = b
                    line_tags.setdefault(i, []).append(f"{uid} wiring") if f"{uid} wiring" not in line_tags.get(i, []) else None
                    continue
                if b["group"] == "Feeder accessories":
                    u["kit"].append(b)
                    if _colour(b) and per:
                        for _ in range(per):
                            give(i, nxt("H"), "lamp", uid, colour=_colour(b))
                    elif f"{uid} kit" not in line_tags.get(i, []):
                        line_tags.setdefault(i, []).append(f"{uid} kit")
                    continue
                if r == "contactor":
                    cts += [(i, _contactor_a(b.get("description", ""), b["article"]))] * per
                    continue
                if r == "aux":
                    u["dev"].setdefault("aux", []).append(i)
                    continue
                if r in ("pm", "cu", "drive_acc", "reactor"):
                    if per:                            # a removed line (qty 0) is not drawn
                        u["dev"].setdefault("drive", []).append(i)
                    continue
                letter = {"mpcb": "Q", "fuse": "F", "ss": "SS", "olr": "OLR", "mpr": "MPR", "timer": "T"}.get(r)
                if r in ("olr", "mpcb") and per:
                    prot += [(i, r)] * per          # decided below: the motor's own, or an auxiliary feeder's
                    continue
                if letter and per:
                    sets = per // 3 if r == "fuse" and per % 3 == 0 else per     # fuse links: one tag per 3-pole set
                    for _ in range(sets):
                        u["dev"].setdefault(r, []).append(give(i, nxt(letter), r, uid))
                elif r is None and f"{uid} kit" not in line_tags.get(i, []):
                    line_tags.setdefault(i, []).append(f"{uid}")
            # a template may hold more contactors than the starter needs (auxiliary drives: lube, blower, …, company p.7);
            # the motor keeps its own set (the largest), the others become auxiliary feeders, motor not stated
            cts.sort(key=lambda c: -c[1])
            n_own = 3 if u["starter"] == "SD" and len(cts) >= 3 else 2 if u["starter"] == "DOL_FR" and len(cts) >= 2 else min(1, len(cts))
            own, extra = cts[:n_own], cts[n_own:]
            roles = ["main", "delta", "star"] if n_own == 3 else ["forward", "reverse"] if n_own == 2 else ["main"]
            for (i, a), role in zip(own, roles):
                u["dev"].setdefault("k", []).append(give(i, nxt("K"), "contactor", uid, role=role))
            flc = u["flc_a"]
            for i, r in prot:                   # the motor's protection: its setting range covers the motor current
                lo_hi = _range_a(bom[i].get("description", ""))
                mine = not extra or (lo_hi and isinstance(flc, (int, float)) and lo_hi[0] <= flc <= lo_hi[1]) or \
                    (not lo_hi and not isinstance(flc, (int, float)))
                letter = "Q" if r == "mpcb" else "OLR"
                if mine:
                    u["dev"].setdefault(r, []).append(give(i, nxt(letter), r, uid))
                else:
                    u.setdefault("aux_prot", []).append(give(i, nxt(letter), r, uid, aux=True))
            for k, (i, a) in enumerate(extra, 1):
                aux = {"tag": f"{uid}-AUX{k}", "feeder": f, "app": "auxiliary drive", "kw": None, "starter": "DOL", "flc_a": None,
                       "cable": "", "status": "template-aux", "dev": {}, "kit": [], "wire": None, "aux_of": uid}
                aux["dev"]["k"] = [give(i, nxt("K"), "contactor", aux["tag"], role="main")]
                u.setdefault("aux_units", []).append(aux)
            if u["dev"].get("drive"):
                ut = nxt("U")
                for i in u["dev"]["drive"]:
                    give(i, ut, "drive", uid)
                u["dev"]["u"] = [ut]
            kt = u["dev"].get("k") or []
            for i in u["dev"].pop("aux", []):
                line_tags.setdefault(i, []).append(("aux " + kt[0]) if kt else "aux")
            units.extend(u.pop("aux_units", []))
    # panel devices
    lamp_colours = {_colour(b) for b in bom if b["group"] == "Control circuit" and "lamp" in str(b.get("description")).lower()}
    phase_lamps = {"red", "yellow", "blue"} <= lamp_colours
    for i, b in enumerate(bom):
        if i in line_tags or b["group"] in ("Not selected", "Out of scope") or not (b.get("article") or b.get("description")):
            continue
        pt = _panel_tag(b)
        qty = b["qty"] if isinstance(b["qty"], (int, float)) else 1
        if pt is None and b["group"] in ("Feeders", "Feeder accessories"):      # a feeder part with no motor named
            r = role_of(b["article"], b.get("description", ""))
            letter = {"mpcb": "Q", "contactor": "K", "fuse": "F", "ss": "SS", "olr": "OLR", "mpr": "MPR", "timer": "T"}.get(r)
            pt = (letter, r) if letter else None
        if pt is None:
            line_tags[i] = ["—"]
            continue
        letter, kind = pt
        if isinstance(b["qty"], (int, float)) and b["qty"] <= 0:
            line_tags[i] = ["removed"]           # a BOM edit took it out: not drawn (audit 2026-10-17)
            continue
        if kind == "meter_acc":
            line_tags[i] = [next((t for t, d in devices.items() if d["kind"] == "meter"), "VAF")]
            continue
        if kind == "smps_n":
            n_ = sum(1 for d in devices.values() if d["kind"] == "smps")
            give(i, "SMPS" if n_ == 0 else f"SMPS{n_ + 1}", "smps")
            continue
        if kind == "incomer":
            if "1SQ1" in devices:
                line_tags[i] = ["1SQ1"]          # rotary handle, spreader links: parts of the incomer (sample BOM rows 2-5)
            else:
                give(i, "1SQ1", kind)
            continue
        if kind == "lamp" and phase_lamps and _colour(b) in ("red", "yellow", "blue") and f"{_colour(b)[0].upper()}-PHASE" not in devices:
            give(i, f"{_colour(b)[0].upper()}-PHASE", kind, colour=_colour(b), phase=True)
            for _ in range(int(qty) - 1):
                give(i, nxt("H"), kind, colour=_colour(b))
            continue
        if kind in ("smps", "spd", "pmr", "uvov", "meter", "ct_sensor", "estop", "hour_meter") and letter not in devices:
            give(i, letter if kind not in ("estop",) else "EPB", kind, **({"colour": _colour(b)} if kind == "lamp" else {}))
            continue
        if kind in ("estop",):
            line_tags[i] = ["EPB"]
            continue
        if kind == "element":                    # the element belongs to the operator line just before it
            prev = line_tags.get(i - 1, ["—"])
            line_tags[i] = list(prev)
            continue
        if kind == "plc":
            give(i, nxt("A"), kind, cpu="cpu" in str(b.get("description")).lower())
            continue
        if kind == "terminal":
            line_tags[i] = ["X2"] if not line_tags.get(i) else line_tags[i]
            continue
        n = min(int(qty), 60) if qty >= 1 else 1
        ch = re.search(r"(\d+)\s*CH\b", str(b.get("description") or "").upper())
        if kind in ("relay", "relay230") and ch:     # a relay board: one tag per channel (company BOM p.14: IR1-IR8, IR9-IR12)
            n = min(int(qty) * int(ch.group(1)), 96)
        for _ in range(n):
            give(i, nxt(letter), kind, **({"colour": _colour(b)} if kind == "lamp" else {}))
    return {"units": units, "devices": devices, "line_tags": {i: _compact(t) for i, t in line_tags.items()}}


def _compact(tags: list[str]) -> str:
    """K1, K2, K3 → K1-K3 (a run of one letter); other tags as listed."""
    out, run = [], []
    def flush():
        if run:
            out.append(run[0][0] + str(run[0][1]) if len(run) == 1 else f"{run[0][0]}{run[0][1]}-{run[-1][0]}{run[-1][1]}")
            run.clear()
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    for t in seen:
        m = re.fullmatch(r"(\d*[A-Z]+)(\d+)", t)
        if m and run and run[-1][0] == m.group(1) and run[-1][1] + 1 == int(m.group(2)):
            run.append((m.group(1), int(m.group(2))))
        else:
            flush()
            if m:
                run.append((m.group(1), int(m.group(2))))
            else:
                out.append(t)
    flush()
    return ", ".join(out)
