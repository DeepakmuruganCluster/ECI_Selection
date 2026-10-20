"""Panel assembly: a load list through the components. Rules: rules.yaml (R-PNL-01 … 09).

Holds no data: every article, rating and loss comes from a component result.
"""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from components.cable.select import select as cable
from components.dol_starter.select import select as dol
from components.enclosure.select import select as enclosure
from components.enclosure_accessories.select import select as accessories
from components.feeder_kit.select import select as feeder_kit
from components.motor_flc.select import select as motor_flc
from components.soft_starter.select import select as soft_starter
from components.vfd.select import select as vfd
from core.provenance import load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "panel"
STARTERS = ("DOL", "VFD", "SS", "SD", "HEATER")
ACCESSORY_ROLES = ("pilot_lamp", "power_terminal", "earth_terminal", "control_terminal", "end_plate", "end_clamp",
                   "wiring_accessories")
# what the panel assembly does not select, keyed by the component that covers it (a caller that runs that component
# drops the entry; e.g. the project runs the PLC and the auxiliary switchgear)
NOT_BUILT_BY = {"incomer_busbar": "Incomer MCCB and busbar (component 8)",
                "short_circuit": "Short-circuit level (component 7): fault_ka is taken as given",
                "plc": "Control power, PLC and network (component 10)",
                "aux_switchgear": "Auxiliary switchgear: MCB, RCCB, SPD (component 11)"}
NOT_BUILT = list(NOT_BUILT_BY.values())


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


def _num(s: str) -> float:
    """A load-list number: finite and > 0 (raises ValueError, which parse reports as an unreadable line)."""
    x = float(s)
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{s!r} is not a usable number (must be finite and > 0)")
    return x


def _kit_make(m) -> str | None:
    """A company-kit item's make column ('SCHNEIDER', 'REPUTED' = any reputed make)."""
    m = str(m or "").strip()
    return None if not m else "Not fixed (any reputed make)" if m.upper() == "REPUTED" else m.upper() if len(m) <= 3 else m.title()


def parse(text: str) -> list[dict]:
    """'TAG kW STARTER [key=value …]' per line; '#' starts a comment. Raises ValueError."""
    loads, seen = [], set()
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"line {n}: expected 'TAG kW STARTER', got {raw.strip()!r}")
        tag, kw_s, starter = parts[0], parts[1], parts[2].upper()
        try:
            kw = _num(kw_s)
        except ValueError:
            raise ValueError(f"line {n}: kW {kw_s!r} is not a number")
        if starter not in STARTERS:
            raise ValueError(f"line {n}: starter {parts[2]!r} must be one of {', '.join(STARTERS)}")
        if tag in seen:
            raise ValueError(f"line {n}: tag {tag} is used twice")
        seen.add(tag)
        opts = {}
        for o in parts[3:]:
            if "=" not in o:
                raise ValueError(f"line {n}: option {o!r} must be key=value")
            k, v = o.split("=", 1)
            if k not in ("cable", "flc", "qty", "standby", "flc_source", "ph", "v", "duty", "app", "kit", "mpcb"):
                raise ValueError(f"line {n}: unknown option {k!r}")
            opts[k] = v
        try:
            qty, standby = int(opts.get("qty", 1)), int(opts.get("standby", 0))
            cable_m = _num(opts["cable"]) if "cable" in opts else None
            flc = _num(opts["flc"]) if "flc" in opts else None
            ph = int(opts.get("ph", 3))
            v = _num(opts["v"]) if "v" in opts else None
        except ValueError:
            raise ValueError(f"line {n}: qty / standby / cable / flc / ph / v must be numbers")
        if ph not in (1, 3):
            raise ValueError(f"line {n}: ph must be 1 or 3")
        if opts.get("duty", "normal") not in ("normal", "heavy"):
            raise ValueError(f"line {n}: duty must be normal or heavy")
        if qty < 1 or not 0 <= standby < qty:
            raise ValueError(f"line {n}: need qty ≥ 1 and 0 ≤ standby < qty")
        if "mpcb" in opts and starter not in ("DOL", "VFD"):  # R-DOL-14 / R-VFD-19: the client's MPCB range (DOL or a drive's MSP)
            raise ValueError(f"line {n}: mpcb=… (the client's MPCB setting range) is for a DOL or VFD line")
        loads.append({"line": n, "tag": tag, "kw": kw, "starter": starter, "qty": qty, "running": qty - standby,
                      "cable_m": cable_m, "flc": flc, "flc_source": opts.get("flc_source", "nameplate"),
                      "phases": ph, "voltage": v, "duty": opts.get("duty"), "app": opts.get("app", "").replace("_", " ") or None,
                      "kit": opts.get("kit"), "mpcb": opts.get("mpcb")})
    if not loads:
        raise ValueError("the load list is empty")
    return loads


