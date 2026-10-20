"""PLC and I/O modules. Rules: rules.yaml.

Omron CP2E + CP1W from the AutoBOM databases (R-PLC-01 … 06); Siemens S7-200 SMART from the system manual V2.7
(SIE-S7-200SMART-SYS, table s7200smart_modules; R-PLC-07 … 12); Siemens S7-1200 G2 from Catalog ST 70 · 2026
(SIE-ST70-2026, table st70_s71200g2; R-PLC-13 … 17); S7-1500 CPU + ET 200SP stations from ST 70 and the CPU 1513-1 PN
equipment manual (tables st70_s71500_et200sp, s71500_cpu1513_power; R-PLC-18 … 22).
"""
from __future__ import annotations

import math
from functools import lru_cache
from itertools import combinations_with_replacement
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "plc"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


_SPARE = __import__("threading").local()       # the designer's spare for this call (audit 2026-10-17: asked, not defaulted)


def _spare(prm: dict) -> float:
    return getattr(_SPARE, "f", None) or prm["spare_factor"]


@lru_cache(maxsize=None)
def _cpus() -> dict:
    return load_sourced_table(data_file("ab_plc.yaml"), ("model", "series", "max_io", "di", "do", "max_ext"))


@lru_cache(maxsize=None)
def _modules() -> dict:
    return load_sourced_table(data_file("ab_plc_io.yaml"), ("model", "di", "do", "i5_a", "eff_5v"))


def _i24(row: dict) -> float:
    """R-PLC-05: 24 V side current of one unit."""
    return (row["i24_a"] or 0.0) + row["i5_a"] * 5.0 / (24.0 * row["eff_5v"])


def _family(series: str) -> str:
    return series.split("-")[0]  # CP2E-S / CP2E-N → CP2E


def _plan(cpu: dict, need_di: int, need_do: int, do_type: str):
    """Fewest compatible modules (≤ Max Ext Mod) covering what the CPU's built-in I/O leaves; None if none fits."""
    rem_di, rem_do = max(need_di - cpu["di"], 0), max(need_do - cpu["do"], 0)
    if not rem_di and not rem_do:
        return []
    mods = [m for m in _modules()["rows"] if _family(cpu["series"]) in m["series_ok"]
            and (m["do"] == 0 or m["do_type"] == do_type)]
    best = None
    for n in range(1, int(cpu["max_ext"]) + 1):
        for combo in combinations_with_replacement(mods, n):
            di, do = sum(m["di"] for m in combo), sum(m["do"] for m in combo)
            if di < rem_di or do < rem_do or cpu["di"] + cpu["do"] + di + do > cpu["max_io"]:
                continue
            key = (n, di + do - rem_di - rem_do, sum(_i24(m) for m in combo))
            if best is None or key < best[0]:
                best = (key, list(combo))
        if best:
            return sorted(best[1], key=lambda m: (-(m["di"] + m["do"]), m["row"]))  # largest first
    return None


@lru_cache(maxsize=None)
def _s7() -> dict:
    return load_sourced_table(data_file("s7200smart_modules.yaml"), ("article", "model", "kind"))


def _s7_i24(units: list[dict]):
    """R-PLC-10 / 11: 24 V sensor-supply current (mA) of CPU + modules, and the modules whose relay current is not printed."""
    total, gaps = 0.0, []
    for u in units:
        total += u.get("di", 0) * (u.get("i24_per_input_ma") or 0)
        if u.get("do_type") == "relay" and u["kind"] != "cpu":
            if u.get("i24_per_relay_ma"):
                total += u["do"] * u["i24_per_relay_ma"]
            elif u.get("i24_fixed_ma"):
                total += u["i24_fixed_ma"]
            else:
                gaps.append(u["model"])
        elif u["kind"] != "cpu":
            total += u.get("i24_loaded_ma") or u.get("i24_fixed_ma") or 0
    return total, gaps


