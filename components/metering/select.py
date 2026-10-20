"""Metering: Siemens SENTRON 7KM PAC3220 energy meter with PROFINET module + Rishabh / Selec CTs.
Rules: RULES.md / rules.yaml (R-MTR-01 … 14)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from core import project as P
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "metering"
MAKES = ("rishabh", "selec")
COMMS = ("profinet", "modbus_tcp", "none")      # none: the meter reads locally only (audit 2026-10-17: asked, not defaulted)
SYSTEMS = ("3P4W",)


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _pac() -> dict:
    return load_sourced_table(data_file("pac3220.yaml"), ("item", "value"))


@lru_cache(maxsize=None)
def _lv10() -> dict:
    return load_sourced_table(data_file("pac3220_lv10.yaml"), ("item", "value", "supply"))


SUPPLIES = {"ac_dc": "article_ac_dc", "dc_24_60": "article_dc_24_60"}


@lru_cache(maxsize=None)
def _pn() -> dict:
    return load_sourced_table(data_file("pac_profinet_module.yaml"), ("device",))


@lru_cache(maxsize=None)
def _ltrp() -> dict:
    return load_sourced_table(data_file("rishabh_ltrp.yaml"), ("size", "primary_a", "va", "class", "window"))


@lru_cache(maxsize=None)
def _tw() -> dict:
    return load_sourced_table(data_file("rishabh_tw.yaml"), ("size", "primary_a", "va", "class", "window_d_mm"))


@lru_cache(maxsize=None)
def _selec() -> dict:
    return load_sourced_table(data_file("selec_ct.yaml"), ("family", "size", "primary_a", "va", "class", "window"))


@lru_cache(maxsize=None)
def _selec_ambient() -> dict:
    return load_sourced_table(data_file("selec_ct_ambient.yaml"), ("family", "ambient_min_c", "ambient_max_c"))


def _p(table: dict, page: int) -> str:
    ref, off = table["source"]["ref"], int(table["source"].get("printed_page_offset") or 0)
    return f"{ref} p.{page}" + (f" (printed {page + off})" if off else "")


def _pac_row(item: str) -> dict:
    return next(r for r in _pac()["rows"] if r["item"] == item)


def _num(v) -> str:
    return f"{float(v):g}"


@lru_cache(maxsize=None)
def _rish_cond(fam: str) -> dict:
    return load_sourced_table(data_file(f"rishabh_{fam.lower()}_conditions.yaml"), ("item", "value"))


def _cond(make: str, fam: str) -> dict:
    """secondary current, Um and ambient limits of a CT family, each with its source."""
    if make == "rishabh":
        t = _rish_cond(fam)
        g = {r["item"]: r for r in t["rows"]}
        return {"secondary_a": (g["secondary_a"]["value"], _p(t, g["secondary_a"]["page"])),
                "um_max_v": (g["um_max_v"]["value"], _p(t, g["um_max_v"]["page"])),
                "ambient_c": (tuple(g["ambient_c"]["value"]), _p(t, g["ambient_c"]["page"]))}
    t, a = _selec(), _selec_ambient()
    amb = next(r for r in a["rows"] if r["family"] == fam)
    return {"secondary_a": (t["conditions"]["secondary_a"], _p(t, t["condition_pages"]["secondary"])),
            "um_max_v": (t["conditions"]["um_max_v"], _p(t, t["condition_pages"]["voltage"])),
            "ambient_c": ((amb["ambient_min_c"], amb["ambient_max_c"]), _p(a, amb["page"]))}


@lru_cache(maxsize=None)
def _ct_rows() -> dict[str, list[dict]]:
    """Every printed CT option of each make, tagged with family, size order, source table and conditions."""
    out: dict[str, list[dict]] = {"rishabh": [], "selec": []}
    for make, fam_tabs in (("rishabh", (("LTRP", _ltrp()), ("TW", _tw()))), ("selec", ((None, _selec()),))):
        for fam, tab in fam_tabs:
            sizes: dict[tuple, int] = {}
            for r in tab["rows"]:
                f = fam or r["family"]
                ix = sizes.setdefault((f, r["size"]), len(sizes))
                out[make].append({**r, "family": f, "window": r.get("window", "round"), "size_ix": ix,
                                  "table": tab, "cond": _cond(make, f)})
    return out


def _class_key(c) -> str | None:
    s = str(c).strip().upper()
    if s.endswith("S"):
        s = s[:-1]
        try:
            return f"{float(s):g}S"
        except ValueError:
            return None
    try:
        return f"{float(s):g}"
    except ValueError:
        return None


def _window_text(r: dict) -> str:
    return f"Ø{_num(r['window_d_mm'])} mm" if r["window"] == "round" else \
        f"{_num(r['window_w_mm'])} × {_num(r['window_h_mm'])} mm"


def _fits(r: dict, bw, bt, cd) -> bool:
    if r["window"] == "round":
        d = r["window_d_mm"]
        return (math.hypot(bw, bt) <= d + 1e-9) if bw is not None else cd <= d + 1e-9
    w, h = r["window_w_mm"], r["window_h_mm"]
    if bw is not None:
        return (bw <= w + 1e-9 and bt <= h + 1e-9) or (bw <= h + 1e-9 and bt <= w + 1e-9)
    return cd <= min(w, h) + 1e-9


def _designation(r: dict) -> str:
    p, va, cls = r["primary_a"], _num(r["va"]), r["class"]
    if r["family"] == "LTRP":
        return f"RISH {r['size']}, {p}/5 A, {va} VA, class {cls}"
    if r["family"] == "TW":
        return f"RISH CT {r['size']}, {p}/5 A, {va} VA, class {cls}"
    return _selec()["designation"][r["family"]].format(size=r["size"], primary=p, va=va, cls=cls)


def select(circuit_a: float, ct_make: str, voltage_v: float = 400.0, system: str = "3P4W",
           accuracy_class: str | None = None, ct_secondary_a: int | None = None,
           busbar_w_mm: float | None = None, busbar_t_mm: float | None = None, cable_od_mm: float | None = None,
           lead_length_m: float | None = None, lead_mm2: float | None = None, lead_temp_c: float | None = None,
           communication: str | None = None, ambient_c: float | None = None,
           client_requirements: dict | None = None, meter_supply: str | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    order = prm["class_order"]

    # --- input validation
    if not circuit_a or circuit_a <= 0:
        return res.invalid(f"circuit current must be > 0 (got {circuit_a})")
    make = str(ct_make or "").strip().lower()
    if make not in MAKES:
        return res.invalid(f"CT make must be rishabh or selec (client: 'Rishabh/Selec', got {ct_make})")
    if not voltage_v or voltage_v <= 0:
        return res.invalid(f"voltage must be > 0 (got {voltage_v})")
    req = _class_key(accuracy_class if accuracy_class is not None else prm["accuracy_class_default"])
    if req not in order:
        return res.invalid(f"accuracy class must be one of {', '.join(order)} (got {accuracy_class})")
    sec = prm["ct_secondary_default"] if ct_secondary_a is None else ct_secondary_a
    if sec not in (1, 5):
        return res.invalid(f"CT secondary must be 1 or 5 A (got {ct_secondary_a})")
    comm = (communication or prm["communication_default"]).strip().lower()
    if comm not in COMMS:
        return res.invalid(f"communication must be profinet, modbus_tcp or none (got {communication})")
    if (busbar_w_mm is None) != (busbar_t_mm is None):
        return res.invalid("give both busbar width and thickness")
    if busbar_w_mm is not None and cable_od_mm is not None:
        return res.invalid("give a busbar or a cable through the CT, not both")
    if any(v is not None and v <= 0 for v in (busbar_w_mm, busbar_t_mm, cable_od_mm)):
        return res.invalid("conductor dimensions must be > 0")
    if (lead_length_m is None) != (lead_mm2 is None):
        return res.invalid("give both lead length and lead cross-section (or neither)")
    if (lead_length_m is not None and lead_length_m <= 0) or (lead_mm2 is not None and lead_mm2 <= 0):
        return res.invalid("lead length and cross-section must be > 0")
    theta = prm["lead_temp_default_c"] if lead_temp_c is None else lead_temp_c

    pac = _pac()
    # --- R-MTR-01 scope
    uln = voltage_v / math.sqrt(3)
    ull_max = _pac_row("rated_voltage_ull_max_v")["value"]
    uln_max = _pac_row("direct_connection_uln_max_v")["value"]
    sysname = str(system).strip().upper()
    if sysname not in SYSTEMS:
        return res.refuse("R-MTR-01", "3-phase 4-wire system (3P4W, three CTs)", f"{system}: not in scope",
                          _p(pac, _pac_row("cts_for_3p4w")["page"]))
    if voltage_v > ull_max + 1e-9 or uln > uln_max + 1e-9:
        return res.refuse("R-MTR-01", f"line voltage ≤ {ull_max} V and line-to-neutral ≤ {uln_max} V (direct connection)",
                          f"{voltage_v:g} V (UL-N {uln:.0f} V)", _p(pac, _pac_row("rated_voltage_ull_max_v")["page"]))
    rows = _ct_rows()[make]
    um, um_src = min(r["cond"]["um_max_v"] for r in rows)
    if voltage_v > um:
        return res.refuse("R-MTR-01", f"CT highest voltage Um ≤ {um} V", f"{voltage_v:g} V", um_src)
    res.add("R-MTR-01", f"3P4W, ≤ {ull_max} V (UL-N ≤ {uln_max} V), CT Um ≤ {um} V",
            f"{sysname} {voltage_v:g} V (UL-N {uln:.0f} V)", PASS, _p(pac, _pac_row("rated_voltage_ull_max_v")["page"]))

    # --- R-MTR-02 meter + PROFINET module
    pn = _pn()
    pn_dev = next(r for r in pn["rows"] if r["device"] == "PAC3220")
    module = next(r for r in pn["rows"] if r["device"] == "module")["article"]
    if comm == "profinet":
        res.add("R-MTR-02", "7KM meter with PROFINET (client); module fits the device",
                f"PAC3220 + {module} (slot {' or '.join(pn_dev['slots'])})", PASS, _p(pn, pn_dev["page"]))
        comm_module = module
    else:
        mtr_text, mtr_src = P.cite(client_requirements, "meter_communication")
        res.add("R-MTR-02", "PROFINET" + (f" asked by the client ({mtr_src}: '{mtr_text}')" if mtr_text else " not asked"),
                ("Modbus TCP over the PAC3220's own Ethernet" if comm == "modbus_tcp" else "no communication (local display only)")
                + ": no PROFINET module" + (" — differs from the client spec" if mtr_text else ""), WARN if mtr_text else INFO,
                "SIE-PAC3220 p.101 (printed 99)")
        comm_module = None

    # --- R-MTR-03 article number; R-MTR-15 (owner 2026-10-20): the full number from the meter's supply, LV 10 p.10/32
    pat, ex = _pac_row("article_pattern"), _pac_row("article_on_certificate_link")
    full = None
    if meter_supply is not None:
        if meter_supply not in SUPPLIES:
            return res.invalid(f"meter_supply must be one of {', '.join(SUPPLIES)} (got {meter_supply})")
        row = next(r for r in _lv10()["rows"] if r["item"] == SUPPLIES[meter_supply])
        full = row["value"]
        res.add("R-MTR-15", "meter order number from its supply version", f"{full}: {row['supply']}", PASS,
                f"SIE-LV10-2026 p.{row['page']} (printed 10/32)")
    else:
        res.add("R-MTR-03", "meter article number",
                f"pattern {pat['value']} (PAC3220 → 7KM3220-…); {ex['value']} printed on p.{ex['page']}, supply version not "
                "given — give the meter's supply (meter_supply) for the full number", INFO, _p(pac, pat["page"]))

    # --- R-MTR-04 CT secondary
    sec_row = _pac_row("ct_secondary_a")
    if sec == 1:
        return res.refuse("R-MTR-04", "CT data for the chosen secondary current",
                          f"1 A: the meter accepts x/1 A (p.{sec_row['page']}) but the {make} data held is 5 A only",
                          rows[0]["cond"]["secondary_a"][1])
    res.add("R-MTR-04", "CT secondary matches a meter input (x/1 A or x/5 A)", "5 A", PASS, _p(pac, sec_row["page"]))

    # --- R-MTR-11 ambient
    amb = _pac_row("ambient_c")
    if ambient_c is None:
        res.add("R-MTR-11", "ambient around meter and CTs", "not given: temperature limits not checked "
                f"(meter {amb['value'][0]} … +{amb['value'][1]} °C, CTs see RULES.md)", WARN, _p(pac, amb["page"]))
    else:
        if not amb["value"][0] <= ambient_c <= amb["value"][1]:
            return res.refuse("R-MTR-11", f"meter ambient {amb['value'][0]} … +{amb['value'][1]} °C", f"{ambient_c:g} °C",
                              _p(pac, amb["page"]))
        lims = {r["family"]: (*r["cond"]["ambient_c"][0], r["cond"]["ambient_c"][1]) for r in rows}
        ok_fam = {f for f, (lo, hi, _) in lims.items() if lo <= ambient_c <= hi}
        if not ok_fam:
            lo, hi, src = next(iter(lims.values()))
            return res.refuse("R-MTR-11", f"{make} CT ambient {lo} … +{hi} °C", f"{ambient_c:g} °C", src)
        rows = [r for r in rows if r["family"] in ok_fam]
        res.add("R-MTR-11", "ambient within meter and CT limits",
                f"{ambient_c:g} °C (meter ≤ +{amb['value'][1]} °C; CT " +
                ", ".join(f"{f} ≤ +{lims[f][1]} °C" for f in sorted(ok_fam)) + ")", PASS, lims[sorted(ok_fam)[0]][2])

    # --- R-MTR-07 / 08 burden
    mb = _pac_row("meter_burden_va")
    meter_va = float(mb["value"])
    res.add("R-MTR-07", "meter burden per phase", f"{meter_va:g} VA at {mb['at_a']} A", PASS, _p(pac, mb["page"]))
    lead_va = None
    if lead_length_m is None:
        res.add("R-MTR-08", "lead burden 2·L·I²·ρ/A",
                "lead length / cross-section not given: lead burden NOT checked — CT VA covers the meter only", WARN,
                "physics, IEC 60028 ρ, α")
    else:
        rho = prm["rho20_cu_ohm_mm2_per_m"] * (1 + prm["alpha20_cu_per_k"] * (theta - 20))
        lead_va = prm["lead_loop_factor"] * lead_length_m * sec ** 2 * rho / lead_mm2
        res.add("R-MTR-08", "lead burden 2·L·I²·ρθ/A",
                f"2 × {lead_length_m:g} m × {sec}² A² × {rho:.5f} Ω·mm²/m ({theta:g} °C) / {lead_mm2:g} mm² = {lead_va:.3f} VA",
                PASS, "physics; ρ20 = 1/58 Ω·mm²/m, α20 = 0.00393 /K (IEC 60028)")
    burden = meter_va + (lead_va or 0.0)

    # --- candidates: R-MTR-05 ratio, R-MTR-06 class, R-MTR-10 window, R-MTR-09 burden
    pmin, pmax = _pac_row("ct_primary_range_a")["value"]
    cand = [r for r in rows if r["primary_a"] >= circuit_a - 1e-9 and pmin <= r["primary_a"] <= pmax]
    if not cand:
        top = max(rows, key=lambda r: r["primary_a"])
        return res.refuse("R-MTR-05", "printed CT primary ≥ circuit current",
                          f"{circuit_a:g} A > largest {make} primary {top['primary_a']} A", _p(top["table"], top["page"]))
    first_p = min(r["primary_a"] for r in cand)
    rank = order.index(req)
    cand = [r for r in cand if r["class"] in order and order.index(r["class"]) <= rank]
    if not cand:
        return res.refuse("R-MTR-06", f"CT class {req} or better", f"no {make} CT ≥ {circuit_a:g} A is printed with "
                          f"class {req} or better", _p(rows[0]["table"], rows[0]["page"]))
    bw, bt, cd = busbar_w_mm, busbar_t_mm, cable_od_mm
    if bw is None and cd is None:
        res.add("R-MTR-10", "conductor fits the CT window", "busbar / cable not given: window NOT checked", WARN,
                "geometry")
        cond_txt = None
    else:
        cond_txt = f"busbar {bw:g} × {bt:g} mm" if bw is not None else f"cable Ø{cd:g} mm"
        cand = [r for r in cand if _fits(r, bw, bt, cd)]
        if not cand:
            return res.refuse("R-MTR-10", "conductor fits the CT window",
                              f"{cond_txt}: no {make} CT ≥ {circuit_a:g} A, class ≤ {req} has a large enough window",
                              "geometry; windows from the data sheets")
    cand = [r for r in cand if r["va"] >= burden - 1e-9]
    if not cand:
        return res.refuse("R-MTR-09", "CT rated burden ≥ total burden",
                          f"{burden:.2f} VA: no qualifying {make} CT has that rating", "rules.yaml (R-MTR-09)")

    # --- R-MTR-12 choice
    forder = prm["family_order"][make]
    c = min(cand, key=lambda r: (r["primary_a"], rank - order.index(r["class"]), r["va"],
                                 forder.index(r["family"]), r["size_ix"]))
    src = _p(c["table"], c["page"])
    if c["primary_a"] > first_p:
        res.add("R-MTR-05", "CT primary = smallest printed primary ≥ circuit current",
                f"{first_p} A has no CT meeting class / window / burden → {c['primary_a']} A taken: the meter reads "
                f"the circuit in the lower part of the CT range", WARN, src)
    else:
        res.add("R-MTR-05", "CT primary = smallest printed primary ≥ circuit current",
                f"{c['primary_a']}/5 A for {circuit_a:g} A", PASS, src)
    res.add("R-MTR-06", f"CT class {req} or better (closest)", f"class {c['class']}", PASS, src)
    if cond_txt:
        res.add("R-MTR-10", "conductor fits the CT window", f"{cond_txt} through {_window_text(c)}", PASS, src)
    res.add("R-MTR-09", "CT rated burden ≥ meter + leads",
            f"{_num(c['va'])} VA ≥ {burden:.2f} VA" + ("" if lead_va is not None else " (meter only)"), PASS, src)
    res.add("R-MTR-12", "smallest primary → closest class → smallest VA → family → size",
            f"{_designation(c)} ({len(cand)} qualified)", PASS, "rules.yaml (R-MTR-12)")
    cts = _pac_row("cts_for_3p4w")
    res.add("R-MTR-13", "quantity per panel", f"1 meter + {cts['value']} CTs (3P4W)", PASS, _p(pac, cts["page"]))
    res.add("R-MTR-14", "CT type code",
            "assembled from the printed Selec nomenclature — confirm with Selec" if make == "selec"
            else "Rishabh prints no order code: order by size, ratio, VA and class — confirm with Rishabh", INFO,
            _p(c["table"], c["table"]["designation_pages"][c["family"]]) if make == "selec" else src)

    res.value = {"meter": "SENTRON PAC3220", "meter_article_pattern": "7KM3220-xBA01-1xA0", "meter_article": full,
                 "meter_article_example": ex["value"], "comm_module": comm_module,
                 "ct_make": make, "ct_family": c["family"], "ct_size": c["size"], "ct_designation": _designation(c),
                 "ct_ratio": f"{c['primary_a']}/5 A", "ct_primary_a": float(c["primary_a"]), "ct_secondary_a": 5,
                 "ct_class": c["class"], "ct_va": float(c["va"]), "ct_window": _window_text(c),
                 "ct_qty": int(cts["value"]), "meter_burden_va": meter_va,
                 "lead_burden_va": None if lead_va is None else round(lead_va, 3), "burden_va": round(burden, 3)}
    res.basis = "PAC3220 manual 10/2019 + 7KM PROFINET manual 01/2020 + " + \
        ("Rishabh LTRP / TW data sheets" if make == "rishabh" else "Selec catalogue 2026")
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
