"""RFQ import, stage 2 (owner 2026-10-18): the questions for what the RFQ does not say, answered once per project, overridable
per panel, and per row where a row needs it. Saved beside the RFQ (rfq/<id>/answers.yaml) with who and when; every change
is kept in the file's history. Nothing is assumed: an unanswered question stays open (the trial, core/rfq_trial.py, then
shows its trial value, labelled as such).

Row questions come from what was read (core/rfq.py):
  running   — a motor row with quantity ≥ 2: how many units run at the same time (the rest are standby)
  feed      — a single-phase motor: fed from this panel (a single-phase starter: no held source → refused) or from
              outside it (e.g. a dosing skid: not in this panel's BOM)
  flc       — kW not in the guide table: the motor current to use (the RFQ's amps offered as a pick, never taken silently)
  units     — the starters stated ≠ the quantity: how many units the panel feeds
"""
from __future__ import annotations

import re
from datetime import datetime

import yaml

from core import rfq
from core.standards import SITE as SITE_KEYS

YN = [["true", "Yes"], ["false", "No"]]
# project questions: (key, question, kind, options, group, used in)
PROJECT = [
    ("voltage_v", "Supply voltage, line to line (V)", "number", None, "Supply and site", "stage 3"),
    ("fault_ka", "Fault level at the panels (kA)", "number", None, "Supply and site", "trial"),
    ("panel_internal_c", "Temperature inside the panels (°C)", "number", None, "Supply and site", "trial"),
    ("cable_ambient_c", "Cable route temperature (°C)", "number", None, "Supply and site", "trial"),
    ("cable_m", "Motor cable length where a row does not say (m)", "number", None, "Supply and site", "trial"),
    ("incomer_factor", "Incomer factor (In ≥ design current × factor; company template 1.5, decision M-1)", "number", None, "Incoming", "trial"),
    ("incomer_series", "Incomer breaker series", "choice", [["3VA", "Siemens 3VA1 — TM240, adjustable thermal and magnetic"], ["3VM", "Siemens 3VM — TM210 fixed / TM220 adjustable"]], "Incoming", "stage 3"),
    ("incomer_release", "Incomer trip unit (3VM)", "choice", [["TM210", "TM210 — fixed"], ["TM220", "TM220 — adjustable"]], "Incoming", "stage 3"),
    ("breaking_basis", "Incomer breaking capacity basis", "choice", [["icu", "Ultimate (Icu)"], ["ics", "Service (Ics)"]], "Incoming", "stage 3"),
    ("spd", "Surge arrester at the incomer?", "choice", YN, "Incoming", "stage 3"),
    ("pmr", "Phase monitoring relay at the incomer?", "choice", YN, "Incoming", "stage 3"),
    ("spd_make", "Surge arrester make", "choice", [["Siemens", "Siemens 5SD7 (type 2, LV 10)"], ["Phoenix", "Phoenix Contact"], ["OBO", "OBO Bettermann"]], "Incoming", "stage 3"),
    ("spd_config", "Surge arrester connection", "choice", [["3Ph+N+PE", "3 phases + N + PE (TN-S / TT)"], ["3Ph+PE", "3 phases + PE"]], "Incoming", "stage 3"),
    ("spd_signalling", "Surge arrester remote signal contact?", "choice", YN, "Incoming", "stage 3"),
    ("meter", "Energy meter at the incomer?", "choice", YN, "Incoming", "stage 3"),
    ("meter_comm", "Energy meter communication", "choice", [["profinet", "PROFINET (7KM module)"], ["modbus_tcp", "Modbus TCP (meter's own Ethernet)"], ["none", "None (local display only)"]], "Incoming", "stage 3"),
    ("ct_make", "Metering CT make", "choice", [["rishabh", "Rishabh"], ["selec", "Selec"]], "Incoming", "stage 3"),
    ("meter_supply", "Energy meter supply", "choice", [["ac_dc", "230 V AC (wide-range supply) → 7KM3220-0BA01-1DA0"], ["dc_24_60", "24 V DC → 7KM3220-1BA01-1EA0"]], "Incoming", "stage 3"),
    ("vfd_protection", "Drive protection", "choice", [["fuse", "Fuse (3NA)"], ["msp", "Motor starter protector (3RV)"], ["breaker", "Circuit breaker (3VA)"]], "Drives", "trial"),
    ("cu_fieldbus", "Drive fieldbus", "choice", [["profinet", "PROFINET"], ["none", "None (hardwired)"]], "Drives", "trial"),
    ("cu_safety", "Drive safe torque off (STO)", "choice", [["sto", "STO"], ["none", "None"]], "Drives", "trial"),
    ("cu_encoder", "Motor encoders for speed feedback?", "choice", YN, "Drives", "stage 3"),
    ("line_reactor_up_to_kw", "Line reactor (input choke) on drives up to (kW) — 0: none by rule", "number", None, "Drives", "stage 3"),
    ("fuse_holder", "What holds each drive's three fuses?", "choice", [["switch_disconnector", "3NP1 fuse switch disconnector (3-pole)"]], "Drives", "stage 3"),
    ("ss_comm", "Soft starter communication module", "choice", [["profinet", "PROFINET (3RW5980-0CS00)"], ["profibus", "PROFIBUS"], ["ethernet_ip", "EtherNet/IP"], ["modbus_rtu", "Modbus RTU"], ["modbus_tcp", "Modbus TCP"], ["none", "None"]], "Drives", "stage 3"),
    ("ss_hmi", "Soft starter display (HMI module)", "choice", [["standard", "Standard (3RW5980-0HS00)"], ["high_feature", "High-Feature (3RW5980-0HF00)"], ["none", "None"]], "Drives", "stage 3"),
    ("ss_hmi_mounting", "Soft starter display mounted", "choice", [["door", "On the panel door (IP65 kit)"], ["device", "In the soft starter (hinged cover)"]], "Drives", "stage 3"),
    ("ss_hmi_cable_m", "Soft starter display cable to the door (m)", "choice", [["0.5", "0.5 m"], ["1", "1 m"], ["2.5", "2.5 m"], ["5", "5 m"]], "Drives", "stage 3"),
    ("contactor_suppressor", "Surge suppressor (varistor) on each DOL contactor?", "choice", [["varistor", "Yes — the varistor for the contactor's size and coil"], ["none", "No"]], "Drives", "stage 3"),
    ("duty", "Drive and soft-starter duty", "choice", [["normal", "Normal (pumps, fans)"], ["heavy", "Heavy (conveyors, crushers)"]], "Drives", "trial"),
    ("emc_filter", "Drive EMC filter", "choice", [["none", "None"], ["C2", "Class C2"]], "Drives", "stage 3"),
    ("mc_copy_parameters", "Memory card per drive (copy parameters)?", "choice", YN, "Drives", "stage 3"),
    ("ss_protection", "Soft-starter protection", "choice", [["fuse_gg", "gG fuses (type 1)"], ["fuse_semi", "Semiconductor fuses (type 2)"], ["mpcb", "Breaker (printed kA only)"]], "Drives", "trial"),
    ("ss_line_contactor", "Line contactor with each soft starter?", "choice", YN, "Drives", "stage 3"),
    ("ss_thermistor", "Motor thermistor protection on the soft starters?", "choice", YN, "Drives", "stage 3"),
    ("plc_family", "PLC family", "choice", [["s7-1500-et200sp", "S7-1500 + ET 200SP"], ["s7-1200g2", "S7-1200 G2"], ["s7-200smart", "S7-200 SMART"]], "PLC and I/O", "trial"),
    ("plc_cpu", "S7-1500 CPU", "choice", [["CPU 1511-1 PN", "CPU 1511-1 PN"], ["CPU 1513-1 PN", "CPU 1513-1 PN"], ["CPU 1515-2 PN", "CPU 1515-2 PN"]], "PLC and I/O", "stage 3"),
    ("plc_mc_mb", "S7-1500 memory card (MB)", "number", None, "PLC and I/O", "stage 3"),
    ("io_basis", "PLC I/O counted from", "choice", [["rfq", "The RFQ's I/O columns (every row, instruments included)"], ["engine", "The engine's I/O rules per starter (motors only)"]], "PLC and I/O", "stage 3"),
    ("plc_spare_pct", "PLC spare I/O (%)", "number", None, "PLC and I/O", "stage 3"),
    ("panel_signals", "Panel signals to the PLC (E-stop, reset, phase failure, trip, warning)?", "choice", YN, "PLC and I/O", "stage 3"),
    ("relay_make", "Interface relay make", "choice", [["finder", "Finder"], ["phoenix", "Phoenix Contact"], ["connectwell", "Connectwell"]], "PLC and I/O", "stage 3"),
    ("terminal_make", "Terminal make", "choice", [["connectwell", "Connectwell"], ["phoenix", "Phoenix Contact"]], "PLC and I/O", "stage 3"),
    ("io_conductor_mm2", "I/O wire size (mm²)", "number", None, "PLC and I/O", "stage 3"),
    ("control_supply", "230 V control supply", "choice", [["transformer", "Control transformer"], ["phase_neutral", "Phase-neutral"]], "Control circuit", "stage 3"),
    ("estop", "Emergency stop on each panel door?", "choice", YN, "Control circuit", "stage 3"),
    ("reset_pb", "Reset push button?", "choice", YN, "Control circuit", "stage 3"),
    ("phase_lamps", "Phase lamps R / Y / B?", "choice", YN, "Control circuit", "stage 3"),
    ("lamp_va", "Pilot lamp power (VA each)", "number", None, "Control circuit", "stage 3"),
    ("smps_input", "24 V supply input", "choice", [["1P+N", "Single-phase"], ["3P", "Three-phase"]], "Control circuit", "stage 3"),
    ("wire_insulation", "Internal wire insulation", "choice", [["70", "70 °C (PVC)"], ["90", "90 °C"]], "Wiring", "stage 3"),
    ("wire_circuits", "Power circuits together in the busiest duct", "number", None, "Wiring", "stage 3"),
    ("cable_other", "Other cables beside each motor cable in the tray", "number", None, "Wiring", "stage 3"),
    ("cable_make", "Motor cable make", "choice", [["polycab", "Polycab"], ["kei", "KEI"]], "Wiring", "stage 3"),
]
PKEYS = {k for k, *_ in PROJECT}
NUM_LIMITS = {"line_reactor_up_to_kw": (0, 1000), "voltage_v": (200, 690), "plc_mc_mb": (1, 32768), "fault_ka": (1, 200), "panel_internal_c": (20, 60), "cable_ambient_c": (10, 60), "cable_m": (1, 2000),
              "incomer_factor": (1, 3), "plc_spare_pct": (0, 100), "io_conductor_mm2": (0.5, 4), "lamp_va": (0.1, 50),
              "wire_circuits": (1, 50), "cable_other": (0, 50)}


