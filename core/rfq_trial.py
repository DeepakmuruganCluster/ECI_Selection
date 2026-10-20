"""RFQ import: the panel structure and a trial selection, one panel at a time (owner 2026-10-18).

Partition — every row of an RFQ panel lands in exactly one functional section, the way a panel builder lays it out:
  Incoming & distribution (selected by the engine: incomer, busbar, metering, surge arrester)
  VFD section · DOL / MCC section · Soft starter section (the motor rows by their stated starter; a motor without a
  clear starter → 'Motors to clarify') · Control supply (transformer, 24 V: selected by the engine)
  PLC & I/O (the panel's I/O totals) · Field instruments and signals (every non-motor row)

Trial — the engine run on one panel (feeders through the panel assembly, incomer, PLC, 24 V supply, power calculation)
BEFORE the stage-2 questions are answered. What stage 2 will ask is filled with TRIAL VALUES, every one listed and
changeable, and the result is marked TRIAL: nothing is saved and nothing is a selection for the client. The RFQ's MPCB
rating is kept (owner decision); its check against the engine (core/rfq.mpcb_check) is shown per row.
"""
from __future__ import annotations

from core import rfq

# what stage 2 asks — here only to run a trial; shown on the page as trial values, never used beyond the trial
TRIAL_VALUES = {"fault_ka": (50, "Fault level at the panel (kA)"), "panel_internal_c": (40, "Temperature inside the panel (°C)"),
                "cable_ambient_c": (40, "Cable route temperature (°C)"), "cable_m": (50, "Motor cable length, every motor (m)"),
                "vfd_protection": ("fuse", "Drive protection (fuse / msp / breaker)"),
                "cu_fieldbus": ("profinet", "Drive fieldbus (profinet / none)"), "cu_safety": ("none", "Drive STO (sto / none)"),
                "duty": ("normal", "Drive and soft-starter duty (normal / heavy)"), "incomer_factor": (1.5, "Incomer factor"),
                "plc_family": ("s7-1500-et200sp", "PLC family (s7-1500-et200sp / s7-1200g2 / s7-200smart)"),
                "ss_protection": ("fuse_gg", "Soft-starter protection (fuse_gg / fuse_semi / mpcb)")}
# the engine's standing reminders on every feeder ('confirm the motor current with the nameplate', an input stage 2 asks):
# shown as 'to confirm', they do not make a row a warning
CONFIRM_RULES = {"R-DOL-09", "R-VFD-13", "R-SS-13", "R-VFD-08"}
SECTIONS = ["Incoming & distribution", "VFD section", "DOL / MCC section", "Soft starter section", "Motors to clarify",
            "Control supply", "PLC & I/O", "Field instruments and signals"]


def _starter(r: dict) -> str | None:
    st = [k for k in ("inv", "dol", "ss") if r.get(k)]
    return {"inv": "VFD", "dol": "DOL", "ss": "SS"}[st[0]] if len(st) == 1 else None


def partition(p: dict) -> list[dict]:
    """The panel's rows by functional section, with each section's totals."""
    rows = {s: [] for s in SECTIONS}
    for r in p["rows"]:
        if r["kind"].startswith("motor"):
            st = _starter(r)
            rows[{"VFD": "VFD section", "DOL": "DOL / MCC section", "SS": "Soft starter section"}.get(st, "Motors to clarify")].append(r)
        else:
            rows["Field instruments and signals"].append(r)
    out = []
    for s in SECTIONS:
        rs = rows[s]
        tot = {k: round(sum(x.get(k) or 0 for x in rs), 2) for k in ("total_kw", "di", "do", "ao", "inv", "dol", "ss")}
        tot["ai"] = round(sum((x.get("ai_420") or 0) + (x.get("ai_010") or 0) for x in rs), 2)
        tot["units"] = round(sum(x.get("qty") or 0 for x in rs), 2)
        note = {"Incoming & distribution": "incomer, busbar, metering and surge arrester: selected by the engine (no RFQ rows)",
                "Control supply": "control transformer and 24 V supply: selected by the engine (no RFQ rows)",
                "PLC & I/O": f"from the panel's I/O totals: DI {p['printed']['di']:g} · DO {p['printed']['do']:g} · "
                             f"AI {p['printed']['ai_420'] + p['printed']['ai_010']:g} · AO {p['printed']['ao']:g}",
                "Motors to clarify": "no single starter stated: VFD / DOL / soft starter to be clarified"}.get(s)
        out.append({"section": s, "n_rows": len(rs), "rows": [f"{x['page']}:{x['sno']}:{x['tag']}" for x in rs], "totals": tot, "note": note})
    return out


