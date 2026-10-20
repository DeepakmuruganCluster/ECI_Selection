"""Auxiliary switchgear from the own database: MCB, RCCB, surge arrester, phase monitoring relay, isolator.

Rules: rules.yaml (R-AUX-01 … 08). Data: own_*.yaml (generated from OWN-SWG-*, one row per CSV line); Siemens breaking
capacity, RCCB type and type 2 surge arresters from Catalog LV 10 · 2026 (lv10_mcb, lv10_rccb, lv10_5sd74_type2).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "aux_switchgear"
DB = {"mcb": ("own_mcb.yaml", ("make", "poles", "in_a", "curve", "article")),
      "rccb": ("own_rccb.yaml", ("make", "poles", "in_a", "idn_ma", "article")),
      "isolator": ("own_isolator.yaml", ("make", "in_a", "article")),
      "sa": ("own_sa.yaml", ("make", "config", "article")),
      "pmr": ("own_pmr.yaml", ("make", "article"))}


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _db(kind: str) -> dict:
    f, fields = DB[kind]
    return load_sourced_table(data_file(f), fields)


@lru_cache(maxsize=None)
def _lv10(name: str) -> dict:
    """LV 10 rows by article without hyphen (the own database writes Siemens articles without it)."""
    return {r["article"].replace("-", ""): r for r in load_sourced_table(data_file(name), ("article",))["rows"]}


def _lv10_row(name: str, article: str):
    """R-AUX-03: the LV 10 row of a Siemens article; the India suffix (RC / CC) is dropped (owner 2026-10-13)."""
    m = re.fullmatch(r"(5S[LYPV]\d{5})[A-Z0-9]*", article.replace("-", "").strip())
    return _lv10(name).get(m.group(1)) if m else None


@lru_cache(maxsize=None)
def _spd() -> dict:
    return load_sourced_table(data_file("lv10_5sd74_type2.yaml"), ("article", "system", "circuit"))


def _src(kind: str, row: dict) -> str:
    return f"{_db(kind)['source']['ref']} line {row['row']}"


def _same(a, b) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def select(circuits: list | None = None, make: str = "Siemens", margin: float | None = None,
           fault_ka: float | None = None, spd: str | None = None, spd_make: str | None = None, pmr: bool = False,
           pmr_make: str | None = None, isolator_ib_a: float | None = None, isolator_make: str | None = None,
           spd_remote_signalling: bool | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    margin = prm["default_margin"] if margin is None else float(margin)
    if margin < 1:
        return res.invalid(f"margin must be ≥ 1 (got {margin})")
    if isinstance(circuits, str):  # typed in a form as JSON
        import json
        try:
            circuits = json.loads(circuits)
        except ValueError:
            return res.invalid("circuits: not a JSON list")
    circuits = circuits or []
    for i, c in enumerate(circuits, 1):
        if not isinstance(c, dict) or c.get("ib_a") is None or float(c["ib_a"]) <= 0:
            return res.invalid(f"circuit {i}: needs ib_a > 0")
        pl = c.get("poles")
        if not isinstance(pl, (int, float)) or isinstance(pl, bool) or pl != int(pl) or int(pl) not in (1, 2, 3, 4):
            return res.invalid(f"circuit {i}: poles must be 1 … 4")
        if not c.get("curve") and c.get("kind") not in prm["curve_by_kind"]:
            return res.invalid(f"circuit {i}: give a curve (B / C / D) or a kind ({', '.join(prm['curve_by_kind'])})")
    if spd and not spd_make:
        return res.invalid("spd_make is required with spd")
    if pmr and not pmr_make:
        return res.invalid("pmr_make is required with pmr")
    if not (circuits or spd or pmr or isolator_ib_a):
        return res.invalid("nothing to select: give circuits, spd, pmr or isolator_ib_a")

    devices, value = [], {}
    fk = f" ({fault_ka:g} kA asked)" if fault_ka is not None else ""

    def device(kind, circuit, row, rating):
        devices.append({"device": kind, "circuit": circuit, "make": row["make"], "article": row["article"],
                        "rating": rating, "source": _src({"MCB": "mcb", "RCCB": "rccb", "Isolator": "isolator",
                                                          "Surge arrester": "sa", "PMR": "pmr"}[kind], row)})

    for i, c in enumerate(circuits, 1):
        name, ib, poles = c.get("name") or f"circuit {i}", float(c["ib_a"]), int(c["poles"])
        curve = (c.get("curve") or prm["curve_by_kind"][c["kind"]]).upper()
        if not c.get("curve"):
            res.add("R-AUX-02", f"{name}: curve from the load kind", f"{c['kind']} → {curve}", INFO)
        rows = [r for r in _db("mcb")["rows"] if _same(r["make"], make)]
        if not rows:
            return res.refuse("R-AUX-01", "make in the own database", f"no MCB rows for {make}")
        need = ib * margin
        fit = sorted((r for r in rows if r["poles"] == poles and r["curve"] == curve and r["in_a"] >= need),
                     key=lambda r: r["in_a"])
        if not fit:
            return res.refuse("R-AUX-02", f"{name}: {make} MCB {poles}P {curve} with In ≥ {need:g} A",
                              "none in the database", _db("mcb")["source"]["ref"])
        m = fit[0]
        res.add("R-AUX-02", f"{name}: MCB {poles}P {curve}, In ≥ {ib:g} A × {margin:g} = {need:g} A",
                f"{m['article']} In {m['in_a']:g} A (trip band {m['trip_lo_a']:g} … {m['trip_hi_a']:g} A)", PASS,
                _src("mcb", m))
        lv = _lv10_row("lv10_mcb.yaml", m["article"]) if _same(m["make"], "Siemens") else None
        if lv is None:
            res.add("R-AUX-03", f"{name}: MCB breaking capacity ≥ fault level{fk}", "not in the held data: not checked", WARN)
        else:
            icn = float(lv["breaking_capacity"].split()[0])
            value[f"mcb_{i}_icn_ka"] = icn
            src = f"SIE-LV10-2026 p.{lv['page']} ({lv['article']}, {lv['series']})"
            if fault_ka is None:
                res.add("R-AUX-03", f"{name}: MCB breaking capacity ≥ fault level", f"{icn:g} kA; fault level not given: "
                        "not compared", WARN, src)
            elif icn >= fault_ka:
                res.add("R-AUX-03", f"{name}: MCB breaking capacity ≥ fault level{fk}", f"{icn:g} kA", PASS, src)
            else:
                res.add("R-AUX-03", f"{name}: MCB breaking capacity ≥ fault level{fk}",
                        f"{icn:g} kA: below — back-up protection or a higher series needed", WARN, src)
        device("MCB", name, m, f"{poles}P {curve}{m['in_a']:g}")
        value.update({f"mcb_{i}": m["article"], f"mcb_{i}_in_a": m["in_a"], f"mcb_{i}_curve": curve})
        if c.get("rcd_ma"):
            rp = 2 if poles <= 2 else 4
            rr = sorted((r for r in _db("rccb")["rows"] if _same(r["make"], make) and r["poles"] == rp
                         and r["idn_ma"] == float(c["rcd_ma"]) and r["in_a"] >= m["in_a"]), key=lambda r: r["in_a"])
            if not rr:
                return res.refuse("R-AUX-04", f"{name}: {make} RCCB {rp}P {c['rcd_ma']} mA, In ≥ {m['in_a']:g} A",
                                  "none in the database", _db("rccb")["source"]["ref"])
            r0 = rr[0]
            res.add("R-AUX-04", f"{name}: RCCB {rp}P {c['rcd_ma']} mA, In ≥ MCB {m['in_a']:g} A",
                    f"{r0['article']} In {r0['in_a']:g} A", PASS, _src("rccb", r0))
            device("RCCB", name, r0, f"{rp}P {r0['in_a']:g} A {r0['idn_ma']:g} mA")
            value[f"rccb_{i}"] = r0["article"]
            lr = _lv10_row("lv10_rccb.yaml", r0["article"]) if _same(r0["make"], "Siemens") else None
            if lr:
                value[f"rccb_{i}_type"] = lr["type"]
                res.add("R-AUX-04", f"{name}: RCCB type", f"type {lr['type']} ({lr['article']})", INFO,
                        f"SIE-LV10-2026 p.{lr['page']}")
            res.add("R-AUX-03", f"{name}: RCCB short-circuit rating{fk}", "not in the held data: not checked", WARN)

    if spd and _same(spd_make, "Siemens"):
        # R-AUX-08: Siemens type 2 surge arrester from LV 10
        if spd != "3Ph+N+PE":
            return res.refuse("R-AUX-08", f"Siemens type 2 surge arrester for {spd}",
                              "not in the held 5SD74 table (only 3Ph+N+PE: TN-S / TT 3+1)", "SIE-LV10-2026 p.518")
        remote = prm["spd_remote_signalling"] if spd_remote_signalling is None else bool(spd_remote_signalling)
        s = next(r for r in _spd()["rows"] if r["system"] == "TN-S and TT" and r["circuit"] == "3+1"
                 and r["remote_signalling"] == remote)
        src = f"SIE-LV10-2026 p.{s['page']}"
        res.add("R-AUX-08", f"Siemens type 2 surge arrester, TN-S / TT 3+1{' with remote signalling' if remote else ''}",
                f"{s['article']}: Uc {s['uc']}, Up L-N ≤ {s['up_ln_kv']:g} kV, In {s['in_ln_ka']:g} kA, Imax {s['imax_ln_ka']:g} kA",
                PASS, src)
        if fault_ka is None:
            res.add("R-AUX-08", f"short-circuit strength {s['sc_strength_ka']:g} kA with max. back-up fuse "
                    f"{s['backup_fuse_stub_a']} A gL/gG", "fault level not given: not compared", WARN, src)
        else:
            res.add("R-AUX-08", f"short-circuit strength {s['sc_strength_ka']:g} kA ≥ fault level ({fault_ka:g} kA), "
                    f"max. back-up fuse {s['backup_fuse_stub_a']} A gL/gG", "yes" if fault_ka <= s["sc_strength_ka"]
                    else "no: a back-up arrangement for the fault level is needed", PASS if fault_ka <= s["sc_strength_ka"]
                    else WARN, src)
        devices.append({"device": "Surge arrester", "circuit": "incomer", "make": "Siemens", "article": s["article"],
                        "rating": f"type 2, {spd}", "source": src})
        value.update({"spd": s["article"], "spd_backup_fuse_a": s["backup_fuse_stub_a"]})
    elif spd:
        rows = [r for r in _db("sa")["rows"] if _same(r["make"], spd_make) and _same(r["config"], spd)]
        if not rows:
            return res.refuse("R-AUX-05", f"{spd_make} surge arrester for {spd}", "none in the database",
                              _db("sa")["source"]["ref"])
        res.add("R-AUX-05", f"surge arrester {spd}", rows[0]["article"], PASS, _src("sa", rows[0]))
        res.add("R-AUX-05", "surge arrester class and protection level", "not in the database: not checked", WARN)
        device("Surge arrester", "incomer", rows[0], spd)
        value["spd"] = rows[0]["article"]
    if pmr:
        rows = [r for r in _db("pmr")["rows"] if _same(r["make"], pmr_make)]
        if not rows:
            return res.refuse("R-AUX-06", f"{pmr_make} phase monitoring relay", "none in the database",
                              _db("pmr")["source"]["ref"])
        res.add("R-AUX-06", "phase monitoring relay", rows[0]["article"], PASS, _src("pmr", rows[0]))
        device("PMR", "incomer", rows[0], "3-phase")
        value["pmr"] = rows[0]["article"]
    if isolator_ib_a:
        imake = isolator_make or make
        need = float(isolator_ib_a) * 1.5
        rows = sorted((r for r in _db("isolator")["rows"] if _same(r["make"], imake) and r["in_a"] >= need),
                      key=lambda r: r["in_a"])
        if not rows:
            return res.refuse("R-AUX-07", f"{imake} isolator In ≥ {need:g} A", "none in the database",
                              _db("isolator")["source"]["ref"])
        res.add("R-AUX-07", f"isolator In ≥ {float(isolator_ib_a):g} A × 1.5 = {need:g} A",
                f"{rows[0]['article']} In {rows[0]['in_a']:g} A", PASS, _src("isolator", rows[0]))
        res.add("R-AUX-03", f"isolator short-circuit rating{fk}", "not in the database: not checked", WARN)
        device("Isolator", "incomer", rows[0], f"{rows[0]['in_a']:g} A")
        value.update({"isolator": rows[0]["article"], "isolator_in_a": rows[0]["in_a"]})

    res.add("R-AUX-01", "devices from the own database: confirm article numbers before ordering",
            f"{len(devices)} device(s)", INFO)
    res.value = {"n_mcb": len(circuits), **value, "devices": devices}
    res.basis = "own switchgear database"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