def _file(rid: str):
    rfq._load(rid)                                    # the RFQ must exist (and the id be well formed)
    return rfq.RFQS / rid / "answers.yaml"


def load(rid: str) -> dict:
    f = _file(rid)
    d = (yaml.safe_load(f.read_text()) or {}) if f.exists() else {}
    return {"project": d.get("project") or {}, "panels": d.get("panels") or {}, "rows": d.get("rows") or {},
            "standard": d.get("standard"), "rules": d.get("rules") or {}, "history": d.get("history") or []}


def _save(rid: str, a: dict) -> None:
    _file(rid).write_text("# RFQ answers (stage 2): standard applied, project, panel overrides, row rules, row answers — written by the web app.\n"
                          + yaml.safe_dump({k: a[k] for k in ("standard", "project", "panels", "rules", "rows", "history")},
                                           sort_keys=False, allow_unicode=True, width=200))


def _std_values(a: dict) -> dict:
    return dict((a.get("standard") or {}).get("values") or {})


# a question that only matters with another answer, or with a starter in the panel (none of these is asked otherwise)
WHEN = {"spd_make": lambda a, st: a.get("spd") == "true", "spd_config": lambda a, st: a.get("spd") == "true",
        "spd_signalling": lambda a, st: a.get("spd") == "true",
        "meter_comm": lambda a, st: a.get("meter") == "true", "ct_make": lambda a, st: a.get("meter") == "true",
        "meter_supply": lambda a, st: a.get("meter") == "true",
        "incomer_release": lambda a, st: a.get("incomer_series") == "3VM",
        "line_reactor_up_to_kw": lambda a, st: "VFD" in st,
        "fuse_holder": lambda a, st: "VFD" in st and a.get("vfd_protection") in (None, "fuse"),
        "contactor_suppressor": lambda a, st: "DOL" in st,
        "ss_comm": lambda a, st: "SS" in st, "ss_hmi": lambda a, st: "SS" in st,
        "ss_hmi_mounting": lambda a, st: "SS" in st and a.get("ss_hmi") not in (None, "none"),
        "ss_hmi_cable_m": lambda a, st: "SS" in st and a.get("ss_hmi_mounting") == "door",
        "plc_cpu": lambda a, st: a.get("plc_family") == "s7-1500-et200sp",
        "plc_mc_mb": lambda a, st: a.get("plc_family") == "s7-1500-et200sp",
        **{k: (lambda a, st: "VFD" in st) for k in ("vfd_protection", "cu_fieldbus", "cu_safety", "cu_encoder", "emc_filter",
                                                     "mc_copy_parameters")},
        "duty": lambda a, st: bool({"VFD", "SS"} & st),
        **{k: (lambda a, st: "SS" in st) for k in ("ss_protection", "ss_line_contactor", "ss_thermistor")}}