def _values(given: dict | None) -> dict:
    v = {k: d for k, (d, _) in TRIAL_VALUES.items()}
    for k, x in (given or {}).items():
        if k not in TRIAL_VALUES:
            raise ValueError(f"unknown trial value {k}")
        d = TRIAL_VALUES[k][0]
        try:
            v[k] = float(x) if isinstance(d, (int, float)) else str(x)
        except (TypeError, ValueError):
            raise ValueError(f"{k} must be like {d!r} (got {x!r})")
    return v


def trial(rid: str, panel_name: str, given: dict | None = None) -> dict:
    """Stage 2 (owner 2026-10-18): the panel's answers (project + panel overrides, rfq_answers) replace the trial values;
    values typed on the trial form are used for this run only; row answers set units, running units, the feed of a
    single-phase motor and the current of a kW not in the guide table."""
    from core import rfq_answers
    bad = sorted(set(given or {}) - set(TRIAL_VALUES))
    if bad:
        raise ValueError(f"not a trial value: {', '.join(bad)}")
    ans, row_ans = rfq_answers.for_panel(rid, panel_name)
    whence = rfq_answers.sources(rid, panel_name)
    src = {}
    merged = {}
    for k in TRIAL_VALUES:
        if given and k in given and given[k] not in (None, ""):
            merged[k], src[k] = given[k], "typed for this trial"
        elif k in ans:
            merged[k], src[k] = ans[k], whence.get(k, "answered")
        else:
            src[k] = "trial value"
    return _trial(rid, panel_name, merged, src, row_ans)


