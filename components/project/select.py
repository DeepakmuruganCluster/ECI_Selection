"""Project BOM for one panel of a client project: every built component chained, with options for open decisions.
Rules: rules.yaml (R-PRJ-01 … 14). Holds no data of its own; project settings come from projects/<project>/project.yaml.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from components.aux_switchgear.select import select as aux_switchgear
from core.makes import fill as fill_makes
from components.power.select import protection_for, select as power_select
from components.client_items.select import _spec as client_spec
from components.client_items.select import select as client_items
from components.control_circuit.select import select as control_circuit
from components.control_power.select import _coil, _method
from components.instruments.select import select as instruments
from components.control_signalling.select import select as control_signalling
from components.internal_wiring.select import select as internal_wiring
from components.io_list.select import select as io_list
from components.load_list.select import select as load_list
from components.metering.select import select as metering
from components.panel.select import NOT_BUILT_BY, coil_loads, select as panel_select
from components.plc.select import select as plc_select
from core import bom_edit
from core import project as P
from core.provenance import load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "project"
OUT_OF_SCOPE = {"panel_layout", "enclosure", "enclosure_accessories"}

# every open decision: id → (question, [(value, label), …]); the first value is the main BOM's choice
DECISIONS = OrderedDict([
    ("cu_safety", ("Drive control unit: STO needed? (VFD decision V-6)",
                   [("sto", "STO → CU240E-2 PN"), ("none", "no STO → CU230P-2 PN")])),
    ("relays", ("Client 'latch relay' on DOL outputs (control decision C-1)",
                [("latching", "Finder 13.12 set/reset latching relay (2 PLC outputs per DOL)"),
                 ("slim", "slim relay on every output (1 PLC output per DOL, matches the client's DO count)")])),
    ("vfd_protection", ("Drive protection (VFD decision V-2)",
                        [("fuse", "Siemens 3NA fuse"), ("msp", "motor starter protector 3RV"),
                         ("breaker", "circuit breaker 3VA / 3RV27")])),
    ("cable_make", ("Motor cable make", [("polycab", "Polycab"), ("kei", "KEI")])),
    ("ct_make", ("Metering CT make", [("rishabh", "Rishabh"), ("selec", "Selec")])),
    ("wire_insulation", ("Internal wiring (wiring decision W-2)",
                         [("70", "H07V-K, 70 °C"), ("heat_90", "H07V2-K, heat-resistant 90 °C")])),
    ("terminals_per_channel", ("I/O terminals per channel", [(1, "one per channel"), (2, "two per channel")])),
    ("mc_copy_parameters", ("Drive memory card", [(True, "one per drive (copy parameters)"), (False, "none")])),
    ("control_supply", ("Control supply (decision CC-1)", [("transformer", "control transformer (company practice)"),
                                                           ("phase_neutral", "phase-neutral, no transformer")])),
])


@lru_cache(maxsize=None)
def _method_fos() -> float:
    from components.control_power.select import _method
    return _method()["main_fos"]["value"]


def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _relay_ref() -> str:
    """The registered document behind the interface relay coil current (control_power params relay_coil_ref)."""
    from components.control_power.select import ROOT as CP_ROOT, _rules as cp_rules
    return load_yaml(CP_ROOT / cp_rules()["params"]["relay_coil_ref"]["file"])["source"]["ref"]


def _client_value(panel: str, item: str, key: str = "model", project: str | None = None):
    return next((r[key] for r in client_spec(project)["rows"] if r["panel"] == panel and r["item"] == item), None)


def select(panel: str, fault_ka: float | None = None, panel_internal_c: float | None = None,
           motor_pf: float | None = None, cable_ambient_c: float | None = None, default_cable_m: float | None = None,
           cu_safety: str | None = None, relays: str | None = None, vfd_protection: str | None = None,
           cable_make: str | None = None, ct_make: str | None = None, wire_insulation: str | None = None,
           power_edits: list | None = None, standby: dict | None = None,
           incomer_factor: float | None = None, min_power_wire_mm2: float | None = None, io_edits: list | None = None,
           terminals_per_channel: int | None = None, mc_copy_parameters: bool | None = None,
           line_reactor_up_to_kw: float | None = 15, control_supply: str | None = None,
           coil_va: float | None = None, lamp_va: float | None = None, instrument_230v_a: float | None = None,
           valve_va: float | None = None, pneumatic_24v_a: float | None = None, tower_lamp_24v_a: float | None = None,
           project: str | None = None, edits: list | None = None, voltage_v: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    try:
        project = P.resolve(project)
        PANELS, client = P.panels(project), P.client(project)
        reqs = P.setting("requirements", project, {}) or {}
        io_src = (reqs.get("io_table") or {}).get("source", P.doc("automation", project))
        dc_src = (reqs.get("supplies_24v") or {}).get("source", P.doc("automation", project))
    except P.ProjectError as e:
        return res.invalid(str(e))
    if panel not in PANELS:
        return res.invalid(f"panel must be one of {', '.join(PANELS)} (got {panel})")
    saved_ = bom_edit.load_settings(project, panel)        # the designer's saved panel settings, unless given here
    incomer_factor = incomer_factor if incomer_factor is not None else saved_.get("incomer_factor")
    min_power_wire_mm2 = min_power_wire_mm2 if min_power_wire_mm2 is not None else saved_.get("min_power_wire_mm2")
    if incomer_factor is not None and not 1 <= incomer_factor <= 3:
        return res.invalid(f"incomer_factor must be from 1 to 3 (got {incomer_factor:g})")
    if min_power_wire_mm2 is not None and min_power_wire_mm2 not in (0.5, 0.75, 1.0, 1.5, 2.5):
        return res.invalid(f"min_power_wire_mm2 must be one of 0.5, 0.75, 1, 1.5, 2.5 (got {min_power_wire_mm2:g})")
    if voltage_v is None:                    # audit 2026-10-17: the project's stated supply, never a silent 400 V
        voltage_v = (P.setting("design_inputs", project, {}) or {}).get("voltage_v")
    # audit 2026-10-17 (owner: "ask each one"): every design input and option comes from this call or the panel's saved
    # settings (answered on the project page) — never a first option or an unsourced project value
    given = dict(inputs)
    fault_ka = fault_ka if fault_ka is not None else saved_.get("fault_ka")
    panel_internal_c = panel_internal_c if panel_internal_c is not None else saved_.get("panel_internal_c")
    motor_pf = motor_pf if motor_pf is not None else saved_.get("motor_pf")
    cable_ambient_c = cable_ambient_c if cable_ambient_c is not None else saved_.get("cable_ambient_c")
    default_cable_m = default_cable_m if default_cable_m is not None else saved_.get("default_cable_m")
    opt = {k: (given[k] if given.get(k) is not None else saved_.get(k)) for k in DECISIONS}
    asks = [("fault_ka", "Fault level at the panel (kA)", None), ("panel_internal_c", "Temperature inside the panel (°C)", None),
            ("motor_pf", "Motor power factor (for the cable voltage drop)", None),
            ("cable_ambient_c", "Cable route temperature (°C)", None),
            ("default_cable_m", "Motor cable length where the load list gives none (m)", None)]
    vals = {"fault_ka": fault_ka, "panel_internal_c": panel_internal_c, "motor_pf": motor_pf, "cable_ambient_c": cable_ambient_c,
            "default_cable_m": default_cable_m}
    questions = [{"input": k, "question": q, "kind": "number"} for k, q, _ in asks if vals[k] is None] + \
                [{"input": k, "question": DECISIONS[k][0], "kind": "choice", "options": [[str(v), l] for v, l in DECISIONS[k][1]]}
                 for k in DECISIONS if opt[k] is None]
    if voltage_v is None:
        return res.invalid("voltage_v is required (state it in the project's design_inputs with its source)")
    if questions:
        res.add("R-PRJ-20", "every design input and option of this panel answered (asked, never a default)",
                "to answer: " + ", ".join(q["input"] for q in questions), WARN)
        res.value = {"panel": panel, "selected": False, "questions": questions, "n_questions": len(questions),
                     "settings": saved_, "bom": [], "feeders": [], "open_points": [], "options": opt}
        return res
    res.add("R-PRJ-07", "options used for this BOM (answered)", "; ".join(f"{k} = {v}" for k, v in opt.items()), INFO)

    lines, opens = [], []

    def carry(r, tag):
        for c in r.checks:
            if c.verdict in ("warn", "fail"):
                opens.append({"tag": tag, "component": r.component, "rule": c.rule,
                              "kind": "warning" if c.verdict == "warn" else "refused",
                              "point": f"{c.requirement}: {c.value}"})

    def add(group, article, desc, qty, unit, status, source, used_by="", make=None):
        lines.append({"group": group, "article": article or "", "description": desc, "qty": qty, "unit": unit,
                      "status": status, "source": source, "used_by": used_by, "make": make})

    # 1. load list (14)
    standby_ = {**bom_edit.load_standby(project, panel), **(standby or {})}   # saved reading, then this call's
    ll = load_list(project=project, panel=panel, default_cable_m=default_cable_m, standby=standby_ or None)
    if ll.status == "invalid":
        return res.invalid("load list: " + next(c.value for c in ll.checks if c.verdict == "fail"))
    carry(ll, "load list")
    res.add("R-PRJ-01", f"load list from {client}'s file", f"{ll.value['n_rows']} rows", PASS, P.doc("load_list", project))

    # 2. feeders (12)
    p = panel_select(load_list=ll.value["load_list"], fault_ka=fault_ka, panel_internal_c=panel_internal_c, voltage_v=voltage_v,
                     motor_pf=motor_pf, cable_ambient_c=cable_ambient_c, cable_make=opt["cable_make"],
                     vfd_protection=opt["vfd_protection"], line_reactor_up_to_kw=line_reactor_up_to_kw,
                     cu_encoder=False, cu_safety=opt["cu_safety"], cu_fieldbus="profinet",
                     mc_copy_parameters=opt["mc_copy_parameters"])
    for o in p.value["open_points"]:
        opens.append(o)
    for b in p.value["bom"]:
        cable = "cable" in b["description"]
        add("Motor cables" if cable else "Feeders", b["article"], b["description"], b["qty"], "m" if cable else "no",
            "engineered — awaiting sign-off", "panel assembly (1, 2, 4, 5, 6)", ", ".join(b["used_by"]), make=b.get("make"))
    res.add("R-PRJ-02", "feeders from the panel assembly",
            f"{p.value['n_selected']} of {p.value['n_lines']} lines selected, {p.value['n_excluded']} excluded", PASS)

    # 3. client-specified items (13), out-of-scope items left out
    plant_panel = P.setting("plant_items_panel", project)
    carry_plant = plant_panel in (None, panel)
    c = client_items(panel=panel, project=project, include_plant=carry_plant)
    carry(c, "client spec")
    plc_client, coverage, n_plant, n_oos = [], [], 0, 0
    if not carry_plant:
        add("Client spec (plant)", "", f"Plant items (UPS, SCADA, network, tower lamps …): in the {plant_panel} BOM", "",
            "", "carried once (R-PRJ-16)", f"project.yaml plant_items_panel")
    for it in c.value["items"]:
        n_plant += it["panel"] == "plant"
        if it.get("verify_by") in OUT_OF_SCOPE:
            n_oos += 1
            add("Out of scope", it["model"] or "", f"{it['item']} — {it['make'] or ''}".strip(" —"),
                it["qty"] if it["qty"] is not None else "not stated", it["unit"],
                "out of scope — owner instruction 2026-10-11", it["source"], make=it.get("make"))
            coverage.append({"kind": "client item", "panel": it["panel"], "item": it["item"], "status": "out of scope",
                             "where": "owner instruction 2026-10-11", "source": it["source"]})
            continue
        coverage.append({"kind": "client item", "panel": it["panel"], "item": it["item"],
                         "status": "selected by the PLC component" if it.get("verify_by") == "plc" else "in the BOM",
                         "where": "PLC lines (R-PRJ-14)" if it.get("verify_by") == "plc" else it["status"],
                         "source": it["source"]})
        if it.get("verify_by") == "plc":
            plc_client.append(it)   # R-PRJ-14: compared with and replaced by the PLC selection
            continue
        if it.get("verify_by") == "aux_switchgear" and "3-phase" in (it["model"] or ""):
            # R-PRJ-10: the client's Phoenix 3-phase surge arrester resolved from the own database (component 11)
            a = aux_switchgear(spd="3Ph+N+PE", spd_make="Phoenix", fault_ka=fault_ka)
            carry(a, f"client spec {it['panel']}")
            if a.status not in ("cannot_select", "invalid"):
                res.add("R-PRJ-10", f"{it['panel']}: client surge arrester (Phoenix, 3-phase)", a.value["spd"], PASS,
                        a.value["devices"][0]["source"])
                add(f"Client spec ({it['panel']})", a.value["spd"], f"{it['item']} — Phoenix Contact (article from the "
                    "own database)", it["qty"], it["unit"], "client-specified, article from aux_switchgear (11)",
                    f"{it['source']}; {a.value['devices'][0]['source']}", make="Phoenix Contact")
                continue
        add(f"Client spec ({it['panel']})", it["model"] or "", f"{it['item']} — {it['make'] or ''}".strip(" —"),
            it["qty"] if it["qty"] is not None else "not stated", it["unit"], it["status"], it["source"], make=it.get("make"))

    # 4. metering (15) on the client's incomer and busbar
    incomer = _client_value(panel, "Main incomer", project=project) or ""
    circuit_a = float(incomer.split(" A")[0].split()[-1]) if " A" in incomer else None
    bus = _client_value(panel, "Busbar", project=project) or ""
    try:
        bw, bt = (float(x) for x in bus.replace("Copper", "").replace("mm", "").split("×"))
    except ValueError:
        bw = bt = None
    m = metering(circuit_a=circuit_a, ct_make=opt["ct_make"], busbar_w_mm=bw, busbar_t_mm=bt, communication=(reqs.get("meter_communication") or {}).get("value"), client_requirements=reqs,
                 ambient_c=panel_internal_c) if circuit_a else None
    if m is None or m.status in ("cannot_select", "invalid"):
        if m:
            carry(m, "metering")
        res.add("R-PRJ-03", "energy meter and CTs", "not selected", WARN)
    else:
        carry(m, "metering")
        v = m.value
        add("Metering", v["meter_article_pattern"], f"{v['meter']} energy meter (complete the article no.)", 1, "no",
            "engineered — awaiting sign-off", "metering (15)")
        add("Metering", v["comm_module"], "PROFINET module for the meter", 1, "no", "engineered — awaiting sign-off",
            "metering (15)")
        add("Metering", v["ct_designation"], f"Current transformer {v['ct_ratio']}", v["ct_qty"], "no",
            "engineered — awaiting sign-off", "metering (15)",
            make={"rishabh": "Rishabh Instruments", "selec": "Selec Controls"}.get(opt["ct_make"], opt["ct_make"]))
        res.add("R-PRJ-03", "energy meter and CTs on the client incomer and busbar",
                f"{circuit_a:g} A, busbar {bw:g} × {bt:g} mm → {v['ct_designation']}", PASS, "metering (15)")

    # 5. relays and terminals (16) from the client's I/O table and the load list
    io = {x["signal"]: x["final"] for x in client_spec(project)["io"] if x["panel"] == panel}
    do_count = io.get("DO", 0)
    dol_units = ll.value.get("units_dol", 0)
    if opt["relays"] == "latching":
        dol_out, other = dol_units, max(do_count - dol_units, 0)
        rel = control_signalling(dol_outputs=dol_out, other_outputs=other, relay_make="finder", latch_make="finder", client_requirements=reqs,
                                 panel_internal_c=panel_internal_c, do_available=do_count)
    else:
        rel = control_signalling(dol_outputs=0, other_outputs=do_count, relay_make="finder", client_requirements=reqs,
                                 panel_internal_c=panel_internal_c, do_available=do_count)
    carry(rel, "relays")
    channels = sum(io.values())
    term = control_signalling(io_terminals=channels * int(opt["terminals_per_channel"]), terminal_make="connectwell",
                              io_conductor_mm2=1.5)
    carry(term, "terminals")
    for r_ in (rel, term):
        for b in (r_.value or {}).get("bom", []):
            add("Control and signalling", b["article"], b["item"], b["qty"], "no", "engineered — awaiting sign-off",
                b["source"])
    res.add("R-PRJ-04", f"interface relays from {client}'s DO count and the DOL units",
            f"DO {do_count}, DOL units {dol_units}, relays: {opt['relays']}", PASS)
    res.add("R-PRJ-05", "I/O terminals", f"{channels} channels × {opt['terminals_per_channel']}", PASS)

    # 6. internal power wiring (19) per feeder
    sizes = OrderedDict()
    for f in p.value["feeders"]:
        if f.get("wire_ib_a") is None:
            continue
        w = internal_wiring(ib_a=f["wire_ib_a"], in_a=f["wire_in_a"], ambient_c=panel_internal_c, client_requirements=reqs,
                            insulation=str(opt["wire_insulation"]), circuits=1,
                            min_size_mm2=min_power_wire_mm2 if min_power_wire_mm2 is not None else _rules()["params"].get("min_power_wire_mm2"))
        f["internal_wire"] = w.value.get("wire") if w.value else None
        if w.status in ("cannot_select", "invalid"):
            carry(w, f["tag"])
            continue
        carry(w, f["tag"])
        key = f"{w.value['size_mm2']:g} mm²"
        s = sizes.setdefault(key, {"n": 0, "tags": []})
        s["n"] += f["qty"]
        s["tags"].append(f["tag"])
    for key, s in sizes.items():
        add("Internal wiring", f"Lapp {'H07V2-K' if str(opt['wire_insulation']).startswith('heat') else 'H07V-K'} {key}",
            f"power wiring for {s['n']} feeder unit(s) (metres not calculated)", "not calculated", "m",
            "engineered — awaiting sign-off", "internal wiring (19)", ", ".join(s["tags"]), make="Lapp")
    res.add("R-PRJ-06", "internal power wiring per feeder", ", ".join(f"{k} × {s['n']}" for k, s in sizes.items()), PASS)

    # 7. I/O list (23): motor signals against the client's I/O table
    il = io_list(load_list=ll.value["load_list"], dol_relays=opt["relays"], vfd_sto=opt["cu_safety"] == "sto",
                 di_available=io.get("DI"), do_available=io.get("DO"), ai_available=io.get("AI"),
                 ao_available=io.get("AO"), edits=bom_edit.load_io(project, panel) + list(io_edits or []) or None)
    io_error = None
    if il.status == "invalid":     # an I/O edit that no longer fits (its signal is gone): shown with its undo, list without edits
        io_error = next(c.value for c in il.checks if c.verdict == "fail")
        res.add("R-PRJ-09", "I/O edits", io_error, WARN, "overrides.yaml")
        il = io_list(load_list=ll.value["load_list"], dol_relays=opt["relays"], vfd_sto=opt["cu_safety"] == "sto",
                     di_available=io.get("DI"), do_available=io.get("DO"), ai_available=io.get("AI"), ao_available=io.get("AO"))
    carry(il, "I/O list")
    res.add("R-PRJ-09", "motor I/O list fits the client's I/O table",
            f"DI {il.value['io_di']}, DO {il.value['io_do']}, PROFINET drives {il.value['io_pn']}, "
            f"STO {il.value['io_safety']}", WARN if il.status == "warning" else PASS)
    logic = p.value["design_logic"] + [{"tag": "I/O list", "component": "io_list", "verdict": c.verdict, "rule": c.rule,
                                        "requirement": c.requirement, "value": c.value, "source": c.source}
                                       for c in il.checks]

    # 8. field devices (component 24): panel-side needs of instruments, switches and valves
    ins = instruments(panel=panel, project=project, instrument_230v_a=instrument_230v_a, valve_va=valve_va,
                      pneumatic_24v_a=pneumatic_24v_a, tower_lamp_24v_a=tower_lamp_24v_a)
    carry(ins, "instruments")
    for b in ins.value["bom"]:
        add("Instrument supplies", b["article"], b["description"], b["qty"], "no", "engineered — awaiting sign-off",
            b["source"])
    res.add("R-PRJ-11", "field devices: panel-side needs from the client's instrument list",
            f"{ins.value['n_loop_tx']} loop transmitters, {ins.value['n_mains_tx']} 230 V instruments, "
            f"{ins.value['n_valves']} valves, {ins.value['n_analog_loops']} analog loops; {client} I/O arithmetic "
            f"{'matches' if ins.value['io_matches'] else 'differs'}", PASS if ins.value["io_matches"] else WARN,
            P.doc("equipment", project))
    logic += [{"tag": "instruments", "component": "instruments", "verdict": c.verdict, "rule": c.rule,
               "requirement": c.requirement, "value": c.value, "source": c.source} for c in ins.checks]

    # 9. control circuit (component 25): supply, MCBs, panel operator devices from the client's list
    dev = {r["tag"] for r in ins.value["devices"]}
    ac_coils, dc_coil_w = coil_loads(p.value["feeders"])
    coil_args = {"coils": dol_units, "coil_va": coil_va} if coil_va is not None else {"coil_power": ac_coils}
    cc = control_circuit(supply=opt["control_supply"], **coil_args, lamps=3, lamp_va=lamp_va,
                         valve_va_total=(ins.value["n_valves"] * valve_va) if valve_va is not None else 0.0,
                         instrument_va_total=(ins.value["n_mains_tx"] * instrument_230v_a * 230.0)
                         if instrument_230v_a is not None else 0.0,
                         estop=1 if any(t.startswith("ES_MP") for t in dev) else 0,
                         reset=1 if any(t.startswith("RS_0") for t in dev) else 0, phase_lamps=True)
    carry(cc, "control circuit")
    for b in cc.value["bom"]:
        add("Control circuit", b["article"], b["description"], b["qty"], "no", "engineered — awaiting sign-off", b["source"])
    res.add("R-PRJ-12", "control circuit: supply, MCBs and panel operator devices",
            f"supply {opt['control_supply']}; transformer "
            f"{(str(cc.value['transformer_va']) + ' VA') if cc.value['transformer_va'] else 'not sized'}; "
            f"{cc.value['n_devices']} device line(s)", PASS if cc.value["transformer_va"] or opt["control_supply"] != "transformer"
            else WARN)
    logic += [{"tag": "control circuit", "component": "control_circuit", "verdict": c.verdict, "rule": c.rule,
               "requirement": c.requirement, "value": c.value, "source": c.source} for c in cc.checks]

    # 10. PLC (R-PRJ-14): settings from the project file, sized on the client's required I/O
    ps = P.setting("plc", project, {}) or {}
    pp = (ps.get("panels") or {}).get(panel, {})
    req = {x["signal"]: x["required"] for x in client_spec(project)["io"] if x["panel"] == panel}
    fin = {x["signal"]: x["final"] for x in client_spec(project)["io"] if x["panel"] == panel}
    relay_load = _coil()["i_ma"] / 1000
    plc = plc_select(di=req.get("DI", 0), do=req.get("DO", 0), ai=sum(v for k, v in req.items() if k.startswith("AI")),
                     ao=sum(v for k, v in req.items() if k.startswith("AO")), make=ps.get("make"), family=ps.get("family"),
                     cpu=pp.get("cpu"), memory_card_mb=pp.get("memory_card_mb"), dq_load_a=relay_load,
                     ambient_c=panel_internal_c)
    carry(plc, "PLC")
    plc_i24 = 0.0
    if plc.status in ("cannot_select", "invalid"):
        res.add("R-PRJ-14", "PLC from the project settings", "not selected", WARN, "project.yaml")
    else:
        pv_ = plc.value
        # every family reports the 24 V it draws from the panel supply as supply_24v_a (R-PLC-24); parts without a
        # qty are single items (CPU, module) — S7-200 SMART and S7-1200 G2 list each module as its own part
        plc_i24 = pv_.get("supply_24v_a") or pv_.get("i24_a") or 0.0
        for part in pv_["parts"]:
            if part.get("qty", 1):
                add("PLC", part["article"], f"{part['role']}: {part.get('model') or part['role']}", part.get("qty", 1), "no",
                    "engineered — awaiting sign-off", part["source"])
        cover = {"DI": pv_["capacity_di"], "DO": pv_["capacity_do"], "AI": pv_["capacity_ai"], "AO": pv_["capacity_ao"]}
        need_f = {s: sum(v for k, v in fin.items() if k.startswith(s)) for s in cover}
        short = [f"{s} {cover[s]} < {need_f[s]}" for s in cover if cover[s] < need_f[s]]
        res.add("R-PRJ-14", "PLC capacity covers the client's final I/O",
                "; ".join(short) if short else ", ".join(f"{s} {cover[s]} ≥ {need_f[s]}" for s in cover),
                WARN if short else PASS, io_src)
        sel = {"PLC CPU": (1 if pv_["cpu"] != "none" else 0, pv_["cpu"]),
               "ET 200SP interface module station": (pv_.get("n_stations") or 0, "IM 155-6 PN ST")}
        if pv_.get("memory_card"):
            sel["Memory card"] = (1, pv_["memory_card"])
        for it in plc_client:
            key = next((k for k in sel if it["item"].startswith(k)), None)
            if key is None:
                continue
            q, what = sel[key]
            same = it["qty"] == q and (key != "PLC CPU" or pv_["cpu"] in (it["model"] or ""))
            same = same and (key != "Memory card" or str(pp.get("memory_card_mb")) + " MB" in it["item"])
            res.add("R-PRJ-14", f"client: {it['item']} × {it['qty']}", f"selection: {what} × {q}" + ("" if same else
                    " — differs: open point"), PASS if same else WARN, it["source"])
            if not same:
                opens.append({"tag": "PLC", "component": "plc", "rule": "R-PRJ-14", "kind": "warning",
                              "point": f"client {it['item']} × {it['qty']} vs selection {what} × {q}"})
    logic += [{"tag": "PLC", "component": "plc", "verdict": c.verdict, "rule": c.rule, "requirement": c.requirement,
               "value": c.value, "source": c.source} for c in plc.checks]

    # 11. 24 V DC: the client's SITOP capacity against the calculated load (R-PRJ-13)
    m = _method()
    load24 = (io.get("DI", 0) * m["di_a"]["value"] + do_count * _coil()["i_ma"] / 1000 + ins.value["dc_load_a"]
              + dc_coil_w / 24.0 + plc_i24)
    stated = sum(float(x) for it in client_spec(project)["rows"] if it["panel"] == panel and "24 V DC power supply" in it["item"]
                 for x in re.findall(r"(\d+(?:\.\d+)?)\s*A\b", it["item"]))
    # R-PRJ-15: the power calculation as its own section (every line with quantity, unit value, total and source)
    def row(item, qty, unit_v, unit, total, source):
        key = {"digital inputs (company template)": "di", "interface relay coils (one per digital output)": "relays"}.get(item, item)
        return {"key": key, "item": item, "qty": qty, "per_unit": unit_v, "unit": unit, "total": total, "source": source}
    dc = [row("digital inputs (company template)", io.get("DI", 0), m["di_a"]["value"], "A",
              round(io.get("DI", 0) * m["di_a"]["value"], 4), f"OWN-SWG-CALC '{m['di_a']['sheet']}' {m['di_a']['cell']}"),
          row("interface relay coils (one per digital output)", do_count, _coil()["i_ma"] / 1000, "A",
              round(do_count * _coil()["i_ma"] / 1000, 4), f"{_relay_ref()} p.{_coil()['page']} (coil {_coil()['coil_code']}, "
              f"{_coil()['coil']})")]
    dc += [row(f"field devices: {r['item']}", r["qty"], r["unit_a"], "A", r["total_a"], r["source"])
           for r in ins.value.get("dc_rows", [])]
    if dc_coil_w:
        dc.append(row("24 V DC contactor coils (holding)", None, None, "A", round(dc_coil_w / 24.0, 4),
                      "SIE-IC10-2026 via the DOL selection (R-DOL-13)"))
    if plc.value and plc.value.get("i24_rows"):
        dc += [row(f"PLC: {r['item']}", r["qty"], r["unit_a"], "A",
                   round(r["qty"] * r["unit_a"], 4) if r["unit_a"] is not None else None, r["source"])
               for r in plc.value["i24_rows"]]
    elif plc_i24:
        dc.append(row("PLC electronics", None, None, "A", plc_i24, "plc selection"))
    sub = round(sum(r["total"] for r in dc if r["total"] is not None), 4)
    fos = m["smps_fos"]["value"]
    power_calc = {
        "dc24": {"rows": dc, "subtotal_a": sub, "factor": fos,
                 "factor_source": f"OWN-SWG-CALC '{m['smps_fos']['sheet']}' {m['smps_fos']['cell']}",
                 "required_a": round(sub * fos, 3), "available_a": stated, "available_source": dc_src,
                 "partial": any(r["total"] is None for r in dc) or ins.value["dc_load_partial"],
                 "not_counted": "HMI (data not held)"},
        "ac230": {"rows": cc.value.get("load_rows", []), "load_va": cc.value.get("load_va"),
                  "factor": cc.value.get("transformer_factor"), "required_va": cc.value.get("required_va"),
                  "transformer_va": cc.value.get("transformer_va"), "supply": opt["control_supply"],
                  "partial": any(r.get("total") is None for r in cc.value.get("load_rows", []))}}
    ac = power_calc["ac230"]
    # the AC side per phase (component power): feeders, single-phase motors, control circuit, 230 V instruments, 24 V supplies
    three, single = [], []
    for f in p.value["feeders"]:
        if f["status"] != "selected" or not f.get("wire_ib_a"):
            continue
        src = "drive input current (PM240-2 data)" if f["starter"] == "VFD" else "motor FLC (component 1)"
        if (f.get("phases") or 3) == 1:
            single.append({"name": f"{f['tag']} {f['kw']:g} kW (single-phase)", "i_a": f["wire_ib_a"] * f["running"], "connection": "LN", "source": src})
        else:
            three.append({"tag": f["tag"], "description": f"{f['kw']:g} kW {f['starter']}" + (f" × {f['running']}" if f["running"] > 1 else ""),
                          "running": f["running"], "i_a": f["wire_ib_a"], "kw": f["kw"], "source": src,
                          "protection": protection_for(f["tag"], lines)})
    if ac["load_va"]:
        single.append({"key": "control", "name": "control circuit (transformer primary, connected load; transformer losses not included)"
                       if ac["supply"] == "transformer" else "control circuit (230 V)",
                       "va": ac["load_va"], "connection": "LL" if ac["supply"] == "transformer" else "LN",
                       "source": "control circuit (25)", "group": "supply", "kind": "Transformer" if ac["supply"] == "transformer" else "Control circuit",
                       "kw": round(ac["load_va"] / 1000, 4),
                       "protection": next((f"{b['article']} — {b['description']}" for b in cc.value.get("bom", [])
                                           if "primary" in b["description"] or "control circuit" in b["description"]), None)})
    def run_power(lines_):                   # audit 2026-10-17: run again on the edited BOM (protection column)
        for r_ in three:
            r_["protection"] = protection_for(r_["tag"], [l for l in lines_ if not (isinstance(l["qty"], (int, float)) and l["qty"] <= 0)])
        return power_select(voltage_v=voltage_v, three_phase=three, single_phase=single, dc=dc, dc_factor=fos,
                      dc_factor_source=power_calc["dc24"]["factor_source"], dc_available_a=stated or None,
                      dc_supply="client's 24 V supplies" if stated else None,
                      not_counted=[f"{f['tag']} {f['kw']:g} kW {f['starter']} ({f['status']}: no current to count — add it with an edit)"
                                   for f in p.value["feeders"] if f["status"] != "selected"]
                      + ["24 V supplies' AC input (their efficiency is not in the client list)", "energy meter", "HMI",
                         "230 V instruments (their supply current is not given)"],
                      edits=bom_edit.load_power(project, panel) + list(power_edits or []),
                      main_fos=float(incomer_factor) if incomer_factor is not None else m["main_fos"]["value"], frequency_hz=50)
    pw = run_power(lines)
    power_calc["ac3"] = pw.value if pw.status not in ("cannot_select", "invalid") else None
    if pw.status == "invalid":
        power_calc["ac3_error"] = next(c.value for c in pw.checks if c.verdict == "fail")
        res.add("R-PRJ-15", "power edits", power_calc["ac3_error"], WARN, "overrides.yaml")
    carry(pw, "power")
    res.add("R-PRJ-15", "power calculation (own section)",
            f"24 V DC: {sub:g} A × {fos:g} = {sub * fos:.2f} A vs {stated:g} A stated"
            + (" (partial)" if power_calc["dc24"]["partial"] else "") + f"; 230 V AC: {ac['load_va']:g} VA"
            + (f" × {ac['factor']:g} = {ac['required_va']:g} VA → {ac['transformer_va']:g} VA transformer"
               if ac["transformer_va"] else " (transformer not sized)") + (" (partial)" if ac["partial"] else ""),
            INFO, "Power calculation sheet")
    res.add("R-PRJ-13", "client's 24 V supplies against the calculated 24 V load (× 1.25 template factor)",
            f"inputs {io.get('DI', 0)} × {m['di_a']['value']:g} A + relay coils {do_count} × {_coil()['i_ma']:g} mA + field "
            f"devices {ins.value['dc_load_a']:g} A" + (f" + 24 V DC contactor coils {dc_coil_w:g} W / 24 V" if dc_coil_w else "") + f" + PLC electronics {plc_i24:g} A = {load24:.2f} A × {m['smps_fos']['value']:g} = "
            f"{load24 * m['smps_fos']['value']:.2f} A without the HMI (data not held); "
            f"client specifies {stated:g} A", WARN if (ins.value["dc_load_partial"] or load24 * m["smps_fos"]["value"] > stated)
            else INFO, dc_src)

    covered = {NOT_BUILT_BY["plc"], NOT_BUILT_BY["aux_switchgear"]}   # the project runs these (R-PRJ-14, R-PRJ-10)
    for n in p.value["not_selected"]:
        if n in covered:
            continue
        add("Not selected", "", n, "", "", "not selected — question open" if "answer" in n else
            "not selected — component not built", "")
    # R-PRJ-16: every load-list line with its status
    refusal = {}
    for o in opens:
        if o.get("kind") == "refused":
            refusal.setdefault(o["tag"], f"{o['component']} {o['rule']}: {o['point']}")
    n_open_lines = 0
    for f in p.value["feeders"]:
        if f["status"] == "selected":
            st, where = "in the BOM", f["devices"]
        elif f["status"] == "excluded":
            st, where = "out of scope", "owner instruction 2026-10-11 (heater feeders)"
            n_oos += 1
            add("Out of scope", "", f"{f['tag']} {f['kw']} kW {f['starter']} × {f['qty']}", f["qty"], "no",
                "out of scope — owner instruction 2026-10-11", P.doc("load_list", project))
        else:
            st, where = "open", refusal.get(f["tag"], "see open points")
            n_open_lines += 1
        coverage.append({"kind": "load-list line", "panel": panel, "item": f"{f['tag']} {f['kw']} kW {f['starter']} × {f['qty']}",
                         "status": st, "where": where, "source": P.doc("load_list", project)})
    res.add("R-PRJ-16", "coverage of the client's items and load list",
            f"{len(coverage)} row(s): {sum(r['status'] == 'in the BOM' for r in coverage)} in the BOM, "
            f"{sum(r['status'].startswith('selected') for r in coverage)} by the PLC, {n_open_lines} open, {n_oos} out of scope"
            + ("" if carry_plant else f"; plant items in the {plant_panel} BOM"), WARN if n_open_lines else PASS, "Coverage sheet")
    res.add("R-PRJ-08", "component warnings and refusals carried", f"{len(opens)} open point(s)",
            WARN if opens else PASS)

    # R-PRJ-17: designer edits, applied last
    saved = bom_edit.load(project)
    extra = [{**e, "id": e.get("id", 1000 + i), "panel": e.get("panel", panel),
              "check": e.get("check") or bom_edit.check(e), "proposed_by": e.get("proposed_by", "designer")}
             for i, e in enumerate(edits or []) if isinstance(e, dict)]   # edits given as an input (preview / golden cases), not saved
    edits = saved + extra
    lines, unmatched = bom_edit.apply(lines, edits, panel)
    fill_makes(lines)
    if any(isinstance(e, dict) and e.get("panel") == panel for e in edits):
        pw2 = run_power(lines)                  # audit 2026-10-17: the power calculation follows the BOM edits
        if pw2.status not in ("cannot_select", "invalid"):
            power_calc["ac3"] = pw2.value
    n_edits = sum(1 for e in edits if isinstance(e, dict) and e.get("panel") == panel)
    if n_edits:
        gone = [e for e in unmatched if not e.get("unusable")]
        bad = [e for e in unmatched if e.get("unusable")]
        unusable = "; ".join(f"id {e.get('id')}: {e['unusable']}" for e in bad)
        res.add("R-PRJ-17", "designer edits applied (original kept on each line)",
                f"{n_edits - len(unmatched)} applied"
                + (f"; {len(gone)} match no line any more (ids {', '.join(str(e.get('id')) for e in gone)})" if gone else "")
                + (f"; {len(bad)} set aside as unusable ({unusable}) — undo them" if bad else ""),
                WARN if unmatched else INFO, "overrides.yaml")

    def qty(article_start):
        return sum(l["qty"] for l in lines if str(l["article"]).startswith(article_start) and isinstance(l["qty"], (int, float)))

    res.value = {"panel": panel, "n_bom_lines": len(lines), "n_open": len(opens),
                 "qty_cu": qty("6SL3243") + qty("6SL3244") + qty("6SL3246"), "qty_bop": qty("6SL3255"),
                 "qty_latch": qty("13.12"), "qty_slim": qty("38.61") + qty("39."), "qty_ct": sum(
                     l["qty"] for l in lines if l["group"] == "Metering" and "Current transformer" in l["description"]),
                 "qty_io_terminals": sum(l["qty"] for l in lines if l["description"].startswith("Terminal block")),
                 "options": opt, "bom": lines, "feeders": p.value["feeders"], "open_points": opens,
                 "heat_known_w": p.value["heat_known_w"],
                 **{k: il.value[k] for k in ("io_di", "io_do", "io_pn", "io_safety")},
                 "io_list": il.value["io_list"], "io_error": io_error, "design_logic": logic,
                 "io_trace": [{"io": t, "count": il.value[f"io_{t.lower()}"], "used_in": "client I/O table (relays, terminals, PLC are sized on it)",
                               "value": f"{il.value[f'io_{t.lower()}']} in the list ≤ {io.get(t, 0)} channels in the client table",
                               "ok": il.value[f"io_{t.lower()}"] <= io.get(t, 0)} for t in ("DI", "DO") if io.get(t) is not None],
                 "spd_article": next((l["article"] for l in lines if "surge arrester, main incomer" in l["description"].lower()
                                      and not (isinstance(l["qty"], (int, float)) and l["qty"] <= 0)), None),
                 "n_fused_terminals": ins.value["n_fused_terminals"], "n_analog_loops": ins.value["n_analog_loops"],
                 "transformer_va": cc.value["transformer_va"], "load_24v_a": round(load24, 3),
                 "power_calc": power_calc, "standby_groups": (ll.value or {}).get("groups", []),
                 "settings": {**saved_, "incomer_factor": incomer_factor, "min_power_wire_mm2": min_power_wire_mm2,
                              "incomer_factor_default": _method_fos(), "min_power_wire_default": _rules()["params"].get("min_power_wire_mm2")}, "coverage": coverage, "n_client_plant": n_plant, "n_out_of_scope": n_oos,
                 "coverage_open_lines": n_open_lines, "n_edits": n_edits,
                 "plc_cpu": (plc.value or {}).get("cpu"), "plc_stations": (plc.value or {}).get("n_stations"),
                 "plc_modules": (plc.value or {}).get("n_modules"), "plc_i24_a": plc_i24 if plc.value else None}
    res.basis = "all built components"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