def _siemens(res: Result, di: int, do: int, ai: int, ao: int, do_type: str, fieldbus, fieldbus_devices) -> Result:
    prm = _rules()["params"]
    rows = _s7()["rows"]
    if do_type not in ("sourcing", "relay"):
        return res.refuse("R-PLC-07", "S7-200 SMART output type", f"{do_type}: the family has sourcing (ST) and relay (SR) "
                          "outputs only", "SIE-S7-200SMART-SYS pp.806, 847")
    f = _spare(prm)
    need = {k: math.ceil(v * f - 1e-9) for k, v in (("di", di), ("do", do), ("ai", ai), ("aq", ao))}
    res.add("R-PLC-08", f"required I/O = signals × {f:g} ({round((f - 1) * 100, 1):g} % spare)",
            f"DI {need['di']}, DO {need['do']}, AI {need['ai']}, AO {need['aq']}", INFO, "OWN-AB-PLCIO 'logic' row 1")
    if fieldbus and fieldbus != "none" and fieldbus != "profinet":
        return res.refuse("R-PLC-12", f"S7-200 SMART with {fieldbus}", "only PROFINET (controller) is on the CPU",
                          "SIE-S7-200SMART-SYS p.801")
    cpus = [r for r in rows if r["kind"] == "cpu" and r["do_type"] == do_type]
    cpus.sort(key=lambda c: (c["di"] + c["do"], c["page"]))
    mods = [m for m in rows if m["kind"] == "em" and not m.get("rtd") and not m.get("tc")
            and (not m.get("do") or m["do_type"] == do_type)]
    res.add("R-PLC-07", f"S7-200 SMART {'ST' if do_type == 'sourcing' else 'SR'} CPUs ({do_type} outputs)",
            ", ".join(c["model"] for c in cpus), INFO, "SIE-S7-200SMART-SYS pp.800-840")
    g = lambda u, k: u.get(k) or 0
    for cpu in cpus:
        rem = {k: max(need[k] - g(cpu, k), 0) for k in need}
        best = None
        if not any(rem.values()):
            best = ((0, 0, 0), [])
        else:
            for n in range(1, int(cpu["max_em"]) + 1):
                for combo in combinations_with_replacement(mods, n):
                    cap = {k: sum(g(m, k) for m in combo) for k in need}
                    if any(cap[k] < rem[k] for k in need):
                        continue
                    bus = sum(m["bus_5v_ma"] for m in combo)
                    if bus > cpu["budget_5v_ma"]:
                        continue
                    key = (n, sum(cap.values()) - sum(rem.values()), bus)
                    if best is None or key < best[0]:
                        best = (key, list(combo))
                if best:
                    break
        if best is None:
            continue
        plan = sorted(best[1], key=lambda m: (-(g(m, "di") + g(m, "do") + g(m, "ai") + g(m, "aq")), m["page"], m["model"]))
        units = [cpu, *plan]
        bus = sum(m["bus_5v_ma"] for m in plan)
        src = f"SIE-S7-200SMART-SYS p.{cpu['page']}" + "".join(f", p.{m['page']}" for m in plan)
        res.add("R-PLC-09", f"smallest CPU covering DI {need['di']} / DO {need['do']} / AI {need['ai']} / AO {need['aq']} "
                f"with ≤ {cpu['max_em']} modules and 5 V ≤ {cpu['budget_5v_ma']} mA",
                f"{cpu['model']} + {', '.join(m['model'] for m in plan) or 'no expansion'}; 5 V bus {bus:g} mA", PASS, src)
        i24, gaps = _s7_i24(units)
        if gaps:
            res.add("R-PLC-11", "relay-coil current printed for every relay module",
                    f"not printed for {', '.join(gaps)}: 24 V budget partial", WARN, src)
        if i24 > cpu["budget_24v_ma"]:
            res.add("R-PLC-10", f"24 V sensor supply {cpu['budget_24v_ma']:g} mA ≥ inputs × 4 mA + relays × 11 mA + analog",
                    f"{i24:g} mA: an external 24 V DC supply of at least {i24 - cpu['budget_24v_ma']:g} mA is needed "
                    "(not in parallel with the sensor supply)", WARN, f"SIE-S7-200SMART-SYS p.901 (Table B-1)")
        else:
            res.add("R-PLC-10", f"24 V sensor supply {cpu['budget_24v_ma']:g} mA ≥ inputs × 4 mA + relays × 11 mA + analog",
                    f"{i24:g} mA", PASS, "SIE-S7-200SMART-SYS p.901 (Table B-1)")
        sup = (cpu.get("in_24v_all_ma") or 0) / 1000 + max(i24 - cpu["budget_24v_ma"], 0) / 1000
        res.add("R-PLC-24", "24 V drawn from the panel supply: CPU with all expansion accessories at max. load + "
                "sensor-supply shortfall", f"{cpu['model']} {cpu.get('in_24v_all_ma') or 0:g} mA" +
                (" (AC-fed)" if not cpu.get("in_24v_all_ma") else "") + f" + {max(i24 - cpu['budget_24v_ma'], 0):g} mA = "
                f"{sup:.3f} A", INFO, f"SIE-S7-200SMART-SYS p.{cpu.get('power_page', cpu['page'])}")
        if fieldbus == "profinet":
            if fieldbus_devices is None:
                res.add("R-PLC-12", f"PROFINET devices ≤ {cpu['profinet_max_devices']}", "number of devices not given",
                        WARN, f"SIE-S7-200SMART-SYS p.{cpu['profinet_page']}")
            elif fieldbus_devices > cpu["profinet_max_devices"]:
                return res.refuse("R-PLC-12", f"PROFINET devices ≤ {cpu['profinet_max_devices']}", f"{fieldbus_devices}",
                                  f"SIE-S7-200SMART-SYS p.{cpu['profinet_page']}")
            else:
                res.add("R-PLC-12", f"PROFINET devices ≤ {cpu['profinet_max_devices']}", f"{fieldbus_devices}", PASS,
                        f"SIE-S7-200SMART-SYS p.{cpu['profinet_page']}")
        cap = {k: g(cpu, k) + sum(g(m, k) for m in plan) for k in need}
        res.value = {"make": "siemens", "cpu": cpu["model"], "cpu_article": cpu["article"], "n_modules": len(plan),
                     **{f"module_{i}": m["model"] for i, m in enumerate(plan, 1)},
                     "required_di": need["di"], "required_do": need["do"], "required_ai": need["ai"], "required_ao": need["aq"],
                     "capacity_di": cap["di"], "capacity_do": cap["do"], "capacity_ai": cap["ai"], "capacity_ao": cap["aq"],
                     "bus_5v_ma": bus, "i24_ma": i24, "i24_partial": bool(gaps),
                     "supply_24v_a": round((cpu.get("in_24v_all_ma") or 0) / 1000 + max(i24 - cpu["budget_24v_ma"], 0) / 1000, 4),
                     "parts": [{"article": u["article"], "role": "CPU" if u is cpu else "Expansion module", "model": u["model"],
                                "di": g(u, "di"), "do": g(u, "do"), "source": f"SIE-S7-200SMART-SYS p.{u['page']}"}
                               for u in units]}
        res.basis = "S7-200 SMART system manual"
        return res
    return res.refuse("R-PLC-09", f"CPU + ≤ 6 modules covering DI {need['di']} / DO {need['do']} / AI {need['ai']} / "
                      f"AO {need['aq']} ({do_type})", "no S7-200 SMART CPU fits", "SIE-S7-200SMART-SYS")