def starters(p: dict) -> set:
    """The starters the panel's motor rows state (VFD / DOL / SS)."""
    return {s for r in p["rows"] if r["kind"].startswith("motor")
            for k, s in (("inv", "VFD"), ("dol", "DOL"), ("ss", "SS")) if r.get(k)}


def relevant(key: str, answers: dict, st: set) -> bool:
    f = WHEN.get(key)
    return f is None or f(answers, st)


def row_questions(read: dict) -> dict:
    """{panel: [{key, tag, kind, question, options|limits, pick}]} from what was read."""
    from components.motor_flc.select import select as motor_flc
    out = {}
    for p in read["panels"]:
        qs = []
        for r in p["rows"]:
            if not r["kind"].startswith("motor"):
                continue
            key = f"{r['page']}:{r['sno']}:{r['tag']}"
            starters = sum(r.get(k) or 0 for k in ("inv", "dol", "ss"))
            q = r.get("qty") or 0
            if starters and q and starters != q:
                qs.append({"key": key, "tag": r["tag"], "kind": "units", "question": f"{r['tag']}: units fed by this panel "
                           f"(the RFQ says quantity {q:g} but {starters:g} starter(s))", "limits": [1, max(q, starters)],
                           "rfq_qty": q, "starters": starters})
            if max(q, starters) >= 2:
                qs.append({"key": key, "tag": r["tag"], "kind": "running", "question": f"{r['tag']} ({r['item']}): units running at "
                           "the same time (the rest are standby)", "limits": [1, max(q, starters)]})
            if r["kind"] == "motor_1ph":
                qs.append({"key": key, "tag": r["tag"], "kind": "feed", "question": f"{r['tag']} ({r['kw']:g} kW single-phase): where is it fed?",
                           "options": [["outside", "Outside this panel (e.g. dosing skid) — not in this BOM"],
                                       ["panel", "From this panel — needs a single-phase starter source (not held: refused)"]]})
            else:
                f = motor_flc(kw=r["kw"], voltage_v=400)
                if f.status in ("cannot_select", "invalid") or not (f.value or {}).get("flc_a"):
                    qs.append({"key": key, "tag": r["tag"], "kind": "flc", "question": f"{r['tag']} ({r['kw']:g} kW, not in the guide table): "
                               "motor current to use (A)", "limits": [0.1, 2000], "pick": r.get("amps")})
        out[p["name"]] = qs
    return out


