"""Motor / feeder cable: Cu XLPE armoured 0.6/1 kV (IS 7098-1), Polycab or KEI data.
Rules: RULES.md / rules.yaml (R-CAB-01 … 13)."""
from __future__ import annotations

from functools import lru_cache
from math import sqrt
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "cable"
MAKES = {"polycab": "POLYCAB-LT-V9", "kei": "KEI-TH-2023"}
TABULATED = ("air", "ground", "duct")
NOT_TABULATED = ("tray", "ladder", "conduit", "trench", "wall", "clipped")
CORES = {3: ("3", "3.5", "4"), 1: ("2",)}
SPACINGS = ("touching", "150", "300", "450")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _data(make: str) -> dict:
    """All tables for one make, normalised: ratings, r/x/isc1 per size, temperature and group factors."""
    if make == "polycab":
        rat = load_sourced_table(data_file("polycab_2xwy_ratings.yaml"),
                                 ("cores", "size", "ground", "duct", "air", "product"))
        cond = load_sourced_table(data_file("polycab_conductor.yaml"), ("qty", "size", "value"))
        fac = load_sourced_table(data_file("polycab_factors.yaml"), ("kind", "factors"))
        el = {(r["qty"], r["size"]): r for r in cond["rows"]}
        rows = [{**r, "r": el[("r_ac90", r["size"])]["value"], "r_page": el[("r_ac90", r["size"])]["page"],
                 "x": el[("x50", r["size"])]["value"], "x_page": el[("x50", r["size"])]["page"],
                 "isc1": el[("isc1", r["size"])]["value"], "isc_page": el[("isc1", r["size"])]["page"]}
                for r in rat["rows"]]
    else:
        rat = load_sourced_table(data_file("kei_armoured_ratings.yaml"),
                                 ("cores", "size", "ground", "duct", "air", "r_ac90", "x50"))
        fac = load_sourced_table(data_file("kei_factors.yaml"), ("kind",))
        isc = {r["size"]: r for r in fac["rows"] if r["kind"] == "isc1"}
        rows = [{**r, "product": True, "r": r["r_ac90"], "r_page": r["page"], "x": r["x50"], "x_page": r["page"],
                 "isc1": isc[r["size"]]["value"], "isc_page": isc[r["size"]]["page"]} for r in rat["rows"]]
    temp = {r["kind"]: r for r in fac["rows"] if r["kind"] in TABULATED}
    group = {(r["kind"].removeprefix("group_"), int(r["cables"])): {**r, "factors": {str(k): v for k, v in
                                                                                       r["factors"].items()}}
             for r in fac["rows"] if r["kind"].startswith("group_")}
    return {"ref": MAKES[make], "reference": rat["reference"], "basis": rat["basis"], "basis_page": rat["basis_page"],
            "rows": rows, "temp": temp, "group": group}


def _p(make: str, page) -> str:
    ref = MAKES[make]
    if make == "kei":       # two printed handbook pages per PDF page (spread)
        return f"{ref} PDF p.{page} (printed {2 * page - 3}/{2 * page - 2})"
    return f"{ref} p.{page}"


def _vd_pct(phases, i, length_m, r, x, pf, u, runs) -> float:
    """pf None: the bound R·cos φ + X·sin φ ≤ √(R² + X²), which holds for every cos φ (R-CAB-09)."""
    k = sqrt(3) if phases == 3 else 2.0
    z = sqrt(r * r + x * x) if pf is None else r * pf + x * sqrt(max(0.0, 1 - pf * pf))
    return k * i * length_m / 1000 * z / runs / u * 100