@lru_cache(maxsize=None)
def _g2() -> dict:
    return load_sourced_table(data_file("st70_s71200g2.yaml"), ("article", "model", "kind"))


@lru_cache(maxsize=None)
def _g2_power() -> dict:
    d = load_sourced_table(data_file("s71200g2_cpu_power.yaml"), ("model",))
    return {r["model"]: r for r in d["rows"]}


def _g2_lplus(mods: list[dict]) -> float:
    """R-PLC-16: 24 V DC load-voltage current of the signal modules (mA)."""
    g = lambda u, k: u.get(k) or 0
    return round(sum(g(m, "di") * g(m, "lplus_per_input_ma") + g(m, "lplus_outputs_ma")
                     + g(m, "do") * g(m, "lplus_per_relay_ma") * (m.get("do_type") == "relay") + g(m, "lplus_typ_ma")
                     for m in mods), 2)


def _s71200g2(res: Result, di, do, ai, ao, do_type, fieldbus, fieldbus_devices, cpu_supply, ambient_c) -> Result:
    prm = _rules()["params"]
    rows = _g2()["rows"]
    src = lambda r: f"SIE-ST70-2026 p.{r['page']} ({r['printed']})"
    if do_type == "sinking":
        return res.refuse("R-PLC-13", "S7-1200 G2 CPU with sinking outputs", "G2 CPU outputs are sourcing (MOSFET) or relay",
                          "SIE-S71200G2-SYS p.376")
    pw = _g2_power()
    tmp = pw["temperature"]
    factor = 1.0
    if ambient_c is not None and ambient_c > tmp["derated_max_c"]:
        return res.refuse("R-PLC-17", f"ambient ≤ {tmp['derated_max_c']} °C", f"{ambient_c:g} °C", "SIE-S71200G2-SYS p.361")
    if ambient_c is not None and ambient_c > tmp["full_spec_max_c"]:
        factor = tmp["derating_factor"]
        res.add("R-PLC-17", f"ambient ≤ {tmp['full_spec_max_c']} °C for maximum specifications",
                f"{ambient_c:g} °C: derating — 50 % of the expansion current, sensor supply and output current, alternate "
                "I/O active", WARN, "SIE-S71200G2-SYS p.361")
    if fieldbus and fieldbus not in ("none", "profinet"):
        return res.refuse("R-PLC-17", f"S7-1200 G2 with {fieldbus}", "only PROFINET is on the CPU", "SIE-ST70-2026 p.395")
    supply = (cpu_supply or "24VDC").upper()
    if do_type == "relay":
        cpus = [c for c in rows if c["kind"] == "cpu" and c["do_type"] == "relay"
                and (c["supply"].endswith("V AC") == (supply == "AC"))]
    else:
        cpus = [c for c in rows if c["kind"] == "cpu" and c["do_type"].startswith("dc")]
    cpus.sort(key=lambda c: (c["di"] + c["do"], c["page"]))
    f = _spare(prm)
    need = {k: math.ceil(v * f - 1e-9) for k, v in (("di", di), ("do", do), ("ai", ai), ("aq", ao))}
    res.add("R-PLC-08", f"required I/O = signals × {f:g} ({round((f - 1) * 100, 1):g} % spare)",
            f"DI {need['di']}, DO {need['do']}, AI {need['ai']}, AO {need['aq']}", INFO, "OWN-AB-PLCIO 'logic' row 1")
    mods = [m for m in rows if m["kind"] == "sm" and (not m.get("do") or m["do_type"] == do_type)]
    g = lambda u, k: u.get(k) or 0
    for cpu in cpus:
        rem = {k: max(need[k] - g(cpu, k), 0) for k in need}
        best = ((0, 0, 0), []) if not any(rem.values()) else None
        if best is None:
            for n in range(1, int(cpu["max_sm"]) + 1):
                for combo in combinations_with_replacement(mods, n):
                    cap = {k: sum(g(m, k) for m in combo) for k in need}
                    if any(cap[k] < rem[k] for k in need):
                        continue
                    bus_n = sum(m["bus_5v_ma"] for m in combo)
                    if bus_n > pw[cpu["model"]]["budget_5v_ma"] * factor:
                        continue
                    key = (n, sum(cap.values()) - sum(rem.values()), bus_n)
                    if best is None or key < best[0]:
                        best = (key, list(combo))
                if best:
                    break
        if best is None:
            continue
        plan = sorted(best[1], key=lambda m: (-(g(m, "di") + g(m, "do") + g(m, "ai") + g(m, "aq")), m["page"], m["model"]))
        units = [cpu, *plan]
        bus = sum(m["bus_5v_ma"] for m in plan)
        res.add("R-PLC-14", f"smallest G2 CPU covering DI {need['di']} / DO {need['do']} / AI {need['ai']} / AO {need['aq']} "
                f"with ≤ {cpu['max_sm']} modules", f"{cpu['model']} + {', '.join(m['model'] for m in plan) or 'no expansion'}",
                PASS, ", ".join(src(u) for u in units))
        cp = pw[cpu["model"]]
        if cpu["do_type"].startswith("dc"):
            res.add("R-PLC-13", "CPU output type", f"{cpu['model']}: solid state MOSFET (sourcing)", PASS,
                    f"SIE-S71200G2-SYS p.{cp['do_page']}")
        res.add("R-PLC-15", f"Σ module 5 V current ≤ CPU expansion current {cp['budget_5v_ma']:g} mA"
                + (f" × {factor:g}" if factor != 1 else ""), f"{bus:g} mA", PASS,
                f"SIE-S71200G2-SYS p.{cp['page']}; " + (", ".join(src(m) for m in plan) or src(cpu)))
        res.add("R-PLC-16", "CPU 24 V sensor supply available (for local inputs or relay coils)",
                f"{cp['sensor_24v_ma'] * factor:g} mA", INFO, f"SIE-S71200G2-SYS p.{cp['page']}")
        lplus = _g2_lplus(plan)
        res.add("R-PLC-16", "24 V DC load voltage (L+) of the signal modules", f"{lplus:g} mA (CPU's own consumption not "
                "printed)", INFO, ", ".join(src(m) for m in plan) or src(cpu))
        if fieldbus == "profinet":
            if fieldbus_devices is not None and fieldbus_devices > cpu["profinet_max_devices"]:
                return res.refuse("R-PLC-17", f"PROFINET IO devices ≤ {cpu['profinet_max_devices']}", f"{fieldbus_devices}",
                                  "SIE-ST70-2026 p.395")
            res.add("R-PLC-17", f"PROFINET IO devices ≤ {cpu['profinet_max_devices']}",
                    f"{fieldbus_devices if fieldbus_devices is not None else 'not given'}",
                    PASS if fieldbus_devices is not None else WARN, "SIE-ST70-2026 p.395")
        cap = {k: g(cpu, k) + sum(g(m, k) for m in plan) for k in need}
        sup = cp.get("in_24v_all_ma", 0) / 1000 + lplus / 1000
        res.add("R-PLC-24", "24 V drawn from the panel supply: CPU input current with all accessories + modules L+",
                f"{cpu['model']} {cp.get('in_24v_all_ma', 0):g} mA" + (" (AC-fed)" if not cp.get("in_24v_all_ma") else "")
                + f" + {lplus:g} mA = {sup:.4f} A", INFO, f"SIE-S71200G2-SYS p.{cp.get('power_page', cp['page'])}")
        res.value = {"make": "siemens", "family": "s7-1200g2", "cpu": cpu["model"], "cpu_article": cpu["article"],
                     "supply_24v_a": round(sup, 4),
                     "n_modules": len(plan), **{f"module_{i}": m["model"] for i, m in enumerate(plan, 1)},
                     "required_di": need["di"], "required_do": need["do"], "required_ai": need["ai"], "required_ao": need["aq"],
                     "capacity_di": cap["di"], "capacity_do": cap["do"], "capacity_ai": cap["ai"], "capacity_ao": cap["aq"],
                     "bus_5v_ma": bus, "i24_lplus_ma": lplus,
                     "parts": [{"article": u["article"], "role": "CPU" if u is cpu else "Signal module", "model": u["model"],
                                "di": g(u, "di"), "do": g(u, "do"), "source": src(u)} for u in units]}
        res.basis = "ST 70 · 2026 catalogue"
        return res
    return res.refuse("R-PLC-14", f"G2 CPU + modules covering DI {need['di']} / DO {need['do']} / AI {need['ai']} / "
                      f"AO {need['aq']} ({do_type})", "no 1212C / 1214C configuration fits", "SIE-ST70-2026 pp.392-461")