def rule_value(q: dict, rules: dict):
    """What the RFQ's row rules give for one row question (None: no rule covers it)."""
    k = q["kind"]
    if k == "running":
        return (rules.get("running") or {}).get(str(int(q["limits"][1])))
    if k == "feed":
        return rules.get("feed")
    if k == "flc":
        return q.get("pick") if rules.get("flc") == "rfq" and q.get("pick") else None
    if k == "units":
        return {"starters": q.get("starters"), "qty": q.get("rfq_qty")}.get(rules.get("units"))
    return None


def questions(rid: str) -> dict:
    """Every question with its effective value and where it comes from: answered (or a panel override) → the applied
    company standard; a row: answered → the RFQ's row rules. Nothing else fills a value."""
    from core import rfq_spec
    read = rfq.get(rid)
    a = load(rid)
    std = _std_values(a)
    rq = row_questions(read)
    # the client's specification (owner 2026-10-20): a value it gives every panel is a project value, else per panel
    spec_p = {p["name"]: rfq_spec.answers_for(rid, p["name"]) for p in read["panels"]}
    spec = {k: v for k, v in (next(iter(spec_p.values()), {}) or {}).items()
            if all(k in sp and sp[k][0] == v[0] for sp in spec_p.values())}
    eff_p = {**std, **{k: v for k, (v, _) in spec.items()}, **a["project"]}
    st_all = set().union(*(starters(p) for p in read["panels"])) if read["panels"] else set()
    proj = []
    for k, q, kind, opts, grp, used in PROJECT:
        ans = a["project"].get(k)
        sv, swhy = spec.get(k, (None, None))
        val = ans if ans is not None else sv if sv is not None else std.get(k)
        proj.append({"key": k, "question": q, "kind": kind, "options": opts, "group": grp, "used_in": used,
                     "limits": NUM_LIMITS.get(k), "answer": ans, "standard": std.get(k), "spec": sv, "spec_why": swhy,
                     "value": val, "source": "answered" if ans is not None else "client spec" if sv is not None
                     else "standard" if val is not None else None,
                     "relevant": relevant(k, eff_p, st_all)})
    n_rule = 0
    for qs in rq.values():
        for q in qs:
            q["answer"] = (a["rows"].get(q["key"]) or {}).get(q["kind"])
            q["by_rule"] = rule_value(q, a["rules"])
            q["value"] = q["answer"] if q["answer"] is not None else q["by_rule"]
            q["source"] = "answered" if q["answer"] is not None else "rule" if q["value"] is not None else None
            n_rule += q["source"] == "rule"
    open_p = sum(1 for q in proj if q["value"] is None and q["relevant"])
    status = {}
    for p in read["panels"]:
        name, qs = p["name"], rq[p["name"]]
        merged = {**std, **{k: v for k, (v, _) in spec_p[name].items()}, **a["project"], **(a["panels"].get(name) or {})}
        status[name] = {"rows_open": sum(1 for q in qs if q["value"] is None), "rows_total": len(qs),
                        "rows_by_rule": sum(1 for q in qs if q["source"] == "rule"),
                        "overrides": a["panels"].get(name) or {},
                        "project_open": [k for k, *_ in PROJECT if merged.get(k) is None and relevant(k, merged, starters(p))]}
    groups = sorted({int(q["limits"][1]) for qs in rq.values() for q in qs if q["kind"] == "running"})
    return {"id": rid, "project": proj, "rows": rq, "panel_overrides": a["panels"], "status": status, "project_open": open_p,
            "standard": {k: v for k, v in (a["standard"] or {}).items() if k != "values"} if a["standard"] else None,
            "rules": a["rules"], "rule_groups": groups, "rows_by_rule": n_rule,
            "site": [k for k, *_ in PROJECT if k in SITE_KEYS],
            "complete": all(not s["rows_open"] and not s["project_open"] for s in status.values()), "history": a["history"][-30:]}


