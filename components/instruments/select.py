"""Field devices: the panel-side needs of instruments, switches and valves. Rules: rules.yaml (R-INS-01 … 06).

Data: the project's field-device table (project.yaml data: field_devices; equipment document);
MCBs through the auxiliary switchgear component (11); fused terminals from the company costing sheet (feeder_kit data).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from components.aux_switchgear.select import select as aux_switchgear
from components.client_items.select import _spec as client_spec
from components.feeder_kit.select import _kits
from core import project as P
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "instruments"
IO_KEYS = {"DI": "di", "DO": "do", "AI 4-20mA": "ai_420", "AI 0-10V": "ai_010", "AO 4-20mA": "ao"}


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _devices(project: str | None = None) -> dict:
    """The project's field-device table (project.yaml data: field_devices)."""
    return load_sourced_table(P.table("field_devices", project), ("panel", "item", "kind", "qty"))


def _kit_item(match: str):
    """A line of the company costing sheet by article or description (first occurrence), with its source."""
    for k in _kits():
        for it in k["items"]:
            if match.upper() in (it["article"] or "").upper() or match.upper() == it["description"].upper():
                return it, f"{k['ref']} sheet '{k['sheet'].strip()}' row {it['row']}"
    return None, None


def _range_count(text: str):
    m = re.search(r"([A-Z]+)(\d+)\s*to\s*([A-Z]*)(\d+)", text, re.I)
    return int(m.group(4)) - int(m.group(2)) + 1 if m else None