@lru_cache(maxsize=None)
def _sp() -> dict:
    return load_sourced_table(data_file("st70_s71500_et200sp.yaml"), ("article", "model", "kind"))


@lru_cache(maxsize=None)
def _cpu1513() -> dict:
    return {r["item"]: r for r in load_sourced_table(data_file("s71500_cpu1513_power.yaml"), ("item", "value"))["rows"]}


@lru_cache(maxsize=None)
def _module_power() -> dict:
    """ET 200SP module manuals: {model: {item: (value, source)}} (R-PLC-21 … 23)."""
    out = {}
    for f, model in (("et200sp_di16st_power.yaml", "DI 16x24VDC ST"), ("et200sp_dq16st_power.yaml", "DQ 16x24VDC/0.5A ST"),
                     ("et200sp_aq4st_power.yaml", "AQ 4xU/I ST"), ("et200sp_ai4st_power.yaml", "AI 4xU/I 2-wire ST")):
        d = load_sourced_table(data_file(f), ("item", "value"))
        out[model] = {r["item"]: (r["value"], f"{d['source']['ref']} p.{r['page']}") for r in d["rows"]}
    return out


def _derated(points: list, ambient: float):
    """R-PLC-23: total current at the next grid point at or above the ambient (no interpolation); None beyond the curve."""
    for temp, amps in points:
        if ambient <= temp:
            return amps, temp
    return None, points[-1][0]