def missing(rid: str, panel: str) -> list[str]:
    """What is still open for one panel (its project questions with its overrides, and its row questions)."""
    q = questions(rid)
    if panel not in q["status"]:
        raise ValueError(f"no panel {panel!r} in {rid}")
    s = q["status"][panel]
    return ([f"project: {k}" for k in s["project_open"]] +
            [f"{x['tag']}: {x['kind']}" for x in q["rows"][panel] if x["value"] is None])


def _check(key: str, value, kind: str | None = None, options=None, limits=None):
    if value in (None, ""):
        return None                                   # clears the answer
    if options is not None:
        if str(value) not in [o[0] for o in options]:
            raise ValueError(f"{key}: one of {', '.join(o[0] for o in options)} (got {value!r})")
        return str(value)
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key}: a number (got {value!r})")
    if limits and not limits[0] <= x <= limits[1]:
        raise ValueError(f"{key}: from {limits[0]:g} to {limits[1]:g} (got {x:g})")
    if kind in ("running", "units") and x != int(x):
        raise ValueError(f"{key}: a whole number (got {x:g})")
    if key in ("plc_mc_mb",) and x != int(x):
        raise ValueError(f"{key}: a whole number (got {x:g})")
    return int(x) if kind in ("running", "units") or key in ("wire_circuits", "cable_other", "plc_mc_mb") else x


