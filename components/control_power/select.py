"""Control power: size the 24 V DC supply. Rules: rules.yaml (R-CP-01 … 05).

Data: data/ab_smps.yaml (OWN-AB-SMPS), data/own_calc_method.yaml (OWN-SWG-CALC), Finder relay coil (FINDER-S38).
PLC, network and UPS selection wait for the Siemens manuals.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.provenance import ROOT, load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "control_power"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _smps() -> dict:
    return load_sourced_table(data_file("ab_smps.yaml"), ("brand", "series", "model", "network", "vout_min", "vout_max",
                                                               "i_out_a", "sheet"))


@lru_cache(maxsize=None)
def _sitop() -> dict:
    """Siemens SITOP PSU6200 from catalogue KT 10.1 (owner 2026-10-20, RFQ part 5) — make 'Siemens'."""
    return load_sourced_table(data_file("sitop_psu6200.yaml"), ("brand", "series", "model", "network", "vout_min", "vout_max",
                                                                  "i_out_a"))


def _norm(s: str) -> str:
    return "".join(str(s).lower().split())


def _verified(row: dict):
    """R-CP-06: the AutoBOM Logsheet entry for the row's series (None if the series is not in it)."""
    log = _smps().get("logsheet") or {}
    return next((v for k, v in log.items() if _norm(k.split("|")[0])[:6] == _norm(row["brand"])[:6]
                 and k.split("|")[1] == row["series"]), None)


@lru_cache(maxsize=None)
def _method() -> dict:
    d = load_sourced_table(data_file("own_calc_method.yaml"), ("item", "value", "sheet"))
    return {r["item"]: r for r in d["rows"]}


@lru_cache(maxsize=None)
def _coil() -> dict:
    ref = _rules()["params"]["relay_coil_ref"]
    d = load_sourced_table(ROOT / ref["file"], ("kind",))
    return next(r for r in d["rows"] if r.get("kind") == "coil" and r.get("coil_code") == ref["coil_code"])