def _s71500(res: Result, di, do, ai, ao, do_type, fieldbus, fieldbus_devices, cpu_name, mc_mb, dq_load_a,
            ambient_c=None, mounting=None) -> Result:
    prm = _rules()["params"]
    rows = _sp()["rows"]
    by = {r["model"]: r for r in rows}
    src = lambda r, k="page": f"SIE-ST70-2026 p.{r[k]}"
    remote = cpu_name is not None and str(cpu_name).lower() == "none"
    cpu = None if remote else by.get(cpu_name or prm["s71500_default_cpu"])
    if not remote and (cpu is None or cpu["kind"] != "cpu"):
        return res.invalid(f"cpu must be none or one of {', '.join(r['model'] for r in rows if r['kind'] == 'cpu')} "
                           f"(got {cpu_name})")
    mc_size = mc_mb if mc_mb is not None else prm["s71500_default_mc_mb"]
    mc = next((r for r in rows if r["kind"] == "mc" and r["size_mb"] == mc_size), None)
    if mc is None:
        return res.invalid(f"memory_card_mb must be one of {', '.join(str(r['size_mb']) for r in rows if r['kind'] == 'mc')}")
    if do_type != "sourcing":
        return res.refuse("R-PLC-19", "ET 200SP Standard digital outputs", f"{do_type}: only sourcing DQ ST modules are built",
                          "SIE-ST70-2026 p.1407")
    if fieldbus and fieldbus not in ("none", "profinet"):
        return res.refuse("R-PLC-20", f"S7-1500 with {fieldbus}", "PROFINET only in this selection", src(cpu))
    if remote:
        res.add("R-PLC-18", "remote-I/O panel", "no CPU here: the ET 200SP stations are run by a CPU in another panel",
                INFO, "designer / project")
    else:
        res.add("R-PLC-18", "S7-1500 CPU (designer's choice; program size and performance not assessed)",
                f"{cpu['model']} ({cpu['program_kb']:g} kB program / {cpu['data_kb']:g} kB data)" + ("" if cpu_name else
                " — not given: default (PLC-S4)"), INFO, src(cpu))
        res.add("R-PLC-18", "SIMATIC Memory Card required", f"{mc['model']}" + ("" if mc_mb is not None else
                " — size not given: default (PLC-S5)"), INFO, src(mc))
    f = _spare(prm)
    need = {k: math.ceil(v * f - 1e-9) for k, v in (("di", di), ("do", do), ("ai", ai), ("aq", ao))}
    res.add("R-PLC-08", f"required I/O = signals × {f:g} ({round((f - 1) * 100, 1):g} % spare)",
            f"DI {need['di']}, DO {need['do']}, AI {need['ai']}, AO {need['aq']}", INFO, "OWN-AB-PLCIO 'logic' row 1")
    # R-PLC-19: modules per signal type
    io = {r["model"]: r for r in rows if r["kind"] == "io"}
    plan, counts = [], {}

    def take(n16, n8, ch):
        return [n16] * math.ceil(ch / 16)   # R-PLC-19: 16-channel modules only (owner 2026-10-13)
    plan += take("DI 16x24VDC ST", "DI 8x24VDC ST", need["di"])
    plan += take("DQ 16x24VDC/0.5A ST", "DQ 8x24VDC/0.5A ST", need["do"])
    plan += ["AI 4xU/I 2-wire ST"] * math.ceil(need["ai"] / 4) + ["AQ 4xU/I ST"] * math.ceil(need["aq"] / 4)
    for key, name in (("n_di16", "DI 16x24VDC ST"), ("n_di8", "DI 8x24VDC ST"), ("n_dq16", "DQ 16x24VDC/0.5A ST"),
                      ("n_dq8", "DQ 8x24VDC/0.5A ST"), ("n_ai4", "AI 4xU/I 2-wire ST"), ("n_aq4", "AQ 4xU/I ST")):
        counts[key] = plan.count(name)
    res.add("R-PLC-19", "ET 200SP Standard modules (16-channel DI / DQ only; 4-channel AI / AQ)",
            ", ".join(f"{plan.count(n)} × {n}" for n in dict.fromkeys(plan)) or "none", PASS,
            ", ".join(src(io[n]) for n in dict.fromkeys(plan)))
    # R-PLC-20: stations
    im = next(r for r in rows if r["kind"] == "im")
    n_st = math.ceil(len(plan) / im["max_modules"])   # no I/O modules (PROFINET devices only) → no station
    devices = n_st + (fieldbus_devices or 0)
    if remote:
        res.add("R-PLC-20", f"stations: ≤ {im['max_modules']} modules per {im['model'].split(' incl')[0]}",
                f"{len(plan)} module(s) → {n_st} station(s); {devices} PROFINET device(s) to count at the controlling CPU",
                PASS, src(im, "spec_page"))
    elif devices > cpu["profinet_max_devices"]:
        return res.refuse("R-PLC-20", f"PROFINET IO devices ≤ {cpu['profinet_max_devices']}",
                          f"{n_st} station(s) + {fieldbus_devices or 0} drive(s) = {devices}", src(cpu, "spec_page"))
    if not remote:
        res.add("R-PLC-20", f"stations: ≤ {im['max_modules']} modules per {im['model'].split(' incl')[0]}",
                f"{len(plan)} module(s) → {n_st} station(s); {devices} PROFINET device(s) ≤ {cpu['profinet_max_devices']}",
                PASS, src(im, "spec_page"))
    # R-PLC-21: BaseUnits and potential groups
    gmax = prm["et200sp_group_max_a"]
    mp = _module_power()
    unknown = sorted({n for n in plan if n not in mp})
    # R-PLC-23: DQ 16 ST derating
    if "DQ 16x24VDC/0.5A ST" in plan:
        dq = mp["DQ 16x24VDC/0.5A ST"]
        mnt = (mounting or "horizontal").lower()
        pts, dsrc = dq[f"derating_{mnt}"]
        amb = ambient_c if ambient_c is not None else 40
        lim, at = _derated(pts, amb)
        per_mod = 16 * (0.5 if dq_load_a is None else float(dq_load_a))
        if lim is None:
            return res.refuse("R-PLC-23", f"DQ 16 ST derating ({mnt})", f"{amb:g} °C is beyond the curve (ends at {at} °C)", dsrc)
        res.add("R-PLC-23", f"DQ 16 ST outputs 16 × load ≤ derated total ({mnt}, {amb:g} °C → {at} °C point: {lim:g} A)"
                + ("" if ambient_c is not None else "; ambient not given: up to 40 °C assumed"),
                f"{per_mod:g} A", PASS if per_mod <= lim + 1e-9 else WARN, dsrc)
    load = 0.5 if dq_load_a is None else float(dq_load_a)
    light = dark = 0
    for s in range(n_st):
        mods = plan[s * im["max_modules"]:(s + 1) * im["max_modules"]]
        group = 0.0
        for i, name in enumerate(mods):
            m = io[name]
            # the current that flows (not capped at the module rating: an overloaded module still loads its group)
            cur = m.get("do", 0) * load if m.get("do") else 0.0
            cur += mp.get(name, {}).get("current_max_ma", (0, ""))[0] / 1000
            if i == 0 or group + cur > gmax + 1e-9:
                light += 1
                group = cur
            else:
                dark += 1
                group += cur
    bu_l = next(r for r in rows if r["kind"] == "bu" and r["starts_group"])
    bu_d = next(r for r in rows if r["kind"] == "bu" and not r["starts_group"])
    res.add("R-PLC-21", f"BaseUnits: light starts a potential group (max. {gmax:g} A), dark continues it; outputs at "
            f"{load:g} A per channel" + (" (not given: 0.5 A, inductive-load rule of the DQ 16 ST manual, PLC-S6)"
                                         if dq_load_a is None else ""),
            f"{light} light + {dark} dark" + (f"; supply current not held for {', '.join(unknown)}: group current partial"
                                              if unknown else ""), WARN if unknown else PASS, src(bu_l))
    # R-PLC-22: 24 V DC
    if remote:
        cpu_a, cpu_txt = 0.0, "no CPU"
    elif cpu["model"] == "CPU 1513-1 PN":
        cpu_a = _cpu1513()["current_rated_a"]["value"]
        cpu_txt = f"CPU {cpu_a:g} A (max. {_cpu1513()['current_max_a']['value']:g} A, SIE-CPU1513-MAN p.44)"
    else:
        cpu_a, cpu_txt = 0.0, f"{cpu['model']}: current not held"
    mod_a = sum(mp[n]["current_max_ma"][0] for n in plan if n in mp) / 1000
    i24_rows = ([] if remote else [{"item": cpu["model"], "qty": 1, "unit_a": cpu_a if cpu["model"] == "CPU 1513-1 PN"
                                    else None, "source": "SIE-CPU1513-MAN p.44" if cpu["model"] == "CPU 1513-1 PN"
                                    else "not held"}])
    i24_rows.append({"item": "IM 155-6 PN ST", "qty": n_st, "unit_a": im["current_ma"] / 1000, "source": src(im, "spec_page")})
    for n in dict.fromkeys(plan):
        i24_rows.append({"item": n, "qty": plan.count(n), "unit_a": mp[n]["current_max_ma"][0] / 1000 if n in mp else None,
                         "source": mp[n]["current_max_ma"][1] if n in mp else "manual not held"})
    i24 = round(cpu_a + n_st * im["current_ma"] / 1000 + mod_a, 3)
    partial = unknown or (not remote and cpu["model"] != "CPU 1513-1 PN")
    res.add("R-PLC-22", "24 V DC of the PLC electronics: CPU + interface modules + I/O modules (output loads excluded)",
            f"{cpu_txt} + {n_st} × {im['current_ma']:g} mA + modules {mod_a:g} A = {i24:g} A"
            + (f"; not held: {', '.join(unknown)}" if unknown else ""), WARN if partial else PASS,
            src(im, "spec_page") + "; " + "; ".join(sorted({mp[n]["current_max_ma"][1] for n in plan if n in mp})))
    parts = [] if remote else [
             {"article": cpu["article"], "role": "CPU", "model": cpu["model"], "qty": 1, "source": src(cpu)},
             {"article": mc["article"], "role": "Memory card", "model": mc["model"], "qty": 1, "source": src(mc)},
             {"article": next(r for r in rows if r["kind"] == "rail")["article"], "role": "Mounting rail",
              "model": "S7-1500 mounting rail 160 mm", "qty": 1, "source": "SIE-ST70-2026 p.524"}]
    parts += [{"article": im["article"], "role": "Interface module", "model": im["model"], "qty": n_st, "source": src(im)},
             {"article": bu_l["article"], "role": "BaseUnit (light)", "model": bu_l["model"], "qty": light, "source": src(bu_l)},
             {"article": bu_d["article"], "role": "BaseUnit (dark)", "model": bu_d["model"], "qty": dark, "source": src(bu_d)}]
    parts += [{"article": io[n]["article"], "role": "I/O module", "model": n, "qty": plan.count(n), "source": src(io[n])}
              for n in dict.fromkeys(plan)]
    g = lambda k: sum(io[n].get(k, 0) for n in plan)
    res.value = {"make": "siemens", "family": "s7-1500-et200sp", "cpu": "none" if remote else cpu["model"],
                 "cpu_article": None if remote else cpu["article"], "memory_card": None if remote else mc["model"], "n_stations": n_st, "n_modules": len(plan), **counts,
                 "n_bu_light": light, "n_bu_dark": dark, "required_di": need["di"], "required_do": need["do"],
                 "required_ai": need["ai"], "required_ao": need["aq"], "capacity_di": g("di"), "capacity_do": g("do"),
                 "capacity_ai": g("ai"), "capacity_ao": g("aq"), "i24_a": i24, "supply_24v_a": i24, "i24_rows": i24_rows, "parts": parts}
    res.basis = "ST 70 · 2026 catalogue + CPU 1513 manual"
    return res


