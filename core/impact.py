"""Impact of one change, before it is made (owner 2026-10-16): the design is run with and without the change and the
results are compared — BOM lines, the main devices, I/O counts, power figures, warnings. Nothing is saved here.

The comparison reports only what the engine actually changes; a change that stays local (a BOM line replaced on its own,
a project list edited) shows that too, so the designer sees exactly what follows and what does not.
"""
from __future__ import annotations

DEVICES = [("incomer", "Incomer"), ("smps", "24 V supply"), ("plc_cpu", "PLC CPU"), ("ct", "Meter CTs"),
           ("transformer_va", "Control transformer VA")]
COUNTS = [("io_di", "Digital inputs"), ("io_do", "Digital outputs"), ("io_ai", "Analog inputs"), ("io_ao", "Analog outputs"),
          ("io_pn", "Drives on the fieldbus"), ("io_safety", "STO signals"), ("qty_relays", "Interface relays"),
          ("qty_io_terminals", "I/O terminals")]
POWER = [("i_l1_a", "L1 current", "A"), ("i_l2_a", "L2 current", "A"), ("i_l3_a", "L3 current", "A"),
         ("imbalance_pct", "Phase imbalance", "%"), ("s_kva", "Apparent power", "kVA"), ("main_load_a", "Load × factor", "A"),
         ("dc_load_a", "24 V load", "A"), ("dc_required_a", "24 V needed (× factor)", "A")]


def _bom(lines: list[dict]) -> dict:
    out = {}
    for l in lines or []:
        if l.get("group") in ("Not selected", "Out of scope") or not l.get("article"):
            continue
        k = (l["group"], str(l["article"]))
        q = l.get("qty")
        out[k] = {"qty": q if isinstance(q, (int, float)) else None, "description": l.get("description", ""),
                  "price": l.get("unit_price_inr")}
    return out


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compare(before: dict, after: dict, power_key: str = "power") -> dict:
    """{bom: [...], devices: [...], counts: [...], power: [...], warnings: {...}, cost_delta_inr, unpriced, n}."""
    b, a = _bom(before.get("bom")), _bom(after.get("bom"))
    bom = []
    for k in sorted(set(b) | set(a)):
        x, y = b.get(k), a.get(k)
        # a line whose quantity is text ('not calculated') counts as present; a quantity 0 as gone (removed by an edit)
        here = lambda l: l is not None and (l["qty"] is None or l["qty"] > 0)
        if here(x) and here(y) and x["qty"] == y["qty"]:
            continue
        if not here(x) and not here(y):
            continue
        qx, qy = ((x or {}).get("qty") if here(x) else 0), ((y or {}).get("qty") if here(y) else 0)
        kind = "added" if not here(x) else "removed" if not here(y) else "quantity"
        bom.append({"group": k[0], "article": k[1], "description": (y or x)["description"], "from": qx, "to": qy, "kind": kind,
                    "price": (y or x).get("price")})
    cost = sum(c["price"] * ((c["to"] or 0) - (c["from"] or 0)) for c in bom
               if c["price"] is not None and isinstance(c["to"] or 0, (int, float)) and isinstance(c["from"] or 0, (int, float)))
    unpriced = sum(1 for c in bom if c["price"] is None)
    devices = [{"what": label, "from": before.get(k), "to": after.get(k)} for k, label in DEVICES if before.get(k) != after.get(k)]
    counts = [{"what": label, "from": before.get(k), "to": after.get(k)} for k, label in COUNTS
              if before.get(k) is not None and after.get(k) is not None and before.get(k) != after.get(k)]
    pb, pa = before.get(power_key) or {}, after.get(power_key) or {}
    power = []
    for k, label, unit in POWER:
        x, y = _num(pb.get(k)), _num(pa.get(k))
        if x is None and y is None:
            continue
        if x is None or y is None or abs(x - y) > 1e-6:
            power.append({"what": label, "from": x, "to": y, "unit": unit})
    wb = {(o.get("tag"), o.get("rule"), o.get("point")) for o in before.get("open_points") or []}
    wa = {(o.get("tag"), o.get("rule"), o.get("point")) for o in after.get("open_points") or []}
    warn = {"new": [f"{t or ''} {r}: {p}".strip() for t, r, p in sorted(wa - wb, key=str)][:12],
            "cleared": [f"{t or ''} {r}: {p}".strip() for t, r, p in sorted(wb - wa, key=str)][:12]}
    gone = sorted({f["tag"] for f in before.get("feeders") or [] if f.get("status") == "selected"}
                  - {f["tag"] for f in after.get("feeders") or [] if f.get("status") == "selected"})
    n = len(bom) + len(devices) + len(counts) + len(power) + len(warn["new"]) + len(warn["cleared"]) + len(gone)
    return {"bom": bom, "devices": devices, "counts": counts, "power": power, "warnings": warn, "feeders_lost": gone,
            "cost_delta_inr": round(cost, 2), "unpriced_changes": unpriced, "n": n}


def machine(base: dict, change: dict | None = None, after: dict | None = None) -> dict:
    """Impact of a change on a new machine: base = the requirement inputs; either change = the inputs to merge (edits
    lists are appended, answers replaced, None removes an answer) or after = the complete inputs after the change."""
    from components.requirement.select import select as requirement
    before = requirement(**{**base, "confirmed": True})
    after_in = dict(after) if after is not None else dict(base)
    for k, v in (change or {}).items() if after is None else ():
        if k in ("edits", "power_edits", "io_edits"):
            after_in[k] = list(base.get(k) or []) + list(v or [])
        elif v is None:
            after_in.pop(k, None)
        else:
            after_in[k] = v
    after = requirement(**{**after_in, "confirmed": True})
    if before.status == "invalid" or not (before.value or {}).get("selected"):
        raise ValueError("confirm the machine first: the impact is worked out on a selected design")
    if after.status == "invalid":
        return {"refused": next((c.value for c in after.checks if c.verdict == "fail"), "not accepted"), "n": 0}
    return compare(before.value, after.value)


def project(project_name: str, panel: str, inputs: dict, change: dict) -> dict:
    """Impact of one project change (edits / power_edits / io_edits / standby / incomer_factor / min_power_wire_mm2)."""
    from components.project.select import select as project_select
    before = project_select(panel=panel, project=project_name, **inputs)
    after = project_select(panel=panel, project=project_name, **{**inputs, **change})
    if before.status == "invalid":
        raise ValueError(next((c.value for c in before.checks if c.verdict == "fail"), "project not selectable"))
    if after.status == "invalid":
        return {"refused": next((c.value for c in after.checks if c.verdict == "fail"), "not accepted"), "n": 0}
    bv, av = dict(before.value), dict(after.value)
    for v in (bv, av):       # the project keeps its power calculation under power_calc.ac3 and its errors apart
        v["power"] = (v.get("power_calc") or {}).get("ac3") or {}
    out = compare(bv, av)
    for k in ("ac3_error",):
        err = ((after.value.get("power_calc") or {}).get(k))
        if err:
            out["refused"] = err
    if after.value.get("io_error"):
        out["refused"] = after.value["io_error"]
    return out
