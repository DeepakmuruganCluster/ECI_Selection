"""Branch MCCB: Siemens SENTRON 3VM, line protection, 380–415 V. Rules: RULES.md / rules.yaml (R-MCCB-01 … 12)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "mccb"
REF = "SIE-3VM-LV31"
RELEASES = {"TM210": "TM210 FTFM", "TM220": "TM220 ATFM"}
NEUTRAL = {"none": "without neutral protection", "100": "100 % neutral protection"}


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _breaking() -> dict:
    return load_sourced_table(data_file("3vm_breaking_capacity.yaml"),
                              ("frame", "size_a", "class", "icu_ka", "ics_ka", "ue_max_v", "in_min_a", "in_max_a"))


@lru_cache(maxsize=None)
def _ratings() -> dict:
    return load_sourced_table(data_file("3vm_trip_ratings.yaml"),
                              ("release", "frame", "in_a", "ir_min_a", "ir_max_a", "ii_a"))


@lru_cache(maxsize=None)
def _articles() -> dict:
    return load_sourced_table(data_file("3vm_line_protection_articles.yaml"),
                              ("poles", "release", "neutral", "frame", "in_a", "class", "article"))


def _p(page) -> str:
    """PDF page (the catalogue prints section/page numbers, e.g. PDF p.29 = '2/5')."""
    off = _breaking()["reference"].get("printed_page_offset")
    return f"{REF} PDF p.{page} (printed {page + int(off)})" if off else f"{REF} p.{page}"


def _bc(frame: str, cls: str) -> dict:
    return next(r for r in _breaking()["rows"] if r["frame"] == frame and r["class"] == cls)


def select(ib_a: float, fault_ka: float | None = None, ambient_c: float | None = None, poles: int | None = None,
           neutral_protection: str | None = None, release: str | None = None, margin: float | None = None,
           breaking_basis: str | None = None, voltage_v: float = 400.0, phases: int = 3,
           altitude_m: float | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    bc = _breaking()
    cond, cpage = bc["conditions"], bc["condition_pages"]

    # --- input validation
    if not ib_a or ib_a <= 0:
        return res.invalid(f"load current Ib must be > 0 (got {ib_a})")
    if fault_ka is None or fault_ka <= 0:
        return res.invalid("fault_ka (prospective short-circuit current at the breaker) is required")
    if ambient_c is None:
        return res.invalid("ambient_c (air temperature around the breaker, inside the panel) is required")
    poles = prm["poles_default"] if poles is None else poles
    if poles not in (1, 2, 3, 4):
        return res.invalid(f"poles must be 3 or 4 (got {poles})")
    release = release or prm["release_default"]
    if release not in RELEASES:
        return res.invalid(f"release must be TM210 (FTFM, fixed) or TM220 (ATFM, adjustable) (got {release})")
    if neutral_protection is not None and str(neutral_protection) not in NEUTRAL:
        return res.invalid(f"neutral_protection must be none or 100 (got {neutral_protection})")
    if neutral_protection is not None and poles != 4:
        return res.invalid("neutral_protection applies to 4-pole breakers only")
    margin = prm["margin_default"] if margin is None else margin
    if margin < 1:
        return res.invalid(f"margin must be ≥ 1 (got {margin:g})")
    basis = breaking_basis or prm["breaking_basis_default"]
    if basis not in ("icu", "ics"):
        return res.invalid(f"breaking_basis must be icu or ics (got {breaking_basis})")
    altitude = altitude_m if altitude_m is not None else cond["altitude_max_m"]

    # --- scope
    if phases != 3 or not cond["voltage_min_v"] <= voltage_v <= cond["voltage_max_v"]:
        return res.refuse("R-MCCB-01", f"3-phase {cond['voltage_min_v']} … {cond['voltage_max_v']} V AC",
                          f"{phases}-phase {voltage_v:g} V", _p(cpage["voltage"]))
    if altitude > cond["altitude_max_m"]:
        return res.refuse("R-MCCB-01", f"altitude ≤ {cond['altitude_max_m']} m (rated data unchanged)",
                          f"{altitude:g} m", _p(cpage["altitude"]))
    if poles not in (3, 4):
        return res.refuse("R-MCCB-01", "3- or 4-pole line protection breaker (scope)",
                          f"{poles}-pole: not transcribed", _p(cpage["voltage"]))
    res.add("R-MCCB-01", "3-phase 380 … 415 V AC, altitude ≤ 2000 m, 3/4-pole",
            f"{voltage_v:g} V, {altitude:g} m" + ("" if altitude_m is not None else " (assumed)") + f", {poles}-pole",
            PASS, _p(cpage["voltage"]))

    # --- ambient (no derating up to +50 °C; above: no values in the catalogue)
    if ambient_c < cond["ambient_min_c"]:
        return res.refuse("R-MCCB-04", f"ambient ≥ {cond['ambient_min_c']} °C (operating range)", f"{ambient_c:g} °C",
                          _p(cpage["ambient"]))
    if ambient_c > cond["ambient_no_derating_max_c"]:
        return res.refuse("R-MCCB-04", f"ambient ≤ {cond['ambient_no_derating_max_c']} °C (no derating)",
                          f"{ambient_c:g} °C: the catalogue reduces the current above +50 °C but gives no values",
                          _p(cpage["ambient"]))
    res.add("R-MCCB-04", f"ambient ≤ {cond['ambient_no_derating_max_c']} °C: no derating", f"{ambient_c:g} °C", PASS,
            _p(cpage["no_derating"]))

    # --- required current
    required = round(ib_a * margin, 3)
    res.add("R-MCCB-02", "required In = Ib × margin", f"{ib_a:g} A × {margin:g} = {required:g} A", PASS,
            "rules.yaml (owner decision M-1)")

    # --- variant (poles, release, neutral)
    neutral = "none"
    if poles == 4:
        if neutral_protection is None:
            res.add("R-MCCB-08", "4-pole: neutral protection stated",
                    "not stated: taken as without N protection — confirm (none / 100 %)", WARN, _p(32))
        else:
            neutral = str(neutral_protection)
    variant = [a for a in _articles()["rows"]
               if a["poles"] == poles and a["release"] == release and str(a["neutral"]) == neutral]
    vname = f"{poles}-pole {RELEASES[release]}" + (f", {NEUTRAL[neutral]}" if poles == 4 else "")
    vpage = min(a["page"] for a in variant)
    res.add("R-MCCB-08", "variant as printed in the ordering tables", f"{vname}: {len(variant)} article numbers",
            PASS, _p(vpage))

    # --- rated current
    by_in = [a for a in variant if a["in_a"] >= required - 1e-9]
    if not by_in:
        return res.refuse("R-MCCB-03", "rated current In ≥ required current",
                          f"{required:g} A > largest {max(a['in_a'] for a in variant)} A ({vname})", _p(vpage))

    # --- breaking capacity
    key = "icu_ka" if basis == "icu" else "ics_ka"
    ok = [a for a in by_in if _bc(a["frame"], a["class"])[key] >= fault_ka - 1e-9]
    if not ok:
        best = max(_bc(a["frame"], a["class"])[key] for a in by_in)
        rule = "R-MCCB-05" if basis == "icu" else "R-MCCB-06"
        return res.refuse(rule, f"{'Icu' if basis == 'icu' else 'Ics'} at 380 … 415 V ≥ fault current",
                          f"{fault_ka:g} kA > highest {best:g} kA for In ≥ {required:g} A ({vname})", _p(10))
    res.add("R-MCCB-06", "breaking-capacity basis", f"{'Icu' if basis == 'icu' else 'Ics'} ≥ fault current",
            PASS if basis == "icu" else INFO, "rules.yaml (owner decision M-2)")

    # --- choice
    corder, forder = prm["class_order"], prm["frame_order"]
    a = min(ok, key=lambda r: (r["in_a"], forder.index(r["frame"]), corder.index(r["class"])))
    b = _bc(a["frame"], a["class"])
    res.add("R-MCCB-03", f"In ≥ {required:g} A", f"In {a['in_a']} A ({a['frame']}, {b['size_a']} A frame)", PASS,
            _p(a["page"]))
    res.add("R-MCCB-05", f"Icu at 380 … 415 V ≥ {fault_ka:g} kA",
            f"class {a['class']}: Icu {b['icu_ka']:g} kA, Ics {b['ics_ka']:g} kA", PASS, _p(b["page"]))
    if basis == "icu" and b["ics_ka"] < fault_ka:
        res.add("R-MCCB-05", "Ics (service breaking capacity) vs fault current",
                f"Ics {b['ics_ka']:g} kA < {fault_ka:g} kA: Icu basis accepted (decision M-2)", INFO, _p(b["page"]))
    res.add("R-MCCB-07", "smallest In, then smallest frame, then lowest class",
            f"{a['article']} ({len(ok)} article numbers qualified)", PASS, "rules.yaml (owner decision M-7)")

    # --- trip settings
    t = next(r for r in _ratings()["rows"]
             if r["release"] == release and r["frame"] == a["frame"] and r["in_a"] == a["in_a"])
    if t["ir_min_a"] == t["ir_max_a"]:
        ir_range, ir_set = f"{t['ir_max_a']} A (fixed)", float(t["ir_max_a"])
        res.add("R-MCCB-09", "overload setting Ir", f"fixed {t['ir_max_a']} A", PASS, _p(t["page"]))
    else:
        ir_range = f"{t['ir_min_a']} … {t['ir_max_a']} A"
        ir_set = float(max(required, t["ir_min_a"]))
        res.add("R-MCCB-09", "set Ir ≥ required current within the printed range",
                f"set Ir ≥ {ir_set:g} A (range {ir_range})", PASS, _p(t["page"]))
    res.add("R-MCCB-10", "instantaneous trip current Ii (fixed)", f"{t['ii_a']} A", INFO, _p(t["page"]))
    res.add("R-MCCB-11", "let-through energy I²t / cut-off current",
            "not published in LV 31: not given — the cable check needs another Siemens source", INFO, "")
    res.add("R-MCCB-12", "article number from the 2018 catalogue",
            "confirm in the current Siemens Industry Mall before ordering", INFO, _p(a["page"]))

    res.value = {"article_no": a["article"], "frame": a["frame"], "frame_size_a": float(b["size_a"]),
                 "in_a": float(a["in_a"]), "release": RELEASES[release], "poles": poles,
                 "neutral_protection": NEUTRAL[neutral] if poles == 4 else None,
                 "breaking_class": a["class"], "icu_ka": float(b["icu_ka"]), "ics_ka": float(b["ics_ka"]),
                 "ir_range": ir_range, "ir_set_a": ir_set, "ii_a": float(t["ii_a"]), "required_a": required,
                 "let_through_i2t": None}
    res.basis = "3VM catalogue LV 31 · 2018"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
