"""Power calculation: AC consumption per phase with single-phase loads balanced over L1 / L2 / L3, and 24 V DC.

Rules: rules.yaml (R-PWR-01 … 09). The loads come from the selections (feeders, control circuit, 24 V supply, PLC …);
this component only adds them up, places the single-phase loads and reports what it could not count.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from core.provenance import load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "power"
PHASES = ("L1", "L2", "L3")
ANGLE = {"L1": 0.0, "L2": -120.0, "L3": 120.0}


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


PROTECTIVE = ("3RV", "3NA", "3NE", "3VA", "3VM", "GZ1E", "GV2", "GV3", "5SY", "5SL")


def protection_for(tag: str, bom: list[dict]) -> str | None:
    """The protective device a BOM gives this load (MPCB, fuse, circuit breaker), as 'article — description'."""
    hits = [b for b in bom if tag in str(b.get("used_by") or "").split(", ") and str(b.get("article") or "").upper().startswith(PROTECTIVE)]
    return "; ".join(f"{b['article']} — {b['description']}" for b in hits[:2]) or None


def select(voltage_v: float | None = None, three_phase: list | None = None, single_phase: list | None = None,
           dc: list | None = None, dc_factor: float | None = None, dc_available_a: float | None = None,
           dc_supply: str | None = None, dc_efficiency: float | None = None, dc_factor_source: str | None = None,
           not_counted: list | None = None, imbalance_limit_pct: float | None = None, main_fos: float | None = None,
           frequency_hz: float | None = None, edits: list | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    u = _num(voltage_v)
    if not u or u <= 0:
        return res.invalid(f"supply voltage (line to line) is required and > 0 (got {voltage_v})")
    u_ln = u / math.sqrt(3)
    limit = imbalance_limit_pct if imbalance_limit_pct is not None else _rules()["params"]["imbalance_limit_pct"]
    phase = {p: 0.0 for p in PHASES}

    # R-PWR-11: the designer's edits (set / add / remove a load), applied before the calculation; every edit must name a load
    edits = [dict(e) if isinstance(e, dict) else e for e in edits or []]   # never change the caller's list
    for e in edits:
        if not isinstance(e, dict) or e.get("action") not in ("set", "add", "remove") or not e.get("key"):
            return res.invalid("each power edit needs an action (set, add or remove) and the key of its load")
        ph = e.get("phase")
        if isinstance(ph, str) and re.search(r"[–-]", ph):
            e["phase"] = ph = re.split(r"\s*[–-]\s*", ph)
        if ph not in (None, "", "auto") and not (ph in PHASES or isinstance(ph, list) and len(ph) == 2 and all(x in PHASES for x in ph)):
            return res.invalid(f"power edit {e['key']}: phase must be L1, L2 or L3 (two of them for a line–line load)")
        if ph in ("", "auto"):
            e["phase"] = None
        # numbers a designer can type: finite, ≥ 0 and within reason (QA 2026-10-16, L2)
        for f_, top in (("i_a", 10000), ("va", 1e6), ("kw", 10000), ("u_v", 1000), ("running", 100)) + \
                ((("qty", 10000), ("per_unit", 100)) if e.get("dc") else ()):
            x = e.get(f_)
            if x is None:
                continue
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 or x > top:
                return res.invalid(f"power edit {e['key']}: {f_} must be a number from 0 to {top:g} (got {x!r})")
            if f_ == "running" and x != int(x):
                return res.invalid(f"power edit {e['key']}: running must be a whole number (got {x!r})")
        if e.get("connection") not in (None, "LN", "LL"):
            return res.invalid(f"power edit {e['key']}: connection must be LN or LL (got {e.get('connection')!r})")
        for f_ in ("key", "name", "description"):
            if e.get(f_) is not None and (not isinstance(e[f_], str) or len(e[f_]) > 120):
                return res.invalid(f"power edit: {f_} must be text of at most 120 characters")
    used, changed, added = set(), [], []

    def apply(items, three):
        out = []
        for it in items:
            k = it.get("key") or it.get("tag") or it.get("name")
            hit = [e for e in edits if e["key"] == k and e["action"] in ("set", "remove") and not e.get("dc")]
            for e in hit:
                used.add(id(e))
                changed.append(f"{e['action']} {k}" + "".join(f", {f} = {e[f]}" for f in ("connection", "phase", "running", "i_a", "va")
                                                               if f in e and e[f] is not None))
            if any(e["action"] == "remove" for e in hit):
                continue
            it = dict(it, key=k)
            for e in hit:
                for f in (("running", "i_a", "kw") if three else ("connection", "phase", "i_a", "va", "u_v", "qty")):
                    if f in e:
                        it[f] = e[f]
                if "va" in e and "i_a" not in e:
                    it.pop("i_a", None)
            out.append(it)
        for e in edits:
            if e["action"] == "add" and not e.get("dc") and bool(e.get("three_phase")) == three:
                used.add(id(e))
                added.append(e.get("name") or e["key"])
                base = {"key": e["key"], "source": "designer edit", "added": True}
                out.append({**base, "tag": e.get("name") or e["key"], "description": e.get("description") or "added by the designer",
                            "running": e.get("running", 1), "i_a": e.get("i_a"), "kw": e.get("kw")} if three else
                           {**base, "name": e.get("name") or e["key"], "description": e.get("description") or "added by the designer",
                            "connection": e.get("connection", "LN"), "phase": e.get("phase"), "i_a": e.get("i_a"), "va": e.get("va"),
                            "u_v": e.get("u_v"), "group": "added", "kind": e.get("name") or e["key"], "kw": e.get("kw")})
        return out

    three_phase = apply([t for t in three_phase or [] if isinstance(t, dict)] if all(isinstance(t, dict) for t in three_phase or [])
                        else three_phase, True)

    # R-PWR-01: 3-phase loads
    tp_rows, kw_rated = [], 0.0
    for i, t in enumerate(three_phase or [], 1):
        if not isinstance(t, dict):
            return res.invalid(f"3-phase load {i} is not a load")
        n, ia = _num(t.get("running", 1)), _num(t.get("i_a"))
        if n is None or n < 0 or ia is None or ia < 0:
            return res.invalid(f"3-phase load {t.get('tag', i)}: running units and current must be numbers ≥ 0")
        for p in PHASES:
            phase[p] += n * ia
        kw = _num(t.get("kw"))
        kw_rated += (kw or 0) * n
        tp_rows.append({"tag": t.get("tag", f"#{i}"), "description": t.get("description", ""), "running": n, "i_a": ia,
                        "total_a": round(n * ia, 3), "kw": kw, "s_kva": round(math.sqrt(3) * u * n * ia / 1000, 3),
                        "source": t.get("source", ""), "protection": t.get("protection"), "accessory": t.get("accessory"),
                        "key": t.get("key") or t.get("tag"), "added": bool(t.get("added")),
                        "min_v": t.get("min_v"), "max_v": t.get("max_v")})
    if tp_rows:
        res.add("R-PWR-01", "3-phase loads: running units × current per phase (standby not counted)",
                " + ".join(f"{r['running']:g} × {r['i_a']:g} A ({r['tag']})" for r in tp_rows) + f" = {phase['L1']:g} A per phase", PASS)

    # R-PWR-07 / 08: 24 V DC, and the supply's AC input as a single-phase load
    sp = [dict(s) for s in (single_phase or []) if isinstance(s, dict)]
    if len(sp) != len(single_phase or []):
        return res.invalid("every single-phase load must be a load")
    dc_out, dchg, dadd = None, [], []
    if dc is not None:
        # R-PWR-12: the designer's edits to the 24 V rows (by key), before the sum
        dc = [dict(d) for d in dc if isinstance(d, dict)]
        for e in edits:
            if not e.get("dc"):
                continue
            if e["action"] == "add":
                used.add(id(e))
                dc.append({"key": e["key"], "item": e.get("name") or e.get("item") or e["key"], "qty": e.get("qty", 1),
                           "per_unit": e.get("per_unit"), "source": "designer edit", "added": True})
                dadd.append(e.get("item") or e.get("name") or e["key"])
                continue
            hit_ = next((d for d in dc if (d.get("key") or d.get("item")) == e["key"]), None)
            if hit_ is None:
                continue          # reported below as naming no load
            used.add(id(e))
            if e["action"] == "remove":
                dc.remove(hit_)
                dchg.append(f"remove {e['key']}")
            else:
                for f_ in ("qty", "per_unit"):
                    if e.get(f_) is not None:
                        hit_[f_] = e[f_]
                hit_.pop("total", None)
                hit_["edited"] = True
                dchg.append(f"set {e['key']}" + "".join(f", {f_} = {e[f_]}" for f_ in ("qty", "per_unit") if e.get(f_) is not None))
        if dchg:
            res.add("R-PWR-12", "designer edits to the 24 V DC rows", "; ".join(dchg), WARN, "designer edit")
        if dadd:
            res.add("R-PWR-12", "24 V DC rows added by the designer", ", ".join(map(str, dadd)), INFO, "designer edit")
        rows, partial = [], False
        for d in dc:
            q, pu = _num(d.get("qty", 1)), _num(d.get("per_unit"))
            total = _num(d.get("total"))
            if total is None and q is not None and pu is not None:
                total = q * pu
            if total is None:
                partial = True
            elif total < 0:
                return res.invalid(f"24 V load {d.get('item')}: negative current")
            rows.append({"item": d.get("item", ""), "qty": q, "per_unit": pu, "total": None if total is None else round(total, 4),
                         "source": d.get("source", ""), "key": d.get("key") or d.get("item", ""), "added": bool(d.get("added")),
                         "edited": bool(d.get("edited"))})
        load = round(sum(r["total"] for r in rows if r["total"] is not None), 4)
        fac = _num(dc_factor) or 1.0
        req = round(load * fac, 4)
        dc_out = {"rows": rows, "load_a": load, "factor": fac, "factor_source": dc_factor_source or "company template",
                  "required_a": req, "available_a": _num(dc_available_a), "supply": dc_supply, "partial": partial}
        res.add("R-PWR-08", f"24 V DC: Σ load × {fac:g}" + (" (partial: a line has no value)" if partial else ""),
                f"{load:g} A × {fac:g} = {req:g} A" + (f" vs {dc_available_a:g} A ({dc_supply or 'supply'})" if dc_available_a is not None else ""),
                WARN if partial or (dc_available_a is not None and req > dc_available_a) else PASS, dc_out["factor_source"])
        eff = _num(dc_efficiency)
        if eff and 0 < eff <= 1 and load:
            p_in = 24.0 * load / eff
            dc_out["input_w"] = round(p_in, 2)
            sp.append({"name": f"24 V DC supply input ({dc_supply or 'supply'}, η {eff:g})", "i_a": p_in / u_ln, "connection": "LN",
                       "source": "R-PWR-07 (24 V × load / efficiency)", "group": "supply", "kind": "SMPS", "key": "smps", "kw": round(p_in / 1000, 4),
                       "protection": None})
            res.add("R-PWR-07", "24 V supply AC input = 24 V × load / efficiency, at power factor 1 (not held: lower bound)",
                    f"24 × {load:g} / {eff:g} = {p_in:.1f} W → {p_in / u_ln:.3f} A", WARN)

    sp = apply(sp, False)
    lost = [e["key"] for e in edits if id(e) not in used]
    if lost:
        return res.invalid(f"power edit(s) name no load in this calculation: {', '.join(map(str, lost))}")
    if changed:
        res.add("R-PWR-11", "designer edits to calculated loads (listed; the calculation no longer follows the selection alone)",
                "; ".join(changed), WARN, "designer edit")
    if added:
        res.add("R-PWR-11", "loads added by the designer", ", ".join(added), INFO, "designer edit")

    # R-PWR-02 / 03: single-phase loads, largest first, to the least-loaded phase(s)
    items = []
    for i, s in enumerate(sp, 1):
        conn = s.get("connection", "LN")
        if conn not in ("LN", "LL"):
            return res.invalid(f"single-phase load {s.get('name', i)}: connection must be LN (line–neutral) or LL (line–line)")
        n = _num(s.get("qty", 1))
        if n is None or n < 0:
            return res.invalid(f"single-phase load {s.get('name', i)}: quantity must be ≥ 0")
        ia = _num(s.get("i_a"))
        if ia is None:
            va = _num(s.get("va"))
            if va is None:
                return res.invalid(f"single-phase load {s.get('name', i)}: give its VA or its current")
            uv = _num(s.get("u_v")) or (u if conn == "LL" else u_ln)
            ia = va / uv
        if ia < 0:
            return res.invalid(f"single-phase load {s.get('name', i)}: negative load")
        fixed = s.get("phase")
        if fixed is not None and (conn == "LN" and fixed not in PHASES or conn == "LL" and (not isinstance(fixed, (list, tuple)) or len(fixed) != 2)):
            return res.invalid(f"single-phase load {s.get('name', i)}: phase must be L1, L2 or L3 (LL: two phases)")
        uv = _num(s.get("u_v")) or (u if conn == "LL" else u_ln)
        # S: the load's own VA when given, else its voltage × current (QA 2026-10-16, L7: not U_LN × I when u_v is given)
        given_va = _num(s.get("va")) if _num(s.get("i_a")) is None else None
        items.append({**s, "connection": conn, "i_a": ia * n, "s_va": (given_va if given_va is not None else uv * ia) * n})
    ln = {p: 0.0 for p in PHASES}
    placed = []
    for s in sorted(items, key=lambda x: (x.get("phase") is None, -x["i_a"])):
        if s["connection"] == "LN":
            p = s.get("phase") or min(PHASES, key=lambda q: (phase[q], PHASES.index(q)))
            phase[p] += s["i_a"]
            ln[p] += s["i_a"]
            on = [p]
        else:
            on = list(s.get("phase") or sorted(PHASES, key=lambda q: (phase[q], PHASES.index(q)))[:2])
            for p in on:
                phase[p] += s["i_a"]
        placed.append({"name": s.get("name", ""), "key": s.get("key"), "added": bool(s.get("added")), "connection": s["connection"], "i_a": round(s["i_a"], 4),
                       "phases": "–".join(sorted(on)), "fixed": s.get("phase") is not None, "source": s.get("source", ""),
                       "on": on, "group": s.get("group", "other"), "kind": s.get("kind"), "kw": s.get("kw"),
                       "protection": s.get("protection"), "accessory": s.get("accessory"), "description": s.get("description", ""),
                       "min_v": s.get("min_v"), "max_v": s.get("max_v")})
    if items:
        res.add("R-PWR-02", "single-phase loads: I = VA / U_LN (line–neutral) or VA / U_LL (line–line, on both lines)",
                "; ".join(f"{x['name']} {x['i_a']:.3f} A on {x['phases']}" for x in placed), PASS)
        res.add("R-PWR-03", "balanced largest first onto the least-loaded phase (decision PWR-2)",
                ", ".join(f"{x['name']} → {x['phases']}" for x in placed), INFO)

    # R-PWR-04 / 05 / 06: imbalance, neutral, apparent power
    vals = [phase[p] for p in PHASES]
    mean = sum(vals) / 3
    imb = round((max(vals) - mean) / mean * 100, 2) if mean else 0.0
    over = limit is not None and imb > limit
    res.add("R-PWR-04", "phase imbalance (largest − mean) / mean" + (f" ≤ {limit:g} % (owner limit)" if limit is not None else " (no limit held: information)"),
            " / ".join(f"{p} {phase[p]:.2f} A" for p in PHASES) + f" → {imb:g} %", WARN if over else INFO)
    nx = sum(ln[p] * math.cos(math.radians(ANGLE[p])) for p in PHASES)
    ny = sum(ln[p] * math.sin(math.radians(ANGLE[p])) for p in PHASES)
    neutral = math.hypot(nx, ny)
    res.add("R-PWR-05", "neutral current: phasor sum of the line–neutral loads (same power factor assumed)", f"{neutral:.2f} A", INFO)
    # S per load: 3-phase √3·U·I, line–neutral U_LN·I, line–line U_LL·I (one current through two lines: not U_LN × 2I)
    s_kva = (sum(r["s_kva"] for r in tp_rows) * 1000 + sum(x["s_va"] for x in items)) / 1000
    res.add("R-PWR-06", "apparent power S = Σ loads (3-phase √3·U·I, line–neutral U_LN·I, line–line U_LL·I); motor kW = rated output only",
            f"{s_kva:.2f} kVA; rated motor output {kw_rated:g} kW (running)", INFO)
    if not_counted:
        res.add("R-PWR-09", "not counted (no consumption data held)", ", ".join(map(str, not_counted)), INFO)

    # R-PWR-10: the company template's layout — one row per AC load with its current on L1 / L2 / L3
    def trow(load, desc, ph, kw, i, prot, acc, on, src, mn, mx, key, conn, added, fixed=False):
        return {"load": load, "description": desc, "phase": ph, "min_v": mn, "max_v": mx, "kw": kw, "current_a": round(i, 4),
                "protection": prot, "accessory": acc, "source": src, "key": key, "connection": conn, "lines": "–".join(on),
                "added": added, "fixed": fixed, **{p.lower(): (round(i, 4) if p in on else None) for p in PHASES}}
    srow = lambda x: trow(x["kind"] or x["name"], x["description"] or x["name"], 1, x["kw"], x["i_a"], x["protection"], x["accessory"],
                          sorted(x["on"]), x["source"], x["min_v"], x["max_v"], x["key"] or x["name"], x["connection"], x["added"], x["fixed"])
    ac_rows = [srow(x) for x in placed if x["group"] == "supply"]
    ac_rows += [trow(r["tag"], r["description"], 3, r["kw"] * r["running"] if r["kw"] else None, r["total_a"], r["protection"], r["accessory"],
                     PHASES, r["source"], r["min_v"], r["max_v"], r["key"], "3P", r["added"]) for r in tp_rows]
    ac_rows += [srow(x) for x in placed if x["group"] != "supply"]
    fos = _num(main_fos)
    main_load = round(max(vals) * fos, 3) if fos else None
    if fos:
        res.add("R-PWR-10", "company template: load current with FOS = largest phase × factor (main switchgear basis)",
                f"{max(vals):.2f} A × {fos:g} = {main_load:g} A; input power √3 × {u:g} V × {max(vals):.2f} A × {fos:g} = "
                f"{math.sqrt(3) * u * max(vals) * fos / 1000:.2f} kVA", INFO, "OWN-SWG-CALC 'U1_Main_Switchgear' L27")
    res.value = {"voltage_v": u, "frequency_hz": _num(frequency_hz), "ac_rows": ac_rows, "edits_applied": changed + [f"add {x}" for x in added] + [f"24 V: {x}" for x in dchg] + [f"24 V: add {x}" for x in dadd], "main_fos": fos, "main_load_a": main_load,
                 "input_kva_fos": round(math.sqrt(3) * u * max(vals) * fos / 1000, 3) if fos else None, "u_ln_v": round(u_ln, 2), "i_l1_a": round(phase["L1"], 4), "i_l2_a": round(phase["L2"], 4),
                 "i_l3_a": round(phase["L3"], 4), "imbalance_pct": imb, "imbalance_limit_pct": limit, "neutral_a": round(neutral, 4),
                 "s_kva": round(s_kva, 3), "kw_rated": round(kw_rated, 3), "three_phase": tp_rows, "single_phase": placed,
                 "dc": dc_out, "not_counted": list(not_counted or [])}
    if dc_out:
        res.value.update({"dc_load_a": dc_out["load_a"], "dc_required_a": dc_out["required_a"],
                          "dc_available_a": dc_out["available_a"], "dc_input_w": dc_out.get("input_w")})
    res.basis = "calculated"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