def select(load_list: str, fault_ka: float | None = None, panel_internal_c: float | None = None,
           motor_pf: float | None = None, cable_ambient_c: float | None = None, site_ambient_c: float | None = None,
           cable_installation: str = "air", cable_make: str = "polycab", voltage_v: float = 400.0,
           coil: str = "230VAC", ie_class: str = "IE3", vfd_protection: str = "fuse", ss_protection: str | None = None,
           line_reactor_up_to_kw: float | None = None, altitude_m: float | None = None, fuse_holder: str | None = None,
           suppressor: str | None = None, ss_comm: str | None = None, ss_hmi: str | None = None,
           ss_hmi_mounting: str | None = None, ss_hmi_cable_m: float | None = None,
           enclosure_area_m2: float | None = None, doors: int | None = None, fans_per_door: int | None = None,
           fan_size_in: int | None = None, fan_supply_v: float | None = None, cu_encoder: bool | None = None,
           cu_safety: str | None = None, cu_fieldbus: str | None = None, mc_copy_parameters: bool | None = None,
           dol_source: str = "siemens", kit_accessories: bool = False, other_cables: int | None = None,
           emc_filter: str | None = None, ss_line_contactor: bool | None = None, ss_thermistor: bool | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    for name, val in (("fault_ka", fault_ka), ("panel_internal_c", panel_internal_c), ("cable_ambient_c", cable_ambient_c)):
        if val is None:
            return res.invalid(f"{name} is required")
    if dol_source not in ("siemens", "company"):
        return res.invalid(f"dol_source must be siemens or company (got {dol_source})")
    if motor_pf is not None and not 0 < motor_pf <= 1:
        return res.invalid(f"motor_pf must be between 0 and 1 (got {motor_pf})")
    try:
        loads = parse(load_list)
    except ValueError as e:
        return res.invalid(str(e))
    res.add("R-PNL-01", "load list readable, tags unique", f"{len(loads)} line(s)", PASS)
    if any(ld["duty"] for ld in loads):
        res.add("R-PNL-11", "drive duty from the load list (duty=…)",
                ", ".join(f"{ld['tag']} {ld['duty']}" for ld in loads if ld["duty"]), INFO)

    lines, open_points, bom, logic = [], [], OrderedDict(), []
    heat, unknown_loss, cu_count, excluded, cu_missing = 0.0, [], 0, [], 0

    def add_bom(article, desc, n, tag, price=None, make=None):
        if not article:
            return
        b = bom.setdefault(article, {"article": article, "description": desc, "qty": 0, "used_by": [], "unit_price_inr": price,
                                     "make": make})
        b["qty"] += n
        b["used_by"].append(tag)

    def kit_lines(ld, k, roles, n):
        """Company kit lines with these roles into the BOM (× n units)."""
        for it in k.value["items"]:
            if it["role"] in roles and it["article"]:
                add_bom(it["article"], f"{it['description'].title()} {it['rating']}".strip() + f" ({it['make']}, company kit)",
                        (it["qty"] or 0) * n, ld["tag"], it["unit_price_inr"], make=_kit_make(it["make"]))
            elif it["role"] in roles and it["role"] == "wiring_accessories":
                add_bom(f"Wiring accessories (kit {it['source'].split(' row ')[0].split('sheet ')[-1]})",
                        "Wiring accessories (company kit, unpriced)", (it["qty"] or 0) * n, ld["tag"],
                        make=f"Not fixed (kit make column: '{it['make']}')" if it.get("make") else None)   # QA L8: the kit names no maker

    def carry(ld, r):
        # every check behind every feeder, for the design-logic view
        logic.extend({"tag": ld["tag"], "component": r.component, "verdict": c.verdict, "rule": c.rule,
                      "requirement": c.requirement, "value": c.value, "source": c.source} for c in r.checks)
        for c in r.checks:
            if c.verdict == "warn":
                open_points.append({"tag": ld["tag"], "component": r.component, "rule": c.rule,
                                    "point": f"{c.requirement}: {c.value}", "kind": "warning"})

    def stop(ld, r, why=None):
        fail = next((c for c in r.checks if c.verdict == "fail"), None) if r else None
        open_points.append({"tag": ld["tag"], "component": r.component if r else "panel",
                            "rule": fail.rule if fail else "R-PNL-02",
                            "point": why or (f"{fail.requirement}: {fail.value}" if fail else r.status),
                            "kind": "refused"})

    for ld in loads:
        rec = {"tag": ld["tag"], "kw": ld["kw"], "starter": ld["starter"], "qty": ld["qty"], "running": ld["running"],
               "status": "selected", "flc_a": None, "devices": "", "cable": "", "wire_ib_a": None, "wire_in_a": None}
        lines.append(rec)
        # 1. motor / heater current
        # single-phase loads: line-to-neutral voltage unless v= is given (RULE: 230 V for a 400 V system)
        v_line = ld["voltage"] or (voltage_v if ld["phases"] == 3 else 230.0)
        f = motor_flc(kw=ld["kw"], load_type="heater" if ld["starter"] == "HEATER" else "motor", voltage_v=v_line,
                      phases=ld["phases"], nameplate_flc_a=ld["flc"], nameplate_source=ld["flc_source"])
        carry(ld, f)
        if f.status in ("cannot_select", "invalid"):
            rec["status"] = "open"
            stop(ld, f)
            continue
        flc, basis = f.value["flc_a"], f.basis
        rec["flc_a"] = flc
        # 2. starter
        if ld["starter"] == "HEATER":
            rec["status"] = "excluded"
            excluded.append(ld["tag"])
            continue
        kit = None
        if ld.get("mpcb") and (dol_source == "company" or kit_accessories):
            rec["status"] = "open"
            stop(ld, None, "the client's MPCB range (mpcb=…) selects from the Siemens Type 2 table, not a company kit (R-DOL-14)")
            continue
        if ld["starter"] == "SD" or (ld["starter"] == "DOL" and (dol_source == "company" or kit_accessories)):
            kflc = ld["flc"] if ld["flc"] else (flc if basis != "guide" else None)
            if ld.get("kit"):                    # the designer's choice (audit 2026-10-17: asked, never the first silently)
                kit = feeder_kit(starter=ld["starter"], kw=ld["kw"], flc_a=kflc, voltage_v=v_line, kit=ld["kit"])
            else:
                kit = feeder_kit(starter=ld["starter"], kw=ld["kw"], application=ld["app"], flc_a=kflc, voltage_v=v_line)
                borrowed = None
                if kit.status == "cannot_select" and ld["app"] and not (kit.value or {}).get("choices"):
                    # none named after the application: the kits of this size for other applications are offered, not taken
                    borrowed = feeder_kit(starter=ld["starter"], kw=ld["kw"], flc_a=kflc, voltage_v=v_line)
                    kit = borrowed
                ch = (kit.value or {}).get("choices") if kit.status == "cannot_select" else None
                if borrowed is not None and kit.status not in ("cannot_select", "invalid"):
                    ch = [{"id": kit.value["kit_id"], "title": kit.value["kit"], "sheet": kit.value.get("sheet", "")}]
                if ch:
                    rec["status"] = "open"
                    rec["kit_choices"] = ch
                    open_points.append({"tag": ld["tag"], "component": "feeder_kit", "rule": "R-KIT-06", "kind": "choose",
                                        "choices": ch, "point": (f"no company kit named after '{ld['app']}': " if borrowed is not None else "")
                                        + "choose the kit: " + "; ".join(c["title"] for c in ch)})
                    continue
            if ld["starter"] == "SD" or dol_source == "company":
                carry(ld, kit)  # the kit's own starter is used: its checks count
            else:  # only its accessories are used: keep the record, not the starter checks
                logic.extend({"tag": ld["tag"], "component": "feeder_kit", "verdict": c.verdict, "rule": c.rule,
                              "requirement": c.requirement, "value": c.value, "source": c.source}
                             for c in kit.checks if c.rule in ("R-KIT-01", "R-KIT-02"))
            if kit.status in ("cannot_select", "invalid"):
                if ld["starter"] == "SD" or dol_source == "company":
                    rec["status"] = "open"
                    stop(ld, kit)
                    continue
                open_points.append({"tag": ld["tag"], "component": "feeder_kit", "rule": "R-PNL-14",
                                    "point": f"no company kit for {ld['kw']:g} kW {ld['starter']}: accessories not added",
                                    "kind": "warning"})
                kit = None
        if ld["starter"] == "SD":
            # R-PNL-12: star-delta starter core from the company kit
            v = kit.value
            core = ("contactor", "overload_relay", "timer", "aux_contact")
            pair, star = v.get("line_contactor"), v.get("star_contactor")
            for it in v["items"]:
                if it["role"] in core and (it["role"] != "contactor" or it["article"] in (pair, star)) and it["article"]:
                    add_bom(it["article"], f"{it['description'].title()} {it['rating']}".strip() + f" ({it['make']}, company kit)",
                            (it["qty"] or 0) * ld["qty"], ld["tag"], it["unit_price_inr"], make=_kit_make(it["make"]))
            if kit_accessories:
                kit_lines(ld, kit, ACCESSORY_ROLES, ld["qty"])
            rec["devices"] = f"star-delta: {pair} × 2 + {star} (company kit {v['kit']})"
            rec["wire_ib_a"], rec["wire_in_a"] = flc, None
            unknown_loss.append(f"{ld['tag']}: star-delta contactors")
            open_points.append({"tag": ld["tag"], "component": "cable", "rule": "R-PNL-12",
                                "point": "star-delta motor cables (two runs at FLC/√3) not sized yet", "kind": "refused"})
            continue
        if ld["starter"] == "DOL" and dol_source == "company":
            # R-PNL-13: the company's DOL kit (MPCB + contactor + auxiliary contacts) instead of the Siemens selection
            v = kit.value
            rng = [x for x in re.findall(r"[\d.]+", next((i["rating"] for i in v["items"] if i["role"] == "mpcb"), ""))]
            kit_lines(ld, kit, ("mpcb", "contactor", "aux_contact") + (ACCESSORY_ROLES if kit_accessories else ()), ld["qty"])
            rec["devices"] = f"{v['mpcb']} + {v['contactor']} (company kit {v['kit']})"
            unknown_loss.append(f"{ld['tag']}: MPCB + contactor")
            rec["wire_ib_a"], rec["wire_in_a"] = flc, float(rng[-1]) if rng else None
            rec["device_in_a"] = rec["wire_in_a"]
            in_a, overload = flc, True
            s = None
        elif ld["starter"] == "SS":
            # R-PNL-15: soft starter (component 5), class from duty=, at the panel's internal temperature
            s = soft_starter(flc_a=flc, flc_basis=basis, fault_ka=fault_ka, ambient_c=panel_internal_c, duty=ld["duty"],
                             voltage_v=v_line, phases=ld["phases"], altitude_m=altitude_m, protection=ss_protection,
                             line_contactor=ss_line_contactor, thermistor=bool(ss_thermistor), comm=ss_comm, hmi=ss_hmi,
                             hmi_mounting=ss_hmi_mounting, hmi_cable_m=ss_hmi_cable_m)
        elif ld["starter"] == "DOL":
            s = dol(flc_a=flc, flc_basis=basis, ie_class=ie_class, fault_ka=fault_ka, coil=coil, voltage_v=v_line,
                    phases=ld["phases"], mpcb_range=ld.get("mpcb"), suppressor=suppressor)
        else:
            if ld["cable_m"] is None:
                rec["status"] = "open"
                stop(ld, None, "VFD line needs cable=… (motor cable length decides output reactors)")
                continue
            s = vfd(kw=ld["kw"], flc_a=flc, flc_basis=basis, ambient_c=panel_internal_c, cable_m=ld["cable_m"],
                    fault_ka=fault_ka, voltage_v=v_line, phases=ld["phases"], protection=vfd_protection, duty=ld["duty"],
                    client_line_reactor_up_to_kw=line_reactor_up_to_kw, altitude_m=altitude_m, fuse_holder=fuse_holder,
                    cu_encoder=cu_encoder, cu_safety=cu_safety, cu_fieldbus=cu_fieldbus,
                    mc_copy_parameters=mc_copy_parameters, emc_filter=emc_filter or "none",
                    msp_range=ld.get("mpcb") if vfd_protection == "msp" else None)
        if s is not None:
            carry(ld, s)
            if s.status in ("cannot_select", "invalid"):
                rec["status"] = "open"
                stop(ld, s)
                continue
            v = s.value
        if s is None:
            pass
        elif ld["starter"] == "SS":
            rec["devices"] = f"{v['soft_starter']} + {v['protection_device']}" + (
                f" × {v['protection_qty']}" if v["protection_qty"] > 1 else "") + (f" + {v['line_contactor']}" if v["line_contactor"] else "")
            for b in v["bom"]:
                add_bom(b["article"], b["description"], b["qty"] * ld["qty"], ld["tag"])
            unknown_loss.append(f"{ld['tag']}: soft starter (power loss not printed)")
            res.add("R-PNL-15", f"{ld['tag']}: soft starter, class {v['starting_class']}, protection {v['protection']}",
                    f"{rec['devices']}; overload set to FLC {flc:g} A protects the cable", INFO)
            # the soft starter's motor protection is set to the FLC: it is the cable's overload device (R-SS-04)
            # QA 2026-10-16: the wiring is sized against that setting (Ib = In = FLC); the short-circuit device's rating is not held
            rec["wire_ib_a"], rec["wire_in_a"], rec["device_in_a"] = flc, flc, None
            in_a, overload = flc, True
        elif ld["starter"] == "DOL":
            rec["devices"] = f"{v['mpcb']} + {v['contactor']}" + (f" + {v['link_module']}" if v["link_module"] else "")
            rec["coil"] = {"coil": v["coil"], "close": v["coil_close"], "hold": v["coil_hold"], "unit": v["coil_unit"]}
            add_bom(v["mpcb"], f"MPCB {v['setting_range_a']} A", ld["qty"], ld["tag"])
            add_bom(v["contactor"], "Contactor (Type 2 partner)", ld["qty"], ld["tag"])
            add_bom(v["link_module"], "Link module", ld["qty"], ld["tag"])
            add_bom(v.get("suppressor"), "Surge suppressor (varistor) for the contactor", ld["qty"], ld["tag"])   # R-DOL-15
            unknown_loss.append(f"{ld['tag']}: MPCB + contactor")
            rec["wire_ib_a"], rec["wire_in_a"] = flc, float(v["setting_range_a"].split("…")[-1])
            rec["device_in_a"] = rec["wire_in_a"]
            in_a, overload = flc, True
            if kit is not None:
                # R-PNL-14: company accessories; the kit's auxiliary contacts fit Schneider devices only
                kit_lines(ld, kit, ACCESSORY_ROLES, ld["qty"])
                open_points.append({"tag": ld["tag"], "component": "feeder_kit", "rule": "R-PNL-14",
                                    "point": "auxiliary contacts for the Siemens MPCB / contactor: article not held "
                                             "(needs catalog IC 10); the company kit's Schneider contacts do not fit",
                                    "kind": "warning"})
        else:
            rec["devices"] = f"{v['power_module']} ({v['rating']}) + {v['protection_device']}"
            add_bom(v["power_module"], f"SINAMICS PM240-2 {v['rating']}", ld["qty"], ld["tag"])
            add_bom(v["protection_device"], f"{v['protection_type']} for the drive (ICC {v['protection_icc_ka']:g} kA)"
                    + (", one per line conductor" if v.get("protection_qty", 1) == 3 else ""),
                    ld["qty"] * v.get("protection_qty", 1), ld["tag"])          # R-VFD-17: 3 fuses per drive
            add_bom(v.get("fuse_holder"), "Fuse switch disconnector for the drive's fuses (3-pole, floor mounting)",
                    ld["qty"], ld["tag"])                                        # R-VFD-18
            add_bom(v["line_reactor"], "Line reactor", ld["qty"], ld["tag"])
            add_bom(v["output_reactor"], "Output reactor", ld["qty"] * (v["output_reactor_qty"] or 0), ld["tag"])
            add_bom(v.get("control_unit"), f"Control Unit {v.get('control_unit_series')}", ld["qty"], ld["tag"])
            add_bom(v.get("operator_panel"), "Operator panel BOP-2", ld["qty"], ld["tag"])
            add_bom(v.get("memory_card"), "Memory card", ld["qty"], ld["tag"])
            if not v.get("control_unit"):
                cu_missing += ld["qty"]
            heat += v["loss_w"] * ld["running"]
            rec["wire_ib_a"], rec["wire_in_a"] = v["input_a"], v["protection_max_a"]
            rec["device_in_a"] = v["protection_max_a"]
            rec["vfd_bom"] = v["vfd_bom"]
            cu_count += ld["qty"]
            in_a, overload = None, False
        # 3. motor cable
        if ld["cable_m"] is None:
            open_points.append({"tag": ld["tag"], "component": "cable", "rule": "R-PNL-02",
                                "point": "no cable length given (cable=…): cable not sized", "kind": "refused"})
            continue
        c = cable(ib_a=flc, length_m=ld["cable_m"], voltage_v=v_line, phases=ld["phases"], pf_run=motor_pf,
                  installation=cable_installation, ambient_c=cable_ambient_c, in_a=in_a, overload_device=overload,
                  make=cable_make, fault_ka=None, other_cables=int(other_cables or 0))
        carry(ld, c)
        if c.status in ("cannot_select", "invalid"):
            rec["status"] = "open"
            stop(ld, c)
            continue
        rec["cable"] = f"{c.value['cable']}, {ld['cable_m']:g} m"
        key = c.value["cable"]
        b = bom.setdefault(key, {"article": key, "description": f"{cable_make} cable (metres)", "qty": 0, "used_by": [],
                                 "make": {"polycab": "Polycab", "kei": "KEI"}.get(str(cable_make).lower(), str(cable_make).title())})
        b["qty"] += ld["qty"] * ld["cable_m"]
        b["used_by"].append(ld["tag"])

    n_open_lines = sum(1 for r in lines if r["status"] == "open")
    if excluded:
        res.add("R-PNL-10", "out of scope (owner instruction): heater feeders", ", ".join(excluded), INFO)
    if n_open_lines:
        res.add("R-PNL-02", "every line selected", f"{n_open_lines} line(s) stopped: see open points", WARN)
    else:
        res.add("R-PNL-02", "every line selected", f"{len(lines)} line(s)", PASS)
    sd_lines = [r["tag"] for r in lines if r["starter"] == "SD"]
    if sd_lines:
        res.add("R-PNL-12", "star-delta starters from the company kit", ", ".join(sd_lines), INFO, "OWN-PROPEL-DOL / OWN-PROPEL-COST")
    if dol_source == "company":
        res.add("R-PNL-13", "DOL starters from the company kit (Schneider)",
                ", ".join(r["tag"] for r in lines if r["starter"] == "DOL") or "no DOL lines", INFO, "OWN-PROPEL-DOL")
    if kit_accessories:
        res.add("R-PNL-14", "company kit accessories on DOL and SD feeders",
                f"{sum(1 for b in bom.values() if '(company kit' in b['description'] or 'company kit, unpriced' in b['description'])}"
                " BOM line(s)", INFO, "OWN-PROPEL-DOL")
    res.add("R-PNL-03", "DOL cables checked with In = MPCB setting (FLC)",
            ", ".join(r["tag"] for r in lines if r["starter"] == "DOL") or "no DOL lines", INFO)
    res.add("R-PNL-04", "VFD motor cables: overload protection by the drive",
            ", ".join(r["tag"] for r in lines if r["starter"] == "VFD") or "no VFD lines", INFO, "SIE-G120-PROT p.3")
    res.add("R-PNL-05", "drives derated at the panel internal temperature", f"{panel_internal_c:g} °C", INFO)

    heat += cu_count * prm["cu_loss_w"]
    res.add("R-PNL-06", "heat: running units; Control Unit for every installed drive",
            f"{heat:g} W ({cu_count} Control Unit(s) × {prm['cu_loss_w']} W)", PASS, "SIE-PM240-2 p.34")
    if unknown_loss:
        res.add("R-PNL-07", "every device loss from a held source",
                f"no sourced loss for {len(unknown_loss)} line(s) ({'; '.join(unknown_loss[:4])}"
                f"{' …' if len(unknown_loss) > 4 else ''}): heat is a lower bound", WARN)
    else:
        res.add("R-PNL-07", "every device loss from a held source", "yes", PASS)

    cooling = {}
    if site_ambient_c is None:
        res.add("R-PNL-05", "enclosure heat balance", "not assessed: site_ambient_c not given", INFO)
    elif heat <= 0:
        res.add("R-PNL-05", "enclosure heat balance", "not assessed: no sourced heat loss", INFO)
    elif altitude_m is None:
        res.add("R-PNL-05", "enclosure heat balance", "not assessed: site altitude not given (fan factor depends on it)",
                INFO, "RITTAL-TSC-3124300 p.12")
    else:
        e = enclosure(heat_loss_w=heat, ambient_c=site_ambient_c, max_internal_c=panel_internal_c,
                      altitude_m=altitude_m, siting="indoor",
                      area_m2=enclosure_area_m2, material="sheet_steel" if enclosure_area_m2 else None)
        carry({"tag": "panel"}, e)
        if e.status in ("cannot_select", "invalid"):
            stop({"tag": "panel"}, e)
        else:
            cooling = e.value
            res.add("R-PNL-05", "enclosure holds the internal temperature", f"method: {e.value.get('method')}", PASS,
                    "enclosure component")
            if cooling.get("method") == "fan" and doors and fan_supply_v:
                a = accessories(required_airflow_m3h=cooling["fan_airflow_m3h"], doors=doors, supply_v=fan_supply_v,
                                frequency_hz=50, fans_per_door=fans_per_door, fan_size_in=fan_size_in,
                                outlet_filters_per_fan=1, site_ambient_c=site_ambient_c)
                carry({"tag": "panel"}, a)
                if a.status in ("cannot_select", "invalid"):
                    stop({"tag": "panel"}, a)
                else:
                    av = a.value
                    cooling["fan_qty"] = av["fan_qty"]
                    add_bom(av["fan"], f"Filter fan {av['fan_size_in']}\" ({av['airflow_per_fan_m3h']:g} m³/h with outlet filter)",
                            av["fan_qty"], "panel")
                    add_bom(av["outlet_filter"], "Outlet filter", av["outlet_filter_qty"], "panel")
                    add_bom(av.get("door_switch"), "Door-operated switch", av.get("door_switch_qty") or 0, "panel")
                    add_bom(av.get("door_light"), "LED panel light", av.get("door_light_qty") or 0, "panel")
            elif cooling.get("method") == "fan":
                res.add("R-PNL-05", "fans and door accessories", "not selected: give doors and fan supply voltage",
                        INFO)

    not_selected = list(NOT_BUILT)
    if cu_missing:
        not_selected.append(f"Drive Control Unit × {cu_missing} (answer encoder, safety and fieldbus)")
    res.add("R-PNL-08", "panel complete", f"not selected yet: {len(not_selected)} item(s)", WARN)
    carried = [p for p in open_points if p["kind"] == "warning"]
    if carried:
        res.add("R-PNL-09", "component warnings carried to open points", f"{len(carried)} warning(s)", WARN)

    res.value = {"n_lines": len(lines), "n_units": sum(r["qty"] for r in lines),
                 "n_selected": len(lines) - n_open_lines - len(excluded), "n_open": len(open_points),
                 "n_excluded": len(excluded),
                 "heat_known_w": round(heat, 1), "cooling_method": cooling.get("method"),
                 "fan_airflow_m3h": cooling.get("fan_airflow_m3h"), "cooling_unit_w": cooling.get("cooling_unit_w"),
                 "fan_qty": cooling.get("fan_qty"),
                 "feeders": lines, "bom": list(bom.values()), "open_points": open_points,
                 "not_selected": not_selected, "design_logic": logic}
    res.basis = "chained components"
    return res


def coil_loads(feeders: list[dict]) -> tuple[list[dict], float]:
    """Contactor coils of the selected DOL / SD feeders: AC coils as control_circuit coil_power entries (catalogue power
    from the DOL selection, None where not held, e.g. company kits), and the 24 V DC holding power in W (R-DOL-13)."""
    ac, dc_w = [], 0.0
    for f in feeders:
        if f["status"] != "selected" or f["starter"] not in ("DOL", "SD"):
            continue
        n = f["qty"] * (3 if f["starter"] == "SD" else 1)
        c = f.get("coil")
        if c and c["coil"] == "24VDC":
            dc_w += c["hold"] * n
        else:
            ac.append({"close_va": c["close"] if c else None, "hold_va": c["hold"] if c else None, "qty": n})
    return ac, dc_w



from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