def select(panel: str, instrument_230v_a: float | None = None, valve_va: float | None = None,
           pneumatic_24v_a: float | None = None, tower_lamp_24v_a: float | None = None, mcb_make: str = "Siemens",
           project: str | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    try:
        PANELS, equip, auto = P.panels(project), P.doc("equipment", project), P.doc("automation", project)
    except P.ProjectError as e:
        return res.invalid(str(e))
    if panel not in PANELS:
        return res.invalid(f"panel must be one of {', '.join(PANELS)} (got {panel})")
    prm = _rules()["params"]
    rows = [r for r in _devices(project)["rows"] if r["panel"] == panel]
    field = [r for r in rows if r["kind"] != "motor"]
    count = lambda kind: sum(r["qty"] for r in field if r["kind"] == kind)
    src = lambda r: f"{equip} p.{r['page']}"

    # R-INS-01: kinds; devices without a stated supply
    unstated = [r for r in field if r["kind"] == "unstated"]
    res.add("R-INS-01", "field devices read from the client specification",
            f"{len(field)} row(s), {sum(r['qty'] for r in field)} device(s)", PASS, f"{equip} (field-device table)")
    if unstated:
        res.add("R-INS-01", "every field device states its supply",
                "not stated: " + "; ".join(f"{r['tag'] or r['item'][:30]} ({r['qty']})" for r in unstated), WARN,
                ", ".join(sorted({src(r) for r in unstated})))

    # R-INS-02: the specification's own arithmetic
    io = {x["signal"]: x["required"] for x in client_spec(project)["io"] if x["panel"] == panel}
    diffs = []
    for sig, key in IO_KEYS.items():
        got = sum(r[key] for r in rows)
        if sig in io and got != io[sig]:
            diffs.append(f"{sig}: motors + field devices {got} ≠ required {io[sig]}")
    res.add("R-INS-02", "motor + field-device I/O = the client's required I/O",
            "; ".join(diffs) if diffs else "yes, for " + ", ".join(io), WARN if diffs else PASS,
            f"{equip} / {auto} p.1")
    ranges = []
    for r in field:
        n = _range_count(f"{r['tag']} {r['marking']}")
        if n is not None and n != r["qty"]:
            ranges.append(f"{r['tag']}: range gives {n}, quantity {r['qty']}")
    if ranges:
        res.add("R-INS-02", "tag ranges match the quantities", "; ".join(ranges), WARN, src(field[0]))

    # R-INS-03: 24 V DC load
    n_loop, n_pn, n_tl = count("loop_transmitter"), count("pneumatic_panel"), count("tower_lamp")
    loop_a = prm["loop_current_a"]
    load, unknown = n_loop * loop_a, []
    parts = [f"{n_loop} loop transmitter(s) × {loop_a:g} A"]
    dc_rows = [{"item": "loop transmitters (4-20 mA)", "qty": n_loop, "unit_a": loop_a, "total_a": round(n_loop * loop_a, 4),
                "source": "instruments R-INS-03 (rules.yaml loop_current_a)"}] if n_loop else []
    for n, given, what in ((n_pn, pneumatic_24v_a, "pneumatic panel"), (n_tl, tower_lamp_24v_a, "tower lamp")):
        if not n:
            continue
        if given is None:
            unknown.append(f"{n} {what}(s): 24 V current not given")
            dc_rows.append({"item": f"{what}s", "qty": n, "unit_a": None, "total_a": None,
                            "source": "current not given: open point"})
        else:
            load += n * given
            parts.append(f"{n} {what}(s) × {given:g} A")
            dc_rows.append({"item": f"{what}s", "qty": n, "unit_a": given, "total_a": round(n * given, 4),
                            "source": "designer input"})
    res.add("R-INS-03", "24 V DC load of the field devices (switch inputs counted with the PLC inputs)",
            " + ".join(parts) + f" = {load:.3f} A" + (f"; partial: {'; '.join(unknown)}" if unknown else ""),
            WARN if unknown else PASS)

    # R-INS-04: 230 V feeds for instruments and valves
    n_mains, n_valves = count("mains_transmitter"), count("mains_valve")
    lines, value = [], {}
    if n_mains:
        if instrument_230v_a is None:
            res.add("R-INS-04", f"{n_mains} 230 V instrument MCB(s)", "instrument current not given: not selected", WARN)
        else:
            a = aux_switchgear(circuits=[{"name": "230 V instrument", "ib_a": instrument_230v_a, "poles": 2, "curve": "C"}],
                               make=mcb_make)
            if a.value:
                lines.append({"article": a.value["mcb_1"], "description": f"MCB 2P C {a.value['mcb_1_in_a']:g} A, one per 230 V instrument",
                              "qty": n_mains, "source": a.value["devices"][0]["source"]})
                value.update({"instrument_mcb": a.value["mcb_1"], "n_instrument_mcb": n_mains})
            res.add("R-INS-04", f"one 2P C MCB per 230 V instrument ({n_mains}) at {instrument_230v_a:g} A",
                    a.value.get("mcb_1", "none in the database") if a.value else "none in the database",
                    PASS if a.value else WARN)
    if n_valves:
        if valve_va is None:
            res.add("R-INS-04", f"230 V valve circuit ({n_valves} valves)", "valve coil VA not given: not selected", WARN)
        else:
            ib = n_valves * valve_va / 230.0
            a = aux_switchgear(circuits=[{"name": "solenoid valves", "ib_a": ib, "poles": 2, "curve": "C"}], make=mcb_make)
            if a.value:
                lines.append({"article": a.value["mcb_1"], "description": f"MCB 2P C {a.value['mcb_1_in_a']:g} A for {n_valves} solenoid valves",
                              "qty": 1, "source": a.value["devices"][0]["source"]})
                value["valve_mcb"] = a.value["mcb_1"]
            value["valve_current_a"] = round(ib, 4)
            res.add("R-INS-04", f"valve circuit: {n_valves} × {valve_va:g} VA / 230 V = {ib:.3f} A",
                    a.value.get("mcb_1", "none in the database") if a.value else "none in the database",
                    PASS if a.value else WARN)

    # R-INS-05: fused terminal per analog loop (company practice)
    n_ai = sum(r["ai_420"] + r["ai_010"] for r in field)
    ft, ft_src = _kit_item(prm["kit_articles"]["fused_terminal"])
    gf, gf_src = _kit_item(prm["kit_articles"]["glass_fuse"])
    if n_ai and ft:
        lines.append({"article": ft["article"], "description": f"Fused terminal block ({ft['make']}), one per analog loop",
                      "qty": n_ai, "source": ft_src, "unit_price_inr": ft["unit_price_inr"]})
        if gf:
            lines.append({"article": gf["article"] or "Glass fuse", "description": f"Glass fuse for the fused terminals ({gf['make']})",
                          "qty": n_ai, "source": gf_src, "unit_price_inr": gf["unit_price_inr"]})
        res.add("R-INS-05", f"fused terminal per analog loop ({n_ai})", f"{ft['article']} + glass fuse", PASS, ft_src)

    # R-INS-06: surge protection for field signals
    res.add("R-INS-06", "surge protection for 4-20 mA loops and the 24 V DC field supply",
            "not in the held data: not selected", WARN)

    res.value = {"panel": panel, "n_loop_tx": n_loop, "n_mains_tx": n_mains, "n_valves": n_valves, "n_pneumatic": n_pn,
                 "n_tower_lamp": n_tl, "n_dc_switch": count("dc_switch"), "n_unstated": sum(r["qty"] for r in unstated),
                 "n_analog_loops": n_ai, "io_matches": not diffs, "range_mismatches": len(ranges),
                 "dc_load_a": round(load, 4), "dc_load_partial": bool(unknown), "dc_rows": dc_rows, "n_fused_terminals": n_ai if ft else 0,
                 **value, "bom": lines,
                 "devices": [{"tag": r["tag"] or r["item"][:30], "item": r["item"], "kind": r["kind"], "qty": r["qty"],
                              "supply": r["supply"], "source": src(r)} for r in field]}
    res.basis = "client specification + rules"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