def select(di: int = 0, do: int = 0, relays: int = 0, plc_a: float | None = None, other_a: float = 0.0,
           input: str = "1P+N", voltage_dc: float = 24.0, brand: str = "Omron", communication: bool = False,
           min_a: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    if min(di, do, relays) < 0 or other_a < 0:
        return res.invalid("counts and currents must not be negative")
    if isinstance(communication, str):        # "no" / "false" must not ask for a network port
        if communication.strip().lower() not in ("true", "yes", "1", "false", "no", "0", ""):
            return res.invalid(f"communication must be yes or no (got {communication!r})")
        communication = communication.strip().lower() in ("true", "yes", "1")
    if input not in ("1P+N", "3P"):
        return res.invalid(f"input must be 1P+N or 3P (got {input})")
    m, coil = _method(), _coil()
    src = lambda k: f"OWN-SWG-CALC '{m[k]['sheet']}' row {m[k]['row']}"
    coil_a = coil["i_ma"] / 1000
    res.add("R-CP-01", "interface relay coil current", f"{relays} × {coil['i_ma']:g} mA = {relays * coil_a:.3f} A", PASS,
            f"FINDER-S38 p.{coil['page']}")
    res.add("R-CP-02", "digital inputs and outputs without a relay",
            f"{di} × {m['di_a']['value']:g} A + {do} × {m['do_a']['value']:g} A", INFO, src("di_a"))
    if plc_a is None:
        return res.refuse("R-CP-03", "PLC, I/O modules and HMI 24 V current given",
                          "not given: their data sheets are not held (CPU / ET 200SP manuals waiting)")
    res.add("R-CP-03", "PLC, I/O modules and HMI 24 V current", f"{plc_a:g} A (given)", INFO)
    load = di * m["di_a"]["value"] + do * m["do_a"]["value"] + relays * coil_a + plc_a + other_a
    fos = m["smps_fos"]["value"]
    need = load * fos
    res.add("R-CP-04", "required output = load × FOS", f"{load:.3f} A × {fos:g} = {need:.3f} A", INFO, src("smps_fos"))
    if min_a is not None:                             # R-CP-09 (owner 2026-10-20): the client's stated rating, at least
        if min_a <= 0:
            return res.invalid(f"min_a must be > 0 (got {min_a})")
        res.add("R-CP-09", "the client's stated rating as the minimum", f"{min_a:g} A" + (
            f" (covers the required {need:.2f} A)" if min_a >= need else f" < required {need:.2f} A: the required current decides"),
            PASS if min_a >= need else WARN, "client specification")
    pick_a = need if min_a is None else max(need, min_a)          # the selection threshold; 'required' stays the load × FOS
    siemens = _norm(brand)[:6] == "siemen"            # R-CP-08: SITOP from the Siemens catalogue, not the AutoBOM list
    table = _sitop() if siemens else _smps()
    rows = [r for r in table["rows"] if _norm(r["brand"])[:6] == _norm(brand)[:6]]
    if not rows:
        return res.refuse("R-CP-05", f"{brand} supplies in the database", "none (makes: Omron, Phoenix Contact, Mean Well, "
                          "Weidmueller; Siemens SITOP PSU6200 from KT 10.1)", _smps()["source"]["ref"])
    order = {id(r): i for i, r in enumerate(table["rows"])}
    # R-CP-07: a network port (…-EIP) exactly when communication is asked
    rows = [r for r in rows if r["model"].upper().endswith("-EIP") == bool(communication)]
    res.add("R-CP-07", "network port on the supply", "asked: port supplies only" if communication
            else "not asked: supplies with a network port left out", INFO)
    fit = [r for r in rows if r["network"] == input and r["vout_min"] <= voltage_dc <= r["vout_max"] and r["i_out_a"] >= pick_a]
    if not fit:
        return res.refuse("R-CP-05", f"{input} supply, {voltage_dc:g} V, ≥ {pick_a:.2f} A", "none in the database",
                          _smps()["source"]["ref"])
    best = min(fit, key=lambda r: (r["i_out_a"], order[id(r)]))
    res.add("R-CP-05", f"smallest {brand} {input} supply ≥ {pick_a:.2f} A",
            f"{best['brand']} {best['model']} {best['i_out_a']:g} A", PASS,
            f"SIE-KT10-1-2022 p.{best['page']}" if siemens else f"OWN-AB-SMPS sheet {best['sheet']} row {best['row']}")
    v = None if siemens else _verified(best)
    if siemens:
        res.add("R-CP-08", f"{best['series']} from the manufacturer's catalogue",
                f"{best['model']}: {best['i_out_a']:g} A, efficiency {best['efficiency'] * 100:g} %, input {best['input_a']:g} A"
                + (f"; mains protection: {best['mains_protection']}" if best.get("mains_protection") else ""),
                PASS, f"SIE-KT10-1-2022 p.{best['page']}")
    elif v and v["verified"]:
        res.add("R-CP-06", f"series {best['series']} verified in the AutoBOM log",
                f"entered by {v['entered_by']}, verified ({v['verified'] if not v['verified'].replace('.', '').isdigit() else 'dated'})",
                PASS, f"OWN-AB-SMPS Logsheet row {v['row']}")
    else:
        res.add("R-CP-06", f"series {best['series']} verified in the AutoBOM log",
                "not verified: check the data sheet before ordering", WARN,
                f"OWN-AB-SMPS Logsheet row {v['row']}" if v else "OWN-AB-SMPS Logsheet")
    if not siemens:
        res.add("R-CP-05", "supply input current for its MCB", "not in the database: input MCB not sized", WARN)
    res.value = {"load_a": round(load, 4), "required_a": round(need, 4), "smps": best["model"], "smps_series": best["series"],
                 "smps_brand": best["brand"], "smps_a": best["i_out_a"], "smps_efficiency": best.get("efficiency"),
                 "smps_input_a": best.get("input_a"),
                 "smps_input": f"{best['vin_min']:g} … "
                 f"{best['vin_max']:g} V AC {best['network']}"}
    res.basis = "own database + template method"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
