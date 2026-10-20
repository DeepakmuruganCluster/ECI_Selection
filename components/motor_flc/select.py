"""Motor / heater full-load current. Rules: RULES.md / rules.yaml (R-FLC-01 … 08)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import FAIL, INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "motor_flc"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _guide() -> dict:
    return load_sourced_table(data_file("siemens_guide_400v_4p.yaml"), ("kw", "flc_a"))


def _src(row: dict) -> str:
    g = _guide()
    return f"{g['source']['ref']} p.{row['page']}"


def _dev(a: float, b: float) -> float:
    return (a - b) / b


def guide_value(kw: float, phases: int, voltage_v: float, frequency_hz: float, poles: int, res: Result):
    """Guide value for the conditions, or None (with the refusal recorded on `res`)."""
    g, p = _guide(), _rules()["params"]
    c = g["conditions"]
    for name, have, want in (("phases", phases, c["phases"]), ("poles", poles, c["poles"]),
                             ("frequency", frequency_hz, c["frequency_hz"])):
        if have != want:
            res.refuse("R-FLC-02", f"guide table applies to {name} = {want:g}", f"{name} = {have:g}",
                       f"{g['source']['ref']} p.29 footnote 1")
            return None
    row = next((r for r in g["rows"] if math.isclose(float(r["kw"]), kw)), None)
    if row is None:
        rng = f"{g['rows'][0]['kw']:g}–{g['rows'][-1]['kw']:g} kW"
        res.refuse("R-FLC-03", "kW listed in the guide table (no interpolation)",
                   f"{kw:g} kW not listed ({rng}); enter the nameplate / data-sheet current", g["source"]["ref"])
        return None
    i400 = float(row["flc_a"])
    res.add("R-FLC-02", "guide value, 3-ph 4-pole 400 V 50 Hz", f"{kw:g} kW → {i400:g} A", PASS, _src(row))
    if math.isclose(voltage_v, c["voltage_v"]):
        return i400, "guide"
    win = p["voltage_window_pct"] / 100
    if abs(voltage_v - c["voltage_v"]) > win * c["voltage_v"] + 1e-9:
        res.refuse("R-FLC-05", f"voltage within ±{p['voltage_window_pct']:g} % of {c['voltage_v']:g} V",
                   f"{voltage_v:g} V; enter the nameplate / data-sheet current", "hand rule")
        return None
    i = i400 * c["voltage_v"] / voltage_v
    res.add("R-FLC-05", "voltage conversion I = I_400 × 400 / U (approximation)",
            f"{i400:g} × {c['voltage_v']:g} / {voltage_v:g} = {i:.3f} A — confirm with the nameplate", WARN, "hand rule")
    return i, "guide_voltage_scaled"


def select(kw: float, load_type: str = "motor", phases: int = 3, voltage_v: float = 400.0,
           frequency_hz: float = 50.0, poles: int = 4, nameplate_flc_a: float | None = None,
           nameplate_source: str = "nameplate", efficiency_pct: float | None = None,
           power_factor: float | None = None, client_flc_a: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    p = _rules()["params"]
    nd = p["round_decimals"]

    # --- input validation
    if not kw or kw <= 0:
        return res.invalid(f"kW must be > 0 (got {kw})")
    if phases not in (1, 3):
        return res.invalid(f"phases must be 1 or 3 (got {phases})")
    if voltage_v <= 0:
        return res.invalid(f"voltage must be > 0 (got {voltage_v})")
    if load_type not in ("motor", "heater"):
        return res.invalid(f"load_type must be motor or heater (got {load_type})")
    if nameplate_source not in ("nameplate", "datasheet"):
        return res.invalid(f"nameplate_source must be nameplate or datasheet (got {nameplate_source})")

    if efficiency_pct is not None and not 0 < efficiency_pct <= 100:
        return res.invalid(f"efficiency must be 0 < η ≤ 100 % (got {efficiency_pct:g})")
    if power_factor is not None and not 0 < power_factor <= 1:
        return res.invalid(f"power factor must be 0 < cos φ ≤ 1 (got {power_factor:g})")
    k = math.sqrt(3) if phases == 3 else 1.0
    if load_type == "heater":
        i = kw * 1000 / (k * voltage_v)
        res.add("R-FLC-04", "resistive load I = P / (√3·U)" if phases == 3 else "resistive load I = P / U",
                f"{kw * 1000:g} W / ({'√3 × ' if phases == 3 else ''}{voltage_v:g} V) = {i:.3f} A", PASS, "physics")
        res.value, res.basis = {"flc_a": round(i, nd)}, "calculated"
    elif nameplate_flc_a:
        i = float(nameplate_flc_a)
        res.add("R-FLC-01", "motor's own rated current takes precedence", f"{i:g} A ({nameplate_source})", PASS,
                "designer entry")
        res.value, res.basis = {"flc_a": round(i, nd)}, nameplate_source
        probe = Result(COMPONENT, {})
        g = guide_value(kw, phases, voltage_v, frequency_hz, poles, probe)
        if g:
            d = _dev(i, g[0])
            lim = p["nameplate_vs_guide_pct"]
            scaled = f", guide scaled to {voltage_v:g} V by R-FLC-05" if g[1] == "guide_voltage_scaled" else ""
            res.add("R-FLC-06", f"nameplate within ±{lim:g} % of the guide value",
                    f"{i:g} A vs {g[0]:.2f} A ({d:+.1%}{scaled})", WARN if round(abs(d) * 100, 2) > lim else PASS,
                    next((c.source for c in probe.checks if c.rule == "R-FLC-02"), ""))
        else:
            res.add("R-FLC-06", "nameplate vs guide value", "no guide value for these conditions", INFO)
        if efficiency_pct and power_factor:
            i_f = kw * 1000 / (k * voltage_v * efficiency_pct / 100 * power_factor)
            d = _dev(i, i_f)
            lim = p["nameplate_vs_formula_pct"]
            res.add("R-FLC-07", f"nameplate current within ±{lim:g} % of P / ({'√3·' if phases == 3 else ''}U·η·cos φ)",
                    f"{i:g} A vs {i_f:.3f} A (η {efficiency_pct:g} %, cos φ {power_factor:g}; {d:+.1%})",
                    WARN if round(abs(d) * 100, 2) > lim else PASS, "physics")
    else:
        g = guide_value(kw, phases, voltage_v, frequency_hz, poles, res)
        if g is None:
            return res
        res.value, res.basis = {"flc_a": round(g[0], nd)}, g[1]

    if client_flc_a:
        design = res.value["flc_a"]
        d = _dev(client_flc_a, design)
        lim = p["client_vs_design_pct"]
        res.add("R-FLC-08", f"client list value within ±{lim:g} % of the design FLC (reported, not used)",
                f"client {client_flc_a:g} A vs {design:g} A ({d:+.1%})", WARN if round(abs(d) * 100, 2) > lim else PASS,
                "client load list")
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