def select(di: int, do: int, ai: int = 0, ao: int = 0, do_type: str | None = None, fieldbus: str | None = None,
           series: str | None = None, make: str | None = None, fieldbus_devices: int | None = None,
           family: str | None = None, cpu_supply: str | None = None, ambient_c: float | None = None,
           cpu: str | None = None, memory_card_mb: int | None = None, dq_load_a: float | None = None,
           mounting: str | None = None, spare_pct: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    if spare_pct is not None and not 0 <= float(spare_pct) <= 100:
        return res.invalid(f"spare_pct must be from 0 to 100 (got {spare_pct})")
    _SPARE.f = 1 + float(spare_pct) / 100 if spare_pct is not None else None
    try:
        return _select(res, di, do, ai, ao, do_type, fieldbus, series, make, fieldbus_devices, family, cpu_supply, ambient_c,
                       cpu, memory_card_mb, dq_load_a, mounting)
    finally:
        _SPARE.f = None


def _select(res, di, do, ai, ao, do_type, fieldbus, series, make, fieldbus_devices, family, cpu_supply, ambient_c,
            cpu, memory_card_mb, dq_load_a, mounting) -> Result:
    prm = _rules()["params"]
    do_type = (do_type or prm["default_do_type"]).lower()
    fieldbus = fieldbus.lower() if isinstance(fieldbus, str) else fieldbus
    make = (make or prm["default_make"]).lower()
    if min(di, do, ai, ao) < 0:
        return res.invalid("inputs and outputs must not be negative")
    if di + do + ai + ao == 0 and not (fieldbus == "profinet" and (fieldbus_devices or 0) >= 1):
        return res.invalid("give the number of inputs and outputs, or the PROFINET devices the PLC controls")
    if do_type not in ("sourcing", "sinking", "relay"):
        return res.invalid(f"do_type must be sourcing, sinking or relay (got {do_type})")
    if make not in ("omron", "siemens"):
        return res.invalid(f"make must be omron or siemens (got {make})")
    if make == "siemens":
        fam = (family or prm["default_siemens_family"]).lower()
        if fam not in ("s7-200smart", "s7-1200g2", "s7-1500-et200sp"):
            return res.invalid(f"family must be s7-200smart, s7-1200g2 or s7-1500-et200sp (got {family})")
        if fam == "s7-1500-et200sp":
            if mounting is not None and mounting not in ("horizontal", "vertical"):
                return res.invalid(f"mounting must be horizontal or vertical (got {mounting})")
            return _s71500(res, di, do, ai, ao, do_type, fieldbus, fieldbus_devices, cpu, memory_card_mb, dq_load_a,
                           ambient_c, mounting)
        if cpu_supply is not None and cpu_supply.upper() not in ("24VDC", "AC"):
            return res.invalid(f"cpu_supply must be 24VDC or AC (got {cpu_supply})")
        if fam == "s7-1200g2":
            return _s71200g2(res, di, do, ai, ao, do_type, fieldbus, fieldbus_devices, cpu_supply, ambient_c)
        return _siemens(res, di, do, ai, ao, do_type, fieldbus, fieldbus_devices)
    skipped = len(_cpus().get("skipped") or []) + len(_modules().get("skipped") or [])
    res.add("R-PLC-01", "complete database rows only",
            f"{len(_cpus()['rows'])} CPU(s), {len(_modules()['rows'])} module(s); {skipped} incomplete row(s) not used "
            "(NX1P / NX: no current or I/O count)", INFO, "OWN-AB-PLC, OWN-AB-PLCIO")
    if ai or ao:
        return res.refuse("R-PLC-02", "analog I/O", f"{ai} AI / {ao} AO: analog module selection is not built yet")
    f = _spare(prm)
    need_di, need_do = math.ceil(di * f - 1e-9), math.ceil(do * f - 1e-9)
    res.add("R-PLC-02", f"required I/O = signals × {f:g} ({round((f - 1) * 100, 1):g} % spare)", f"DI {di} → {need_di}, DO {do} → {need_do}", INFO,
            "OWN-AB-PLCIO 'logic' row 1")
    if fieldbus and fieldbus != "none":
        return res.refuse("R-PLC-06", f"PLC with {fieldbus} for the drives",
                          "no CPU in the database records a fieldbus: choose another PLC make and give its 24 V current")
    cpus = sorted((c for c in _cpus()["rows"] if c["do_type"] == do_type and (not series or c["series"] == series)),
                  key=lambda c: (c["max_io"], c["row"]))
    res.add("R-PLC-03", "output type", f"{do_type}: {len(cpus)} CPU(s)", INFO)
    for cpu in cpus:
        plan = _plan(cpu, need_di, need_do, do_type)
        if plan is None:
            continue
        units = [cpu, *plan]
        i24 = sum(_i24(u) for u in units)
        mods = ", ".join(m["model"] for m in plan) or "no expansion"
        res.add("R-PLC-04", f"smallest CPU covering DI {need_di} / DO {need_do} with ≤ {int(cpu['max_ext'])} module(s)",
                f"{cpu['model']} ({cpu['di']:g} DI / {cpu['do']:g} DO built in) + {mods}", PASS,
                f"OWN-AB-PLC db row {cpu['row']}" + "".join(f"; OWN-AB-PLCIO db_DIO row {m['row']}" for m in plan))
        blank = [u["model"] for u in units if u["i24_a"] is None]
        res.add("R-PLC-05", "24 V current = 24 V + 5 V × 5 / (24 × efficiency)",
                " + ".join(f"{u['model']} {_i24(u):.4f} A" for u in units) + f" = {i24:.4f} A", PASS)
        if blank:
            res.add("R-PLC-05", "24 V current in the database for every unit",
                    f"blank for {', '.join(blank)}: taken as 0", WARN)
        res.value = {"cpu": cpu["model"], "cpu_series": cpu["series"], "n_modules": len(plan),
                     **{f"module_{i}": m["model"] for i, m in enumerate(plan, 1)},
                     "required_di": need_di, "required_do": need_do,
                     "capacity_di": cpu["di"] + sum(m["di"] for m in plan),
                     "capacity_do": cpu["do"] + sum(m["do"] for m in plan), "i24_a": round(i24, 4),
                     "parts": [{"article": u["model"], "role": "CPU" if u is cpu else "I/O module",
                                "di": u["di"], "do": u["do"], "source": f"{'OWN-AB-PLC db' if u is cpu else 'OWN-AB-PLCIO db_DIO'} row {u['row']}"}
                               for u in units]}
        res.basis = "AutoBOM PLC database"
        return res
    return res.refuse("R-PLC-04", f"CPU + ≤ max modules covering DI {need_di} / DO {need_do} ({do_type})",
                      "no CPU in the database fits")


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
