"""Enclosure heat balance and cooling (Rittal TSC 3124300). Rules: RULES.md / rules.yaml (R-ENC-01 … 18)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "enclosure"
SITINGS = ("indoor", "outdoor")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _altitude() -> dict:
    return load_sourced_table(data_file("rittal_altitude_factor.yaml"), ("h_min_m", "h_max_m", "f"))


@lru_cache(maxsize=None)
def _k() -> dict:
    return load_sourced_table(data_file("rittal_heat_transfer.yaml"), ("material", "k_w_m2k", "siting"))


@lru_cache(maxsize=None)
def _formulas() -> dict:
    return load_sourced_table(data_file("rittal_formulas.yaml"), ("id", "printed"))


@lru_cache(maxsize=None)
def _products() -> dict:
    return load_sourced_table(data_file("rittal_products.yaml"), ("kind", "article"))


@lru_cache(maxsize=None)
def _siemens() -> dict:
    return load_sourced_table(data_file("siemens_cooling_air.yaml"), ("quantity", "value"))


def _p(table: dict, page) -> str:
    """Document reference with the PDF page and, where it differs, the printed page."""
    ref = table["source"]["ref"]
    off = int(table["reference"].get("printed_page_offset", 0))
    return f"{ref} PDF p.{page} (printed {page + off})" if off else f"{ref} p.{page}"


def _formula(fid: str) -> dict:
    return next(r for r in _formulas()["rows"] if r["id"] == fid)


def _fr(fid: str) -> str:
    return _p(_formulas(), _formula(fid)["page"])


def select(heat_loss_w: float | None = None, ambient_c: float | None = None, max_internal_c: float | None = None,
           altitude_m: float | None = None, siting: str | None = None, area_m2: float | None = None,
           material: str | None = None, sections: list | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]

    # --- input validation (no defaults for physical inputs)
    if heat_loss_w is None or heat_loss_w <= 0:
        return res.invalid(f"heat_loss_w (total heat loss inside the enclosure, W) must be > 0 (got {heat_loss_w})")
    if ambient_c is None:
        return res.invalid("ambient_c (maximum ambient temperature Tu around the enclosure) is required")
    if max_internal_c is None:
        return res.invalid("max_internal_c (maximum permitted internal temperature Ti) is required")
    if altitude_m is None:
        return res.invalid("altitude_m (site altitude) is required")
    if siting not in SITINGS:
        return res.invalid(f"siting must be indoor or outdoor (got {siting})")
    if area_m2 is not None:
        if area_m2 <= 0:
            return res.invalid(f"area_m2 must be > 0 (got {area_m2})")
        if not material:
            return res.invalid("material is required with area_m2 (it decides k)")
    if sections is not None and not (isinstance(sections, list) and all(isinstance(s, dict) for s in sections)):
        return res.invalid("sections must be a list of {width_mm, height_mm, depth_mm, installation}")

    qv, tu, ti, h = float(heat_loss_w), float(ambient_c), float(max_internal_c), float(altitude_m)
    dt = ti - tu

    # --- scope (R-ENC-01)
    kpage = next(r["page"] for r in _k()["rows"] if r.get("basis"))
    if siting != "indoor":
        return res.refuse("R-ENC-01", "indoor siting (k basis: indoor siting, static air)", siting, _p(_k(), kpage))
    bands = _altitude()["rows"]
    h_lo, h_hi = min(b["h_min_m"] for b in bands), max(b["h_max_m"] for b in bands)
    if not h_lo <= h <= h_hi:
        return res.refuse("R-ENC-01", f"site altitude {h_lo} … {h_hi} m (compensating factor f)", f"{h:g} m",
                          _p(_altitude(), bands[0]["page"]))
    res.add("R-ENC-01", "indoor siting, altitude 0 … 1000 m", f"{siting}, {h:g} m", PASS,
            _p(_altitude(), bands[0]["page"]))

    # --- surface area (R-ENC-02, R-ENC-03) and k (R-ENC-04)
    adef = _fr("area_def")
    if area_m2 is None and sections:
        return res.refuse("R-ENC-02", "effective surface area A to IEC 890 from the sizes and installation type",
                          f"{len(sections)} section(s) given: the IEC 890 installation-type formulas are not printed in "
                          "the held Rittal catalogue and IEC TR 60890 is not held — enter A (area_m2)", adef)
    k = a = None
    if area_m2 is not None:
        a = float(area_m2)
        res.add("R-ENC-03", "effective surface area A (designer entry, to IEC TR 60890)",
                f"{a:g} m² — not checked: IEC TR 60890 not held", WARN, adef)
        if sections:
            res.add("R-ENC-02", "section sizes", f"{len(sections)} section(s) recorded; A from the designer is used",
                    INFO, adef)
        krow = next((r for r in _k()["rows"] if r["material"] == material), None)
        if krow is None:
            mats = sorted({r["material"] for r in _k()["rows"]})
            return res.refuse("R-ENC-04", f"heat transfer coefficient k given for {', '.join(mats)}",
                              f"{material}: no k in the catalogue", _p(_k(), _k()["rows"][0]["page"]))
        k = float(krow["k_w_m2k"])
        res.add("R-ENC-04", f"k for {material}", f"{k:g} W/m²K", PASS, _p(_k(), krow["page"]))

    v: dict = {"k_w_m2k": k, "area_m2": a}

    # --- natural convection (R-ENC-05 … R-ENC-07)
    passive = "not assessed"
    if a is not None:
        dt_nat = qv / (k * a)
        t_nat = tu + dt_nat
        qs = a * k * dt
        res.add("R-ENC-05", "(ΔT)max = Q̇v / (k·A)",
                f"{qv:g} / ({k:g}×{a:g}) = {dt_nat:.2f} K → {t_nat:.2f} °C without cooling", PASS, _fr("delta_t_max"))
        res.add("R-ENC-06", "Q̇s = A·k·ΔT, ΔT = Ti − Tu",
                f"{a:g}×{k:g}×({dt:g}) = {qs:.1f} W" + (" (taken in: Ti < Tu)" if qs < 0 else ""), PASS,
                _fr("q_surface"))
        passive = "yes" if t_nat <= ti + 1e-9 else "no"
        res.add("R-ENC-07", f"no cooling needed if Tu + (ΔT)max ≤ Ti = {ti:g} °C",
                f"{t_nat:.2f} °C: " + ("enough" if passive == "yes" else "not enough"), PASS, _fr("delta_t_max"))
        v.update(delta_t_natural_k=round(dt_nat, 2), internal_natural_c=round(t_nat, 2), surface_w=round(qs, 2))
    else:
        res.add("R-ENC-07", "no cooling needed?", "not assessed: A not given", INFO, _fr("delta_t_max"))
    v["passive"] = passive

    # --- ambient-air cooling: fans and heat exchangers (R-ENC-08 … R-ENC-14)
    fans_possible = dt > 0
    if fans_possible:
        res.add("R-ENC-08", "fans / air-air heat exchangers need Tu < Ti", f"{tu:g} °C < {ti:g} °C", PASS,
                _fr("fan_prerequisite"))
        cands = [b for b in bands if b["h_min_m"] <= h <= b["h_max_m"]]
        band = max(cands, key=lambda b: b["f"]) if prm["boundary_altitude"] == "higher" else \
            min(cands, key=lambda b: b["f"])
        f = float(band["f"])
        if len(cands) > 1:
            res.add("R-ENC-10", "altitude on a band boundary → higher f",
                    f"{h:g} m is in " + " and ".join(f"{b['h_min_m']}–{b['h_max_m']} m" for b in cands) + f" → f = {f:g}",
                    INFO, _p(_altitude(), band["page"]))
        airflow = f * qv / dt
        res.add("R-ENC-09", "V̇ = f · Q̇v / ΔT",
                f"{f:g} × {qv:g} / {dt:g} = {airflow:.2f} m³/h (= {airflow / 3.6:.2f} l/s; f for "
                f"{band['h_min_m']}–{band['h_max_m']} m)", PASS, _p(_altitude(), band["page"]))
        srow = next(r for r in _siemens()["rows"] if r["quantity"] == "airflow_coefficient")
        coef = float(srow["value"])
        sie_ls = qv * coef / dt
        f0 = float(next(b for b in bands if b["h_min_m"] == h_lo)["f"])
        agree = abs(f0 / 3.6 - coef) / coef * 100
        res.add("R-ENC-13", f"Siemens cross-check: airflow [l/s] = Q̇v × {coef:g} / ΔT",
                f"{sie_ls:.2f} l/s vs Rittal {airflow / 3.6:.2f} l/s; at 0–100 m Rittal f/3.6 = {f0 / 3.6:.3f} vs "
                f"{coef:g} ({agree:.1f} % apart)" + ("; Siemens has no altitude factor, Rittal governs"
                                                      if f != f0 else ""), INFO, _p(_siemens(), srow["page"]))
        v.update(altitude_factor=f, fan_airflow_m3h=round(airflow, 2), fan_airflow_ls=round(airflow / 3.6, 2),
                 siemens_airflow_ls=round(sie_ls, 2))

        qw = (qv - (a * dt * k if a is not None else 0.0)) / dt
        qw = max(qw, 0.0)
        hx = [r for r in _products()["rows"] if r["kind"] == "heat_exchanger"]
        pick = next((r for r in sorted(hx, key=lambda r: r["q_w_per_k"]) if r["q_w_per_k"] >= qw - 1e-9), None) \
            if qw > 0 else None
        if a is None:
            res.add("R-ENC-16", "heat exchanger without A: surface ignored", f"qw = {qv:g} / {dt:g}", INFO,
                    _fr("heat_exchanger"))
        if qw == 0:
            txt = "0 W/K: the surface removes the heat, none needed"
        elif pick:
            txt = f"qw = {qw:.2f} W/K → {pick['article']} ({pick['q_w_per_k']:g} W/K)"
        else:
            txt = f"qw = {qw:.2f} W/K > largest listed {max(r['q_w_per_k'] for r in hx):g} W/K: no model"
        res.add("R-ENC-14", "air/air heat exchanger qw = (Q̇v − A·ΔT·k)/ΔT, smallest listed model ≥ qw", txt, INFO,
                _fr("heat_exchanger"))
        v.update(heat_exchanger_w_per_k=round(qw, 2), heat_exchanger=pick["article"] if pick else None)
    else:
        res.add("R-ENC-08", "fans / air-air heat exchangers need Tu < Ti",
                f"Ti {ti:g} °C ≤ Tu {tu:g} °C: not possible, only a cooling unit can hold Ti", INFO,
                _fr("fan_prerequisite"))

    # --- cooling unit (R-ENC-15 … R-ENC-17)
    if a is not None:
        qe = qv - k * a * dt
        res.add("R-ENC-15", "Q̇E = Q̇v − k·A·ΔT", f"{qv:g} − {k:g}×{a:g}×({dt:g}) = {qe:.2f} W", PASS,
                _fr("cooling_unit"))
    elif dt < 0:
        return res.refuse("R-ENC-15", "Q̇E = Q̇v − k·A·ΔT with Ti < Tu needs A (heat taken in through the surface)",
                          f"Ti {ti:g} °C < Tu {tu:g} °C and A not given", _fr("cooling_unit"))
    else:
        qe = qv
        res.add("R-ENC-16", "cooling unit without A: surface ignored (A = 0)", f"Q̇E = Q̇v = {qv:g} W", INFO,
                _fr("cooling_unit"))
    margin = float(prm["cooling_margin_pct"])
    qe_req = max(qe, 0.0) * (1 + margin / 100)
    res.add("R-ENC-17", "margin on the cooling-unit output", f"{margin:g} % → {qe_req:.2f} W", INFO, "rules.yaml")
    v["cooling_unit_w"] = round(qe_req, 2)

    # --- recommended method (R-ENC-18, R-ENC-11, R-ENC-12)
    if passive == "yes":
        method = "passive"
    elif fans_possible and dt >= prm["min_fan_dt_k"]:
        method = "fan"
    else:
        method = "cooling_unit"
    if fans_possible and passive != "yes" and dt < prm["min_fan_dt_k"]:
        res.add("R-ENC-11", f"fans practical only if Ti − Tu ≥ {prm['min_fan_dt_k']} K",
                f"{dt:g} K: needs {v['fan_airflow_m3h']:g} m³/h — cooling unit recommended", WARN,
                _p(_altitude(), bands[0]["page"]))
    if method == "fan":
        rng = next(r for r in _products()["rows"] if r["kind"] == "fan_and_filter_range")
        if v["fan_airflow_m3h"] > rng["airflow_max_m3h"]:
            res.add("R-ENC-12", f"airflow within one Blue e+ fan-and-filter unit (≤ {rng['airflow_max_m3h']} m³/h)",
                    f"{v['fan_airflow_m3h']:g} m³/h: several units, roof-mounted fans or a cooling unit needed", WARN,
                    _p(_products(), rng["page"]))
        else:
            res.add("R-ENC-12", f"airflow within one Blue e+ fan-and-filter unit (≤ {rng['airflow_max_m3h']} m³/h)",
                    f"{v['fan_airflow_m3h']:g} m³/h; model not selected (no per-model table)", PASS,
                    _p(_products(), rng["page"]))
    res.add("R-ENC-18", "method: no cooling → fans → cooling unit", method, PASS, "rules.yaml")

    res.value = {"method": method, **{key: val for key, val in v.items() if val is not None or key == "heat_exchanger"}}
    res.basis = "Rittal TSC 3124300"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