def _trial(rid: str, panel_name: str, given: dict, src: dict, row_ans: dict) -> dict:
    """Run the engine on one RFQ panel with the trial values. → {values, sections, feeders, incomer, plc, smps, power, verdicts}."""
    from components.panel.select import select as panel_select
    from components.mccb.select import select as mccb
    from components.plc.select import select as plc_select
    from components.control_power.select import select as control_power
    from components.power.select import select as power_calc
    from components.motor_flc.select import select as motor_flc
    r = rfq.get(rid)
    p = next((x for x in r["panels"] if x["name"] == panel_name), None)
    if p is None:
        raise ValueError(f"no panel {panel_name!r} in {rid}")
    v = _values(given)
    # 1. the motor rows as a load list (one engine tag per row; a tag used twice gets its S.NO)
    lines, by_tag, seen = [], {}, {}
    for r_ in p["rows"]:
        if not r_["kind"].startswith("motor"):
            continue
        st = _starter(r_)
        key = f"{r_['page']}:{r_['sno']}:{r_['tag']}"
        ra = row_ans.get(key) or {}
        if st is None or not r_.get("kw") or not r_.get("qty"):
            by_tag[key] = {"row": r_, "etag": None, "why": "no single starter, kW or quantity stated"}
            continue
        if r_["kind"] == "motor_1ph" and ra.get("feed") == "outside":
            by_tag[key] = {"row": r_, "etag": None, "outside": True, "why": "fed from outside this panel (your answer): not in this BOM"}
            continue
        qty = int(ra.get("units") or r_["qty"])
        running = int(ra["running"]) if ra.get("running") else None
        if running is not None and running > qty:
            running = qty
        base = "".join(ch if ch.isalnum() or ch in "-_/." else "_" for ch in (r_["tag"] or f"ROW{r_['sno']}"))
        etag = base if base not in seen else f"{base}@{r_['page']}.{r_['sno']}"
        seen[etag] = key
        line = f"{etag} {r_['kw']:g} {st} cable={v['cable_m']:g} qty={qty}"
        if running is not None and running < qty:
            line += f" standby={qty - running}"
        if r_["kind"] == "motor_1ph":
            line += " ph=1 v=230"
        f = motor_flc(kw=r_["kw"], phases=1 if r_["kind"] == "motor_1ph" else 3, voltage_v=230 if r_["kind"] == "motor_1ph" else 400)
        if ra.get("flc"):
            line += f" flc={float(ra['flc']):g} flc_source=datasheet"   # your answer
        elif (f.status in ("cannot_select", "invalid") or not (f.value or {}).get("flc_a")) and r_.get("amps"):
            line += f" flc={r_['amps']:g} flc_source=datasheet"     # not in the guide table: the RFQ's current (the client's motor data), said so
        if st in ("VFD", "SS"):
            line += f" duty={v['duty']}"
        lines.append(line)
        by_tag[key] = {"row": r_, "etag": etag, "line": line}
    if not lines:
        raise ValueError(f"panel {panel_name}: no motor row with a single starter, kW and quantity")
    pr = panel_select(load_list="\n".join(lines), fault_ka=v["fault_ka"], panel_internal_c=v["panel_internal_c"],
                      cable_ambient_c=v["cable_ambient_c"], voltage_v=400.0, vfd_protection=v["vfd_protection"],
                      cu_encoder=False, cu_safety=v["cu_safety"], cu_fieldbus=v["cu_fieldbus"], mc_copy_parameters=False,
                      dol_source="siemens", kit_accessories=False, ss_protection=v["ss_protection"])
    if pr.status == "invalid":
        raise ValueError("panel assembly: " + next(c.value for c in pr.checks if c.verdict == "fail"))
    pv = pr.value
    feed = {f["tag"]: f for f in pv["feeders"]}
    opens = {}
    for o in pv["open_points"]:
        opens.setdefault(o.get("tag"), []).append(o)
    rows_out = []
    for key, b in by_tag.items():
        r_ = b["row"]
        if b.get("etag") is None:
            rows_out.append({"key": key, "tag": r_["tag"], "verdict": "outside" if b.get("outside") else "fail",
                             "status": "outside this panel" if b.get("outside") else "not run", "why": b["why"],
                             "starter": _starter(r_), "kw": r_["kw"], "qty": r_["qty"]})
            continue
        f = feed.get(b["etag"], {})
        os_ = opens.get(b["etag"], [])
        refused = [o for o in os_ if o.get("kind") == "refused"]
        warns = [o for o in os_ if o.get("kind") != "refused" and o.get("rule") not in CONFIRM_RULES]
        confirm = [o for o in os_ if o.get("kind") != "refused" and o.get("rule") in CONFIRM_RULES]
        mc = r_.get("mpcb_check") or {}
        verdict = "fail" if refused or f.get("status") != "selected" else \
            "warning" if warns or mc.get("state") in ("unsafe", "differs") else "pass"
        why = ("single-phase motor: the held Siemens DOL tables are 3-phase 400 V only — no starter selected"
               if any(o.get("rule") == "R-DOL-01" for o in refused) else None)
        rows_out.append({"key": key, "tag": r_["tag"], "engine_tag": b["etag"], "starter": _starter(r_), "kw": r_["kw"],
                         "qty": r_["qty"], "status": f.get("status"), "devices": f.get("devices"), "cable": f.get("cable"),
                         "flc_a": f.get("flc_a"), "wire": f.get("internal_wire"), "mpcb_check": mc,
                         "rfq_mpcb": r_.get("mpcb_rating"), "verdict": verdict, "why": why,
                         "flc_from_rfq": "flc_source=datasheet" in b["line"] and not (row_ans.get(key) or {}).get("flc"),
                         "running": f.get("running"), "row_answers": row_ans.get(key) or {},
                         "points": [f"{o['rule']}: {o['point']}"[:220] for o in refused + warns][:6],
                         "confirm": [f"{o['rule']}: {o['point']}"[:160] for o in confirm][:4]})
    # 2. incomer (design current × factor), 3. PLC from the panel's I/O totals, 4. 24 V supply, 5. power calculation
    sel = [f for f in pv["feeders"] if f["status"] == "selected" and f.get("wire_ib_a")]
    ib = round(sum(f["wire_ib_a"] * f["running"] for f in sel if (f.get("phases") or 3) == 3), 2)
    inc = mccb(ib_a=ib, fault_ka=v["fault_ka"], ambient_c=v["panel_internal_c"], voltage_v=400.0, margin=v["incomer_factor"]) if ib else None
    pt = p["printed"]
    io = {"di": int(pt["di"]), "do": int(pt["do"]), "ai": int(pt["ai_420"] + pt["ai_010"]), "ao": int(pt["ao"])}
    plc = plc_select(**io, make="siemens", family=v["plc_family"], fieldbus=v["cu_fieldbus"] if v["cu_fieldbus"] != "none" else None,
                     fieldbus_devices=int(pt["inv"]) if v["cu_fieldbus"] == "profinet" else None, ambient_c=v["panel_internal_c"])
    plc_a = (plc.value or {}).get("supply_24v_a", (plc.value or {}).get("i24_a")) if plc.status not in ("cannot_select", "invalid") else None
    cp = control_power(di=io["di"], relays=io["do"], plc_a=plc_a)
    three, single = [], []
    for f in sel:
        row = {"tag": f["tag"], "description": f"{f['kw']:g} kW {f['starter']}" + (f" × {f['running']}" if f["running"] > 1 else ""),
               "running": f["running"], "i_a": f["wire_ib_a"], "kw": f["kw"], "source": "panel assembly (trial)"}
        if (f.get("phases") or 3) == 1:
            single.append({"name": f"{f['tag']} {f['kw']:g} kW (single-phase)", "i_a": f["wire_ib_a"] * f["running"],
                           "connection": "LN", "source": "panel assembly (trial)"})
        else:
            three.append(row)
    pw = power_calc(voltage_v=400.0, three_phase=three, single_phase=single, main_fos=v["incomer_factor"])
    pwv = pw.value if pw.status not in ("cannot_select", "invalid") else None
    # sections with the trial result
    part = partition(p)
    res_by_key = {x["key"]: x for x in rows_out}
    for s in part:
        rs = [res_by_key[k] for k in s["rows"] if k in res_by_key]
        s["verdicts"] = {k: sum(1 for x in rs if x["verdict"] == k) for k in ("pass", "warning", "fail", "outside")}
    for s in part:
        if s["section"] == "Incoming & distribution":
            s["result"] = (f"incomer {inc.value['article_no']} (In {inc.value['in_a']:g} A) for {ib:g} A × {v['incomer_factor']:g}"
                           if inc and inc.status not in ("cannot_select", "invalid") else
                           f"incomer not selected for {ib:g} A × {v['incomer_factor']:g}: " + (next((c.value for c in inc.checks if c.verdict == "fail"), "") if inc else "no current")
                           + (" — every unit counted as running: answer the running units (stage 2 questions)" if not any((x or {}).get("running") for x in row_ans.values()) else ""))
            s["verdict"] = "pass" if inc and inc.status not in ("cannot_select", "invalid") else "fail"
        elif s["section"] == "PLC & I/O":
            s["result"] = (f"{plc.value.get('cpu') or 'remote I/O'} + {plc.value.get('n_modules', '')} module(s); 24 V {plc_a} A"
                           if plc.status not in ("cannot_select", "invalid") else "PLC not selected: " + next((c.value for c in plc.checks if c.verdict == "fail"), plc.status))
            s["verdict"] = "pass" if plc.status not in ("cannot_select", "invalid") else "fail"
        elif s["section"] == "Control supply":
            s["result"] = (f"24 V supply {cp.value['smps_brand']} {cp.value['smps']} ({cp.value['smps_a']:g} A, needs {cp.value['required_a']:g} A); "
                           "control transformer: sized in stage 3 (coil and lamp VA are asked)"
                           if cp.status not in ("cannot_select", "invalid") else "24 V supply not selected: " + next((c.value for c in cp.checks if c.verdict == "fail"), cp.status)
                           + " — the load needs more than one supply (several supplies are chosen in stage 3)")
            s["verdict"] = "pass" if cp.status not in ("cannot_select", "invalid") else "fail"
    n = {k: sum(1 for x in rows_out if x["verdict"] == k) for k in ("pass", "warning", "fail", "outside")}
    return {"rfq": rid, "panel": panel_name, "trial": True, "values": v, "sources": src,
            "complete": all(x != "trial value" for x in src.values()),
            "value_labels": {k: lab for k, (_, lab) in TRIAL_VALUES.items()}, "sections": part, "rows": rows_out,
            "verdicts": n, "incomer": {"ib_a": ib, "article": inc.value["article_no"] if inc and inc.status not in ("cannot_select", "invalid") else None,
                                       "in_a": inc.value["in_a"] if inc and inc.status not in ("cannot_select", "invalid") else None},
            "power": {k: pwv.get(k) for k in ("i_l1_a", "i_l2_a", "i_l3_a", "imbalance_pct", "s_kva", "main_load_a")} if pwv else None,
            "n_bom_lines": len(pv["bom"]) + (1 if inc else 0) + len((plc.value or {}).get("parts", [])) + (1 if cp.status not in ("cannot_select", "invalid") else 0)}
