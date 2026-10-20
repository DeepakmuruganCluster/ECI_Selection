"""VFD: SINAMICS G120 PM240-2, 400 V. Rules: RULES.md / rules.yaml (R-VFD-01 … 13)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "vfd"
REF = "SIE-PM240-2"
FLC_BASES = ("nameplate", "datasheet", "guide", "guide_voltage_scaled", "calculated")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _modules() -> dict:
    return load_sourced_table(data_file("pm240_2_400v.yaml"),
                              ("order_no", "order_no_c2", "frame", "lo_kw", "lo_in", "lo_out", "ho_kw", "ho_in",
                               "ho_out", "fuse", "fuse_a", "loss_w", "air_ls"))


@lru_cache(maxsize=None)
def _derating() -> dict:
    return load_sourced_table(data_file("pm240_2_derating.yaml"), ("group", "duty", "pct"))


@lru_cache(maxsize=None)
def _lengths() -> dict:
    return load_sourced_table(data_file("pm240_2_cable_lengths.yaml"),
                              ("group", "filter", "shielded", "reactors", "v_min", "v_max", "max_m"))


@lru_cache(maxsize=None)
def _protection() -> dict:
    return load_sourced_table(data_file("pm240_2_protection.yaml"),
                              ("module", "type", "article", "max_a", "icc_ka", "phased_out"))


@lru_cache(maxsize=None)
def _msp_table() -> dict:
    return load_sourced_table(data_file("3rv2_class10.yaml"), ("article", "family", "lo", "hi", "icu_ka"))


@lru_cache(maxsize=None)
def _fuse_sizes() -> dict:
    return load_sourced_table(data_file("3na_fuse_sizes.yaml"), ("article", "size", "in_a"))


@lru_cache(maxsize=None)
def _fuse_switches() -> dict:
    return load_sourced_table(data_file("3np1_fuse_switch.yaml"), ("size", "iu_a", "article"))


@lru_cache(maxsize=None)
def _own_cu() -> dict:
    return load_sourced_table(data_file("own_control_units.yaml"), ("series", "article", "fieldbus"))


@lru_cache(maxsize=None)
def _own_cu_logic() -> dict:
    return load_sourced_table(data_file("own_cu_logic.yaml"), ("branch", "fieldbus", "series"))


@lru_cache(maxsize=None)
def _own_mc_logic() -> dict:
    return load_sourced_table(data_file("own_memory_card_logic.yaml"), ("cu250s", "advanced", "positioning", "copy"))


FIELDBUS = {"none": "none", "modbus": "modbus", "profibus": "profibus", "profinet": "profinet", "ethernet_ip": "profinet"}


def _pp(page) -> str:
    return f"SIE-G120-PROT p.{page}"


@lru_cache(maxsize=None)
def _reactors() -> dict:
    return load_sourced_table(data_file("pm240_2_reactors.yaml"), ("kind", "module", "article"))


def _p(page) -> str:
    """PDF page and the page number printed on it (this manual prints 2 lower)."""
    off = int(_modules()["reference"].get("printed_page_offset", 0))
    return f"{REF} PDF p.{page} (printed {page + off})" if off else f"{REF} p.{page}"


def _stem(order_no: str) -> str:
    return order_no[:15]          # 6SL3210-1PE21-8


def _derate_group(frame: str) -> str:
    return "FSA-FSC" if frame in ("FSA", "FSB", "FSC") else "FSD-FSF"


def _length_group(frame: str) -> str:
    return "FSA-FSC" if frame in ("FSA", "FSB", "FSC") else ("FSF" if frame == "FSF" else "FSD-FSE")


def select(kw: float, flc_a: float, ambient_c: float | None = None, cable_m: float | None = None,
           fault_ka: float | None = None, flc_basis: str | None = None, duty: str | None = None,
           altitude_m: float | None = None, voltage_v: float = 400.0, phases: int = 3,
           cable_shielded: bool = True, emc_filter: str = "none", network_uk_pct: float | None = None,
           client_line_reactor_up_to_kw: float | None = None, protection: str = "fuse",
           preferred_family: str | None = None, earthing: str = "TN", cu_encoder: bool | None = None,
           cu_safety: str | None = None, cu_sbc: bool | None = None, cu_fieldbus: str | None = None,
           mc_basic_positioning: bool | None = None, mc_copy_parameters: bool | None = None,
           mc_customer_article: str | None = None, fuse_holder: str | None = None, msp_range: str | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    mods = _modules()
    cond, cpage = mods["conditions"], mods["condition_pages"]

    # --- input validation
    if not kw or kw <= 0:
        return res.invalid(f"motor kW must be > 0 (got {kw})")
    if not flc_a or flc_a <= 0:
        return res.invalid(f"FLC must be > 0 (got {flc_a})")
    if ambient_c is None:
        return res.invalid("ambient_c (air temperature around the drive, inside the panel) is required")
    if not cable_m or cable_m <= 0:
        return res.invalid("cable_m (motor cable length) is required")
    if fault_ka is None or fault_ka <= 0:
        return res.invalid("fault_ka (prospective short-circuit current at the drive) is required")
    duty = duty or prm["duty_default"]
    if duty not in ("normal", "heavy"):
        return res.invalid(f"duty must be normal or heavy (got {duty})")
    if emc_filter not in ("none", "C2"):
        return res.invalid(f"emc_filter must be none or C2 (got {emc_filter})")
    if protection not in ("fuse", "msp", "breaker"):
        return res.invalid(f"protection must be fuse, msp or breaker (got {protection})")
    want = None
    if msp_range is not None:                      # R-VFD-19: the client's MSP setting range, 'lo-hi' or 'hi' in A
        try:
            want = tuple(float(x) for x in str(msp_range).replace("…", "-").replace(" ", "").split("-"))
        except ValueError:
            want = ()
        if len(want) not in (1, 2) or (len(want) == 2 and not 0 < want[0] < want[1]):
            return res.invalid(f"msp_range must be 'low-high' or 'high' in A (got {msp_range!r})")
    if fuse_holder is not None and fuse_holder != "switch_disconnector":
        return res.invalid(f"fuse_holder must be switch_disconnector (got {fuse_holder})")
    if earthing not in ("TN", "TT", "IT"):
        return res.invalid(f"earthing must be TN, TT or IT (got {earthing})")
    if cu_safety is not None and cu_safety not in ("none", "sto", "advanced"):
        return res.invalid(f"cu_safety must be none, sto or advanced (got {cu_safety})")
    if flc_basis is not None and flc_basis not in FLC_BASES:
        return res.invalid(f"flc_basis must be one of {', '.join(FLC_BASES)} (got {flc_basis})")
    altitude = altitude_m if altitude_m is not None else prm["altitude_default_m"]

    # --- scope
    if phases != 3 or not cond["voltage_min_v"] <= voltage_v <= cond["voltage_max_v"]:
        return res.refuse("R-VFD-01", f"3-phase {cond['voltage_min_v']} … {cond['voltage_max_v']} V",
                          f"{phases}-phase {voltage_v:g} V", _p(cpage["voltage"]))
    alt_max = _derating()["conditions"]["altitude_max_m"]
    if altitude > alt_max:
        return res.refuse("R-VFD-01", f"installation altitude ≤ {alt_max} m (scope)", f"{altitude:g} m", _p(118))
    res.add("R-VFD-01", "3-phase 380 … 480 V, altitude ≤ 1000 m",
            f"{voltage_v:g} V, {altitude:g} m" + ("" if altitude_m is not None else " (assumed)"), PASS,
            _p(cpage["voltage"]))
    if fault_ka > cond["max_fault_ka"]:
        return res.refuse("R-VFD-06", f"short-circuit current ≤ {cond['max_fault_ka']} kA", f"{fault_ka:g} kA",
                          _p(cpage["fault"]))
    res.add("R-VFD-06", f"short-circuit current ≤ {cond['max_fault_ka']} kA", f"{fault_ka:g} kA", PASS,
            _p(cpage["fault"]))

    # --- derating temperature
    temps = sorted(int(t) for t in _derating()["rows"][0]["pct"])
    t_col = next((t for t in temps if t >= ambient_c), None)
    if t_col is None:
        return res.refuse("R-VFD-03", f"ambient ≤ {temps[-1]} °C (derating tables)", f"{ambient_c:g} °C", _p(118))
    rating = "HO" if duty == "heavy" else "LO"
    key = rating.lower()
    res.add("R-VFD-02", f"{duty} duty → {rating} base-load rating", rating, PASS, _p(99))

    def pct(frame):
        row = next(r for r in _derating()["rows"] if r["group"] == _derate_group(frame) and r["duty"] == rating)
        return float(row["pct"][t_col]) / 100, row

    # --- module
    by_kw = [m for m in mods["rows"] if m[f"{key}_kw"] >= kw]
    if not by_kw:
        return res.refuse("R-VFD-04", f"a module with {rating} power ≥ motor kW",
                          f"{kw:g} kW > largest {mods['rows'][-1][f'{key}_kw']:g} kW", _p(105))
    chosen = None
    for m in by_kw:
        k, drow = pct(m["frame"])
        if m[f"{key}_out"] * k >= flc_a - 1e-9:
            chosen, k_used, drow_used = m, k, drow
            break
    if chosen is None:
        return res.refuse("R-VFD-04", f"derated {rating} output current ≥ FLC",
                          f"no module up to {by_kw[-1][f'{key}_kw']:g} kW gives {flc_a:g} A at {ambient_c:g} °C", _p(105))
    m = chosen
    out_a = round(m[f"{key}_out"] * k_used, 2)
    temp_note = f"{ambient_c:g} °C → {t_col} °C column" if t_col != ambient_c else f"{t_col} °C"
    res.add("R-VFD-03", "derating at the next table temperature (no interpolation)",
            f"{temp_note}: {k_used:.0%} (Table {drow_used['table']}, {_derate_group(m['frame'])})", PASS,
            _p(drow_used["page"]))
    upsized = m is not by_kw[0]
    res.add("R-VFD-04", f"{rating} power ≥ {kw:g} kW and derated output ≥ FLC {flc_a:g} A",
            f"{m['order_no']} {m['frame']}: {m[f'{key}_kw']:g} kW, {m[f'{key}_out']:g} A × {k_used:.2f} = {out_a:g} A"
            + (f" — upsized from {by_kw[0][f'{key}_kw']:g} kW because of the derating" if upsized else ""),
            WARN if upsized else PASS, _p(m["page"]))
    share = kw / m[f"{key}_kw"] * 100
    if share < cond["motor_power_min_pct"]:
        return res.refuse("R-VFD-05", f"motor power ≥ {cond['motor_power_min_pct']} % of converter power",
                          f"{kw:g} / {m[f'{key}_kw']:g} kW = {share:.0f} %", _p(cpage["motor_power"]))
    res.add("R-VFD-05", "motor power 25 … 150 % of converter power", f"{share:.0f} %", PASS, _p(cpage["motor_power"]))

    order_no = m["order_no_c2"] if emc_filter == "C2" else m["order_no"]
    # --- protective device (Siemens list for the module)
    pt = _protection()
    names = {"fuse": "LV HRC fuse", "msp": "motor starter protector", "breaker": "circuit breaker"}
    i_in = m[f"{key}_in"]
    listed = [r for r in pt["rows"] if r["module"] == _stem(m["order_no"]) and r["type"] == protection]
    if not listed:
        return res.refuse("R-VFD-07", f"a {names[protection]} listed by Siemens for {m['order_no']}",
                          "none listed: use another protection type", _pp(pt["pages"][protection]))
    if protection == "msp" and earthing == "IT":
        return res.refuse("R-VFD-15", "MSP short-circuit ratings valid for TN / TT systems only", "IT system",
                          _pp(pt["pages"]["msp"]))
    if preferred_family:
        fam = [r for r in listed if r["article"].startswith(preferred_family)]
        if not fam:
            return res.refuse("R-VFD-14", f"preferred family {preferred_family} listed by Siemens for this drive",
                              "listed: " + ", ".join(sorted({r['article'][:4] for r in listed})),
                              _pp(pt["pages"][protection]))
        listed = fam
    usable = [r for r in listed if not r["phased_out"] and r["icc_ka"] >= fault_ka and r["max_a"] >= i_in]
    skipped = [r for r in listed if r["phased_out"]]
    if not usable:
        best = max((r["icc_ka"] for r in listed if not r["phased_out"]), default=0)
        return res.refuse("R-VFD-07", f"listed {names[protection]}, not phased out, ICC ≥ {fault_ka:g} kA, "
                                      f"rating ≥ input {i_in:g} A",
                          f"highest ICC available {best:g} kA" + (f"; phased out: {len(skipped)}" if skipped else ""),
                          _pp(pt["pages"][protection]))
    dev = usable[0]
    res.add("R-VFD-07", f"{names[protection]} listed for {_stem(m['order_no'])}: ICC ≥ {fault_ka:g} kA, "
                        f"rating ≥ input {i_in:g} A",
            f"{dev['article']} up to {dev['max_a']:g} A, ICC {dev['icc_ka']:g} kA"
            + (f" (phased-out devices skipped: {', '.join(r['article'] for r in skipped)})" if skipped else ""),
            PASS, _pp(dev["page"]))
    if len(usable) > 1:
        res.add("R-VFD-14", "several listed devices qualify → first in Siemens' table order",
                ", ".join(r["article"] for r in usable), PASS, _pp(dev["page"]))
    if protection == "msp":
        res.add("R-VFD-15", "MSP ratings valid for TN / TT", earthing, PASS, _pp(pt["pages"]["msp"]))
    # --- R-VFD-19 (owner 2026-10-20, RFQ part 3): a motor starter protector sized to the drive's input current, of a type
    # Siemens lists for the module (same type, lower rating allowed — p.3), from the IC 10 3RV2 table
    if protection == "msp":
        types = {r["article"][:7]: r for r in usable}
        rows = [r for r in _msp_table()["rows"] if r["family"] in types and r["hi"] <= types[r["family"]]["max_a"] + 1e-9
                and r["icu_ka"] >= fault_ka - 1e-9 and r["hi"] >= i_in - 1e-9]
        if not rows:
            return res.refuse("R-VFD-19", f"a 3RV of a listed type ({', '.join(types)}) rated ≥ the input {i_in:g} A, "
                              f"Icu ≥ {fault_ka:g} kA", "none in IC 10 pp.7/25-7/28", "SIE-IC10-2026 p.639")
        order = list(types)
        rows.sort(key=lambda r: (order.index(r["family"]), r["hi"]))     # Siemens' order (smaller size first), then the smallest rating
        pick = rows[0]
        if want:
            match = [r for r in _msp_table()["rows"] if (len(want) == 2 and abs(r["lo"] - want[0]) < 1e-6 and abs(r["hi"] - want[1]) < 1e-6)
                     or (len(want) == 1 and abs(r["hi"] - want[0]) < 1e-6)]
            ok = [r for r in match if r in rows]
            if ok:
                pick = ok[0]
                res.add("R-VFD-19", "the client's MSP range fits the drive (listed type, rated ≥ the input current, Icu)",
                        f"{msp_range} A → {pick['article']}", PASS, f"SIE-IC10-2026 p.{pick['page']}")
            else:
                why = (f"the client's {msp_range} A is below the drive's input current {i_in:g} A" if want[-1] < i_in - 1e-9
                       else f"the client's {msp_range} A is not a 3RV2 setting range in IC 10" if not match
                       else f"the client's {msp_range} A ({', '.join(r['article'] for r in match)}) is not a type Siemens lists for "
                            f"this drive, or its Icu is below {fault_ka:g} kA")
                res.add("R-VFD-19", "the client's MSP range for the drive", why + f" — {pick['article']} ({pick['lo']:g} … {pick['hi']:g} A) "
                        "offered instead (owner 2026-10-20: sized to the drive); tell the client", WARN, f"SIE-IC10-2026 p.{pick['page']}")
        res.add("R-VFD-19", "MSP: a listed type, rated ≥ the drive's input current (set at max(input, bottom of range)), Icu ≥ fault",
                f"{pick['article']}: {pick['lo']:g} … {pick['hi']:g} A, set {max(i_in, pick['lo']):g} A for input {i_in:g} A, Icu {pick['icu_ka']:g} kA (type {pick['family']}, "
                f"listed up to {types[pick['family']]['max_a']:g} A, ICC {types[pick['family']]['icc_ka']:g} kA)", PASS,
                f"SIE-IC10-2026 p.{pick['page']}, SIE-G120-PROT p.11")
        dev = {**types[pick["family"]], "article": pick["article"], "max_a": pick["hi"]}

    # --- R-VFD-17 / 18 (owner 2026-10-20, RFQ part 2): a fuse in each line conductor, and what holds them
    prot_qty, holder = 1, None
    if protection == "fuse":
        prot_qty = 3
        res.add("R-VFD-17", "one fuse in each line conductor L1, L2, L3", f"3 × {dev['article']} per drive", PASS,
                "SIE-PM240-2 p.60 (Figure 4-5, printed 58)")
        size = next((r for r in _fuse_sizes()["rows"] if r["article"] == dev["article"]), None)
        if fuse_holder is None:
            res.add("R-VFD-18", "what holds the drive's fuses", "not given (the panel asks it: fuse_holder)",
                    INFO, "rules.yaml (owner 2026-10-20)")
        elif size is None:                       # the drive stays selected; only its holder is open
            res.add("R-VFD-18", f"the size of {dev['article']} (to choose its holder)",
                    "not transcribed (LV 10 · 2026 pp.7/46-7/48: sizes 000, 00 and 1 only) — holder not selected", WARN,
                    "SIE-LV10-2026 p.570")
            sw = None
        else:
            sw = next((r for r in _fuse_switches()["rows"] if r["size"] == size["size"] and r["iu_a"] >= size["in_a"]), None)
            if sw is None:
                res.add("R-VFD-18", f"a 3NP1 fuse switch disconnector for size {size['size']} fuses",
                        "none transcribed for this size — holder not selected", WARN, "SIE-LV10-2026 p.713")
        if fuse_holder is not None and size is not None and sw is not None:
            holder = sw["article"]
            res.add("R-VFD-18", "fuse switch disconnector for the fuse size (3-pole, floor mounting, without fuse monitoring)",
                    f"{dev['article']} is size {size['size']} → {sw['article']} NH{sw['size']}, Iu {sw['iu_a']:g} A",
                    PASS, f"SIE-LV10-2026 p.{size['page']}, p.{sw['page']}")
    vols = pt["conditions"]["min_enclosure_m3"]
    need_vol = protection != "fuse" or fault_ka > pt["conditions"]["fuse_no_enclosure_limit_up_to_ka"]
    min_vol = vols.get(m["frame"]) if need_vol else None
    res.add("R-VFD-16", "minimum enclosure volume for this drive + protection",
            f"{min_vol:g} m³ (to the enclosure component)" if min_vol else "no restriction", INFO,
            _pp(pt["pages"][protection]))

    # --- line reactor
    small = m["frame"] in ("FSA", "FSB", "FSC")
    line = None
    stem = _stem(m["order_no"])
    lr = next((r for r in _reactors()["rows"] if r["kind"] == "line" and r["module"] == stem), None)
    if not small:
        res.add("R-VFD-08", "line reactor", f"{m['frame']}: no line impedance restriction, none needed"
                + (" (client rule not applicable)" if client_line_reactor_up_to_kw and kw <= client_line_reactor_up_to_kw
                   else ""), PASS, _p(cpage["voltage"]))
    elif client_line_reactor_up_to_kw and kw <= client_line_reactor_up_to_kw:
        line = lr
        res.add("R-VFD-08", f"client rule: line reactor up to {client_line_reactor_up_to_kw:g} kW", lr["article"], PASS,
                _p(lr["page"]))
    elif network_uk_pct is not None and network_uk_pct < 1:
        line = lr
        res.add("R-VFD-08", "line impedance uk < 1 % → line reactor", f"uk {network_uk_pct:g} % → {lr['article']}",
                PASS, _p(lr["page"]))
    elif network_uk_pct is None:
        res.add("R-VFD-08", "FSA … FSC without line reactor need 1 % ≤ uk < 4 %",
                "uk not given: confirm the supply impedance, or add the line reactor", WARN, _p(cpage["voltage"]))
    elif network_uk_pct >= 4:
        res.add("R-VFD-08", "FSA … FSC need 1 % ≤ uk < 4 %", f"uk {network_uk_pct:g} % is outside the stated range",
                WARN, _p(cpage["voltage"]))
    else:
        res.add("R-VFD-08", "FSA … FSC need 1 % ≤ uk < 4 %", f"uk {network_uk_pct:g} %: no line reactor needed",
                PASS, _p(cpage["voltage"]))

    # --- motor cable length → output reactors
    grp = _length_group(m["frame"])
    options = sorted((r for r in _lengths()["rows"]
                      if r["group"] == grp and r["filter"] == emc_filter and r["shielded"] == cable_shielded
                      and r["v_min"] <= voltage_v <= r["v_max"]), key=lambda r: r["reactors"])
    fit = next((r for r in options if cable_m <= r["max_m"]), None)
    kind = "shielded" if cable_shielded else "unshielded"
    listed = "; ".join(f"{r['reactors']} reactor(s): {r['max_m']} m" for r in options) or "no permitted combination"
    if fit is None:
        return res.refuse("R-VFD-09", f"{kind} motor cable within the permitted length ({grp}, filter {emc_filter}, "
                                      f"{voltage_v:g} V)", f"{cable_m:g} m; permitted: {listed}",
                          _p(options[0]["page"] if options else (63 if grp == "FSF" else 62)))
    res.add("R-VFD-09", f"{kind} motor cable within the permitted length ({grp}, filter {emc_filter})",
            f"{cable_m:g} m ≤ {fit['max_m']} m with {fit['reactors']} output reactor(s)", PASS, _p(fit["page"]))
    out_r, qty = None, fit["reactors"]
    if qty:
        out_r = next(r for r in _reactors()["rows"] if r["kind"] == "output" and r["module"] == stem)
        res.add("R-VFD-10", "output reactor for the module" + (" (two in series)" if qty == 2 else ""),
                f"{qty} × {out_r['article']}", PASS, _p(out_r["page"]))
        res.add("R-VFD-10", "with output reactor: pulse frequency ≤ 4 kHz, output frequency ≤ 150 Hz",
                "set p0230 at commissioning", INFO, _p(160))

    res.add("R-VFD-11", "motor cable ohmic losses < 5 % of converter rating", "checked with the cable component", INFO,
            _p(62))
    # --- control unit, operator panel, memory card (company logic and database)
    cu = None
    answered = cu_encoder is not None and cu_fieldbus is not None and (cu_encoder or cu_safety is not None)
    if not answered:
        res.add("R-VFD-12", "Control Unit", "not selected: answer encoder, safety and fieldbus", INFO, "")
    else:
        if cu_encoder:
            branch = "encoder"
        elif cu_safety == "advanced":
            branch = "sbc" if cu_sbc else "advanced"
        else:
            branch = cu_safety
        bus = FIELDBUS.get(str(cu_fieldbus).lower())
        leaf = next((r for r in _own_cu_logic()["rows"] if r["branch"] == branch and r["fieldbus"] == bus), None)
        if leaf is None:
            res.add("R-VFD-17", "a Control Unit for the requested fieldbus",
                    f"{cu_fieldbus}: part not available for other fieldbus communications", WARN, "OWN-CU-LOGIC-ALT p.1")
        else:
            cu = next(r for r in _own_cu()["rows"] if r["series"] == leaf["series"])
            res.add("R-VFD-17", "Control Unit from the company selection logic",
                    f"{branch} → {cu_fieldbus} → {cu['series']} {cu['article']}", PASS, "OWN-CU-LOGIC-ALT p.1")
            need = {"sto": ["STO"], "advanced": ["SS1", "SLS", "SSM", "SDI"]}.get(cu_safety or "none", [])
            if cu_sbc:
                need = need + ["SBC"]
            missing = [f for f in need if cu["safety"].get(f) not in ("yes", "License")]
            licensed = [f for f in need if cu["safety"].get(f) == "License"]
            ok_bus = bus == "none" or (bus in cu["fieldbus"] or str(cu_fieldbus).lower() in cu["fieldbus"])
            res.add("R-VFD-18", "Control Unit offers the requested functions (company database)",
                    ("missing: " + ", ".join(missing) if missing else "safety functions available")
                    + (f"; licence on the memory card for {', '.join(licensed)}" if licensed else "")
                    + ("" if ok_bus else f"; fieldbus {cu_fieldbus} not listed"),
                    WARN if missing or not ok_bus else PASS, f"OWN-VFD-DB row {cu['row']}")
        res.add("R-VFD-12", "Control Unit permitted ambient", "not checked: CU240E-2 / CU230P-2 manual not held",
                INFO, "")
    bop = _own_cu()["operator_panel"]
    res.add("R-VFD-19", "operator panel for every drive", f"{bop['name']} {bop['article']}", PASS,
            f"OWN-VFD-DB {bop['sheet']} row {bop['row']}")
    mc = None
    if mc_customer_article:
        mc = mc_customer_article
        res.add("R-VFD-20", "memory card: customer preference takes precedence", mc, PASS, "OWN-MC-LOGIC p.1")
    elif mc_copy_parameters is not None or (cu and cu["series"].startswith("CU250S")):
        cu250 = bool(cu and cu["series"].startswith("CU250S"))
        adv = cu_safety == "advanced"
        pos = bool(mc_basic_positioning)
        cp = bool(mc_copy_parameters)
        match = lambda v, x: v == "any" or v == x
        row = next(r for r in _own_mc_logic()["rows"] if r["cu250s"] == cu250 and match(r["advanced"], adv)
                   and match(r["positioning"], pos) and match(r["copy"], cp))
        mc = row["article"]
        res.add("R-VFD-20", "memory card from the company logic",
                f"CU250S-2: {cu250}, advanced safety: {adv}, positioning: {pos}, copy parameters: {cp} → {mc or 'not required'}",
                PASS, "OWN-MC-LOGIC p.1")
    else:
        res.add("R-VFD-20", "memory card", "not decided: answer 'copy parameters between drives?'", INFO, "")

    if flc_basis in ("nameplate", "datasheet"):
        res.add("R-VFD-13", "FLC from the motor's own data", flc_basis, PASS, "designer entry")
    elif flc_basis == "calculated":
        res.add("R-VFD-13", "FLC basis", "calculated", INFO, "")
    else:
        res.add("R-VFD-13", "FLC from the motor's own data",
                f"basis {flc_basis or 'not stated'}: confirm with the nameplate", WARN, "")

    # BOM in the ECI-VFD-Selection structure: Power Module → Control Unit → Memory Card → Operator Panel
    safety = ", ".join(f + (" (licence)" if v_ == "License" else "") for f, v_ in cu["safety"].items()) if cu else ""
    proto = {"none": "None", "modbus": "Modbus RTU", "profibus": "PROFIBUS DP", "profinet": "PROFINET IP",
             "ethernet_ip": "EtherNet/IP"}.get(str(cu_fieldbus).lower(), str(cu_fieldbus)) if cu_fieldbus else ""
    vfd_bom = [
        {"phase": "power-module", "category": "Power Module", "component": f"Power Module PM240-2 {m['frame']}",
         "part_number": order_no, "qty": 1,
         "specifications": f"{rating} {m[f'{key}_kw']:g} kW, {m[f'{key}_out']:g} A ({out_a:g} A at {ambient_c:g} °C); "
                           f"input {m[f'{key}_in']:g} A; loss {m['loss_w']:g} W"},
        {"phase": "control-unit", "category": "Control Unit",
         "component": f"Control Unit {cu['series']}" if cu else "Control Unit — not selected",
         "part_number": cu["article"] if cu else None, "qty": 1 if cu else 0,
         "specifications": (f"Safety: {safety or 'none'}; protocol: {proto}" if cu
                            else "answer encoder, safety and fieldbus")},
        {"phase": "memory-card", "category": "Memory Card",
         "component": "SINAMICS memory card" if mc else "Memory card — not required / not decided",
         "part_number": mc, "qty": 1 if mc else 0,
         "specifications": (("licence " + mc.split("-Z ")[1]) if mc and "-Z " in mc else ("parameter copy" if mc else ""))},
        {"phase": "operator-panel", "category": "Operator Panel", "component": "BOP-2 Operator Panel",
         "part_number": bop["article"], "qty": 1, "specifications": "one per drive"},
        {"phase": "accessory", "category": "Protection", "component": {"fuse": "LV HRC fuse", "msp": "Motor starter protector",
                                                                        "breaker": "Circuit breaker"}[protection],
         "part_number": dev["article"], "qty": prot_qty, "specifications": f"up to {dev['max_a']:g} A, ICC {dev['icc_ka']:g} kA"
         + (", one per line conductor" if prot_qty == 3 else "")},
    ]
    if holder:
        vfd_bom.append({"phase": "accessory", "category": "Fuse holder", "component": "Fuse switch disconnector",
                        "part_number": holder, "qty": 1, "specifications": "3-pole, floor mounting, without fuse monitoring"})
    if line:
        vfd_bom.append({"phase": "accessory", "category": "Line reactor", "component": "Line reactor",
                        "part_number": line["article"], "qty": 1, "specifications": "Table 8-4"})
    if qty:
        vfd_bom.append({"phase": "accessory", "category": "Output reactor", "component": "Output reactor",
                        "part_number": out_r["article"], "qty": qty,
                        "specifications": f"{cable_m:g} m motor cable" + (", two in series" if qty == 2 else "")})

    res.value = {"power_module": order_no, "frame": m["frame"], "rating": f"{rating} {m[f'{key}_kw']:g} kW",
                 "output_a_derated": out_a, "fuse": f"{m['fuse']} ({m['fuse_a']} A)",
                 "protection_device": dev["article"], "protection_type": protection, "protection_qty": prot_qty,
                 "fuse_holder": holder,
                 "protection_icc_ka": float(dev["icc_ka"]), "protection_max_a": float(dev["max_a"]),
                 "input_a": float(m[f"{key}_in"]), "min_enclosure_m3": min_vol,
                 "control_unit": cu["article"] if cu else None, "control_unit_series": cu["series"] if cu else None,
                 "operator_panel": bop["article"], "memory_card": mc, "vfd_bom": vfd_bom,
                 "line_reactor": line["article"] if line else None,
                 "output_reactor": out_r["article"] if out_r else None, "output_reactor_qty": qty,
                 "loss_w": float(m["loss_w"]), "cooling_air_ls": float(m["air_ls"])}
    res.basis = "PM240-2 manual"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
