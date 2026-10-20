"""RFQ import, stage 3 (owner 2026-10-18): the full BOM of each RFQ panel from the stage-2 answers, broken down panel by
panel and, inside a panel, by its functional section.

Each panel runs through the same complete-panel engine as a new machine (components/requirement): feeders, incomer,
surge arrester, metering, control transformer and circuit, 24 V supply, PLC, relays, terminals, wiring, power. What the
RFQ states is passed as answers, never guessed:
  - every motor row with one starter, kW and quantity, under the RFQ's own tag; the units running together (stage 2);
  - the RFQ's MPCB setting range on a DOL row (R-DOL-14: the RFQ value wins, flagged when the motor current is outside
    it). DOL starters therefore come from the Siemens Type 2 table, without company-kit accessories (said on the BOM);
  - the motor current answered for a kW not in the guide table;
  - the PLC I/O from the RFQ's own I/O columns or from the engine's rules — as answered (io_basis).
Not in a panel's BOM, each listed with the reason: single-phase motors fed from outside the panel (answered), single-phase
motors fed from the panel (no single-phase starter source held: refused), motor rows without one starter / kW / quantity.
Nothing is built until every question of that panel is answered (core/rfq_answers.missing).
"""
from __future__ import annotations

import re

from core import rfq, rfq_answers
from core.rfq_trial import _starter

PLC_MAKE = {"s7-1500-et200sp": "siemens_s71500", "s7-1200g2": "siemens_s71200g2", "s7-200smart": "siemens_s7200smart"}
GENERAL = ("smps_brand", "smps_split", "smps_cpu_min_a", "smps_io_min_a", "smps_min_a", "voltage_v", "fault_ka", "panel_internal_c", "cable_ambient_c", "incomer_factor", "incomer_series", "incomer_release", "breaking_basis",
           "spd", "pmr", "spd_make", "spd_config", "spd_signalling", "meter", "meter_comm", "meter_supply", "ct_make", "vfd_protection",
           "cu_fieldbus", "cu_safety", "cu_encoder", "emc_filter", "mc_copy_parameters", "fuse_holder", "line_reactor_up_to_kw", "contactor_suppressor",
           "ss_comm", "ss_hmi", "ss_hmi_mounting", "ss_hmi_cable_m", "ss_protection", "ss_line_contactor",
           "ss_thermistor", "plc_cpu", "plc_mc_mb", "plc_spare_pct", "panel_signals", "relay_make", "terminal_make",
           "io_conductor_mm2", "control_supply", "estop", "reset_pb", "phase_lamps", "lamp_va", "smps_input",
           "wire_insulation", "wire_circuits", "cable_other", "cable_make")
# the panel's functional sections (the RFQ structure, core/rfq_trial.SECTIONS), in build order
SECTIONS = ["Incoming & distribution", "VFD section", "DOL / MCC section", "Soft starter section", "Motor feeders — shared parts",
            "Control supply & control circuit", "PLC & I/O", "Motor cables (outgoing)", "Internal wiring", "Other items",
            "Not selected"]
STARTER_SECTION = {"VFD": "VFD section", "DOL": "DOL / MCC section", "SS": "Soft starter section"}
GROUP_SECTION = {"Incomer": "Incoming & distribution", "Busbar": "Incoming & distribution", "Metering": "Incoming & distribution",
                 "Auxiliary switchgear": "Incoming & distribution", "Control power": "Control supply & control circuit",
                 "Control circuit": "Control supply & control circuit", "PLC": "PLC & I/O", "Control and signalling": "PLC & I/O",
                 "Instruments": "PLC & I/O", "Motor cables": "Motor cables (outgoing)", "Cables": "Motor cables (outgoing)",
                 "Internal wiring": "Internal wiring", "Not selected": "Not selected", "Out of scope": "Not selected"}
BASIS = ["DOL starters: Siemens SIRIUS Type 2 table (the RFQ states MPCB setting ranges; R-DOL-14), no company-kit accessories",
         "Motor cable length, temperatures, fault level and every panel choice: the stage-2 answers (rfq/<id>/answers.yaml)",
         "Single-phase motors fed from outside the panel and motor rows without one starter, kW and quantity are not in the BOM"]