def answer(rid: str, scope: str, key: str, value, user: str | None = None) -> dict:
    """scope 'project' (key = a project question), 'panel:<name>' (an override of a project question for one panel) or
    'row' (key = '<row key>|<kind>'). value None / '' clears it."""
    from core import auth
    auth.require("designer")
    read = rfq.get(rid)
    a = load(rid)
    spec = {k: (kind, opts, NUM_LIMITS.get(k)) for k, _, kind, opts, _, _ in PROJECT}
    if scope == "project" or scope.startswith("panel:"):
        if key not in PKEYS:
            raise ValueError(f"no project question {key!r}")
        kind, opts, lim = spec[key]
        v = _check(key, value, kind, opts, lim)
        if scope == "project":
            target = a["project"]
        else:
            pname = scope.split(":", 1)[1]
            if pname not in [p["name"] for p in read["panels"]]:
                raise ValueError(f"no panel {pname!r}")
            target = a["panels"].setdefault(pname, {})
    elif scope == "row":
        rkey, _, kind = str(key).rpartition("|")
        q = next((q for qs in row_questions(read).values() for q in qs if q["key"] == rkey and q["kind"] == kind), None)
        if q is None:
            raise ValueError(f"no row question {key!r}")
        v = _check(f"{q['tag']} {kind}", value, kind, q.get("options"), q.get("limits"))
        target = a["rows"].setdefault(rkey, {})
        key = kind
    else:
        raise ValueError("scope must be project, panel:<name> or row")
    old = target.get(key)
    if v is None:
        target.pop(key, None)
    else:
        target[key] = v
    a["panels"] = {k: x for k, x in a["panels"].items() if x}
    a["rows"] = {k: x for k, x in a["rows"].items() if x}
    a["history"].append({"at": datetime.now().isoformat(timespec="seconds"), "by": user, "scope": scope, "key": key,
                         "from": old, "to": v})
    _save(rid, a)
    return {"scope": scope, "key": key, "value": v, "from": old}


