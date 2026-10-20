"""Internal panel wiring: minimum conductor cross section from the Lapp Cable Guide "Power Rating"
(extracts of DIN VDE 0298-4:2003-08). Rules: RULES.md / rules.yaml (R-WIR-01 … 13)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core import project as P
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "internal_wiring"
REF = "LAPP-POWER"
COLUMN = {"single": "A", "multi": "C"}
OUT_OF_SCOPE_TYPES = {"cord": "category B (cords for home / portable apparatus)",
                      "rubber": "category D / Table 12-9 (heavy-duty rubber cables)",
                      "welding": "Table 12-10 (welding cables)", "awg": "Table 13 (NEC / AWG sizes)"}
GROUPED = ("duct", "surface")
SPACED = "air_spaced"
NOT_TABULATED = {
    "tray": "cable trays (Tables 12-7 / 12-8) are not used inside a panel",
    "ladder": "cable ladders (Tables 12-7 / 12-8) are not used inside a panel",
    "air_bundled": "single cores touching free in air: footnote 3 gives 0.8 / 0.7 'before applying Table 12-8', "
                   "which is for cable trays — no factor for wires free in air without a tray",
    "ceiling": "ceiling rows of Table 12-6 are not a panel installation",
    "one_layer": "one-layer rows of Table 12-6 are not used (wiring in a panel is bunched)",
}
CIRCUITS = ("3ac", "1ac", "dc")
LOADED = {"3ac": 3, "1ac": 2, "dc": 2}
INSULATIONS = ("60", "70", "80", "85", "90", "heat_90", "heat_110", "heat_145", "heat_180")
WORDS = {"duct": "in a wiring duct / conduit, bunched", "surface": "bunched on the mounting plate / wall",
         "air_spaced": "free in air, spaced ≥ d"}


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _data() -> dict:
    rat = load_sourced_table(data_file("lapp_t12_1_ratings.yaml"), ("column", "size"))
    fac = load_sourced_table(data_file("lapp_t12_factors.yaml"), ("kind",))
    group: dict = {}
    for r in fac["rows"]:
        if r["kind"] == "group":
            for n, f in r["factors"].items():
                group.setdefault(r["method"], {})[int(n)] = (float(f), r["printed"])
    return {
        "ratings": rat["rows"],
        "bundle": {r["place"]: r for r in fac["rows"] if r["kind"] == "bundle"},
        "temp": {str(r["insulation"]): r for r in fac["rows"] if r["kind"] in ("temp", "heat")},
        "cores": sorted((r for r in fac["rows"] if r["kind"] == "cores"), key=lambda r: r["n"]),
        "group": group,
    }


def _p(page: int, printed: int | None = None) -> str:
    """PDF page plus the printed page (each PDF page is a spread: printed 2·p + 142 / 2·p + 143)."""
    pr = printed if printed is not None else f"{2 * page + 142}/{2 * page + 143}"
    return f"{REF} PDF p.{page} (printed {pr})"


def select(ib_a: float, ambient_c: float, insulation: str | None = None, in_a: float | None = None,
           overload_device: bool = True, conductor_type: str = "single", installation: str = "duct",
           circuit: str = "3ac", circuits: int | None = None, loaded_cores: int | None = None,
           min_size_mm2: float | None = None, client_requirements: dict | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]

    # --- input validation
    if not ib_a or ib_a <= 0:
        return res.invalid(f"design current Ib must be > 0 (got {ib_a})")
    if ambient_c is None:
        return res.invalid("ambient_c (air temperature around the wiring, inside the panel) is required")
    if insulation is None:
        return res.invalid("insulation (rated conductor temperature from the Lapp product page: "
                           f"{', '.join(INSULATIONS)}) is required — no default")
    insulation = str(insulation).lower().removesuffix("c").strip()
    if insulation not in INSULATIONS:
        return res.invalid(f"insulation must be one of {', '.join(INSULATIONS)} (got {insulation!r})")
    if overload_device and in_a is None:
        return res.invalid("in_a (rated / set current of the overload protective device) is required, "
                           "or set overload_device = false")
    conductor_type = str(conductor_type or "").lower()
    if conductor_type not in COLUMN and conductor_type not in OUT_OF_SCOPE_TYPES:
        return res.invalid(f"conductor_type must be single or multi (got {conductor_type!r})")
    installation = str(installation or "").lower()
    if installation not in GROUPED + (SPACED,) + tuple(NOT_TABULATED):
        return res.invalid(f"installation must be one of duct, surface, air_spaced (got {installation!r})")
    circuit = str(circuit or "").lower()
    if circuit not in CIRCUITS:
        return res.invalid(f"circuit must be one of {', '.join(CIRCUITS)} (got {circuit!r})")
    if installation in GROUPED and circuits is None:
        return res.invalid("circuits (number of circuits / multicore cables bunched together in the duct or on "
                           "the plate, including this one) is required — no default")
    if circuits is not None and (int(circuits) != circuits or circuits < 1):
        return res.invalid(f"circuits must be a whole number ≥ 1 (got {circuits})")
    if loaded_cores is not None:
        if conductor_type != "multi":
            return res.invalid("loaded_cores applies to a multicore cable only")
        if int(loaded_cores) != loaded_cores or loaded_cores < LOADED[circuit]:
            return res.invalid(f"loaded_cores must be a whole number ≥ {LOADED[circuit]} for a {circuit} circuit")
    if min_size_mm2 is not None and min_size_mm2 <= 0:
        return res.invalid(f"min_size_mm2 must be > 0 (got {min_size_mm2})")

    d = _data()

    # --- scope (R-WIR-01)
    if conductor_type in OUT_OF_SCOPE_TYPES:
        return res.refuse("R-WIR-01", "Lapp category A (single cores) or C (multicore power / control cables)",
                          f"{conductor_type}: {OUT_OF_SCOPE_TYPES[conductor_type]} is out of scope", _p(2, 146))
    col = COLUMN[conductor_type]
    wir_text, wir_src = P.cite(client_requirements, "internal_wiring")
    res.add("R-WIR-01", "Lapp wiring" + (f" (client: '{wir_text}')" if wir_text else "") + ", category A or C",
            f"category {col} ({'single cores' if col == 'A' else 'multicore cable'})", PASS,
            (f"{wir_src}; " if wir_text else "") + _p(2, 146))

    # --- installation (R-WIR-03)
    if installation in NOT_TABULATED:
        return res.refuse("R-WIR-03", "installation tabulated by Lapp for panel wiring (duct / surface / air_spaced)",
                          f"{installation}: {NOT_TABULATED[installation]}", _p(2, 147))
    if installation == SPACED and col == "C":
        return res.refuse("R-WIR-03", "installation drawn for column C (a cable on a wall / floor)",
                          "multicore cable free in air: not drawn in Table 12-1 column C", _p(1, 145))
    res.add("R-WIR-03", "installation as tabulated", WORDS[installation], PASS,
            _p(4, 150) if installation in GROUPED else _p(1, 144))

    # --- temperature (R-WIR-08, R-WIR-09)
    trow = d["temp"][insulation]
    temps = sorted(int(t) for t in trow["factors"])
    tsrc = _p(trow["page"], trow["printed"])
    table = "12-4" if trow["kind"] == "heat" else "12-2"
    if ambient_c > temps[-1]:
        return res.refuse("R-WIR-09", f"ambient ≤ {temps[-1]} °C (Table {table}, {trow.get('label') or insulation + ' °C'}"
                          " column; no extrapolation)", f"{ambient_c:g} °C", tsrc)
    t_row = next(t for t in temps if t >= ambient_c)
    k_t = float(trow["factors"][t_row])
    if t_row != ambient_c:
        how = "lowest row" if ambient_c < temps[0] else "next hotter row"
        if trow["kind"] == "heat" and t_row == temps[0]:
            how = "'up to 50' row"
        res.add("R-WIR-09", "temperature between rows → next hotter row; below the table → lowest row",
                f"{ambient_c:g} °C → {t_row} °C ({how})", PASS, tsrc)
    label = trow.get("label") or f"rated conductor temperature {insulation} °C"
    res.add("R-WIR-08", f"Table {table} temperature factor ({label})",
            f"{'up to ' if trow['kind'] == 'heat' and t_row == temps[0] else ''}{t_row} °C: {k_t:g}", PASS, tsrc)

    # --- bundling of single cores (R-WIR-04, R-WIR-05)
    k_b = 1.0
    if col == "A" and installation in GROUPED:
        b = d["bundle"]["surface"]
        k_b = float(b["factors"][circuit])
        res.add("R-WIR-05", "single cores in a duct / on the plate = 'bundled on surfaces' + Table 12-6 'bunched'",
                f"{WORDS[installation]} (our reading; Lapp sends conduits in buildings to VDE 0298-4 Tables 3 / 5)",
                INFO, _p(2, 147))
        res.add("R-WIR-04", "single cores bundled on surfaces (footnote 3)",
                f"{'3~AC' if circuit == '3ac' else '1~AC or DC'}: {k_b:g}", PASS, _p(b["page"], b["printed"]))
    elif col == "A":
        res.add("R-WIR-04", "single cores spaced ≥ d (column A drawing): no bundling factor", "1", PASS, _p(1, 144))

    # --- grouping (R-WIR-06, R-WIR-09)
    k_g, g_src = 1.0, _p(1, 144)
    if installation in GROUPED:
        g = d["group"]["bunched"]
        counts = sorted(g)
        if circuits > counts[-1]:
            return res.refuse("R-WIR-09", f"≤ {counts[-1]} circuits / cables bunched (Table 12-6; no extrapolation)",
                              f"{circuits} in the group", _p(4, 151))
        n_col = next(n for n in counts if n >= circuits)
        k_g, pr = g[n_col]
        g_src = _p(4, pr)
        if n_col != circuits:
            res.add("R-WIR-09", "number between columns → next larger number", f"{circuits} → {n_col}", PASS, g_src)
        res.add("R-WIR-06", "Table 12-6 'bunched … in conduits or in wireways'",
                f"{circuits} {'circuit(s)' if col == 'A' else 'cable(s)'}: {k_g:g}", PASS, g_src)
        if circuits > 1:
            res.add("R-WIR-06", "condition: similarly loaded, similar installation, sizes within one step",
                    "the designer must make sure (Lapp notice)", INFO, _p(4, 151))
    else:
        res.add("R-WIR-06", "no grouping factor (conductors spaced ≥ d)", "1", PASS, g_src)

    # --- loaded conductors in a multicore cable (R-WIR-07, R-WIR-09)
    k_c, max_size = 1.0, None
    n_loaded = loaded_cores if loaded_cores is not None else LOADED[circuit]
    if col == "C" and n_loaded > 3:
        rows = d["cores"]
        if n_loaded > rows[-1]["n"]:
            return res.refuse("R-WIR-09", f"≤ {rows[-1]['n']} loaded conductors (Table 12-3; no extrapolation)",
                              f"{n_loaded}", _p(3, 148))
        crow = next(r for r in rows if r["n"] >= n_loaded)
        k_c, max_size = float(crow["free_air"]), 10
        if crow["n"] != n_loaded:
            res.add("R-WIR-09", "number between rows → next larger number", f"{n_loaded} → {crow['n']}", PASS,
                    _p(3, 148))
        res.add("R-WIR-07", "Table 12-3 more than 3 loaded conductors (free air), up to 10 mm²",
                f"{n_loaded} loaded: {k_c:g}", PASS, _p(crow["page"], crow["printed"]))
    elif col == "C":
        res.add("R-WIR-07", "2 or 3 loaded conductors (column C basis)", f"{n_loaded}: no factor", PASS, _p(1, 145))

    # --- overload coordination (R-WIR-10)
    if overload_device:
        if in_a < ib_a - 1e-9:
            return res.refuse("R-WIR-10", "Ib ≤ In (overload coordination)", f"In {in_a:g} A < Ib {ib_a:g} A", "")
        need = in_a
    else:
        need = ib_a

    # --- size (R-WIR-02, R-WIR-11, R-WIR-12)
    k = k_t * k_b * k_g * k_c
    floor = max(prm["smallest_offered_mm2"], min_size_mm2 or 0)
    sizes = sorted((r for r in d["ratings"] if r["column"] == col and r["amps"] is not None
                    and r["size"] >= prm["smallest_offered_mm2"]), key=lambda r: r["size"])
    allowed = [r for r in sizes if r["size"] >= floor - 1e-9 and (max_size is None or r["size"] <= max_size)]
    chosen = next((r for r in allowed if r["amps"] * k >= need - 1e-9), None)
    if chosen is None:
        if not allowed:
            return res.refuse("R-WIR-11", "a size ≥ the project minimum in the column",
                              f"none ≥ {floor:g} mm² in column {col}", _p(1))
        big = allowed[-1]
        if max_size is not None:
            return res.refuse("R-WIR-07", "Table 12-3 covers multicore cables up to 10 mm² only",
                              f"10 mm²: {big['amps']} × {k:.4g} = {big['amps'] * k:.2f} A < {need:g} A", _p(3, 148))
        return res.refuse("R-WIR-11", "one conductor per phase, largest size in column " + col,
                          f"{big['size']:g} mm²: {big['amps']} × {k:.4g} = {big['amps'] * k:.2f} A < {need:g} A "
                          "(parallel conductors not tabulated)", _p(big["page"], big["printed"]))

    iz = chosen["amps"] * k
    idx = sizes.index(chosen)
    if idx == 0:
        bound = "smallest size offered"
    elif sizes[idx - 1]["amps"] * k >= need - 1e-9:
        bound = "project minimum size"
    else:
        bound = "ampacity"
    src = _p(chosen["page"], chosen["printed"])
    res.add("R-WIR-02", f"Table 12-1 column {col} at 30 °C", f"{chosen['size']:g} mm²: {chosen['amps']:g} A", PASS, src)
    res.add("R-WIR-11", f"smallest size ≥ {floor:g} mm²" + (" (project minimum)" if min_size_mm2 else "")
            + (" and ≤ 10 mm² (Table 12-3)" if max_size else ""),
            f"{chosen['size']:g} mm² ({bound})", PASS, src)
    parts = " × ".join(f"{f:g}" for f in (k_t, k_b, k_g, k_c) if f != 1.0)
    iz_txt = f"{chosen['amps']:g} A" + (f" × {parts}" if parts else "") + f" = {iz:.2f} A"
    res.add("R-WIR-12", "Iz = rating × temperature × bundling × grouping × loaded-conductor factors", iz_txt, PASS,
            src)
    if overload_device:
        res.add("R-WIR-10", "Ib ≤ In ≤ Iz", f"{ib_a:g} ≤ {in_a:g} ≤ {iz:.2f} A", PASS, "")
    else:
        res.add("R-WIR-10", "Iz ≥ Ib (device gives no overload protection of the wiring)",
                f"{iz:.2f} ≥ {ib_a:g} A", PASS, "")
    res.add("R-WIR-13", "not checked (no held source)",
            "voltage drop, short-circuit withstand, mechanical minimum size, colours, metres of wire", INFO, "")

    kind = "single core" if col == "A" else f"multicore ({n_loaded} loaded)"
    res.value = {"wire": f"{chosen['size']:g} mm² {kind}, Lapp T12-1 column {col}",
                 "size_mm2": chosen["size"], "iz_a": round(iz, 2), "i_table_a": chosen["amps"],
                 "k_temp": k_t, "k_bundle": k_b, "k_group": k_g, "k_cores": k_c, "bound_by": bound}
    res.basis = "Lapp T12 (DIN VDE 0298-4)"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