def _name(tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", tag).strip("_")[:28] or "ROW"


def section_of(line: dict, starter_of: dict) -> str:
    """The panel section of a BOM line: by its group, a feeder line by the starter of the motors that use it."""
    g = line.get("group", "")
    if g in ("Feeders", "Feeder accessories"):
        st = {starter_of.get(t.strip()) for t in str(line.get("used_by") or "").split(",") if t.strip()}
        st.discard(None)
        return STARTER_SECTION.get(next(iter(st)), "Motor feeders — shared parts") if len(st) == 1 else "Motor feeders — shared parts"
    return GROUP_SECTION.get(g, "Other items")


def _inputs(rid: str, p: dict, ans: dict, row_ans: dict) -> tuple[dict, dict, list, list]:
    """→ (requirement inputs, engine tag → RFQ row, outside rows, rows not in the BOM)."""
    st = rfq_answers.starters(p)
    g = {k: ans[k] for k in GENERAL if ans.get(k) is not None and rfq_answers.relevant(k, ans, st)}
    g["plc_make"] = PLC_MAKE[ans["plc_family"]]
    g.update(dol_source="siemens", kit_accessories=False)                 # BASIS[0]
    motors, rows, outside, left = [], {}, [], []
    seen = set()
    for r in p["rows"]:
        if not r["kind"].startswith("motor"):
            continue
        key = f"{r['page']}:{r['sno']}:{r['tag']}"
        ra = row_ans.get(key) or {}
        s = _starter(r)
        if r["kind"] == "motor_1ph":
            (outside if ra.get("feed") == "outside" else left).append(
                {"tag": r["tag"], "item": r["item"], "kw": r["kw"], "qty": r["qty"],
                 "why": "fed from outside this panel (your answer)" if ra.get("feed") == "outside"
                 else "single-phase motor fed from this panel: no single-phase starter source is held — not selected"})
            continue
        if s is None or not r.get("kw") or not r.get("qty"):
            left.append({"tag": r["tag"], "item": r["item"], "kw": r.get("kw"), "qty": r.get("qty"),
                         "why": "no single starter, kW or quantity stated in the RFQ — to clarify with the client"})
            continue
        base = re.sub(r"[^A-Za-z0-9_\-/.]", "_", r["tag"] or f"ROW{r['sno']}")[:30]
        tag = base if base not in seen else f"{base}@{r['page']}.{r['sno']}"
        seen.add(tag)
        qty = int(ra.get("units") or r["qty"])
        m = {"tag": tag, "kw": r["kw"], "qty": qty, "starter": s, "cable_m": ans["cable_m"]}
        if qty > 1 and ra.get("running"):
            m["running"] = min(int(ra["running"]), qty)
        if s in ("VFD", "SS"):
            m["duty"] = ans["duty"]
        if ra.get("flc"):
            m["flc_a"] = float(ra["flc"])
        lo, hi = rfq._range(r.get("mpcb_rating"))
        if s == "DOL" and lo is not None and hi is not None:
            m["mpcb_range"] = f"{lo:g}-{hi:g}"                             # the RFQ value wins (R-DOL-14)
        elif s == "VFD" and hi is not None:                                # a drive's MSP: used when it fits the drive (R-VFD-19)
            m["mpcb_range"] = f"{lo:g}-{hi:g}" if lo is not None else f"{hi:g}"
        motors.append(m)
        rows[tag] = r
    g["motors"] = motors
    return g, rows, outside, left


def client_checks(reqs: list[dict], bom: list[dict], starter_of: dict | None = None, feeders: list | None = None,
                  panel: str | None = None) -> list[dict]:
    """Each requirement of the client's specification (part 1, incoming) against what the engine put in the BOM:
    complies / deviation (with what differs) / not built (the engine selected nothing for it)."""
    out = []
    find = lambda f: next((b for b in bom if f(b)), None)
    for r in reqs:
        q, words = r["require"], f"{r['label']}: {r['value']}"
        base = {"part": r.get("part_name"), "requirement": words, "page": r["page"]}
        if r["kind"] == "vfd":                            # part 2: drive family, normal load, line reactors
            pms = [b for b in bom if b["group"] == "Feeders" and b["article"].startswith("6SL3210")]
            if not pms:
                out.append({**base, "verdict": "not built", "detail": "no drive in this panel's BOM"})
                continue
            diff = []
            if q.get("family") == "G120" and not all(b["article"].startswith("6SL3210-1PE") for b in pms):
                diff.append("a power module that is not a G120 PM240-2")
            if q.get("duty") == "normal" and not all(" LO " in f" {b['description']} " for b in pms):
                diff.append("not every drive is rated for low overload (normal load)")
            if q.get("reactor_up_to_kw") is not None:
                lim = q["reactor_up_to_kw"]
                reactor_tags = {t.strip() for b in bom if "reactor" in b["description"].lower() and "line" in b["description"].lower()
                                for t in str(b["used_by"]).split(",")}
                need = sorted({t.strip() for b in pms for t in str(b["used_by"]).split(",")
                               if (m := re.search(r"LO (\d+(?:\.\d+)?) kW", b["description"])) and float(m[1]) <= lim})
                miss = [t for t in need if t not in reactor_tags]
                if miss:
                    diff.append(f"no line reactor for {', '.join(miss)} (≤ {lim:g} kW)")
                base["detail_ok"] = f"line reactors on {len(need)} drive line(s) ≤ {lim:g} kW"
            n = sum(b["qty"] for b in pms if isinstance(b["qty"], (int, float)))
            out.append({**{k: v for k, v in base.items() if k != "detail_ok"}, "verdict": "deviation" if diff else "complies",
                        "detail": "; ".join(diff) or f"{n:g} × SINAMICS G120 PM240-2 LO (normal load)"
                        + (f"; {base['detail_ok']}" if base.get("detail_ok") else "")})
            continue
        if r["kind"] == "smps":                           # part 5: SITOP, the number and ratings of the 24 V supplies
            ps = [b for b in bom if b["group"] == "Control power"]
            if not ps:
                out.append({**base, "verdict": "not built", "detail": "no 24 V supply in this panel's BOM"})
                continue
            got = sorted(float(m[1]) for b in ps for _ in range(int(b["qty"]) if isinstance(b["qty"], (int, float)) else 1)
                         if (m := re.search(r"power supply (\d+(?:\.\d+)?) A", b["description"])))
            want = (q.get("ratings") or {}).get(panel)
            diff = []
            if q.get("make") == "Siemens" and not all(b["article"].startswith("Siemens 6EP") or b.get("make") == "Siemens" for b in ps):
                diff.append("a 24 V supply that is not a Siemens SITOP")
            if want and got != sorted(want):
                diff.append(f"{', '.join(f'{x:g} A' for x in got)} offered, the client states {', '.join(f'{x:g} A' for x in sorted(want))} "
                            "(the required current decides when it is larger — R-CP-09)")
            out.append({**base, "verdict": "deviation" if diff else "complies",
                        "detail": "; ".join(diff) or ", ".join(f"{b['article']} — {b['description']}" for b in ps)})
            continue
        if r["kind"] == "soft_starter":                   # part 4: 3RW52, display, communication; the RFQ's protection range
            ss = [b for b in bom if b["group"] == "Feeders" and b["article"].startswith("3RW5") and not b["article"].startswith("3RW59")]
            if not ss:
                out.append({**base, "verdict": "not built", "detail": "no soft starter in this panel's BOM"})
                continue
            diff, notes = [], []
            if q.get("family") and not all(b["article"].startswith(q["family"]) for b in ss):
                diff.append(f"a soft starter that is not {q['family']}")
            n_ss = sum(b["qty"] for b in ss if isinstance(b["qty"], (int, float)))
            com = sum(b["qty"] for b in bom if b["article"].startswith("3RW5980-0C"))
            hmi = sum(b["qty"] for b in bom if b["article"] in ("3RW5980-0HS00", "3RW5980-0HF00"))   # HMI modules (IC 10 6/76)
            if q.get("comm") and com < n_ss:
                diff.append(f"communication module on {com:g} of {n_ss:g} soft starter(s)")
            if q.get("display") and hmi < n_ss:
                diff.append(f"display (HMI module) on {hmi:g} of {n_ss:g} soft starter(s)")
            for f in feeders or []:
                if f["starter"] == "SS" and f.get("rfq_mpcb") and f.get("devices"):
                    notes.append(f"{f['tag']}: protection {f['devices'].split(' + ')[1] if ' + ' in f['devices'] else f['devices']} — "
                                 f"Siemens' tested combination at the fault level, instead of the RFQ's {f['rfq_mpcb']} (owner 2026-10-20; tell the client)")
            out.append({**base, "verdict": "deviation" if diff or notes else "complies",
                        "detail": "; ".join(diff + notes) or f"{n_ss:g} × 3RW52 with display and communication module"})
            continue
        if r["kind"] == "dol":                            # part 3: 3RV, link modules, a surge suppressor per contactor
            tags_of = lambda b: {t.strip() for t in str(b["used_by"]).split(",") if t.strip()}
            feed = [b for b in bom if b["group"] == "Feeders"]
            dol = {t for b in feed for t in tags_of(b) if (starter_of or {}).get(t) == "DOL"}       # by starter: a merged line can
            mp = [b for b in feed if b["article"].startswith("3RV") and tags_of(b) & dol]          # serve a drive's MSP too
            if not dol:
                out.append({**base, "verdict": "not built", "detail": "no DOL feeder in this panel's BOM"})
                continue
            diff, notes = [], []
            if q.get("mpcb_family"):
                no_mp = sorted(dol - set().union(*(tags_of(b) for b in mp))) if mp else sorted(dol)
                if no_mp:
                    diff.append(f"no {q['mpcb_family']} MPCB: {', '.join(no_mp)}")
            if q.get("link_module"):
                linked = set().union(*(tags_of(b) for b in bom if b["description"] == "Link module")) if bom else set()
                wired = sorted(dol - linked)
                if wired:
                    diff.append(f"wired, no link module: {', '.join(wired)} — Siemens' tested Type 2 pair (S00 MPCB + S0 contactor) "
                                "has none (SIE-SIRIUS-CM Table 2-1; owner 2026-10-20: the tested pair is kept, tell the client)")
            if q.get("suppressor"):
                sup = [b for b in bom if "surge suppressor" in b["description"].lower()]
                covered = set().union(*(tags_of(b) for b in sup)) if sup else set()
                if dol - covered:
                    diff.append(f"no surge suppressor: {', '.join(sorted(dol - covered))}")
                other = sorted({b["article"] for b in sup} - {q["suppressor"]}) if q["suppressor"] != "varistor" else []
                if other:
                    notes.append(f"{', '.join(other)} for the contactors of another size (the client's {q['suppressor']} fits size S00; "
                                 "IC 10 p.3/96)")
            out.append({**base, "verdict": "deviation" if diff else "complies",
                        "detail": "; ".join(diff + notes) or f"{len(dol)} DOL feeder lines: 3RV MPCB, link module and surge suppressor on each"})
            continue
        if r["kind"] == "incomer":
            b = find(lambda b: b["group"] == "Incomer")
            if not b:
                out.append({**base, "verdict": "not built", "detail": "no incomer selected"})
                continue
            icu = float(m[1]) if (m := re.search(r"Icu\s*(\d+(?:\.\d+)?)\s*kA", b["description"])) else None
            inn = float(m[1]) if (m := re.search(r"In\s*(\d+(?:\.\d+)?)\s*A", b["description"])) else None
            diff = []
            if q.get("series") and not b["article"].upper().startswith(q["series"]):
                diff.append(f"series {b['article'][:3]} offered, the client asks {q['series']} (the {q['series']} data is not held yet)")
            if q.get("in_a") and inn is not None and inn != q["in_a"]:
                diff.append(f"In {inn:g} A, the client asks {q['in_a']:g} A")
            if q.get("icu_ka") and (icu is None or icu < q["icu_ka"]):
                diff.append(f"breaking capacity {icu:g} kA < the client's {q['icu_ka']:g} kA" if icu is not None else "breaking capacity not printed")
            if q.get("adjustable") and not re.search(r"TM2[2-9]0|ATFM|adjustable", b["description"]):
                diff.append("trip unit: the client asks an adjustable thermal-magnetic release")
            out.append({**base, "verdict": "deviation" if diff else "complies", "detail": "; ".join(diff) or f"{b['article']} — {b['description']}",
                        "offered": b["article"]})
        elif r["kind"] == "spd":
            b = find(lambda b: b["group"] == "Auxiliary switchgear" and "surge" in b["description"].lower())
            if not b:
                out.append({**base, "verdict": "not built", "detail": "no surge arrester selected (answer: surge arrester at the incomer)"})
                continue
            made = (b.get("make") or "") + " " + b["description"]
            ok = not q.get("make") or q["make"].lower() in made.lower()
            out.append({**base, "verdict": "complies" if ok else "deviation", "offered": b["article"],
                        "detail": f"{b['article']} — {b['description']}" + ("" if ok else f": the client asks {q['make']}")})
        elif r["kind"] == "meter":
            b = find(lambda b: b["group"] == "Metering" and "meter" in b["description"].lower() and "module" not in b["description"].lower())
            pn = find(lambda b: b["group"] == "Metering" and "profinet" in b["description"].lower())
            if not b:
                out.append({**base, "verdict": "not built", "detail": "no energy meter selected (answer: energy meter at the incomer)"})
                continue
            diff = ([f"{b['article']} is not a {q['family']}"] if q.get("family") and not b["article"].startswith(q["family"]) else []) + \
                   (["no PROFINET module"] if q.get("profinet") and not pn else [])
            note = "; the order number is a pattern — complete it (R-MTR-03)" if "x" in b["article"] else ""
            out.append({**base, "verdict": "deviation" if diff else "complies", "offered": b["article"],
                        "detail": ("; ".join(diff) or f"{b['article']}" + (f" + {pn['article']}" if pn else "")) + note})
        elif r["kind"] == "ct":
            b = find(lambda b: b["group"] == "Metering" and "current transformer" in b["description"].lower())
            if not b:
                out.append({**base, "verdict": "not built", "detail": "no current transformers selected"})
                continue
            make = "rishabh" if "RISH" in b["article"].upper() else "selec" if "SPCT" in b["article"].upper() else None
            ok = not q.get("makes") or make in q["makes"]
            out.append({**base, "verdict": "complies" if ok else "deviation", "offered": b["article"],
                        "detail": f"{b['qty']} × {b['article']}" + ("" if ok else f": the client allows {', '.join(q['makes'])}")})
    return out


def _rfq_io_edits(p: dict, io_list: list[dict]) -> list[dict]:
    """io_basis 'rfq': the engine's motor signals out, every RFQ row's I/O columns in (named after the RFQ tag)."""
    edits = [{"action": "remove", "name": x["name"]} for x in io_list
             if x.get("starter") and x.get("type") in ("DI", "DO", "AI", "AO")]
    used = {x["name"] for x in io_list if not (x.get("starter") and x.get("type") in ("DI", "DO", "AI", "AO"))}
    for r in p["rows"]:
        n = {"DI": r.get("di") or 0, "DO": r.get("do") or 0, "AI": (r.get("ai_420") or 0) + (r.get("ai_010") or 0), "AO": r.get("ao") or 0}
        stem = _name(r["tag"] or f"ROW{r['sno']}")
        if any(f"I_{stem}_DI1" == u or f"O_{stem}_DO1" == u or f"I_{stem}_AI1" == u or f"O_{stem}_AO1" == u for u in used):
            stem = f"{stem}_{r['sno']}"
        for t, k in n.items():
            for i in range(1, int(k) + 1):
                name = f"{'I' if t in ('DI', 'AI') else 'O'}_{stem}_{t}{i}"
                used.add(name)
                edits.append({"action": "add", "type": t, "name": name, "unit": r["tag"],
                              "signal": f"{r['item']} ({t} {i} of {int(k)}) — RFQ p.{r['page']} S.NO {r['sno']}"})
    return edits


def build(rid: str, panel: str) -> dict:
    """The full BOM of one RFQ panel, with its section break. Refused (ValueError) while a question of the panel is open."""
    from components.requirement.select import select as requirement
    read = rfq.get(rid)
    p = next((x for x in read["panels"] if x["name"] == panel), None)
    if p is None:
        raise ValueError(f"no panel {panel!r} in {rid}")
    open_ = rfq_answers.missing(rid, panel)
    if open_:
        return {"rfq": rid, "panel": panel, "ready": False, "missing": open_}
    ans, row_ans = rfq_answers.for_panel(rid, panel)
    g, rows, outside, left = _inputs(rid, p, ans, row_ans)
    if not g["motors"]:
        raise ValueError(f"panel {panel}: no motor row with one starter, kW and quantity")
    text = "\n".join(f"{m['kw']:g} kW" for m in g["motors"])
    r = requirement(text, confirmed=True, **g)
    if r.status == "invalid":
        raise ValueError("panel engine: " + next(c.value for c in r.checks if c.verdict == "fail"))
    if ans["io_basis"] == "rfq" and r.value.get("selected"):
        r = requirement(text, confirmed=True, io_edits=_rfq_io_edits(p, r.value["io_list"]), **g)
        if r.status == "invalid":
            raise ValueError("panel engine (RFQ I/O): " + next(c.value for c in r.checks if c.verdict == "fail"))
    v = r.value
    if not v.get("selected"):                      # a question only the engine can ask (e.g. a coil's power): shown, not guessed
        return {"rfq": rid, "panel": panel, "ready": False, "missing": [],
                "engine_questions": [{"input": q["input"], "question": q["question"], "why": q.get("why")} for q in v.get("questions", [])]}
    starter_of = {f["tag"]: f["starter"] for f in v["feeders"]}
    bom = [{**b, "section": section_of(b, starter_of)} for b in v["bom"]]
    from core import rfq_spec                      # the client's specification (owner 2026-10-20): its own lines, its checks
    for ln in rfq_spec.lines_for(rid, panel):
        bom.append({"group": "Client-specified", "article": "as specified by the client", "description": ln["description"],
                    "make": "", "qty": ln.get("qty", 1), "unit": ln.get("unit", "set"), "used_by": "panel",
                    "source": ln["source"] + " — not engine-checked", "section": ln.get("section", "Incoming & distribution")})
    checks = client_checks(rfq_spec.requirements_for(rid, panel), bom, starter_of, panel=panel, feeders=
                           ([{"tag": f["tag"], "starter": f["starter"], "devices": f.get("devices"),
                             "rfq_mpcb": rows[f["tag"]].get("mpcb_rating") if f["tag"] in rows else None} for f in v["feeders"]]))
    bom.sort(key=lambda b: SECTIONS.index(b["section"]))
    secs = []
    for s in SECTIONS:
        ls = [b for b in bom if b["section"] == s]
        if ls:
            priced = [b for b in ls if b.get("unit_price_inr") is not None and isinstance(b.get("qty"), (int, float))]
            secs.append({"section": s, "n_lines": len(ls), "n_priced": len(priced),
                         "indicative_inr": round(sum(b["unit_price_inr"] * b["qty"] for b in priced), 2)})
    pt = p["printed"]
    feeders = [{"tag": f["tag"], "rfq_tag": rows[f["tag"]]["tag"] if f["tag"] in rows else f["tag"],
                "item": rows[f["tag"]]["item"] if f["tag"] in rows else "", "starter": f["starter"], "kw": f["kw"],
                "qty": f["qty"], "running": f.get("running"), "status": f["status"], "devices": f.get("devices"),
                "cable": f.get("cable"), "flc_a": f.get("flc_a"),
                "rfq_mpcb": rows[f["tag"]].get("mpcb_rating") if f["tag"] in rows else None} for f in v["feeders"]]
    return {"rfq": rid, "panel": panel, "ready": True, "missing": [], "basis": BASIS, "answers": ans,
            "io_basis": ans["io_basis"], "bom": bom, "sections": secs, "feeders": feeders, "outside": outside,
            "not_in_bom": left, "open_points": v["open_points"], "not_selected": v.get("not_selected_detail", []),
            "n_bom_lines": len(bom), "indicative_inr": v.get("indicative_inr"), "n_priced": v.get("n_priced"),
            "client_checks": checks,
            # the RFQ's MPCB kept although the motor current is outside it (owner: the RFQ value wins, flagged)
            "rfq_mpcb_flags": sorted({o["tag"] for o in v["open_points"] if o.get("rule") == "R-DOL-14" and "not protected" in o["point"]}),
            "rfq_mpcb_ie_class": sorted({o["tag"] for o in v["open_points"] if o.get("rule") == "R-DOL-14" and "IE class" in o["point"]}),
            "incomer": {"article": v.get("incomer"), "in_a": v.get("incomer_in_a"), "ib_a": v.get("incomer_ib_a")},
            "io": {"engine": {k: v.get(f"io_{k}") for k in ("di", "do", "ai", "ao")},
                   "rfq": {"di": pt["di"], "do": pt["do"], "ai": pt["ai_420"] + pt["ai_010"], "ao": pt["ao"]}},
            "plc_cpu": v.get("plc_cpu"), "transformer_va": v.get("transformer_va"), "smps": v.get("smps"),
            "power": {k: (v.get("power") or {}).get(k) for k in ("i_l1_a", "i_l2_a", "i_l3_a", "s_kva", "main_load_a")}
            if v.get("power") else None,
            "io_list": v["io_list"], "load_list": v["load_list"], "design_logic": v["design_logic"]}


def _sheet(panel: str, what: str) -> str:
    return (re.sub(r"[\[\]:*?/\\]", "_", panel)[:31 - len(what) - 1] + " " + what)[:31]


def export(rid: str) -> tuple[bytes, dict]:
    """The Excel workbook: a summary per panel and per section, then each panel's BOM (by section), feeders, I/O and open
    points; what is not in a BOM and why; every article across the panels. A panel with open questions is listed, not built."""
    from datetime import date
    from core.bom_export import io_sheet
    from core.xlsx import workbook
    read = rfq.get(rid)
    built = {p["name"]: build(rid, p["name"]) for p in read["panels"]}
    head = [["RFQ", f"{read.get('project_ref') or ''} — {read['filename']}"], ["SHA-256", read["sha256"]], ["Date", date.today().isoformat()],
            ["Status", "DRAFT — components awaiting sign-off; not for ordering"], ["", ""]]
    summ = head + [["Panel", "Built", "BOM lines", "Incomer", "Design current (A)", "PLC CPU", "In the BOM: DI / DO / AI / AO",
                    "RFQ DI / DO / AI / AO", "I/O basis", "Open points", "Not in this BOM", "Open questions",
                    "RFQ MPCB kept, motor current outside it (tell the client)", "RFQ MPCB: confirm the IE class"]]
    for n, b in built.items():
        if not b["ready"]:
            summ.append([n, "no", "", "", "", "", "", "", "", "", "",
                         "; ".join(b["missing"] or [q["input"] for q in b.get("engine_questions", [])])])
            continue
        e, q = b["io"]["engine"], b["io"]["rfq"]
        summ.append([n, "yes", b["n_bom_lines"], f"{b['incomer']['article'] or 'not selected'}" + (f" ({b['incomer']['in_a']:g} A)" if b["incomer"]["in_a"] else ""),
                     b["incomer"]["ib_a"] or "", b["plc_cpu"] or "", " / ".join(str(e[k]) for k in ("di", "do", "ai", "ao")),
                     " / ".join(f"{q[k]:g}" for k in ("di", "do", "ai", "ao")), b["io_basis"], len(b["open_points"]),
                     len(b["outside"]) + len(b["not_in_bom"]), "", ", ".join(b["rfq_mpcb_flags"]), ", ".join(b["rfq_mpcb_ie_class"])])
    summ += [["", ""], ["Panel", "Section", "BOM lines", "Priced lines", "Indicative (INR, priced lines only)"]]
    for n, b in built.items():
        for s in b.get("sections", []):
            summ.append([n, s["section"], s["n_lines"], s["n_priced"], s["indicative_inr"] or ""])
    summ += [["", ""], ["Basis", ""]] + [["", x] for x in BASIS]
    sheets = [("Summary", summ, [16, 34, 10, 34, 14, 16, 20, 20, 10, 11, 14, 40, 60, 60])]
    allp, gone = {}, [["Panel", "Tag", "Item", "kW", "Qty", "Why not in the BOM"]]
    for n, b in built.items():
        if not b["ready"]:
            continue
        rows = [["Section", "Group", "Article / model", "Description", "Make", "Qty", "Unit", "Used by (RFQ tags)", "Source / basis",
                 "Indicative unit price (INR)"]]
        cur = None
        for x in b["bom"]:
            if x["section"] != cur:
                cur = x["section"]
                rows.append([cur.upper(), "", "", "", "", "", "", "", "", ""])
            rows.append([x["section"], x["group"], x["article"], x["description"], x.get("make") or "", x["qty"], x["unit"],
                         x["used_by"], x["source"], x["unit_price_inr"] if x.get("unit_price_inr") is not None else ""])
            if x["article"] and x["section"] != "Not selected":
                a = allp.setdefault((x["article"], x["description"]), {})
                a[n] = a.get(n, 0) + x["qty"] if isinstance(x["qty"], (int, float)) else x["qty"]
        sheets.append((_sheet(n, "BOM"), rows, [26, 20, 30, 56, 14, 8, 6, 34, 30, 14]))
        sheets.append((_sheet(n, "feeders"), [["Tag", "Item", "Starter", "kW", "Units", "Running", "Status", "Devices", "Motor cable",
                                               "Motor current (A)", "RFQ MPCB"]] +
                       [[f["tag"], f["item"], f["starter"], f["kw"], f["qty"], f["running"], f["status"], f["devices"] or "",
                         f["cable"] or "", f["flc_a"] or "", f["rfq_mpcb"] or ""] for f in b["feeders"]],
                       [14, 40, 8, 7, 7, 8, 9, 60, 40, 10, 12]))
        io_rows = [r for r in b["io_list"] if r.get("dir") in ("input", "output")]
        sheets.append((_sheet(n, "I-O"), io_sheet(io_rows), [9, 30, 6, 14, 70, 9]))
        sheets.append((_sheet(n, "open points"), [["Tag", "Component", "Rule", "Kind", "Open point"]] +
                       [[o["tag"], o["component"], o["rule"], o["kind"], o["point"]] for o in b["open_points"]], [14, 16, 11, 9, 110]))
        gone += [[n, x["tag"], x["item"], x["kw"], x["qty"], x["why"]] for x in b["outside"] + b["not_in_bom"]]
    sheets.append(("Not in a BOM", gone, [10, 16, 44, 7, 6, 80]))
    names = [n for n, b in built.items() if b["ready"]]
    cons = [["Article / model", "Description", *names, "Total"]]
    for (art, desc), q in sorted(allp.items()):
        nums = [q.get(n, "") for n in names]
        tot = sum(x for x in nums if isinstance(x, (int, float)))
        cons.append([art, desc, *nums, tot if all(isinstance(x, (int, float)) or x == "" for x in nums) else ""])
    sheets.append(("All panels", cons, [30, 56, *[10] * len(names), 10]))
    return workbook(sheets), {"panels": len(built), "built": len(names)}
