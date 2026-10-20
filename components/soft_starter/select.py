"""Soft starter: Siemens SIRIUS 3RW52 General Performance, standard (inline) circuit. Rules: rules.yaml (R-SS-01 … 14).

Data from Catalog IC 10 · 2026 (SIE-IC10-2026): ic10_3rw52_ratings (pp. 6/59–6/62), ic10_3rw52_coordination
(pp. 6/63–6/65), ic10_3rw52_ordering (pp. 6/67–6/70). Imported by scripts/import_ic10_3rw52.py.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from core.data import data_file
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "soft_starter"
CLASSES = ("10A", "10E", "20E")
PROTECTIONS = {"mpcb": "mpcb_type1", "fuse_gg": "gG_fuse_type1", "fuse_semi": "gRgS_fuse_type2"}
FLC_BASES = ("nameplate", "datasheet", "guide", "guide_voltage_scaled", "calculated")
SRC = "SIE-IC10-2026"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _ratings() -> list[dict]:
    return load_sourced_table(data_file("ic10_3rw52_ratings.yaml"), ("type", "ie_a", "im_min_a", "im_max_a"))["rows"]


@lru_cache(maxsize=None)
def _coordination() -> dict:
    rows = load_sourced_table(data_file("ic10_3rw52_coordination.yaml"), ("type", "kind", "protection"))["rows"]
    return {(r["type"], r["kind"]): r for r in rows}


@lru_cache(maxsize=None)
def _ordering() -> list[dict]:
    return load_sourced_table(data_file("ic10_3rw52_ordering.yaml"), ("article", "type", "control_supply"))["rows"]


def _p(row: dict) -> str:
    return f"{SRC} p.{row['printed']} (PDF {row['page']})"


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


@lru_cache(maxsize=None)
def _accessories() -> dict:
    return load_sourced_table(data_file("3rw52_accessories.yaml"), ("item", "value", "article"))


def _bool(x) -> bool | None:
    if x is None or isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return True if s in ("true", "yes", "1") else False if s in ("false", "no", "0") else None


def select(flc_a: float | None = None, fault_ka: float | None = None, ambient_c: float | None = None,
           flc_basis: str | None = None, duty: str | None = None, starting_class: str | None = None,
           voltage_v: float = 400, protection: str | None = None, line_contactor: bool | None = None,
           control_supply: str | None = None, thermistor: bool = False, terminals: str | None = None,
           starts_per_hour: float | None = None, start_current_pct: float | None = None,
           start_time_s: float | None = None, circuit: str = "inline", phases: int = 3,
           altitude_m: float | None = None, load_type: str = "motor", comm: str | None = None, hmi: str | None = None,
           hmi_mounting: str | None = None, hmi_cable_m: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]

    # --- input validation (fail closed, no defaults for what the rules require)
    flc, fault, amb, volt = _num(flc_a), _num(fault_ka), _num(ambient_c), _num(voltage_v)
    if flc is None or flc <= 0:
        return res.invalid(f"motor FLC must be a number > 0 A (got {flc_a})")
    if fault is None or fault <= 0:
        return res.invalid(f"fault_ka (prospective short-circuit current) is required and > 0 (got {fault_ka})")
    if amb is None:
        return res.invalid(f"ambient_c (temperature around the soft starter) is required (got {ambient_c})")
    if volt is None or volt <= 0:
        return res.invalid(f"voltage_v must be a number > 0 (got {voltage_v})")
    if flc_basis is not None and flc_basis not in FLC_BASES:
        return res.invalid(f"flc_basis must be one of {', '.join(FLC_BASES)} (got {flc_basis})")
    if starting_class is not None:
        starting_class = str(starting_class).upper().removeprefix("CLASS").strip()
        if starting_class not in CLASSES:
            return res.invalid(f"starting_class must be one of {', '.join(CLASSES)} (got {starting_class})")
    if duty is not None and duty not in ("normal", "heavy"):
        return res.invalid(f"duty must be normal or heavy (got {duty})")
    if protection is not None and protection not in PROTECTIONS:
        return res.invalid(f"protection must be one of {', '.join(PROTECTIONS)} (got {protection})")
    control_supply = control_supply or prm["control_supply_default"]
    if control_supply not in ("230VAC", "24V"):
        return res.invalid(f"control_supply must be 230VAC or 24V (got {control_supply})")
    terminals = terminals or prm["terminals_default"]
    if terminals not in ("screw", "spring"):
        return res.invalid(f"terminals must be screw or spring (got {terminals})")
    acc = _accessories()["rows"]
    choice = lambda item: {r["value"] for r in acc if r["item"] == item}
    if comm is not None and comm not in choice("comm") | {"none"}:
        return res.invalid(f"comm must be one of {', '.join(sorted(choice('comm')))} or none (got {comm})")
    if hmi is not None and hmi not in choice("hmi") | {"none"}:
        return res.invalid(f"hmi must be standard, high_feature or none (got {hmi})")
    if hmi_mounting is not None and hmi_mounting not in ("door", "device"):
        return res.invalid(f"hmi_mounting must be door or device (got {hmi_mounting})")
    if hmi_cable_m is not None and f"{float(hmi_cable_m):g}" not in choice("cable") - {"0.1"}:
        return res.invalid(f"hmi_cable_m must be one of 0.5, 1, 2.5, 5 m (got {hmi_cable_m})")
    thermistor, lc = _bool(thermistor), _bool(line_contactor)
    if thermistor is None:
        return res.invalid("thermistor must be true or false")
    if line_contactor is not None and lc is None:
        return res.invalid("line_contactor must be true or false")
    freq = [starts_per_hour, start_current_pct, start_time_s]
    if any(x is not None for x in freq) and not all(x is not None for x in freq):
        return res.invalid("the starting-frequency check needs starts_per_hour, start_current_pct and start_time_s together "
                           "(no defaults are assumed)")
    if all(x is not None for x in freq):
        freq = [_num(x) for x in freq]
        if any(x is None or x <= 0 for x in freq):
            return res.invalid("starts_per_hour, start_current_pct and start_time_s must be numbers > 0")
        if freq[1] < 100:
            return res.invalid(f"starting current is a multiple of the motor current, at least 100 % (got {freq[1]:g} %)")

    # --- R-SS-01 / R-SS-14 scope
    if phases != 3 or load_type != "motor":
        return res.refuse("R-SS-01", "3-phase motor", f"{phases}-phase {load_type}: out of scope", f"{SRC} p.6/58")
    if circuit != "inline":
        return res.refuse("R-SS-01", "standard (inline) circuit",
                          f"{circuit}: inside-delta ordering and fuse tables not built", f"{SRC} p.6/58")
    if not 200 <= volt <= 600:
        return res.refuse("R-SS-01", "operational voltage 200 … 600 V", f"{volt:g} V", f"{SRC} p.6/58")
    ue = "200-480" if volt <= 480 else "200-600"
    res.add("R-SS-01", "3-phase motor, inline circuit, voltage in range", f"{volt:g} V → version {ue} V", PASS, f"{SRC} p.6/58")
    if altitude_m is None:
        res.add("R-SS-14", "installation altitude", "not given: taken as ≤ 1 000 m (no derating), confirm for the site", INFO, f"{SRC} p.6/8")
    elif _num(altitude_m) is None or _num(altitude_m) > 1000:
        return res.refuse("R-SS-14", "installation altitude ≤ 1 000 m (derating curve not transcribed)",
                          f"{altitude_m} m", f"{SRC} p.6/8")
    if amb > 60:
        return res.refuse("R-SS-03", "ambient −25 … +60 °C", f"{amb:g} °C", f"{SRC} p.6/13")
    if amb < -25:
        return res.refuse("R-SS-03", "ambient −25 … +60 °C", f"{amb:g} °C", f"{SRC} p.6/13")
    col = next(c for c in prm["columns_c"] if amb <= c)

    # --- R-SS-06 starting class
    if starting_class:
        cls, why = starting_class, "given"
    elif duty:
        cls, why = prm["class_by_duty"][duty], f"duty {duty} (decision SS-1)"
    else:
        cls, why = "10A", "not given: the ordering data are for Class 10 (p. 6/8)"
    res.add("R-SS-06", "starting class", f"Class {cls} — {why}", INFO, f"{SRC} p.6/8")

    # --- R-SS-10 protection, R-SS-09 fuseless only Class 10
    if protection is None:
        protection = prm["protection_by_class"][cls] if volt <= 500 else "fuse_gg"   # no fuseless combination > 500 V
        res.add("R-SS-10", "short-circuit protection not given", f"Class {cls} → {protection} (decision SS-2)", INFO, f"{SRC} p.6/12")
    if protection == "mpcb" and cls == "20E":
        return res.refuse("R-SS-09", "fuseless feeder (3RV2 / 3VA) tested for Class 10 only",
                          "Class 20E needs fuses: choose fuse_gg or fuse_semi", f"{SRC} p.6/12")
    if protection == "mpcb" and lc:
        return res.refuse("R-SS-11", "tested line contactor", "none printed with the fuseless combination", f"{SRC} p.6/63")

    # --- R-SS-03 / 04 / 05 / 07 / 08: smallest type that passes
    key = f"im_{cls}_a"
    kind = PROTECTIONS[protection]
    reasons, fits = [], []      # fits: types that carry the current but fail the starting frequency
    chosen = None
    for r in _ratings():
        im = r[key][str(col)]
        if im < flc:
            reasons.append(f"{r['type']} IM {im:g} A < {flc:g} A")
            continue
        if not r["im_min_a"] <= flc <= r["im_max_a"]:
            reasons.append(f"{r['type']} setting {r['im_min_a']:g} … {r['im_max_a']:g} A does not hold {flc:g} A")
            continue
        if all(x is not None for x in freq):
            sph, pct, ts = freq
            if pct > 350:
                return res.refuse("R-SS-07", "starting current ≤ 350 % IM (tabulated)", f"{pct:g} %", _p(r))
            pct_key = "300%" if pct <= 300 else "350%"
            times = sorted({int(k.split()[1]) for k in r[f"starts_{cls}_per_h"]})
            t_col = next((t for t in times if ts <= t), None)
            if t_col is None:
                return res.refuse("R-SS-07", f"startup time ≤ {times[-1]} s (Class {cls}, tabulated)", f"{ts:g} s", _p(r))
            allowed = r[f"starts_{cls}_per_h"][f"{pct_key} {t_col} s"]
            if allowed < sph:
                reasons.append(f"{r['type']} {allowed:g} starts/h < {sph:g}")
                fits.append(reasons[-1])
                continue
        chosen = r
        break
    if chosen is None:
        return res.refuse("R-SS-05", f"a 3RW52 for {flc:g} A, Class {cls}, {col} °C column",
                          ("starting frequency: " + "; ".join(fits[:3]) + (f" … ({len(fits)} types)" if len(fits) > 3 else ""))
                          if fits else "; ".join(reasons[-3:]) or "none", f"{SRC} pp.6/59–6/62")
    r = chosen
    im = r[key][str(col)]
    res.add("R-SS-02", "selected on the motor current, not on kW", f"FLC {flc:g} A", INFO, f"{SRC} p.6/8")
    res.add("R-SS-03", f"IM Class {cls} at {col} °C column (ambient {amb:g} °C) ≥ FLC", f"{r['type']}: {im:g} A ≥ {flc:g} A", PASS, _p(r))
    res.add("R-SS-04", "FLC within the adjustable IM; motor protection set to the FLC",
            f"{r['im_min_a']:g} … {r['im_max_a']:g} A ∋ {flc:g} A → set IM = {flc:g} A", PASS, _p(r))
    res.add("R-SS-05", "smallest type that passes", r["type"] + (f" ({'; '.join(reasons[-2:])})" if reasons else ""), PASS, _p(r))
    if all(x is not None for x in freq):
        res.add("R-SS-07", "permissible starts per hour", f"{freq[0]:g}/h ≤ table (Class {cls}, ON 70 %)", PASS, _p(r))
    else:
        short = min(int(k.split()[1]) for k in r[f"starts_{cls}_per_h"])
        res.add("R-SS-07", "starting frequency", f"not checked (not given); table: {r[f'starts_{cls}_per_h'][f'300% {short} s']} "
                f"starts/h at 300 % IM, {short} s", INFO, _p(r))

    # protection
    co = _coordination().get((r["type"], kind))
    if co is None:
        return res.refuse("R-SS-08", f"tested {protection} for {r['type']}", "not printed", f"{SRC} pp.6/63–6/65")
    if kind == "mpcb_type1":
        # p. 6/63 prints '400 V systems' and '500 V systems' columns only (decision SS-5)
        if volt > 500:
            return res.refuse("R-SS-08", "tested 3RV2 / 3VA combination for the voltage",
                              f"{volt:g} V: printed for 400 V and 500 V systems only — choose fuses", _p(co))
        dev, iq = (co["protection"], co["iq_400v_ka"]) if volt <= 415 else (co["protection_500v"], co["iq_500v_ka"])
        if dev is None or iq is None:
            return res.refuse("R-SS-08", f"tested 3RV2 / 3VA for {r['type']} at {volt:g} V", "printed '--'", _p(co))
        qty, coord = 1, "1"
    else:
        dev, iq = co["protection"], co["iq_400v_ka"]
        if co.get("note") and volt > 500:
            return res.refuse("R-SS-08", f"{dev} {co['note']}", f"{volt:g} V", _p(co))
        qty, coord = 3 * co["fuses_in_parallel"], "1" if kind == "gG_fuse_type1" else "2"
    if iq < fault:
        return res.refuse("R-SS-08", f"Iq of the tested combination ≥ fault current", f"{dev}: {iq:g} kA < {fault:g} kA — "
                          + ("choose fuses (Iq 65 kA)" if kind == "mpcb_type1" else "above the tested 65 kA"), _p(co))
    res.add("R-SS-08", f"short-circuit protection, type of coordination {coord}",
            f"{dev}{f' × {qty}' if qty > 1 else ''}: Iq {iq:g} kA ≥ {fault:g} kA", PASS, _p(co))
    res.add("R-SS-09", "Class against the protection", f"Class {cls} with {protection}", PASS, f"{SRC} p.6/12")

    # line contactor
    contactor = None
    if kind == "mpcb_type1":
        res.add("R-SS-11", "line contactor", "none (fuseless combination)", INFO, f"{SRC} p.6/12")
    else:
        want = lc if lc is not None else cls == "20E"
        if want:
            contactor = co["line_contactor_480v"] if volt <= 480 else co["line_contactor_600v"]
            if contactor in (None, "--"):
                return res.refuse("R-SS-11", "line contactor printed for this voltage", "'--'", _p(co))
            res.add("R-SS-11", "line contactor (Q21)" + ("" if lc is not None else " — Class 20E with fuses (decision SS-3)"),
                    f"{contactor}: coil version not in this table — choose it with the contactor (open point)", WARN, _p(co))
        else:
            res.add("R-SS-11", "line contactor", "not added" + (" (designer)" if lc is False else f" (Class {cls}, decision SS-3)"),
                    INFO, f"{SRC} p.6/12")

    # article
    us = "24 V AC/DC" if control_supply == "24V" else "110-250 V AC"
    func = "thermistor" if thermistor else "analog output"
    o = next((x for x in _ordering() if x["type"] == r["type"] and x["control_supply"] == us
              and x["operational_voltage"] == ue and x["function"] == func), None)
    if o is None:
        return res.refuse("R-SS-12", "article in the ordering data", f"{r['type']}, {us}, {ue} V, {func}", f"{SRC} pp.6/67–6/70")
    article = o["article"] if terminals == "screw" else o["article_spring"]
    res.add("R-SS-12", "article (ordering data)", f"{article}: {terminals} control terminals, {func}, Us {us}, Ue {ue} V", PASS, _p(o))

    # basis and heat
    if flc_basis in (None, "guide", "guide_voltage_scaled"):
        res.add("R-SS-13", "FLC from the motor's rated data", f"basis {flc_basis or 'not stated'}: confirm the nameplate current",
                WARN, f"{SRC} p.6/8")
    res.add("R-SS-14", "power loss", "not printed in IC 10 for the 3RW52: not in the panel heat", INFO, "")

    bom = [{"role": "soft starter", "article": article, "description": f"SIRIUS 3RW52 soft starter {r['type']} ({r['ie_a']:g} A)",
            "qty": 1, "source": _p(o)},
           {"role": "protection", "article": dev, "description": ("motor starter protector / circuit breaker" if kind == "mpcb_type1"
                                                                  else "gG fuse" if kind == "gG_fuse_type1" else "SITOR gR/gS fuse")
            + f", type of coordination {coord}", "qty": qty, "source": _p(co)}]
    if contactor:
        bom.append({"role": "line contactor", "article": contactor, "description": "line contactor (coil version open)", "qty": 1,
                    "source": _p(co)})
    # --- R-SS-15 (owner 2026-10-20, RFQ part 4): communication module, HMI module and its mounting (IC 10 pp.6/75-6/76)
    pick = lambda item, value: next(x for x in acc if x["item"] == item and x["value"] == value)
    if comm and comm != "none":
        c = pick("comm", comm)
        bom.append({"role": "communication", "article": c["article"], "description": c["description"], "qty": 1})
        res.add("R-SS-15", "communication module", f"{c['article']} {c['description']}", PASS, f"SIE-IC10-2026 p.{c['page']} (6/75)")
    if hmi and hmi != "none":
        h = pick("hmi", hmi)
        parts = [h]
        if hmi_mounting == "device":
            parts += [pick("cover", hmi), pick("cable", "0.1")]
        elif hmi_mounting == "door":
            parts.append(pick("door_kit", "ip65"))
            if hmi_cable_m is None:
                res.add("R-SS-15", "HMI connecting cable for door mounting", "length not given (0.5 / 1 / 2.5 / 5 m): cable not selected",
                        WARN, "SIE-IC10-2026 p.508 (6/76)")
            else:
                parts.append(pick("cable", f"{float(hmi_cable_m):g}"))
        else:
            res.add("R-SS-15", "HMI module mounting", "not given (door / in the device): cover or door kit not selected", WARN,
                    "SIE-IC10-2026 p.507")
        for x in parts:
            bom.append({"role": "hmi", "article": x["article"], "description": x["description"], "qty": 1})
        res.add("R-SS-15", f"HMI module ({hmi.replace('_', '-')}) with its mounting ({hmi_mounting or 'not given'})",
                ", ".join(x["article"] for x in parts), PASS, "SIE-IC10-2026 pp.507-508 (6/75-6/76)")

    res.value = {"soft_starter": article, "type": r["type"], "ie_a": r["ie_a"], "im_rated_a": im, "set_im_a": flc,
                 "starting_class": cls, "column_c": col, "protection": protection, "protection_device": dev,
                 "protection_qty": qty, "coordination": coord, "iq_ka": iq, "line_contactor": contactor,
                 "kw_400v_guide": o["kw_400v"], "bom": bom}
    res.basis = "catalogue"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