def for_panel(rid: str, panel: str) -> tuple[dict, dict]:
    """(effective project values for the panel: standard ← project answers ← the panel's overrides; effective row values:
    row rules ← row answers) — for the trial and stage 3."""
    from core import rfq_spec
    a = load(rid)
    proj = {**_std_values(a), **{k: v for k, (v, _) in rfq_spec.answers_for(rid, panel).items()}, **a["project"],
            **(a["panels"].get(panel) or {})}
    rows = {}
    if a["rules"]:
        for qs in row_questions(rfq.get(rid)).values():
            for q in qs:
                v = rule_value(q, a["rules"])
                if v is not None:
                    rows.setdefault(q["key"], {})[q["kind"]] = v
    for key, ans in a["rows"].items():
        rows.setdefault(key, {}).update(ans)
    return proj, rows


def sources(rid: str, panel: str) -> dict:
    """Where each project value of a panel comes from: 'panel override', 'answered' or 'standard <name> v<n>'."""
    a = load(rid)
    from core import rfq_spec
    out = {k: f"standard {a['standard']['name']} v{a['standard']['v']}" for k in _std_values(a)}
    out.update({k: why for k, (_, why) in rfq_spec.answers_for(rid, panel).items()})
    out.update({k: "answered" for k in a["project"]})
    out.update({k: "panel override" for k in (a["panels"].get(panel) or {})})
    return out


def apply_standard(rid: str, sid: str | None, user: str | None = None) -> dict:
    """Start the RFQ from an approved company standard (its latest approved version is copied in); None removes it.
    Answers already given stay and win over the standard."""
    from core import auth, standards
    auth.require("designer")
    rfq.get(rid)
    a = load(rid)
    old = (a["standard"] or {}).get("name")
    a["standard"] = standards.snapshot(sid) if sid else None
    new = (a["standard"] or {}).get("name")
    a["history"].append({"at": datetime.now().isoformat(timespec="seconds"), "by": user, "scope": "standard", "key": "standard",
                         "from": old, "to": f"{new} v{a['standard']['v']}" if new else None})
    _save(rid, a)
    return {"standard": {k: v for k, v in (a["standard"] or {}).items() if k != "values"} if a["standard"] else None}


RULE_CHOICES = {"feed": ("outside", "panel"), "flc": ("rfq",), "units": ("starters", "qty")}


def set_rules(rid: str, rules: dict, user: str | None = None) -> dict:
    """The RFQ's row rules: running units per group size ({'running': {'2': 1, '3': 2}}), where single-phase motors are fed
    (feed: outside / panel), the RFQ's current where a kW is not in the guide table (flc: rfq), units fed where the
    quantity and the starters differ (units: starters / qty). An explicit row answer always wins over a rule."""
    from core import auth
    auth.require("designer")
    rfq.get(rid)
    if not isinstance(rules, dict):
        raise ValueError("rules must be an object")
    clean = {}
    for k, v in rules.items():
        if v in (None, "", {}):
            continue
        if k == "running":
            if not isinstance(v, dict):
                raise ValueError("running: {group size: units running}")
            run = {}
            for g, n in v.items():
                if n in (None, ""):
                    continue
                try:
                    g_, n_ = int(g), float(n)
                except (TypeError, ValueError):
                    raise ValueError(f"running: group {g!r} → {n!r} is not a number")
                if g_ < 2 or n_ != int(n_) or not 1 <= n_ <= g_:
                    raise ValueError(f"running: in a group of {g_}, 1 … {g_} units run (got {n})")
                run[str(g_)] = int(n_)
            if run:
                clean["running"] = run
        elif k in RULE_CHOICES:
            if v not in RULE_CHOICES[k]:
                raise ValueError(f"{k}: one of {', '.join(RULE_CHOICES[k])} (got {v!r})")
            clean[k] = v
        else:
            raise ValueError(f"no row rule {k!r}")
    a = load(rid)
    old = a["rules"]
    a["rules"] = clean
    a["history"].append({"at": datetime.now().isoformat(timespec="seconds"), "by": user, "scope": "rules", "key": "rules",
                         "from": old, "to": clean})
    _save(rid, a)
    return {"rules": clean}
