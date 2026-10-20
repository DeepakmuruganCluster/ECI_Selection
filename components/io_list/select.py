"""I/O list: the PLC signals each motor feeder needs. Rules: rules.yaml (R-IO-01 … 07). Holds no catalogue data."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from components.panel.select import parse
from core.provenance import load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "io_list"
TYPES = ("DI", "DO", "AI", "AO", "PN", "SAFETY")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


def _signals(starter: str, dol_relays: str, vfd_control: str, vfd_sto: bool) -> list[tuple[str, str, str, str]]:
    """(type, signal, rule, name part) for one installed unit (name part: R-IO-09)."""
    if starter == "DOL":
        run = [("DO", "start (latching relay set)", "R-IO-02", "Start"), ("DO", "stop (latching relay reset)", "R-IO-02", "Stop")] \
            if dol_relays == "latching" else [("DO", "run command (interface relay)", "R-IO-02", "Run")]
        return [("DI", "running (contactor auxiliary contact)", "R-IO-02", "Running"),
                ("DI", "tripped (MPCB auxiliary contact)", "R-IO-02", "Tripped"), *run]
    if starter == "SD":
        return [("DI", "running (main contactor auxiliary contact)", "R-IO-08", "Running"),
                ("DI", "tripped (overload relay contact)", "R-IO-08", "Tripped"),
                ("DO", "run command (star-delta sequence by the timer)", "R-IO-08", "Run")]
    if starter == "SS":
        return [("DI", "running", "R-IO-03", "Running"), ("DI", "fault", "R-IO-03", "Fault"), ("DO", "run command", "R-IO-03", "Run")]
    if vfd_control == "hardwired":
        sig = [("DO", "run command", "R-IO-04", "Run"), ("DI", "running", "R-IO-04", "Running"), ("DI", "fault", "R-IO-04", "Fault"),
               ("AO", "speed setpoint", "R-IO-04", "SpeedSetpoint"), ("AI", "actual speed", "R-IO-04", "ActualSpeed")]
    else:
        sig = [("PN", "drive on the fieldbus: commands, setpoint, status, actual values", "R-IO-04", "")]
    if vfd_sto:
        sig.append(("SAFETY", "STO (safe torque off) from the safety relay / F-DO", "R-IO-05", "STO"))
    return sig


NAME = re.compile(r"^[IO]_[A-Za-z0-9_]{1,40}$")
DIRS = {"DI": "I", "AI": "I", "DO": "O", "AO": "O"}


def _apply_edits(rows: list[dict], edits: list, res: Result) -> str | None:
    """R-IO-12: add / remove / rename / set (type within its direction). Returns why it is invalid, or None."""
    changed, added = [], []
    for i, e in enumerate(edits, 1):
        if not isinstance(e, dict) or e.get("action") not in ("add", "remove", "rename", "set"):
            return f"I/O edit {i}: action must be add, remove, rename or set"
        names = [r.get("name") for r in rows]
        a = e["action"]
        if a == "add":
            t, n = e.get("type"), e.get("name")
            if t not in DIRS:
                return f"I/O edit {i}: type must be DI, DO, AI or AO (got {t!r})"
            if not isinstance(n, str) or not NAME.match(n):
                return f"I/O edit {i}: name {n!r} must be I_… or O_… (letters, digits, '_', at most 40)"
            if n[0] != DIRS[t]:
                return f"I/O edit {i}: {n} — a {t} is {'an input: I_' if DIRS[t] == 'I' else 'an output: O_'}…"
            if n in names:
                return f"I/O edit {i}: {n} is already in the list (names are unique)"
            sig = str(e.get("signal") or n)[:120]
            rows.append({"unit": str(e.get("unit") or "panel")[:40], "starter": "", "type": t, "signal": sig, "rule": "R-IO-12",
                         "name": n, "source": "designer edit", "edited": "added"})
            added.append(n)
            continue
        n = e.get("name")
        hit = next((r for r in rows if r.get("name") == n), None)
        if hit is None:
            return f"I/O edit {i}: no signal named {n!r} in this list"
        if a == "remove":
            rows.remove(hit)
            changed.append(f"removed {n}")
        elif a == "rename":
            to = e.get("to")
            if not isinstance(to, str) or not NAME.match(to) or to[0] != n[0]:
                return f"I/O edit {i}: new name {to!r} must be {n[0]}_… (letters, digits, '_', at most 40)"
            if to in names:
                return f"I/O edit {i}: {to} is already in the list"
            hit.update(name=to, edited="renamed", was=hit.get("was") or n)
            changed.append(f"renamed {n} → {to}")
        else:   # set
            t = e.get("type", hit["type"])
            if t not in DIRS or hit["type"] not in DIRS:
                return f"I/O edit {i}: type must be DI, DO, AI or AO"
            if DIRS[t] != DIRS[hit["type"]]:
                return (f"I/O edit {i}: {n} is an {'input' if n[0] == 'I' else 'output'}; {t} is not — remove it and add "
                        f"an {'O' if n[0] == 'I' else 'I'}_ signal")
            hit.update(type=t, edited="changed")
            if e.get("signal"):
                hit["signal"] = str(e["signal"])[:120]
            changed.append(f"set {n}: {t}" + (f", '{hit['signal']}'" if e.get("signal") else ""))
    if changed:
        res.add("R-IO-12", "designer edits to the I/O list (the rules' list no longer applies alone)", "; ".join(changed), WARN, "designer edit")
    if added:
        res.add("R-IO-12", "signals added by the designer", ", ".join(added), INFO, "designer edit")
    return None


def _name(typ: str, unit: str, part: str) -> str:
    """R-IO-09: I_<unit>_<Signal> for inputs, O_… for outputs, PN_<unit> on the fieldbus, O_<unit>_STO for STO."""
    u = re.sub(r"[^A-Za-z0-9]+", "_", unit).strip("_")     # P1.2 → P1_2, P301A/B → P301A_B: PLC tags take letters, digits, _
    if typ == "PN":
        return f"PN_{u}"
    return f"{'I' if typ in ('DI', 'AI') else 'O'}_{u}_{part}"


def select(load_list: str, dol_relays: str | None = None, vfd_control: str | None = None, vfd_sto: bool = False,
           di_available: int | None = None, do_available: int | None = None, ai_available: int | None = None,
           ao_available: int | None = None, panel_signals: bool = False, pmr: bool = False,
           edits: list | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    prm = _rules()["params"]
    dol_relays = dol_relays or prm["dol_relays_default"]
    vfd_control = vfd_control or prm["vfd_control_default"]
    if dol_relays not in ("slim", "latching"):
        return res.invalid(f"dol_relays must be slim or latching (got {dol_relays})")
    if vfd_control not in ("fieldbus", "hardwired"):
        return res.invalid(f"vfd_control must be fieldbus or hardwired (got {vfd_control})")
    try:
        loads = parse(load_list)
    except ValueError as e:
        return res.invalid(str(e))
    res.add("R-IO-01", "load list readable; one set of signals per installed unit",
            f"{len(loads)} line(s), {sum(ld['qty'] for ld in loads)} unit(s)", PASS)

    rows, excluded = [], []
    # R-IO-10: the panel signals of the company drawing, before the motor signals
    if panel_signals:
        for p in prm["panel_signals"]:
            if p.get("needs") == "pmr" and not pmr:
                continue
            rows.append({"unit": "panel", "starter": "", "type": p["type"], "signal": p["signal"], "rule": "R-IO-10",
                         "name": p["name"], "source": f"OWN-PROPEL-SCH160 p.12 '{p['drawing']}'"})
        res.add("R-IO-10", "panel signals as in the company drawing (sheet 12)",
                ", ".join(r["name"] for r in rows), INFO, "OWN-PROPEL-SCH160 p.12")
    for ld in loads:
        if ld["starter"] == "HEATER":
            excluded.append(ld["tag"])
            continue
        for n in range(1, ld["qty"] + 1):
            unit = ld["tag"] if ld["qty"] == 1 else f"{ld['tag']}.{n}"
            for typ, signal, rule, part in _signals(ld["starter"], dol_relays, vfd_control, vfd_sto):
                rows.append({"unit": unit, "starter": ld["starter"], "type": typ, "signal": signal, "rule": rule,
                             "name": _name(typ, unit, part)})
    # R-IO-12: the designer's edits, checked, before counting and numbering
    if edits:
        why = _apply_edits(rows, edits, res)
        if why:
            return res.invalid(why)
    count = {t: sum(1 for r in rows if r["type"] == t) for t in TYPES}
    # R-IO-11: channel numbers per type, in list order; inputs and outputs apart; bus and STO apart
    seen = {t: 0 for t in TYPES}
    for r in rows:
        seen[r["type"]] += 1
        r["channel"] = f"{r['type']}{seen[r['type']]:02d}" if r["type"] in ("DI", "DO", "AI", "AO") else ""
        r["dir"] = {"DI": "input", "AI": "input", "DO": "output", "AO": "output", "PN": "bus", "SAFETY": "safety"}[r["type"]]
    order = {"DI": 0, "AI": 1, "DO": 0, "AO": 1}
    inputs = sorted((r for r in rows if r["dir"] == "input"), key=lambda r: order[r["type"]])     # stable: list order kept
    outputs = sorted((r for r in rows if r["dir"] == "output"), key=lambda r: order[r["type"]])
    bus = [r for r in rows if r["dir"] == "bus"]
    safety = [r for r in rows if r["dir"] == "safety"]
    names = [r["name"] for r in rows]
    if rows:
        res.add("R-IO-09", "every signal named (I_ inputs, O_ outputs, PN_ drives on the bus)",
                f"{len(inputs)} input(s), {len(outputs)} output(s), {len(bus)} bus device(s), {len(safety)} STO signal(s)"
                + (f"; names repeated: {', '.join(sorted({n for n in names if names.count(n) > 1}))}" if len(set(names)) < len(names) else ""),
                WARN if len(set(names)) < len(names) else PASS)
        res.add("R-IO-11", "inputs and outputs listed apart, numbered per type (list positions, not PLC addresses)",
                ", ".join(f"{t} {count[t]}" for t in ("DI", "AI", "DO", "AO") if count[t]) or "no PLC channels", INFO)

    starters = {ld["starter"] for ld in loads}
    if "DOL" in starters:
        res.add("R-IO-02", "DOL: running + tripped DI, run DO", f"relay: {dol_relays}", INFO)
    if "SD" in starters:
        res.add("R-IO-08", "star-delta: running + tripped DI, one run DO (the timer switches star → delta)", "per unit", INFO)
    if "SS" in starters:
        res.add("R-IO-03", "soft starter: running + fault DI, run DO", "per unit", INFO)
    if "VFD" in starters:
        res.add("R-IO-04", "VFD control", vfd_control, INFO)
        res.add("R-IO-05", "STO signal per drive", "yes" if vfd_sto else "no STO", INFO)
    if excluded:
        res.add("R-IO-06", "out of scope (owner instruction): heater feeders", ", ".join(excluded), INFO)

    avail = {"DI": di_available, "DO": do_available, "AI": ai_available, "AO": ao_available}
    given = {t: a for t, a in avail.items() if a is not None}
    if given:
        short = [f"{t} {count[t]} > {a}" for t, a in given.items() if count[t] > a]
        res.add("R-IO-07", "motor signals fit in the available channels",
                "; ".join(short) if short else ", ".join(f"{t} {count[t]} ≤ {a}" for t, a in given.items()),
                WARN if short else PASS)

    res.value = {"n_signals": len(rows), "n_excluded": len(excluded),
                 **{f"io_{t.lower()}": count[t] for t in TYPES}, "io_list": rows,
                 "inputs": inputs, "outputs": outputs, "bus": bus, "safety": safety,
                 "n_inputs": len(inputs), "n_outputs": len(outputs),
                 "input_names": ", ".join(r["name"] for r in inputs), "output_names": ", ".join(r["name"] for r in outputs),
                 "input_channels": ", ".join(r["channel"] for r in inputs), "output_channels": ", ".join(r["channel"] for r in outputs),
                 "bus_names": ", ".join(r["name"] for r in bus), "safety_names": ", ".join(r["name"] for r in safety)}
    res.basis = "signal standard (RULE)"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
