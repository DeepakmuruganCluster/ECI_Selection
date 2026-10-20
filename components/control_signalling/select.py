"""Control and signalling: interface relays (latching for DOL outputs, slim for other outputs), screwless
terminal blocks with end plates / end clamps / markers / short links, Rittal door switch and light.
Rules: RULES.md / rules.yaml (R-CTL-01 … 19)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from core import project as P
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result
from core.data import data_file

HERE = Path(__file__).parent
COMPONENT = "control_signalling"
FILES = {"s38": "finder_s38.yaml", "s39": "finder_s39.yaml", "s13": "finder_s13.yaml", "s40": "finder_s40.yaml",
         "s20": "finder_s20.yaml", "cwes": "connectwell_es.yaml", "cwtb": "connectwell_tb.yaml",
         "door": "rittal_door_switch.yaml", "light": "rittal_system_light.yaml"}
MAKES = ("finder", "connectwell", "phoenix")
LOADS = {"ac1": "AC-1", "ac15": "AC-15", "dc1": "DC-1", "dc13": "DC-13"}
CONDUCTORS = {"flex": "stranded / flexible", "solid": "solid", "ferrule": "flexible with ferrule"}
EPS = 1e-9


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _data(key: str) -> dict:
    return load_sourced_table(data_file(FILES[key]), ("kind",))


def _rows(key: str, **match) -> list[dict]:
    return [r for r in _data(key)["rows"] if all(r.get(k) == v for k, v in match.items())]


def _one(key: str, **match) -> dict:
    rows = _rows(key, **match)
    if len(rows) != 1:
        raise LookupError(f"{FILES[key]}: {len(rows)} rows for {match}")
    return rows[0]


def _src(key: str, page: int) -> str:
    d = _data(key)
    off = int(d["source"].get("printed_page_offset") or 0)
    ref = d["source"]["ref"]
    return f"{ref} PDF p.{page} (printed {page + off})" if off else f"{ref} p.{page}"


def _ceil(x: float) -> int:
    return math.ceil(x - EPS)


def _fmt(v: float) -> str:
    return f"{v:g}"


def _list(items: dict[str, int]) -> str:
    return ", ".join(f"{a} ×{q}" for a, q in items.items())


MAX_COUNT = 2000    # outputs / terminals / doors per panel: above this the number is a typing error, not a panel
MAX_LIST = 500


# ------------------------------------------------------------------ jumper arithmetic
@lru_cache(maxsize=50_000)   # bounded: the keys come from the designer's numbers (QA 2026-10-16, M6)
def _best(target: int, pieces: int, poles: tuple[int, ...], maxp: int) -> tuple[int, ...] | None:
    """lexicographically largest non-increasing tuple of `pieces` poles (each ≤ maxp) summing to target"""
    if pieces == 0:
        return () if target == 0 else None
    for p in poles:                                  # poles sorted descending
        if p > maxp or p > target:
            continue
        sub = _best(target - p, pieces - 1, poles, p)
        if sub is not None:
            return (p, *sub)
    return None


def exact_pieces(n: int, poles: list[int]) -> tuple[int, ...]:
    """fewest non-cuttable jumpers whose poles add up exactly to n (blocks joined by a wire)"""
    ps = tuple(sorted(set(poles), reverse=True))
    for m in range(1, n + 1):
        if (b := _best(n, m, ps, ps[0])) is not None:
            return b
    raise ValueError(f"{n} cannot be made from {poles}")


def overlap_pieces(n: int, poles: list[int]) -> tuple[int, ...]:
    """fewest jumpers in two rows, consecutive pieces sharing one terminal: Σ poles − (pieces − 1) = n"""
    ps = tuple(sorted(set(poles), reverse=True))
    for m in range(1, n + 1):
        if (b := _best(n + m - 1, m, ps, ps[0])) is not None:
            return b
    raise ValueError(f"{n} cannot be bridged with {poles}")


def _split(n: int, groups: int) -> list[int]:
    base, extra = divmod(n, groups)
    return [base + (1 if i < extra else 0) for i in range(groups)]


# ------------------------------------------------------------------ contact rating
def _contact_check(c: dict, load: str, v: float, a: float) -> tuple[bool | None, str]:
    """(True ok / False exceeds / None duty not rated, explanation) for one contact row"""
    if "ac15_va" in c or "ac1_va" in c:          # Finder layout
        if load == "ac1":
            lim = min(c["rated_a"], c["ac1_va"] / v)
            ok = v <= c["rated_v_ac"] + EPS and a <= lim + EPS
            return ok, f"AC-1: {_fmt(a)} A at {_fmt(v)} V vs ≤ {c['rated_v_ac']} V, ≤ {_fmt(round(lim, 2))} A ({c['rated_a']} A, {c['ac1_va']} VA)"
        if load == "ac15":
            ref = _rules()["params"]["ac15_reference_v"]
            lim = c["ac15_va"] / ref
            ok = v <= c["rated_v_ac"] + EPS and a <= lim + EPS
            return ok, f"AC-15: {_fmt(a)} A at {_fmt(v)} V vs ≤ {c['ac15_va']} VA / {ref} V = {lim:.2f} A, ≤ {c['rated_v_ac']} V"
        pts = [(vv, c.get(f"dc1_{vv}v_a")) for vv in (24, 110, 220) if c.get(f"dc1_{vv}v_a") is not None]
        if not pts:
            return None, f"{LOADS[load]}: no DC rating printed for {c.get('type') or c.get('article')}"
        at = next(((vv, lim) for vv, lim in pts if vv >= v - EPS), None)
        if at is None:
            return False, f"{LOADS[load]}: {_fmt(v)} V DC above the highest printed DC1 voltage {pts[-1][0]} V"
        return a <= at[1] + EPS, f"DC-1 breaking capacity at {at[0]} V: {at[1]} A vs {_fmt(a)} A at {_fmt(v)} V"
    # Connectwell CSR layout: only max current, voltage and switching power
    if load == "ac1":
        lim = min(c["rated_a"], c["max_va"] / v)
        ok = v <= c["max_v_ac"] + EPS and a <= lim + EPS
        return ok, f"AC-1: {_fmt(a)} A at {_fmt(v)} V vs ≤ {c['max_v_ac']} V AC, ≤ {lim:.2f} A ({c['rated_a']} A, {c['max_va']} VA)"
    if load == "dc1":
        lim = min(c["rated_a"], c["max_w_dc"] / v)
        ok = v <= c["max_v_dc"] + EPS and a <= lim + EPS
        return ok, f"DC-1: {_fmt(a)} A at {_fmt(v)} V vs ≤ {c['max_v_dc']} V DC, ≤ {lim:.2f} A ({c['rated_a']} A, {c['max_w_dc']} W)"
    return None, f"{LOADS[load]}: the catalogue gives no {LOADS[load]} rating (only {c['rated_a']} A, {c['max_v_ac']} V AC / {c['max_v_dc']} V DC, {c['max_va']} VA / {c['max_w_dc']} W)"


# ------------------------------------------------------------------ select
def select(dol_outputs: int = 0, other_outputs: int = 0, coil_v_dc: float = 24, relay_make: str | None = None,
           latch_make: str | None = None, finder_series: str | None = None, relay_connection: str | None = None,
           relay_groups: int | None = None, spare_pct: float | None = None, contact_v: float | None = None,
           contact_a: float | None = None, contact_load: str | None = None, panel_internal_c: float | None = None,
           do_available: int | None = None, terminal_make: str | None = None, io_terminals: int = 0,
           io_conductor_mm2: float | None = None, conductor_type: str | None = None,
           jumper_groups: list | None = None, power_terminals: list | None = None, client_requirements: dict | None = None,
           terminal_strips: int | None = None, doors: int = 0) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]

    # ---------------------------------------------------------------- input validation
    def whole(name, v, lo=0):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and v >= lo
    for name, v in (("dol_outputs", dol_outputs), ("other_outputs", other_outputs),
                    ("io_terminals", io_terminals), ("doors", doors)):
        if not whole(name, v):
            return res.invalid(f"{name} must be a whole number ≥ 0 (got {v})")
        if v > MAX_COUNT:
            return res.invalid(f"{name} {v:g} is above {MAX_COUNT} — more than one panel holds; check the number")
    for name, v in (("jumper_groups", jumper_groups), ("power_terminals", power_terminals)):
        if v is not None and (not isinstance(v, list) or len(v) > MAX_LIST):
            return res.invalid(f"{name} must be a list of at most {MAX_LIST} entries")
    dol_outputs, other_outputs, io_terminals, doors = int(dol_outputs), int(other_outputs), int(io_terminals), int(doors)
    power_terminals = power_terminals or []
    if not (dol_outputs or other_outputs or io_terminals or power_terminals or doors):
        return res.invalid("nothing to select: give outputs, terminals or doors")
    relay_make = relay_make or prm["relay_make_default"]
    latch_make = latch_make or relay_make
    terminal_make = terminal_make or prm["terminal_make_default"]
    for name, v in (("relay_make", relay_make), ("latch_make", latch_make)):
        if v not in MAKES:
            return res.invalid(f"{name} must be one of {', '.join(MAKES)} (got {v})")
    if terminal_make not in ("connectwell", "phoenix"):
        return res.invalid(f"terminal_make must be connectwell or phoenix (got {terminal_make})")
    finder_series = str(finder_series or prm["finder_series_default"])
    if finder_series not in ("38", "39"):
        return res.invalid(f"finder_series must be 38 or 39 (got {finder_series})")
    relay_connection = relay_connection or prm["relay_connection_default"]
    if relay_connection not in ("screwless", "screw"):
        return res.invalid(f"relay_connection must be screwless or screw (got {relay_connection})")
    relay_groups = prm["relay_groups_default"] if relay_groups is None else relay_groups
    if not whole("relay_groups", relay_groups, 1):
        return res.invalid(f"relay_groups must be a whole number ≥ 1 (got {relay_groups})")
    relay_groups = int(relay_groups)
    spare_pct = prm["spare_pct_default"] if spare_pct is None else spare_pct
    if spare_pct < 0:
        return res.invalid(f"spare_pct must be ≥ 0 (got {spare_pct})")
    if contact_load is not None or contact_v is not None or contact_a is not None:
        if contact_load not in LOADS:
            return res.invalid(f"contact_load must be one of {', '.join(LOADS)} (got {contact_load})")
        if not (contact_v and contact_v > 0 and contact_a and contact_a > 0):
            return res.invalid("contact_load needs contact_v (V) and contact_a (A), both > 0")
    if do_available is not None and not whole("do_available", do_available):
        return res.invalid(f"do_available must be a whole number ≥ 0 (got {do_available})")
    conductor_type = conductor_type or prm["conductor_type_default"]
    if conductor_type not in CONDUCTORS:
        return res.invalid(f"conductor_type must be one of {', '.join(CONDUCTORS)} (got {conductor_type})")
    if io_terminals and not (io_conductor_mm2 and io_conductor_mm2 > 0):
        return res.invalid("io_conductor_mm2 (conductor size of the I/O wiring) is required with io_terminals")
    jumper_groups = list(jumper_groups or [])
    if any(not whole("jumper group", g, 2) for g in jumper_groups):
        return res.invalid(f"each jumper group must be a whole number ≥ 2 (got {jumper_groups})")
    if sum(jumper_groups) > io_terminals:
        return res.invalid(f"commoned groups ({sum(jumper_groups)} terminals) exceed the I/O terminals ({io_terminals})")
    for i, p in enumerate(power_terminals):
        if not (isinstance(p, dict) and (p.get("mm2") or 0) > 0 and whole("count", p.get("count"), 1)
                and (p.get("a") or 0) > 0):
            return res.invalid(f"power_terminals[{i}] needs mm2 > 0, count ≥ 1 and a (circuit current) > 0 (got {p})")
    if terminal_strips is not None and not whole("terminal_strips", terminal_strips, 1):
        return res.invalid(f"terminal_strips must be a whole number ≥ 1 (got {terminal_strips})")

    req_text, req_src = P.cite(client_requirements, "relay_terminal_scheme")
    res.add("R-CTL-01", f"relay and terminal scheme ({'client requirement' if req_text else 'designer choice'})",
            req_text or "as given in the inputs (no client statement passed)", INFO, req_src)
    value: dict = {"latch_relay": None, "slim_relay": None}
    bom: list[dict] = []

    def line(item, article, qty, src):
        bom.append({"item": item, "article": article, "qty": qty, "source": src})

    # ================================================================ relays
    if dol_outputs or other_outputs:
        if coil_v_dc not in prm["coil_v_dc_supported"]:
            return res.refuse("R-CTL-02", "relay coil voltage", f"{_fmt(coil_v_dc)} V DC: only 24 V DC (PLC DQ) versions are transcribed")
        res.add("R-CTL-02", "relay coil voltage", "24 V DC (PLC output)", PASS)
        for make, needed in ((latch_make, dol_outputs), (relay_make, other_outputs)):
            if needed and make == "phoenix":
                return res.refuse("R-CTL-03", "relay make held", "Phoenix Contact data sheets are not held yet (not in sources/register.yaml)")
        factor = (100 + spare_pct) / 100
        used: list[tuple[str, dict, str, str]] = []   # (label, contact row, data key, source)

        if dol_outputs:
            if latch_make == "connectwell":
                return res.refuse("R-CTL-04", "24 V DC latching (set/reset) relay, Connectwell",
                                  "the Connectwell Electronic Solutions catalogue has no latching or bistable relay",
                                  "CW-ES-2526 (whole catalogue)")
            lr = _one("s13", kind="latching")
            q = _ceil(dol_outputs * factor)
            res.add("R-CTL-04", "latching relay with SET and RESET inputs, 24 V DC",
                    f"{lr['article']} Call & Reset relay {lr['supply']}, {lr['contacts']} {lr['rated_a']} A, "
                    f"{lr['width_mm']} mm (rejected: 13.01 / 20 series step relays toggle; 40.xx.6 resets by reversing the coil "
                    "current, S40 p.10; 38/39 series and Connectwell have none)", PASS,
                    f"{_src('s13', lr['page'])}, {_src('s13', _one('s13', kind='code')['page'])}")
            res.add("R-CTL-05", "SET / RESET command from the PLC",
                    f"2 outputs per latching relay (inputs {lr['inputs']}), pulse {_fmt(lr['impulse_min_s'] * 1000)} ms … "
                    f"{_fmt(lr['impulse_max_s'])} s — not a held output", INFO,
                    f"{_src('s13', lr['page'])}, {_src('s13', _one('s13', kind='wiring')['page'])}")
            value.update(latch_relay=lr["article"], latch_relay_qty=q)
            line("Latching relay (DOL outputs), set/reset", lr["article"], q, _src("s13", lr["page"]))
            used.append(("latching relay", lr, "s13", _src("s13", lr["page"])))

        if other_outputs:
            if relay_make == "finder":
                key = "s38" if finder_series == "38" else "s39"
                match = {"kind": "module", "connection": relay_connection}
                if key == "s38":
                    match["coil_code"] = prm["finder_38_coil"]
                mod = _one(key, **match)
                coil = _one(key, kind="coil", coil_code=mod["coil_code"])
                contact = _one(key, kind="contact")
                coil_ma = coil["i_ma"]
                detail = f"relay {mod['relay']} + socket {mod['socket']}, {mod['coil']} coil {coil['umin_v']}…{coil['umax_v']} V, {coil['i_ma']} mA"
            else:
                key = "cwes"
                mod = _one(key, kind="module", connection=relay_connection)
                contact = _one(key, kind="contact")
                coil_ma = mod["nominal_input_ma"]
                detail = f"{mod['coil']} ({mod['polarity']}), pick-up {mod['pickup_v']} V, {mod['nominal_input_ma']} mA"
            q = _ceil(other_outputs * factor)
            res.add("R-CTL-06", "slim relay, 1 CO, 24 V DC PLC output",
                    f"{mod['article']} ({mod['connection']}, {mod['width_mm']} mm): {detail}", PASS, _src(key, mod["page"]))
            value.update(slim_relay=mod["article"], slim_relay_qty=q, slim_coil_ma=round(q * coil_ma, 2))
            line("Slim relay (other outputs)", mod["article"], q, _src(key, mod["page"]))
            used.append(("slim relay", contact, key, _src(key, contact["page"])))

            # accessories
            if relay_groups > q:
                return res.invalid(f"relay_groups ({relay_groups}) is more than the relays ({q}): a group holds at least one relay")
            groups = _split(q, relay_groups)
            if key in ("s38", "s39"):
                jmp = _one(key, kind="accessory", use="jumper")
                sep = _one(key, kind="accessory", use="separator")
                mk = _one(key, kind="accessory", use="marker")
                nj = sum(_ceil(g / jmp["ways"]) for g in groups if g >= 2)
                ns = sep["per_group"] * relay_groups
                nm = _ceil(q / mk["tags"])
                res.add("R-CTL-11", "separators and markers as printed",
                        f"separator {sep['article']}: {sep['per_group']} per group × {relay_groups} = {ns}; "
                        f"marker sheet {mk['article']} ({mk['tags']} tags): ceil({q}/{mk['tags']}) = {nm}", PASS,
                        _src(key, sep["page"]))
                res.add("R-CTL-12", "coil common (A2) jumper link, cut to length",
                        f"{jmp['article']} {jmp['ways']}-way ({jmp['rated_a']} A max): "
                        f"{' + '.join(f'ceil({g}/{jmp['ways']})' for g in groups)} = {nj}; blocks joined by a wire", PASS,
                        _src(key, jmp["page"]))
                value.update(slim_jumper=f"{jmp['article']} ×{nj}", slim_jumper_qty=nj,
                             slim_separator=sep["article"] if ns else None, slim_separator_qty=ns,
                             slim_marker=mk["article"], slim_marker_qty=nm, slim_end_clamp=None, slim_end_clamp_qty=0)
                line("Jumper link (coil common A2)", jmp["article"], nj, _src(key, jmp["page"]))
                if ns:
                    line("Plastic separator (group start and end)", sep["article"], ns, _src(key, sep["page"]))
                line("Marker tag sheet", mk["article"], nm, _src(key, mk["page"]))
            else:
                jumpers = {r["ways"]: r["article"] for r in _rows("cwes", kind="accessory", use="jumper")}
                pieces: dict[str, int] = {}
                for g in groups:
                    if g >= 2:
                        for p in exact_pieces(g, list(jumpers)):
                            pieces[jumpers[p]] = pieces.get(jumpers[p], 0) + 1
                card = _one("cwtb", kind="marker", article=_one("cwes", kind="accessory", use="marker")["article"])
                nm = _ceil(q / card["tags"])
                clamp = prm["end_clamp"]
                _one("cwes", kind="accessory", use="end_clamp", article=clamp)
                nc = 2 * relay_groups
                res.add("R-CTL-11", "markers as printed",
                        f"marker card {card['article']} ({card['tags']} tags): ceil({q}/{card['tags']}) = {nm}", PASS,
                        f"{_src('cwes', 45)}, {_src('cwtb', card['page'])}")
                res.add("R-CTL-12", "coil common jumpers (not cuttable) and end clamps",
                        f"JX4 poles {sorted(jumpers)}: {_list(pieces) or 'none'}; end clamps {clamp}: 2 × {relay_groups} = {nc}",
                        PASS, f"{_src('cwes', 45)}, {_src('cwtb', 283)}")
                value.update(slim_jumper=_list(pieces) or None, slim_jumper_qty=sum(pieces.values()),
                             slim_separator=None, slim_separator_qty=0, slim_marker=card["article"], slim_marker_qty=nm,
                             slim_end_clamp=clamp, slim_end_clamp_qty=nc)
                for a, n in pieces.items():
                    line("Jumper (coil common)", a, n, _src("cwes", 45))
                line("Marker card", card["article"], nm, _src("cwes", 45))
                line("End clamp", clamp, nc, _src("cwtb", 283))

        res.add("R-CTL-07", "quantity = outputs × (1 + spare %)",
                f"spare {_fmt(spare_pct)} %: latching {value.get('latch_relay_qty', 0)}, slim {value.get('slim_relay_qty', 0)}", PASS)

        do_needed = 2 * dol_outputs + other_outputs
        value["do_needed"] = do_needed
        txt = f"2 × {dol_outputs} (SET + RESET) + {other_outputs} = {do_needed}"
        if do_available is not None and do_needed > do_available:
            res.add("R-CTL-05", "PLC outputs needed ≤ client's DO count",
                    f"{txt} > {do_available} available: the client's I/O count does not allow this (decision C-1/C-2)", WARN,
                    _src("s13", _one("s13", kind="wiring")["page"]))
        else:
            res.add("R-CTL-05", "PLC outputs needed", txt + (f" ≤ {do_available} available" if do_available is not None else ""),
                    PASS, _src("s13", _one("s13", kind="wiring")["page"]))

        # contact load
        if contact_load is None:
            res.add("R-CTL-08", "contact load within the printed rating", "load not given: not checked", WARN)
        else:
            for label, c, key, src in used:
                ok, msg = _contact_check(c, contact_load, contact_v, contact_a)
                if ok is None:
                    return res.refuse("R-CTL-08", f"{label}: {LOADS[contact_load]} rating", msg, src)
                if not ok:
                    return res.refuse("R-CTL-08", f"{label}: contact load within the rating", msg, src)
                res.add("R-CTL-08", f"{label}: contact load within the rating", msg, PASS, src)
                if contact_load == "dc13":
                    st = _rows(key, kind="statement", topic="dc13")
                    if not st:      # pragma: no cover  (no DC rating at all is refused above)
                        return res.refuse("R-CTL-08", f"{label}: DC-13 rating", "no DC-13 statement printed", src)
                    res.add("R-CTL-09", f"{label}: DC-13 (inductive DC load)",
                            "fit a diode in parallel with the load (then electrical life as DC-1)", WARN, _src(key, st[0]["page"]))

        # ambient
        if panel_internal_c is None:
            res.add("R-CTL-10", "panel internal temperature within the relay range", "not given: not checked", WARN)
        else:
            for label, c, key, src in used:
                lo, hi = c["ambient_min_c"], c["ambient_max_c"]
                if not lo <= panel_internal_c <= hi:
                    return res.refuse("R-CTL-10", f"{label}: ambient {lo} … +{hi} °C", f"{_fmt(panel_internal_c)} °C inside the panel", src)
                res.add("R-CTL-10", f"{label}: ambient {lo} … +{hi} °C", f"{_fmt(panel_internal_c)} °C", PASS, src)

    # ================================================================ terminal blocks
    if io_terminals or power_terminals:
        if terminal_make == "phoenix":
            return res.refuse("R-CTL-03", "terminal make held", "Phoenix Contact data sheets are not held yet (not in sources/register.yaml)")
        order = prm["terminal_order"]
        blocks = sorted(_rows("cwtb", kind="terminal"), key=lambda r: order.index(r["article"]))

        def choose(mm2: float, amps: float | None, what: str):
            for b in blocks:
                lo, hi = b.get(f"{conductor_type}_min"), b.get(f"{conductor_type}_max")
                if lo is None or not lo - EPS <= mm2 <= hi + EPS:
                    continue
                if amps is not None and b["iec_a"] < amps - EPS:
                    continue
                return b
            return None

        counts: dict[str, int] = {}
        reqs = ([("I/O", io_conductor_mm2, None, io_terminals)] if io_terminals else []) + \
               [(f"power {i + 1}", p["mm2"], p["a"], int(p["count"])) for i, p in enumerate(power_terminals)]
        for what, mm2, amps, n in reqs:
            b = choose(mm2, amps, what)
            need = f"{what}: {_fmt(mm2)} mm² {CONDUCTORS[conductor_type]}" + (f", {_fmt(amps)} A" if amps else "")
            if b is None:
                return res.refuse("R-CTL-13", "CP push-in feed-through block for the conductor and current",
                                  f"{need}: no CP block (CP1.5 … CP16) covers it", _src("cwtb", 14))
            res.add("R-CTL-13", "smallest CP block for the conductor and current",
                    f"{need} → {b['article']} ({conductor_type} {b[f'{conductor_type}_min']}–{b[f'{conductor_type}_max']} mm², "
                    f"IEC {b['iec_a']} A / {b['iec_v']} V) ×{n}", PASS, _src("cwtb", b["page"]))
            counts[b["article"]] = counts.get(b["article"], 0) + n
        counts = {a: counts[a] for a in order if a in counts}
        types = {a: _one("cwtb", kind="terminal", article=a) for a in counts}
        strips = len(counts) if terminal_strips is None else int(terminal_strips)

        # end plates: one per group of identical blocks; a strip beyond the number of groups adds one
        plates: dict[str, int] = {}
        for a in counts:
            plates[types[a]["end_plate"]] = plates.get(types[a]["end_plate"], 0) + 1
        if strips > len(counts):
            big = types[max(counts, key=counts.get)]["end_plate"]
            plates[big] += strips - len(counts)
        res.add("R-CTL-14", "end plate at the end of each group of identical blocks and at every size change",
                f"{len(counts)} group(s) on {strips} strip(s): {_list(plates)}", PASS,
                f"{_src('cwtb', 297)}, {_src('cwtb', types[next(iter(counts))]['page'])}")
        clamp = prm["end_clamp"]
        _one("cwtb", kind="end_clamp", article=clamp)
        res.add("R-CTL-15", "end clamps on both sides of each assembly",
                f"{clamp}: 2 × {strips} strip(s) = {2 * strips}" + (" (one strip per terminal type, decision C-8)" if terminal_strips is None else ""),
                PASS, _src("cwtb", 283))
        cards: dict[str, int] = {}
        for a, n in counts.items():
            card = _one("cwtb", kind="marker", article=types[a]["marker"])
            cards[card["article"]] = cards.get(card["article"], 0) + _ceil(n / card["tags"])
        res.add("R-CTL-16", "one marking tag per terminal, on the card printed for the block",
                ", ".join(f"{a}: {n} tags → {types[a]['marker']}" for a, n in counts.items()) + f" → {_list(cards)}",
                PASS, _src("cwtb", 289))
        value.update(terminals=_list(counts), terminal_qty=sum(counts.values()), end_plates=_list(plates),
                     end_plate_qty=sum(plates.values()), end_clamp=clamp, end_clamp_qty=2 * strips,
                     markers=_list(cards), marker_cards=sum(cards.values()))
        for a, n in counts.items():
            line("Terminal block, push-in", a, n, _src("cwtb", types[a]["page"]))
        for a, n in plates.items():
            line("End plate", a, n, _src("cwtb", 297))
        line("End clamp", clamp, 2 * strips, _src("cwtb", 283))
        for a, n in cards.items():
            line("Marker card", a, n, _src("cwtb", 289))

        if jumper_groups:
            io_block = choose(io_conductor_mm2, None, "I/O")
            jr = _one("cwtb", kind="jumper", series=io_block["jumper_series"])
            pieces: dict[str, int] = {}
            detail = []
            for g in jumper_groups:
                ps = overlap_pieces(int(g), jr["poles"])
                detail.append(f"{g} → {' + '.join(map(str, ps))}" + (f" − {len(ps) - 1}" if len(ps) > 1 else ""))
                for p in ps:
                    pieces[f"{jr['series']}/{p}"] = pieces.get(f"{jr['series']}/{p}", 0) + 1
            pieces = dict(sorted(pieces.items(), key=lambda kv: -int(kv[0].split("/")[-1])))
            res.add("R-CTL-17", "short links for commoned groups (two jumper rows, pieces overlap one terminal)",
                    f"{jr['series']} poles {jr['poles']} (Imax {jr['imax_a']} A): " + "; ".join(detail) + f" → {_list(pieces)}",
                    PASS, f"{_src('cwtb', jr['page'])}, {_src('cwtb', 10)}")
            value.update(jumpers=_list(pieces), jumper_qty=sum(pieces.values()))
            for a, n in pieces.items():
                line("Pluggable jumper (short link)", a, n, _src("cwtb", jr["page"]))

    # ================================================================ Rittal door switch and light
    if doors:
        sw = _one("door", kind="door_switch")
        lt = _one("light", kind="light")
        ns, nl = doors * prm["switches_per_door"], doors * prm["lights_per_door"]
        cur = round(nl * lt["current_a"], 2)
        rows_min = _ceil(cur / lt["row_max_a"])
        per_switch = prm["lights_per_door"] * lt["current_a"]
        res.add("R-CTL-18", "door-operated switch and LED light per door",
                f"{ns} × {sw['article']} (24 V DC / {sw['rating_24vdc_a']} A ≥ {per_switch:g} A light), "
                f"{nl} × {lt['article']} ({lt['supply']}, {lt['current_a']} A each = {cur:g} A; rows ≤ {lt['row_max_a']} A → ≥ {rows_min} row(s))",
                PASS if per_switch <= sw["rating_24vdc_a"] else WARN,
                f"{_src('door', sw['page'])}, {_src('light', lt['page'])}, {_src('light', 2)}")
        value.update(door_switch=sw["article"], door_switch_qty=ns, light=lt["article"], light_qty=nl,
                     light_current_a=cur, light_rows_min=rows_min)
        line("Door-operated switch", sw["article"], ns, _src("door", sw["page"]))
        line("LED system light 24 V DC", lt["article"], nl, _src("light", lt["page"]))

    res.add("R-CTL-19", "article numbers and coverage",
            "catalogue editions of 2026-10-11: confirm before ordering; tower lamp, suppressors, distribution blocks, "
            "PE terminals and Phoenix parts not covered", INFO)
    value["bom"] = bom
    res.value = value
    res.basis = "manufacturer catalogues + client specification"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
