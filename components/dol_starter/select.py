"""DOL starter: Siemens 3RV2 + 3RT2, Type 2, 400 V. Rules: RULES.md / rules.yaml (R-DOL-01 … 13).

24 V DC coils and coil power from Catalog IC 10 · 2026 (SIE-IC10-2026): ic10_3rt2_contactors, ic10_3rt2_coil_power.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "dol_starter"
IE_CLASSES = ("IE1", "IE2", "IE3", "IE4")
FLC_BASES = ("nameplate", "datasheet", "guide", "guide_voltage_scaled", "calculated")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _table() -> dict:
    return load_sourced_table(data_file("siemens_type2_400v.yaml"),
                              ("range", "range_ie3", "mpcb", "contactor", "size"))


@lru_cache(maxsize=None)
def _links() -> dict:
    return load_sourced_table(data_file("siemens_link_modules.yaml"), ("size", "coil", "article"))


@lru_cache(maxsize=None)
def _ic10() -> dict:
    return {r["article"]: r for r in load_sourced_table(data_file("ic10_3rt2_contactors.yaml"), ("article", "type", "uc_v"))["rows"]}


@lru_cache(maxsize=None)
def _coil_power() -> list[dict]:
    return load_sourced_table(data_file("ic10_3rt2_coil_power.yaml"), ("size", "types", "coil"))["rows"]


def _dc_version(ac_article: str, driver: str):
    """R-DOL-07 / 12: the 24 V DC version of the row's contactor (same type, screw terminals, same aux contacts)."""
    ic = _ic10()
    ac = ic[ac_article]
    same = [r for r in ic.values() if r["type"] == ac["type"] and r["article"][8] == "1" and r["aux_ident"] == ac["aux_ident"]
            and r["uc_v"] in ("24", "20 ... 33") and r["operation"] != "AC" and "-" not in r["article"][9:]]
    coupling = next((r for r in same if r["operation"].startswith("DC (coupling") and r["article"][9:11] == "KB"), None)
    varistor = next((r for r in same if "varistor" in r["version"] and not r["operation"].startswith("DC (coupling")), None)
    return coupling if driver == "plc" else varistor, varistor


def _first(v) -> float:
    """'27/24.3' (50 Hz / 60 Hz) → 27 (owner 2026-10-13: 50 Hz figures for 50 Hz coils)."""
    return float(str(v).split("/")[0])


def _coil(article: str):
    """R-DOL-13: closing / holding power of the contactor's coil and the row it comes from."""
    r = _ic10()[article]
    rows = [c for c in _coil_power() if r["type"] in c["types"]]
    code = article[9:11]
    if r["operation"] == "AC":
        c = next((c for c in rows if c["coil"] == "AC" and "50 Hz, standard" in c["version"]), None) or \
            next((c for c in rows if c["coil"] == "AC" and "50/60 Hz, standard" in c["version"]), None)
        return c and (_first(c["ac_close_va"]), _first(c["ac_hold_va"]), "VA", c)
    if r["operation"].startswith("DC (coupling"):
        c = next((c for c in rows if c["coil"] == "DC coupling" and f".{code}4." in c["version"]), None)
    elif r["operation"] == "AC/DC":
        c = next((c for c in rows if c["coil"] == "AC/DC" and (".N.3." in c["version"] or ".NB3." in c["version"])), None)
        return c and (float(c.get("acdc_dc_close_va") or c["dc_close_w"]), float(c.get("acdc_dc_hold_va") or c["dc_hold_w"]),
                      "VA" if c.get("acdc_dc_close_va") else "W", c)
    else:
        c = next((c for c in rows if c["coil"] == "DC"), None)
    return c and (float(c["dc_close_w"]), float(c["dc_hold_w"]), "W", c)


def _src(row: dict, ref: str = "SIE-SIRIUS-CM") -> str:
    return f"{ref} p.{row['page']}"


