"""Enclosure accessories: filter fans + outlet filters (count from the required airflow), plinth side trims,
door switch and light (Rittal data sheets). Rules: RULES.md / rules.yaml (R-ACC-01 … 17)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from core.data import data_file
from core import project as P
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "enclosure_accessories"
ROW = ("quantity", "value")
FAN_FILES = ("rittal_sk3239100.yaml", "rittal_sk3240100.yaml")
OUTLET_FILES = ("rittal_sk3239200.yaml", "rittal_sk3240200.yaml")
TRIM_FILES = ("rittal_ts8601060.yaml", "rittal_ts8602060.yaml")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _table(name: str) -> dict:
    return load_sourced_table(data_file(name), ROW)


def fans() -> list[dict]:
    return [_table(f) for f in FAN_FILES]


def _rows(t: dict, quantity: str, **attrs) -> list[dict]:
    return [r for r in t["rows"] if r["quantity"] == quantity and all(r.get(k) == v for k, v in attrs.items())]


def _one(t: dict, quantity: str, **attrs) -> dict:
    rows = _rows(t, quantity, **attrs)
    if len(rows) != 1:
        raise LookupError(f"{t['source']['ref']}: {quantity} {attrs}: {len(rows)} rows")
    return rows[0]


def _v(t: dict, quantity: str, **attrs):
    return _one(t, quantity, **attrs)["value"]


def _p(t: dict, page) -> str:
    return f"{t['source']['ref']} p.{page}"


def size_in(fan: dict) -> int:
    """R-ACC-02: nominal inch size from the outer frame width."""
    return round(_v(fan, "frame_width_mm") / 25.4)


def _per_fan(fan: dict, hz: int, n_out: int) -> dict:
    return _one(fan, "airflow_outlet_m3h", hz=hz, outlet_filters=n_out)


def select(required_airflow_m3h: float | None = None, doors: int | None = None, supply_v: float | None = None,
           frequency_hz: float | None = None, fans_per_door: int | None = None, fan_size_in: int | None = None,
           outlet_filters_per_fan: int | None = None, site_ambient_c: float | None = None,
           plinth_height_mm: float | None = None, enclosure_depth_mm: float | None = None, suites: int | None = None,
           section_widths_mm: list | None = None, client_requirements: dict | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]

    # --- input validation (no defaults for physical inputs)
    if required_airflow_m3h is None or required_airflow_m3h < 0:
        return res.invalid(f"required_airflow_m3h (from the enclosure component) must be ≥ 0 (got {required_airflow_m3h})")
    if not isinstance(doors, int) or doors < 1:
        return res.invalid(f"doors (number of doors that can take a fan / light) must be a whole number ≥ 1 (got {doors})")
    if supply_v is None:
        return res.invalid("supply_v (fan supply voltage) is required")
    if frequency_hz is None:
        return res.invalid("frequency_hz (fan supply frequency) is required")
    fpd = prm["default_fans_per_door"] if fans_per_door is None else fans_per_door
    fan_text, fan_src = P.cite(client_requirements, "cooling_fans_per_door")
    if not isinstance(fpd, int) or fpd < 1:
        return res.invalid(f"fans_per_door must be a whole number ≥ 1 (got {fans_per_door})")
    n_out = prm["default_outlet_filters_per_fan"] if outlet_filters_per_fan is None else outlet_filters_per_fan
    if not isinstance(n_out, int) or n_out < 1:
        return res.invalid(f"outlet_filters_per_fan must be a whole number ≥ 1 (got {outlet_filters_per_fan})")
    if plinth_height_mm is not None:
        if plinth_height_mm <= 0:
            return res.invalid(f"plinth_height_mm must be > 0 (got {plinth_height_mm})")
        if enclosure_depth_mm is None or not isinstance(suites, int) or suites < 1:
            return res.invalid("a plinth needs enclosure_depth_mm and suites (number of free-standing suites, ≥ 1)")
    if section_widths_mm is not None and not isinstance(section_widths_mm, list):
        return res.invalid("section_widths_mm must be a list of widths in mm")

    req = float(required_airflow_m3h)
    v: dict = {"required_airflow_m3h": req}

    # --- fans and outlet filters (R-ACC-01 … R-ACC-11)
    all_fans = fans()
    f0 = all_fans[0]
    volts = {_v(f, "rated_voltage_v") for f in all_fans}
    hzs = {r["hz"] for f in all_fans for r in _rows(f, "airflow_outlet_m3h")}
    vrow = _one(f0, "rated_voltage_v")
    if float(supply_v) not in volts or int(frequency_hz) not in hzs or frequency_hz != int(frequency_hz):
        return res.refuse("R-ACC-01", "fans rated 230 V, 1~, 50 Hz/60 Hz",
                          f"{supply_v:g} V {frequency_hz:g} Hz: no fan held for this supply", _p(f0, vrow["page"]))
    hz = int(frequency_hz)
    res.add("R-ACC-01", "fans rated 230 V, 1~, 50/60 Hz", f"{supply_v:g} V, {hz} Hz", PASS, _p(f0, vrow["page"]))

    outs = {n for f in all_fans for n in (r["outlet_filters"] for r in _rows(f, "airflow_outlet_m3h"))}
    if n_out not in outs:
        return res.refuse("R-ACC-05", f"outlet filters per fan with a printed airflow: {sorted(outs)}",
                          f"{n_out}", _p(f0, _per_fan(f0, hz, 1)["page"]))
    res.add("R-ACC-05", "outlet filters per fan (printed: 1 or 2)", f"{n_out}", PASS if outlet_filters_per_fan else INFO,
            _p(f0, _per_fan(f0, hz, 1)["page"]) + ("" if outlet_filters_per_fan else "; default 1 (decision A-2)"))

    positions = doors * fpd
    v["fan_positions"] = positions
    fan = None
    if req > 0:
        sized = sorted(all_fans, key=lambda f: _per_fan(f, hz, n_out)["value"])
        if fan_size_in is not None:
            fan = next((f for f in sized if size_in(f) == fan_size_in), None)
            if fan is None:
                return res.refuse("R-ACC-02", "fan sizes held: " + ", ".join(
                    f"{size_in(f)} inch = {f['article']} ({_v(f, 'frame_width_mm')} mm)" for f in sized),
                    f"{fan_size_in} inch", _p(f0, _one(f0, "frame_width_mm")["page"]))
            res.add("R-ACC-02", "fan size = frame width ÷ 25.4",
                    f"{fan_size_in} inch → {fan['article']} ({_v(fan, 'frame_width_mm')} × "
                    f"{_v(fan, 'frame_height_mm')} mm = {_v(fan, 'frame_width_mm') / 25.4:.2f} inch)", PASS,
                    _p(fan, _one(fan, "frame_width_mm")["page"]))
        else:
            fits = [f for f in sized if math.ceil(req / _per_fan(f, hz, n_out)["value"] - 1e-9) <= positions]
            fan = fits[0] if fits else sized[-1]
            res.add("R-ACC-08", "no size given: smaller fan if it fits the positions, else the larger",
                    ", ".join(f"{f['article']} ({size_in(f)} inch) needs "
                              f"{math.ceil(req / _per_fan(f, hz, n_out)['value'] - 1e-9)}" for f in sized)
                    + f" for {positions} position(s) → {fan['article']}", INFO, "rules.yaml")

        # operating temperature (R-ACC-09)
        tmin, tmax = _one(fan, "operating_temp_min_c"), _one(fan, "operating_temp_max_c")
        if site_ambient_c is not None:
            if not tmin["value"] <= site_ambient_c <= tmax["value"]:
                return res.refuse("R-ACC-09", f"{fan['article']} operating range {tmin['value']} … {tmax['value']} °C",
                                  f"site {site_ambient_c:g} °C", _p(fan, tmax["page"]))
            res.add("R-ACC-09", f"site air within {tmin['value']} … {tmax['value']} °C", f"{site_ambient_c:g} °C", PASS,
                    _p(fan, tmax["page"]))
        else:
            res.add("R-ACC-09", f"site air within {tmin['value']} … {tmax['value']} °C", "site ambient not given",
                    INFO, _p(fan, tmax["page"]))

        # outlet filter (R-ACC-03)
        out_t = next(_table(o) for o in OUTLET_FILES if _table(o)["article"] == fan["outlet_filter"])
        fit = _one(out_t, "to_fit")
        if fan["article"].replace("SK ", "")[:6] not in fit["value"]:
            return res.refuse("R-ACC-03", "outlet filter to fit the fan", f"{out_t['article']} fits {fit['value']}",
                              _p(out_t, fit["page"]))
        res.add("R-ACC-03", "outlet filter to fit the fan", f"{out_t['article']} ('to fit {fit['value']}')", PASS,
                _p(out_t, fit["page"]))

        # airflow and count (R-ACC-04, R-ACC-06)
        row = _per_fan(fan, hz, n_out)
        per = float(row["value"])
        free = _one(fan, "airflow_free_m3h", hz=hz, filter="chopped_fibre")["value"]
        res.add("R-ACC-04", "airflow per fan with outlet filter(s), chopped-fibre mat",
                f"{n_out} × {out_t['article']} at {hz} Hz: {per:g} m³/h (free-blowing {free:g} m³/h not used)", PASS,
                _p(fan, row["page"]))
        n = math.ceil(req / per - 1e-9)
        res.add("R-ACC-06", "n = ceil(required ÷ airflow per fan)",
                f"{req:g} / {per:g} = {req / per:.2f} → {n} fan(s), {n * per:g} m³/h", PASS,
                _p(_table("rittal_tsc_fan_principle.yaml"), 12))

        # positions (R-ACC-07)
        if n > positions:
            res.add("R-ACC-07", f"fans fit the positions ({doors} door(s) × {fpd})",
                    f"{n} needed > {positions}: {positions} × {per:g} = {positions * per:g} m³/h "
                    f"= {positions * per / req * 100:.0f} % of {req:g} m³/h (short by {req - positions * per:g})",
                    WARN, f"{fan_src}" + (f" '{fan_text}'" if fan_text else ""))
            v["airflow_at_positions_m3h"] = round(positions * per, 2)
        else:
            res.add("R-ACC-07", f"fans fit the positions ({doors} door(s) × {fpd})", f"{n} ≤ {positions}", PASS,
                    fan_src)

        # electrical load (R-ACC-10)
        pw = _rows(fan, "power_w", hz=hz)
        ia = _rows(fan, "current_a", hz=hz)
        p_w, i_a = max(r["value"] for r in pw), max(r["value"] for r in ia)
        two = len({r["value"] for r in pw}) > 1 or len({r["value"] for r in ia}) > 1
        res.add("R-ACC-10", "fan load = n × power, n × current (higher where two values are printed)",
                f"{n} × {p_w:g} W = {n * p_w:g} W, {n} × {i_a:g} A = {n * i_a:.2f} A"
                + (" (data sheet prints " + " / ".join(f"{r['value']:g} W p.{r['page']}" for r in pw) + ", "
                   + " / ".join(f"{r['value']:g} A p.{r['page']}" for r in ia) + ")" if two else ""),
                INFO, ", ".join(sorted({_p(fan, r["page"]) for r in pw + ia})))
        ip = _one(fan, "ip_standard")
        res.add("R-ACC-11", "protection with chopped-fibre filter", f"IP {ip['value']}", INFO, _p(fan, ip["page"]))
        v.update(fan=fan["article"], fan_size_in=size_in(fan), outlet_filter=out_t["article"],
                 airflow_per_fan_m3h=per, fan_qty=n, outlet_filter_qty=n * n_out,
                 delivered_airflow_m3h=round(n * per, 2), fan_power_w=round(n * p_w, 2),
                 fan_current_a=round(n * i_a, 3), fan_noise_dba=_v(fan, "noise_dba", hz=hz),
                 fan_cutout_mm=f"{_v(fan, 'cutout_width_mm')} × {_v(fan, 'cutout_height_mm')}")
    else:
        res.add("R-ACC-06", "n = ceil(required ÷ airflow per fan)", "no airflow required: no fans", INFO,
                _p(_table("rittal_tsc_fan_principle.yaml"), 12))
        v.update(fan=None, fan_qty=0, outlet_filter=None, outlet_filter_qty=0, delivered_airflow_m3h=0,
                 fan_power_w=0, fan_current_a=0)

    # --- plinth (R-ACC-12 … R-ACC-14)
    if plinth_height_mm is not None:
        trims = [_table(t) for t in TRIM_FILES]
        heights = {_v(t, "height_mm"): t for t in trims}
        t1 = trims[0]
        note = _one(t1, "two_100_for_200")
        trim = heights.get(plinth_height_mm)
        if trim is None:
            res.add("R-ACC-12", "plinth heights held: " + " / ".join(f"{h:g} mm ({t['article']})"
                                                               for h, t in sorted(heights.items())),
                    f"{plinth_height_mm:g} mm asked: not offered in the held Rittal data sheets — no plinth article",
                    WARN, _p(t1, note["page"]))
        else:
            res.add("R-ACC-12", "plinth height held", f"{plinth_height_mm:g} mm → {trim['article']}", PASS,
                    _p(trim, _one(trim, "height_mm")["page"]))
            fitw = _rows(trim, "fits_width_mm")
            if float(enclosure_depth_mm) not in {float(r["value"]) for r in fitw}:
                res.add("R-ACC-13", "side trim fits W (= enclosure depth) 600 mm",
                        f"depth {enclosure_depth_mm:g} mm: no side trim held", WARN, _p(trim, fitw[0]["page"]))
                trim = None
            else:
                pack = _v(trim, "pieces_per_pack")
                res.add("R-ACC-13", "side trim: 1 pack (left + right end) per suite",
                        f"depth {enclosure_depth_mm:g} mm; {suites} suite(s) × 1 pack of {pack}", PASS,
                        _p(trim, fitw[0]["page"]))
        v["plinth_height_mm"] = plinth_height_mm
        v["plinth_side_trim"] = trim["article"] if trim else None
        v["plinth_side_trim_qty"] = suites if trim else 0
        res.add("R-ACC-14", "plinth corner pieces and front / rear trims per section width",
                "not selected: no data sheet held"
                + (f" (sections {', '.join(f'{w:g}' for w in section_widths_mm)} mm recorded)" if section_widths_mm else ""),
                WARN, "rules.yaml")

    # --- door switch and light (R-ACC-15 … R-ACC-17)
    sw, lt = _table("rittal_sz4127010.yaml"), _table("rittal_sz4140820.yaml")
    i_l, sw_a = _one(lt, "current_a"), _one(sw, "rating_24vdc_a")
    door_text, door_src = P.cite(client_requirements, "door_switch_light")
    res.add("R-ACC-15", "one door switch and one light per door" + (f" (client: '{door_text}')" if door_text else ""),
            f"{doors} × {sw['article']}, {doors} × {lt['article']}", PASS, door_src)
    per_row = int(2.0 / i_l["value"] + 1e-9)           # row of lights ≤ 2 A (SZ 4140.820 p.3)
    rows = math.ceil(doors / per_row) if doors else 0
    v["light_rows"] = rows
    res.add("R-ACC-16", f"light 24 V DC {i_l['value']:g} A; switch 24 V DC {sw_a['value']:g} A; row of lights ≤ 2 A",
            f"{doors} × {i_l['value']:g} = {doors * i_l['value']:.2f} A at 24 V DC to control power, in {rows} row(s) of "
            f"≤ {per_row} lights; {i_l['value']:g} A ≤ {sw_a['value']:g} A", PASS,
            f"{_p(lt, i_l['page'])}, {_p(sw, sw_a['page'])}")
    res.add("R-ACC-17", "door switch supplied without connection cable; light has an integral door switch",
            "connection cable not selected", INFO, f"{_p(sw, _one(sw, 'design')['page'])}, "
                                                    f"{_p(lt, _one(lt, 'switch_type')['page'])}")
    v.update(door_switch=sw["article"], door_switch_qty=doors, door_light=lt["article"], door_light_qty=doors,
             light_24vdc_a=round(doors * i_l["value"], 3))

    res.value = v
    res.basis = "Rittal data sheets"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
