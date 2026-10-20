"""Control circuit: control supply (transformer or phase-neutral), its MCBs, and operator devices.

Rules: rules.yaml (R-CC-01 … 06). Transformers and devices from the company costing sheet (feeder_kit data),
MCBs from the own switchgear database (component 11), transformer factor from the switchgear template.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from components.aux_switchgear.select import select as aux_switchgear
from components.control_power.select import _method
from components.feeder_kit.select import _kits
from core.provenance import load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "control_circuit"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _transformers() -> list[dict]:
    """Company-standard control transformers: VA, price and source row (first occurrence of each rating)."""
    out = {}
    for k in _kits():
        for it in k["items"]:
            if "CONTROL TRANSFORMER" in it["description"].upper():
                m = re.search(r"(\d+(?:\.\d+)?)\s*(K?)VA", f"{it['rating']} {it['article']}".upper())
                if m:
                    va = float(m.group(1)) * (1000 if m.group(2) else 1)
                    out.setdefault(va, {"va": va, "description": f"Control transformer {va:g} VA, 415/230 V AC ({it['make']})",
                                        "unit_price_inr": it["unit_price_inr"],
                                        "source": f"{k['ref']} sheet '{k['sheet'].strip()}' row {it['row']}"})
    return sorted(out.values(), key=lambda t: t["va"])


def _kit_item(match: str):
    for k in _kits():
        for it in k["items"]:
            if match.upper() == (it["article"] or "").upper().strip() or match.upper() == it["description"].upper().strip():
                return it, f"{k['ref']} sheet '{k['sheet'].strip()}' row {it['row']}"
    return None, None


def select(supply: str, coils: int = 0, coil_va: float | None = None, lamps: int = 0, lamp_va: float | None = None,
           valve_va_total: float = 0.0, instrument_va_total: float = 0.0, other_va: float = 0.0, estop: int = 0,
           reset: int = 0, phase_lamps: bool = False, hour_meters: int = 0, mcb_make: str = "Siemens",
           coil_power: list[dict] | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    if supply not in ("transformer", "phase_neutral"):
        return res.invalid(f"supply must be transformer or phase_neutral (got {supply})")
    if min(coils, lamps, estop, reset, hour_meters) < 0 or min(valve_va_total, instrument_va_total, other_va) < 0:
        return res.invalid("counts and loads must not be negative")
    if coil_power is not None and (coil_va is not None or coils):
        return res.invalid("give contactor coils either as coils + coil_va (designer) or as coil_power (catalogue), not both")
    for c in coil_power or []:
        q, cl, ho = c.get("qty"), c.get("close_va"), c.get("hold_va")
        if not isinstance(q, (int, float)) or isinstance(q, bool) or q < 0 or q != int(q):
            return res.invalid(f"coil_power qty must be a whole number ≥ 0 (got {q!r})")
        for name, x in (("close_va", cl), ("hold_va", ho)):
            if x is not None and (not isinstance(x, (int, float)) or isinstance(x, bool) or not 0 <= x < float("inf")):
                return res.invalid(f"coil_power {name} must be a number ≥ 0 (got {x!r})")
        if cl is not None and ho is not None and cl < ho:
            return res.invalid(f"coil_power closing {cl:g} VA < holding {ho:g} VA: a coil draws more when closing (data error)")
    coil_power = [c for c in coil_power or [] if c["qty"]] if coil_power is not None else None   # qty 0: not in the panel
    prm = _rules()["params"]

    # R-CC-01: control load
    load, parts, missing, rows = 0.0, [], [], []
    if coil_power:
        # R-CC-06: Σ holding VA + the largest single closing step
        known = [c for c in coil_power if c.get("hold_va") is not None and c.get("close_va") is not None]
        unknown = sum(int(c["qty"]) for c in coil_power if c not in known)
        if unknown:
            missing.append(f"{unknown} contactor coil(s): no catalogue power")
        if known:
            hold = sum(c["hold_va"] * c["qty"] for c in known)
            step = max(c["close_va"] - c["hold_va"] for c in known)
            load += hold + step
            n = sum(int(c["qty"]) for c in known)
            parts.append(f"{n} contactor coil(s): Σ holding {hold:g} VA + largest closing step {step:g} VA")
            rows += [{"item": "contactor coils, holding (catalogue)", "qty": n, "unit": "VA", "per_unit": None,
                      "total": round(hold, 2), "source": "SIE-IC10-2026 via the DOL selection (R-CC-06)"},
                     {"item": "largest closing step (closing − holding)", "qty": 1, "unit": "VA", "per_unit": round(step, 2),
                      "total": round(step, 2), "source": "SIE-IC10-2026 via the DOL selection (R-CC-06)"}]
            res.add("R-CC-06", "contactor coils from the catalogue: Σ holding + largest closing step",
                    f"{hold:g} + {step:g} = {hold + step:g} VA", PASS, "SIE-IC10-2026 (via the DOL selection)")
        if unknown:
            rows.append({"item": "contactor coils without catalogue power", "qty": unknown, "unit": "VA", "per_unit": None,
                         "total": None, "source": "open point (e.g. company-kit contactors)"})
    for n, va, what in ((coils, coil_va, "contactor coil"), (lamps, lamp_va, "pilot lamp")):
        if not n:
            continue
        if va is None:
            missing.append(f"{n} {what}(s): VA not given")
            rows.append({"item": f"{what}s", "qty": n, "unit": "VA", "per_unit": None, "total": None,
                         "source": "VA not given: open point"})
        else:
            load += n * va
            parts.append(f"{n} {what}(s) × {va:g} VA")
            rows.append({"item": f"{what}s", "qty": n, "unit": "VA", "per_unit": va, "total": round(n * va, 2),
                         "source": "designer input"})
    for va, what in ((valve_va_total, "solenoid valves"), (instrument_va_total, "230 V instruments"), (other_va, "other")):
        if va:
            load += va
            parts.append(f"{what} {va:g} VA")
            rows.append({"item": what, "qty": None, "unit": "VA", "per_unit": None, "total": round(va, 2),
                         "source": "from the field devices / designer"})
    res.add("R-CC-01", "230 V AC control load", (" + ".join(parts) or "none") + f" = {load:g} VA" +
            (f"; partial: {'; '.join(missing)}" if missing else ""), WARN if missing else PASS)
    res.add("R-CC-05", "device consumption from the maker's data", "coil and lamp VA as given by the designer", INFO)

    value, lines = {"load_va": round(load, 2), "required_va": None, "transformer_va": None, "primary_mcb": None,
                    "secondary_mcb": None, "control_mcb": None}, []

    def mcb(name, ib, curve):
        a = aux_switchgear(circuits=[{"name": name, "ib_a": ib, "poles": 2, "curve": curve}], make=mcb_make)
        return a.value if a.status not in ("cannot_select", "invalid") else None

    if supply == "transformer":
        fos = _method()["transformer_fos"]
        need = load * fos["value"]
        value["required_va"] = round(need, 2)
        if missing:
            res.add("R-CC-02", "control transformer", "not sized: the control load is partial", WARN)
        else:
            t = next((t for t in _transformers() if t["va"] >= need), None)
            if t is None:
                res.add("R-CC-02", f"company transformer ≥ {need:g} VA (load × {fos['value']:g})",
                        f"none: largest is {_transformers()[-1]['va']:g} VA", WARN, f"OWN-SWG-CALC '{fos['sheet']}' {fos['cell']}")
            else:
                res.add("R-CC-02", f"company transformer ≥ {need:g} VA (load × {fos['value']:g})", t["description"], PASS,
                        t["source"])
                value["transformer_va"] = t["va"]
                lines.append({"article": f"Control transformer {t['va']:g} VA", "description": t["description"], "qty": 1,
                              "source": t["source"], "unit_price_inr": t["unit_price_inr"]})
                p = mcb("transformer primary", t["va"] / prm["primary_v"], "D")
                s = mcb("transformer secondary", t["va"] / prm["secondary_v"], "C")
                res.add("R-CC-03", f"transformer MCBs: primary {t['va'] / prm['primary_v']:.2f} A (D), secondary "
                        f"{t['va'] / prm['secondary_v']:.2f} A (C)", f"{p and p['mcb_1']} / {s and s['mcb_1']}",
                        PASS if p and s else WARN)
                for v_, what in ((p, "primary"), (s, "secondary")):
                    if v_:
                        value[f"{what}_mcb"] = v_["mcb_1"]
                        lines.append({"article": v_["mcb_1"], "description": f"MCB 2P {v_['mcb_1_curve']} {v_['mcb_1_in_a']:g} A, "
                                      f"control transformer {what}", "qty": 1, "source": v_["devices"][0]["source"]})
    elif missing:
        res.add("R-CC-03", "control circuit MCB (phase-neutral)", "not sized: the control load is partial", WARN)
    elif load:
        c = mcb("control circuit", load / prm["secondary_v"], "C")
        res.add("R-CC-03", f"control circuit MCB at {load / prm['secondary_v']:.2f} A (C)", c["mcb_1"] if c else "none",
                PASS if c else WARN)
        if c:
            value["control_mcb"] = c["mcb_1"]
            lines.append({"article": c["mcb_1"], "description": f"MCB 2P C {c['mcb_1_in_a']:g} A, control circuit", "qty": 1,
                          "source": c["devices"][0]["source"]})

    # R-CC-04: operator devices (company costing sheet)
    want = [("estop", estop), ("reset", reset), ("phase_lamps", 1 if phase_lamps else 0), ("hour_meter", hour_meters)]
    n_dev = 0
    for key, n in want:
        if not n:
            continue
        for d in prm["devices"][key]:
            it, src = _kit_item(d["match"])
            if it:
                lines.append({"article": it["article"] or it["description"].title(),
                              "description": f"{it['description'].title()} {it['rating']}".strip() + f" ({it['make']})",
                              "qty": d["qty"] * n, "source": src, "unit_price_inr": it["unit_price_inr"]})
                n_dev += 1
    if n_dev:
        res.add("R-CC-04", "operator devices from the company costing sheet", f"{n_dev} line(s)", PASS, "OWN-PROPEL-COST")
    res.value = {**value, "n_devices": n_dev, "bom": lines, "load_rows": rows,
                 "transformer_factor": _method()["transformer_fos"]["value"]}
    res.basis = "company standard + template"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
