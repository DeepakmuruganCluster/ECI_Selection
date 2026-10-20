"""Incomer / line MCCB: Siemens SENTRON 3VA1 with the TM240 ATAM trip unit. Rules: rules.yaml (R-3VA-01 … 08).

Owner 2026-10-20 (RFQ part 1): the client asks a 3VA incomer (630 A, 55 kA, adjustable thermal-magnetic). The 3VM
component (components/mccb) is unchanged; this one is chosen when the incomer series is 3VA.
Data: data/makers/siemens/3va1_line_structure.yaml (LV 10 · 2026) and the held data sheets 3va1_ds_*.yaml.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.data import data_file, tables
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "mccb_3va"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _structure() -> dict:
    return load_sourced_table(data_file("3va1_line_structure.yaml"), ("frame", "digit", "size_a", "in_a", "classes"))


@lru_cache(maxsize=None)
def _datasheets() -> dict:
    """{article: row} from every held 3VA1 data sheet (data/makers/siemens/3va1_ds_*.yaml)."""
    out = {}
    for f in tables():
        if f.name.startswith("3va1_ds_"):
            d = load_sourced_table(f, ("article", "in_a", "icu_ka", "ics_ka"))
            for r in d["rows"]:
                out[r["article"]] = {**r, "ref": d["source"]["ref"]}
    return out


def _p(page) -> str:
    return f"SIE-LV10-2026 p.{page}"


def select(ib_a: float, fault_ka: float | None = None, ambient_c: float | None = None, poles: int | None = None,
           margin: float | None = None, breaking_basis: str | None = None, voltage_v: float = 400.0, phases: int = 3,
           frame: str | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    st = _structure()
    cond, pg = st["conditions"], st["conditions"]["pages"]

    # --- input validation
    if not ib_a or ib_a <= 0:
        return res.invalid(f"load current Ib must be > 0 (got {ib_a})")
    if fault_ka is None or fault_ka <= 0:
        return res.invalid("fault_ka (prospective short-circuit current at the breaker) is required")
    if ambient_c is None:
        return res.invalid("ambient_c (air temperature around the breaker, inside the panel) is required")
    margin = prm["margin_default"] if margin is None else margin
    if margin < 1:
        return res.invalid(f"margin must be ≥ 1 (got {margin:g})")
    basis = breaking_basis or prm["breaking_basis_default"]
    if basis not in ("icu", "ics"):
        return res.invalid(f"breaking_basis must be icu or ics (got {breaking_basis})")
    if frame is not None and frame not in prm["frame_order"]:
        return res.invalid(f"frame must be one of {', '.join(prm['frame_order'])} (got {frame})")
    poles = prm["poles_default"] if poles is None else poles

    # --- scope (R-3VA-01)
    if phases != 3 or not 380 <= voltage_v <= 415:
        return res.refuse("R-3VA-01", "3-phase 380 … 415 V AC (the Icu / Ics row transcribed)", f"{phases}-phase {voltage_v:g} V",
                          _p(pg["ratings"]))
    if poles != 3:
        return res.refuse("R-3VA-01", "3-pole line protection without neutral protection (scope)",
                          f"{poles}-pole: the neutral-protection codes are not transcribed", _p(pg["structure"] + 1))
    res.add("R-3VA-01", "3VA1, TM240 ATAM, 3-pole, 380 … 415 V AC, nut keeper kit", f"{voltage_v:g} V, 3-pole", PASS,
            _p(pg["breaking"]))

    # --- required current (R-3VA-02)
    required = round(ib_a * margin, 3)
    res.add("R-3VA-02", "required In = Ib × margin", f"{ib_a:g} A × {margin:g} = {required:g} A", PASS,
            "rules.yaml (owner decision M-1)")

    # --- candidates: (In, frame) with In ≥ required (R-3VA-03)
    frames = [r for r in st["rows"] if frame is None or r["frame"] == frame]
    cands = [(i_, r) for r in frames for i_ in r["in_a"] if i_ >= required - 1e-9]
    if not cands:
        top = max(i_ for r in frames for i_ in r["in_a"])
        return res.refuse("R-3VA-03", "rated current In ≥ required current",
                          f"{required:g} A > largest {top} A" + (f" on {frame}" if frame else " (3VA1)"), _p(pg["structure"]))

    # --- breaking capacity (R-3VA-05)
    key = "icu_ka" if basis == "icu" else "ics_ka"
    ok = [(i_, r, c) for i_, r in cands for c in r["classes"] if c[key] >= fault_ka - 1e-9]
    if not ok:
        best = max(c[key] for _, r in cands for c in r["classes"])
        return res.refuse("R-3VA-05", f"{'Icu' if basis == 'icu' else 'Ics'} at 380 … 415 V ≥ fault current",
                          f"{fault_ka:g} kA > highest {best:g} kA for In ≥ {required:g} A", _p(pg["ratings"]))

    # --- choice (R-3VA-06)
    fo, co = prm["frame_order"], prm["class_order"]
    in_a, row, cls = min(ok, key=lambda x: (x[0], fo.index(x[1]["frame"]), co.index(x[2]["class"])))
    codes = st["codes"]
    article = (f"3VA1{row['digit']}{codes['in_a'][in_a]}-{codes['breaking_ka'][cls['icu_ka']]}{cond['neutral_code']}"
               f"{cond['trip_code']}{cond['poles_code']}{cond['connection_code']}{cond['suffix']}")
    res.add("R-3VA-03", f"In ≥ {required:g} A", f"In {in_a} A ({row['frame']}, {row['size_a']} A frame), rated at "
            f"{cond['rated_ambient_c']} °C", PASS, _p(pg["structure"]))
    res.add("R-3VA-05", f"{'Icu' if basis == 'icu' else 'Ics'} at 380 … 415 V ≥ {fault_ka:g} kA",
            f"class {cls['class']}: Icu {cls['icu_ka']:g} kA, Ics {cls['ics_ka']:g} kA", PASS, _p(pg["ratings"]))
    res.add("R-3VA-06", "smallest In, then the smallest frame, then the lowest class" + (f" (frame {frame} given)" if frame else ""),
            f"{row['frame']} {in_a} A class {cls['class']} ({len(ok)} combination(s) qualified)", PASS, "rules.yaml (owner 2026-10-20)")

    # --- the article and its data sheet (R-3VA-07, 08)
    ds = _datasheets().get(article)
    if ds:
        res.add("R-3VA-07", "article confirmed by its Siemens data sheet", article, PASS, f"{ds['ref']} p.{ds['page']}")
    else:
        res.add("R-3VA-07", "article built from the catalogue structure (an overview)",
                f"{article}: confirm with its Siemens data sheet (save it to sources/inbox) or the 3VA configurator", WARN,
                _p(pg["structure"]))

    # --- ambient (R-3VA-04)
    at_amb = None
    if ambient_c > cond["rated_ambient_c"]:
        table = (ds or {}).get("in_at_c") or {}
        pts = sorted((float(t), float(v)) for t, v in table.items())
        above = [v for t, v in pts if t >= ambient_c - 1e-9]
        if not ds or not above:
            return res.refuse("R-3VA-04", f"ambient ≤ {cond['rated_ambient_c']} °C (In rated at 50 °C), or the data sheet's derating",
                              f"{ambient_c:g} °C: " + ("no data sheet held for " + article if not ds else "beyond the data sheet's table"),
                              _p(pg["ratings"]))
        at_amb = next(v for t, v in pts if t >= ambient_c - 1e-9)
        if at_amb < required - 1e-9:
            return res.refuse("R-3VA-04", "current at the ambient ≥ required current",
                              f"{at_amb:g} A at {ambient_c:g} °C < {required:g} A", f"{ds['ref']} p.{ds['page']}")
        res.add("R-3VA-04", "current at the ambient (data sheet) ≥ required current", f"{at_amb:g} A at {ambient_c:g} °C ≥ {required:g} A",
                PASS, f"{ds['ref']} p.{ds['page']}")
    else:
        res.add("R-3VA-04", f"ambient ≤ {cond['rated_ambient_c']} °C: rated current applies", f"{ambient_c:g} °C", PASS, _p(pg["ratings"]))

    if ds:
        ir_range, ii_range = f"{ds['ir_min_a']:g} … {ds['ir_max_a']:g} A", f"{ds['ii_min_a']:g} … {ds['ii_max_a']:g} A"
        ir_set = float(max(required, ds["ir_min_a"]))
        res.add("R-3VA-08", "set Ir ≥ required current within the data sheet's range", f"set Ir {ir_set:g} A (range {ir_range}); "
                f"Ii {ii_range}", PASS, f"{ds['ref']} p.{ds['page']}")
    else:
        ir_range = ii_range = None
        ir_set = required
        res.add("R-3VA-08", "TM240 settings Ir, Ii (adjustable)", f"ranges not held: set Ir at {required:g} A — the ranges are "
                "on the article's data sheet", INFO, _p(181))

    res.value = {"article_no": article, "frame": row["frame"], "frame_size_a": float(row["size_a"]), "in_a": float(in_a),
                 "release": "TM240 ATAM", "poles": 3, "breaking_class": cls["class"], "icu_ka": float(cls["icu_ka"]),
                 "ics_ka": float(cls["ics_ka"]), "ir_range": ir_range, "ir_set_a": ir_set, "ii_range": ii_range,
                 "required_a": required, "confirmed": bool(ds), "in_at_ambient_a": at_amb, "series": "3VA"}
    res.basis = "SENTRON 3VA1, Catalog LV 10 · 2026" + (" + data sheet" if ds else "")
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