def select(ib_a: float, length_m: float, voltage_v: float, pf_run: float | None = None, installation: str = "", ambient_c: float | None = None,
           in_a: float | None = None, overload_device: bool = True, phases: int = 3, cores: str | None = None,
           make: str | None = None, conductor: str = "Cu", frequency_hz: float = 50.0, other_cables: int = 0,
           group_spacing: str | None = None, depth_mm: float | None = None, soil_kmw: float | None = None,
           vd_limit_pct: float | None = None, start_multiple: float | None = None, pf_start: float | None = None,
           fault_ka: float | None = None, clearing_s: float | None = None, i2t_a2s: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]

    # --- input validation
    if not ib_a or ib_a <= 0:
        return res.invalid(f"design current Ib must be > 0 (got {ib_a})")
    if not length_m or length_m <= 0:
        return res.invalid(f"cable length must be > 0 m (got {length_m})")
    if not voltage_v or voltage_v <= 0:
        return res.invalid(f"voltage must be > 0 V (got {voltage_v})")
    if pf_run is not None and not 0 < pf_run <= 1:
        return res.invalid(f"running power factor must be 0 < cos φ ≤ 1 (got {pf_run})")
    if phases not in CORES:
        return res.invalid(f"phases must be 1 or 3 (got {phases})")
    cores = str(cores) if cores is not None else CORES[phases][0]
    if cores not in CORES[phases]:
        return res.invalid(f"{phases}-phase feeder: cores must be one of {', '.join(CORES[phases])} (got {cores})")
    make = (make or prm["make_default"]).lower()
    if make not in MAKES:
        return res.invalid(f"make must be one of {', '.join(MAKES)} (no held source for {make!r})")
    installation = (installation or "").lower()
    if installation not in TABULATED + NOT_TABULATED:
        return res.invalid(f"installation must be one of {', '.join(TABULATED)} (got {installation!r})")
    if ambient_c is None:
        return res.invalid("ambient_c (air temperature in air, ground temperature for ground / duct) is required")
    if overload_device and in_a is None:
        return res.invalid("in_a (rated / set current of the overload protective device) is required, "
                           "or set overload_device = false (e.g. a VFD protects the motor cable)")
    if other_cables is None or other_cables < 0:
        return res.invalid(f"other_cables must be ≥ 0 (got {other_cables})")
    if group_spacing is not None:
        group_spacing = str(group_spacing).lower().removesuffix("mm").strip()
        if group_spacing not in SPACINGS:
            return res.invalid(f"group_spacing must be one of {', '.join(SPACINGS)} (mm) (got {group_spacing})")
    if (start_multiple is None) != (pf_start is None):
        return res.invalid("starting check needs both start_multiple and pf_start (no defaults are assumed)")
    if start_multiple is not None and (start_multiple < 1 or not 0 < pf_start <= 1):
        return res.invalid("start_multiple must be ≥ 1 and 0 < pf_start ≤ 1")
    if i2t_a2s is not None and fault_ka is not None:
        return res.invalid("give either i2t_a2s or fault_ka + clearing_s, not both")
    if (fault_ka is None) != (clearing_s is None):
        return res.invalid("short-circuit check needs both fault_ka and clearing_s")
    limit = vd_limit_pct if vd_limit_pct is not None else prm["vd_run_limit_pct"]
    if limit <= 0:
        return res.invalid(f"vd_limit_pct must be > 0 (got {limit})")

    d = _data(make)
    basis = d["basis"]
    bp = _p(make, d["basis_page"])

    # --- scope (R-CAB-01)
    if str(conductor).lower() not in ("cu", "copper"):
        return res.refuse("R-CAB-01", "copper conductor", f"{conductor}: aluminium cable data not transcribed", bp)
    if voltage_v > 1100:
        return res.refuse("R-CAB-01", "system voltage ≤ 1100 V AC (650/1100 V cable)", f"{voltage_v:g} V", bp)
    if frequency_hz != 50:
        return res.refuse("R-CAB-01", "50 Hz (reactance tabulated at 50 Hz)", f"{frequency_hz:g} Hz", bp)
    res.add("R-CAB-01", "Cu XLPE armoured (2XWY) 650/1100 V, 50 Hz", f"{cores}-core, {voltage_v:g} V, {phases}-phase",
            PASS, bp)
    res.add("R-CAB-02", "one make for every value", f"{make} ({d['ref']})", INFO, "")

    # --- installation (R-CAB-03)
    if installation not in TABULATED:
        return res.refuse("R-CAB-03", "installation tabulated by the maker (air / ground / duct)",
                          f"{installation}: not tabulated by {make}", bp)
    if installation != "air":
        if depth_mm is not None and depth_mm != basis["depth_mm"]:
            return res.refuse("R-CAB-03", f"laying depth {basis['depth_mm']} mm (rating basis)", f"{depth_mm:g} mm",
                              bp)
        if soil_kmw is not None and soil_kmw != basis["soil_kmw"]:
            return res.refuse("R-CAB-03", f"soil thermal resistivity {basis['soil_kmw']} K.m/W (rating basis)",
                              f"{soil_kmw:g} K.m/W", bp)
    words = {"air": "in air", "ground": "buried direct in the ground", "duct": "in single-way buried duct"}
    res.add("R-CAB-03", "installation as tabulated", words[installation]
            + ("" if installation == "air" else f", soil {basis['soil_kmw']} K.m/W, depth {basis['depth_mm']} mm"),
            PASS, bp)

    # --- temperature (R-CAB-04, R-CAB-05)
    trow = d["temp"][installation]
    temps = sorted(int(t) for t in trow["factors"])
    if ambient_c > temps[-1]:
        return res.refuse("R-CAB-05", f"temperature ≤ {temps[-1]} °C (maker's table, no extrapolation)",
                          f"{ambient_c:g} °C", _p(make, trow["page"]))
    t_col = next((t for t in temps if t >= ambient_c), temps[0])
    k_t = float(trow["factors"][t_col])
    medium = "air" if installation == "air" else "ground"
    if t_col != ambient_c:
        res.add("R-CAB-05", "temperature between columns → next higher column; below the table → lowest column",
                f"{ambient_c:g} °C → {t_col} °C column", PASS, _p(make, trow["page"]))
    res.add("R-CAB-04", f"{medium} temperature rating factor", f"{t_col} °C: {k_t:g}", PASS, _p(make, trow["page"]))

    # --- grouping (R-CAB-06)
    def k_group(n: int):
        """(factor, row) or (None, reason)."""
        if n == 1:
            return 1.0, None
        row = d["group"].get((installation, n))
        if row is None:
            have = sorted(c for (inst, c) in d["group"] if inst == installation)
            why = (f"{make} gives no group factor for {words[installation]}" if not have
                   else f"{make} tabulates {have[0]} … {have[-1]} cables, not {n}")
            return None, why
        if group_spacing is None:
            return None, "spacing"
        return float(row["factors"][group_spacing]), row

    if other_cables:
        k, why = k_group(1 + other_cables)
        if k is None:
            if why == "spacing":
                return res.invalid("a group of cables needs group_spacing (touching / 150 / 300 / 450 mm)")
            return res.refuse("R-CAB-06", "maker's group factor for the cables in the group",
                              f"{1 + other_cables} cables: {why}", bp)

    # --- overload coordination (R-CAB-07)
    if overload_device:
        if in_a < ib_a - 1e-9:
            return res.refuse("R-CAB-07", "Ib ≤ In (overload coordination)", f"In {in_a:g} A < Ib {ib_a:g} A", "")
        need = in_a
    else:
        need = ib_a

    i2t = i2t_a2s if i2t_a2s is not None else ((fault_ka * 1000) ** 2 * clearing_s if fault_ka is not None else None)
    if clearing_s is not None and clearing_s > prm["sc_max_clearing_s"]:
        return res.refuse("R-CAB-12", f"clearing time ≤ {prm['sc_max_clearing_s']:g} s (adiabatic rating, RULE)",
                          f"{clearing_s:g} s", "")
    s_limit = prm["vd_start_limit_pct"]

    def evaluate(row, runs, kg):
        iz = runs * row[installation] * k_t * kg
        vd = _vd_pct(phases, ib_a, length_m, row["r"], row["x"], pf_run, voltage_v, runs)
        vds = (_vd_pct(phases, ib_a * start_multiple, length_m, row["r"], row["x"], pf_start, voltage_v, runs)
               if start_multiple is not None else None)
        fails = []
        if iz < need - 1e-9:
            fails.append("ampacity")
        if vd > limit + 1e-9:
            fails.append("voltage drop")
        if vds is not None and vds > s_limit + 1e-9:
            fails.append("starting voltage drop")
        if i2t is not None and i2t > (row["isc1"] * 1000) ** 2 * (1 + 1e-9):
            fails.append("short circuit")
        return iz, vd, vds, fails

    sizes = sorted((r for r in d["rows"] if r["cores"] == cores and r["product"]), key=lambda r: r["size"])
    chosen, no_group = None, None
    for runs in range(1, prm["max_runs"] + 1):
        kg, grow = k_group(runs + other_cables)
        if kg is None:
            no_group = grow if grow != "spacing" else None
            if grow == "spacing":
                return res.invalid("parallel runs form a group: give group_spacing (touching / 150 / 300 / 450 mm)")
            break
        for i, row in enumerate(sizes):
            iz, vd, vds, fails = evaluate(row, runs, kg)
            if not fails:
                chosen = (row, runs, kg, grow, iz, vd, vds, i)
                break
        if chosen:
            break

    if chosen is None:
        big = sizes[-1]
        _, _, _, fails = evaluate(big, 1, k_group(1 + other_cables)[0])
        if no_group is not None:
            return res.refuse("R-CAB-06", "one run is not enough; parallel runs need the maker's group factor",
                              f"largest {cores}C×{big['size']} fails {', '.join(fails)}; {no_group}", bp)
        return res.refuse("R-CAB-08", f"a size with up to {prm['max_runs']} parallel runs",
                          f"none passes ({cores}C×{big['size']} single run fails {', '.join(fails)})", bp)

    row, runs, kg, grow, iz, vd, vds, idx = chosen
    rp = _p(make, row["page"])
    if idx == 0:
        bound = "smallest size offered"
    else:
        bound = ", ".join(evaluate(sizes[idx - 1], runs, kg)[3])
    others = [r["size"] for r in d["rows"] if r["cores"] == cores and not r["product"]]
    res.add("R-CAB-13", f"{cores}-core sizes listed as products",
            f"{sizes[0]['size']} … {sizes[-1]['size']} mm²"
            + (f" (rating row but no product: {', '.join(f'{s} mm²' for s in others)})" if others else ""), PASS, rp)
    n = runs + other_cables
    if n > 1:
        res.add("R-CAB-06", "group factor", f"{n} cables, spacing {group_spacing}: {kg:g}", PASS,
                _p(make, grow["page"]))
    else:
        res.add("R-CAB-06", "single cable (no grouping)", "group factor 1", PASS, bp)
    res.add("R-CAB-08", f"fewest runs (≤ {prm['max_runs']}), then smallest size",
            f"{runs} × {cores}C × {row['size']} mm²; smaller size fails: {bound}", PASS, rp)
    tab = row[installation]
    iz_txt = (f"{runs} × " if runs > 1 else "") + f"{tab} A × {k_t:g}" + (f" × {kg:g}" if kg != 1 else "") \
        + f" = {iz:.2f} A"
    if overload_device:
        res.add("R-CAB-07", "Ib ≤ In ≤ Iz", f"{ib_a:g} ≤ {in_a:g} ≤ {iz_txt}", PASS, rp)
    else:
        res.add("R-CAB-07", "Iz ≥ Ib (cable not overload-protected by the device; e.g. VFD protects it)",
                f"{iz_txt} ≥ {ib_a:g} A", PASS, rp)
    res.add("R-CAB-09", "ΔU with R(AC, 90 °C) and X(50 Hz)", f"R {row['r']:g}, X {row['x']:g} Ω/km", PASS,
            f"{_p(make, row['r_page'])}, {_p(make, row['x_page'])}" if row["r_page"] != row["x_page"]
            else _p(make, row["r_page"]))
    res.add("R-CAB-10", f"running voltage drop ≤ {limit:g} %"
            + (" (project limit)" if vd_limit_pct is not None else " (RULE parameter)"),
            f"{vd:.2f} % at {ib_a:g} A, {length_m:g} m, "
            + (f"cos φ {pf_run:g}" if pf_run is not None else "cos φ not given: worst case √(R² + X²)"), PASS, "")
    if vds is not None:
        res.add("R-CAB-11", f"starting voltage drop ≤ {s_limit:g} %",
                f"{vds:.2f} % at {start_multiple:g} × Ib, cos φ {pf_start:g}", PASS, "")
    else:
        res.add("R-CAB-11", "starting voltage drop", "not checked (start_multiple / pf_start not given)", INFO, "")
    if i2t is not None:
        res.add("R-CAB-12", "I²t ≤ (1-s rating)² per run",
                f"{i2t:.3g} A²s ≤ ({row['isc1']:g} kA)² = {(row['isc1'] * 1000) ** 2:.3g} A²s", PASS,
                _p(make, row["isc_page"]))
    else:
        res.add("R-CAB-12", "short-circuit withstand", "not checked (no let-through I²t / fault current given)", INFO,
                _p(make, row["isc_page"]))

    res.value = {"make": make, "cable": f"{runs} × {cores}C × {row['size']} mm² Cu XLPE armoured"
                 + (" (2XWY)" if make == "polycab" else ""),
                 "cores": cores, "size_mm2": row["size"], "runs": runs, "iz_a": round(iz, 2), "k_temp": k_t,
                 "k_group": kg, "vd_pct": round(vd, 2), "vd_start_pct": round(vds, 2) if vds is not None else None,
                 "isc1_ka": row["isc1"], "bound_by": bound}
    res.basis = f"{make} data"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