def select(flc_a: float, fault_ka: float | None = None, ie_class: str | None = None,
           flc_basis: str | None = None, starting_current_a: float | None = None, phases: int = 3,
           voltage_v: float = 400.0, load_type: str = "motor", coil: str | None = None,
           coil_driver: str | None = None, mpcb_range: str | None = None, suppressor: str | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    p = _rules()["params"]
    tab = _table()
    cond = tab["conditions"]
    coil = (coil or p["coil_default"]).upper().replace(" ", "")

    # --- input validation
    if not flc_a or flc_a <= 0:
        return res.invalid(f"FLC must be > 0 (got {flc_a})")
    if fault_ka is None or fault_ka <= 0:
        return res.invalid("prospective fault current at the starter (fault_ka) is required")
    if ie_class is not None and str(ie_class).upper() not in IE_CLASSES:
        return res.invalid(f"ie_class must be one of {', '.join(IE_CLASSES)} (got {ie_class})")
    if flc_basis is not None and flc_basis not in FLC_BASES:
        return res.invalid(f"flc_basis must be one of {', '.join(FLC_BASES)} (got {flc_basis})")
    if coil_driver is not None and coil_driver not in ("plc", "relay"):
        return res.invalid(f"coil_driver must be plc or relay (got {coil_driver})")
    if suppressor not in (None, "varistor", "none"):
        return res.invalid(f"suppressor must be varistor or none (got {suppressor})")
    want = None
    if mpcb_range is not None:                      # R-DOL-14: the client's MPCB setting range, 'lo-hi' in A
        try:
            want = tuple(float(x) for x in str(mpcb_range).replace("…", "-").replace(" ", "").split("-"))
        except ValueError:
            want = ()
        if len(want) != 2 or not 0 < want[0] < want[1]:
            return res.invalid(f"mpcb_range must be 'low-high' in A (got {mpcb_range!r})")

    # --- scope
    if load_type != "motor":
        return res.refuse("R-DOL-01", "motor load (table is for 3-phase motors)", f"load type {load_type}",
                          _src({"page": 28}))
    if phases != cond["phases"] or abs(voltage_v - cond["voltage_v"]) > 1e-9:
        return res.refuse("R-DOL-01", f"3-phase {cond['voltage_v']:g} V AC",
                          f"{phases}-phase {voltage_v:g} V", _src({"page": 28}))
    res.add("R-DOL-01", "3-phase motor, 400 V AC", "in scope", PASS, _src({"page": 28}))
    if coil not in p["coils_in_scope"]:
        return res.refuse("R-DOL-07", "contactor coil 230 V AC 50 Hz or 24 V DC",
                          f"{coil}: not in scope", "SIE-SIRIUS-CM p.29 footnote 2")
    if fault_ka > cond["iq_ka"]:
        return res.refuse("R-DOL-06", f"Iq {cond['iq_ka']:g} kA ≥ prospective fault current",
                          f"{fault_ka:g} kA", _src({"page": 28}))
    res.add("R-DOL-06", f"Iq {cond['iq_ka']:g} kA ≥ prospective fault current", f"{fault_ka:g} kA", PASS,
            _src({"page": 28}))

    # --- IE class
    if ie_class is None:
        ie = p["ie_class_default"]
        res.add("R-DOL-11", "IE class given", f"not given: {ie} limits applied (lower maximum setting)", INFO,
                "hand rule")
    else:
        ie = str(ie_class).upper()
    high_inrush = ie in ("IE3", "IE4")
    col = "range_ie3" if high_inrush else "range"
    col_label = "IE3/IE4" if high_inrush else "IE1/IE2"

    lo = min(r[col][0] for r in tab["rows"])
    hi = max(r[col][1] for r in tab["rows"])
    if want is not None:
        return _suppress(_client_range(res, tab, want, flc_a, col, col_label, coil, coil_driver, flc_basis), suppressor)
    if not lo <= flc_a <= hi:
        return res.refuse("R-DOL-10", f"FLC within the 3RV2 ranges ({lo:g} … {hi:g} A, {col_label})",
                          f"{flc_a:g} A", _src({"page": 28 if flc_a < lo else 29}))

    # --- candidate rows
    cands = []
    for i, r in enumerate(tab["rows"]):
        a, b = (float(x) for x in r[col])
        if not a <= flc_a <= b:
            continue
        limit = r.get("ie3_start_max_a")
        if high_inrush and limit:
            if starting_current_a is None or starting_current_a > limit:
                why = "not given" if starting_current_a is None else f"{starting_current_a:g} A"
                res.add("R-DOL-03", f"{r['mpcb']} usable for IE3/IE4 only up to {limit:g} A starting current",
                        f"starting current {why}: row skipped", INFO, _src(r))
                continue
            res.add("R-DOL-03", f"{r['mpcb']} IE3/IE4 starting-current limit {limit:g} A",
                    f"{starting_current_a:g} A", PASS, _src(r))
        margin = min(flc_a - a, b - flc_a) / (b - a)
        cands.append((margin, i, r, (a, b)))
    if not cands:
        return res.refuse("R-DOL-02", f"a {col_label} setting range containing the FLC",
                          f"{flc_a:g} A: no usable row (see skipped rows)", _src({"page": 28}))

    margin, _, row, (a, b) = max(cands, key=lambda c: (round(c[0], 9), -c[1]))
    res.add("R-DOL-02", f"setting range ({col_label}) contains FLC", f"{flc_a:g} A in {a:g} … {b:g} A ({row['mpcb']})",
            PASS, _src(row))
    if len(cands) > 1:
        others = "; ".join(f"{r['mpcb']}+{r['contactor'].split('-')[0]} {m:.3f}" for m, _, r, _ in cands if r is not row)
        res.add("R-DOL-04", "largest margin min(FLC−min, max−FLC)/(max−min); tie → table order",
                f"chosen {margin:.3f}; others: {others}", PASS, "hand rule")
    return _suppress(_finish(res, row, a, b, flc_a, coil, coil_driver, flc_basis), suppressor)


def _finish(res: Result, row: dict, a: float, b: float, flc_a: float, coil: str, coil_driver, flc_basis) -> Result:
    """R-DOL-05 … 13 for the chosen Type 2 row: contactor (and its 24 V DC version), coil power, link module, FLC basis."""
    p = _rules()["params"]
    cond = _table()["conditions"]
    res.add("R-DOL-05", "contactor from the same Type 2 row", f"{row['contactor']} ({row['size']})", PASS, _src(row))
    contactor = row["contactor"]
    if coil == "24VDC":
        driver = coil_driver or p["coil_driver_default"]
        if coil_driver is None:
            res.add("R-DOL-12", "who drives the 24 V DC coil", "not given: PLC output assumed", INFO, "owner decision 2026-10-13")
        chosen, varistor = _dc_version(contactor, driver)
        if chosen is None and driver == "plc" and varistor:
            chosen = varistor
            res.add("R-DOL-12", f"coupling contactor (KB4.) for direct PLC control of {contactor[:7]}",
                    f"none in IC 10: {chosen['article']} (varistor) — an interposing relay is needed between the PLC output "
                    "and the coil", WARN, f"SIE-IC10-2026 p.{chosen['page']}")
        elif chosen is None:
            return res.refuse("R-DOL-07", f"24 V DC version of {contactor}", "none in IC 10", "SIE-IC10-2026 pp.177-188")
        else:
            res.add("R-DOL-12", "24 V DC coil version: " + ("coupling contactor for direct PLC control" if driver == "plc"
                    else "varistor"), chosen["article"], PASS, "owner decision 2026-10-13")
        res.add("R-DOL-07", f"24 V DC version of {contactor}: same type, screw terminals, aux contacts {chosen['aux_ident']}",
                f"{chosen['article']} (Uc {chosen['uc_v']} V)", PASS,
                f"SIE-SIRIUS-CM p.29 footnote 2; SIE-IC10-2026 p.{chosen['page']} ({chosen['printed']})")
        contactor = chosen["article"]
    cp = _coil(contactor)
    if cp:
        close, hold, unit, crow = cp
        note = f"; {crow['pickup_note']}" if crow.get("pickup_note") else ""
        res.add("R-DOL-13", "coil power (closing / holding)", f"{close:g} / {hold:g} {unit}{note}", INFO,
                f"SIE-IC10-2026 p.{crow['page']} ({crow['printed']})")
    
    # --- link module
    m_size, c_size = row["size"].split("/")
    link = None
    if m_size == c_size:
        coil_kind = "AC" if coil.endswith("AC") else "DC"
        lk = _links()["rows"]
        link = next((x for x in lk if x["size"] == c_size and x["coil"] in ("any", coil_kind)), None)
    if link:
        res.add("R-DOL-08", f"link module MPCB – contactor size {c_size}", link["article"], PASS,
                _src(link))
    else:
        res.add("R-DOL-08", "link module for the size pair in Table 2-1",
                f"{row['size']}: not in Table 2-1 — confirm in the SIRIUS configurator or wire directly", WARN,
                "SIE-SIRIUS-CM p.22")
    
    # --- FLC basis
    if flc_basis in ("nameplate", "datasheet"):
        res.add("R-DOL-09", "FLC from the motor's own data", flc_basis, PASS, "designer entry")
    elif flc_basis == "calculated":
        res.add("R-DOL-09", "FLC basis", "calculated", INFO, "")
    else:
        res.add("R-DOL-09", "FLC from the motor's own data (selection depends on actual motor data)",
                f"basis {flc_basis or 'not stated'}: confirm the setting with the nameplate", WARN,
                "SIE-SIRIUS-CM p.29 footnote 1")
    
    res.value = {"mpcb": row["mpcb"], "setting_range_a": f"{a:g} … {b:g}", "set_at_a": flc_a,
                 "device_range_a": f"{float(row['range'][0]):g} … {float(row['range'][1]):g}",   # the MPCB's printed range
                 "contactor": contactor, "size": row["size"], "coil": coil,
                 "coil_close": cp[0] if cp else None, "coil_hold": cp[1] if cp else None, "coil_unit": cp[2] if cp else None,
                 "link_module": link["article"] if link else None, "iq_ka": float(cond["iq_ka"])}
    res.basis = "Type 2 table"
    return res


@lru_cache(maxsize=None)
def _suppressors() -> dict:
    return load_sourced_table(data_file("3rt2_surge_suppressors.yaml"), ("size", "article", "ac_v", "dc_v"))


def _suppress(res: Result, suppressor: str | None) -> Result:
    """R-DOL-15 (owner 2026-10-20, RFQ part 3): a varistor surge suppressor on the contactor, by its size and coil voltage."""
    if res.value is None:
        return res
    res.value["suppressor"] = None
    if suppressor != "varistor":
        return res
    v = res.value
    size = str(v["size"]).split("/")[-1]
    uc = (230.0, "ac") if str(v["coil"]).endswith("AC") else (24.0, "dc")
    key = "ac_v" if uc[1] == "ac" else "dc_v"
    row = next((r for r in _suppressors()["rows"] if r["size"] == size and r[key][0] <= uc[0] <= r[key][1]), None)
    if row is None:
        res.add("R-DOL-15", f"varistor for a size {size} contactor, {uc[0]:g} V {uc[1].upper()} coil", "none transcribed", WARN,
                "SIE-IC10-2026 p.224")
        return res
    res.add("R-DOL-15", f"varistor surge suppressor for the size {size} contactor, {uc[0]:g} V {uc[1].upper()} coil",
            f"{row['article']} ({row[key][0]:g} … {row[key][1]:g} V {uc[1].upper()})", PASS, f"SIE-IC10-2026 p.{row['page']} (printed 3/96)")
    v["suppressor"] = row["article"]
    return res


def _client_range(res: Result, tab: dict, want: tuple, flc_a: float, col: str, col_label: str, coil: str, coil_driver,
                  flc_basis) -> Result:
    """R-DOL-14 (owner 2026-10-18, RFQ import: 'the RFQ value wins, flag if unsafe'): the Type 2 row whose MPCB has the
    client's printed setting range; its contactor follows (tested pair). The motor current outside the row's usable range
    → warning (the motor is not protected as the client states). No row with that range → refused (no source)."""
    rows = [(i, r) for i, r in enumerate(tab["rows"]) if abs(float(r["range"][0]) - want[0]) < 1e-6 and abs(float(r["range"][1]) - want[1]) < 1e-6]
    if not rows:
        return res.refuse("R-DOL-14", f"a 3RV2 with the client's setting range {want[0]:g} … {want[1]:g} A in the Type 2 table",
                          "none: the client's MPCB has no tested Type 2 row (ask the client or use the engine's choice)", _src({"page": 28}))
    def fits(r):
        a, b = (float(x) for x in r[col])
        return a <= flc_a <= b, (min(flc_a - a, b - flc_a) / (b - a)) if a <= flc_a <= b else -1
    i, row = max(rows, key=lambda x: (fits(x[1])[0], round(fits(x[1])[1], 9), -x[0]))
    a, b = (float(x) for x in row[col])
    if row.get("ie3_start_max_a") and col == "range_ie3":
        res.add("R-DOL-03", f"{row['mpcb']} usable for IE3/IE4 only up to {row['ie3_start_max_a']:g} A starting current",
                "the client's choice: confirm the motor's starting current", WARN, _src(row))
    res.add("R-DOL-14", "the client's MPCB setting range (RFQ value wins, owner 2026-10-18)",
            f"{want[0]:g} … {want[1]:g} A → {row['mpcb']} + {row['contactor']} ({row['size']})", PASS, _src(row))
    if a <= flc_a <= b:
        res.add("R-DOL-02", f"setting range ({col_label}) contains FLC", f"{flc_a:g} A in {a:g} … {b:g} A ({row['mpcb']})",
                PASS, _src(row))
    elif want[0] <= flc_a <= want[1]:
        res.add("R-DOL-14", f"motor current within the client's MPCB usable range ({col_label} {a:g} … {b:g} A)",
                f"{flc_a:g} A is inside the printed {want[0]:g} … {want[1]:g} A but above the {col_label} usable maximum: "
                "confirm the motor's IE class with the client", WARN, _src(row))
    else:
        res.add("R-DOL-14", f"motor current within the client's MPCB range ({want[0]:g} … {want[1]:g} A)",
                f"{flc_a:g} A is outside it: the motor is not protected as the client states — tell the client", WARN, _src(row))
    return _finish(res, row, a, b, flc_a, coil, coil_driver, flc_basis)


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
