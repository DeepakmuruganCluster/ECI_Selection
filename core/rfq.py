"""RFQ import, stage 1 (owner 2026-10-18): read a client's equipment panel specification (request for quotation, PDF) —
the layout of the client's 'Complete Equipment Panel Specification' (a sample is held under sources/Sample complete/) — and show
what was read for review. Nothing is selected here; stage 2 asks the gaps, stage 3 generates.

Fail closed:
  * the table must have the 19 known columns (header names checked one by one) — another layout is refused, never guessed;
  * every panel's rows must add up to the panel's printed total row (kW, VFD / DOL / soft starter counts, DI, DO, AI, AO)
    — any difference refuses the file and names the column;
  * values are copied as printed; every row keeps its page and S.NO.
What the engine cannot use as printed is flagged per row (kW not in the guide table, single-phase motors, starter counts
not adding up to the quantity, motor current outside the stated MPCB range, …) — shown before any question is asked.

Stored per RFQ (rfq/<id>/): source.pdf (the uploaded file, unchanged) and read.yaml (what was read, with the file's SHA-256).
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime
from pathlib import Path

import yaml

from core.result import WARN

ROOT = Path(__file__).resolve().parents[1]
RFQS = ROOT / "rfq"
MAX_BYTES = 9 * 1024 * 1024
MAX_PAGES = 60
COLS = ["sno", "item", "tag", "marking", "supply", "kw", "amps", "mpcb_rating", "mpcb", "qty", "total_kw", "inv", "dol", "ss",
        "di", "do", "ai_420", "ai_010", "ao"]
# what each header cell must say (spaces, case, line breaks and a 'Reg'/'Req' typo ignored)
HEADER = ["s.no", "item", "instrumentid", "groupmarking", "operatingvoltage", "kw", "amps", "mpcb/mccbrating", "mpcb/mccb",
          "totalqty", "totalkw", "reqinverter", "reqdol", "reqsoftstarter", "reqdi", "reqdo", "reqai4-20ma",
          "reqai0-10v/4-20ma", "reqao4-20ma"]
TOTAL_COLS = ["total_kw", "inv", "dol", "ss", "di", "do", "ai_420", "ai_010", "ao"]
LABEL = {"total_kw": "total kW", "inv": "VFDs", "dol": "DOL starters", "ss": "soft starters", "di": "DI", "do": "DO",
         "ai_420": "AI 4-20 mA", "ai_010": "AI 0-10 V / 4-20 mA", "ao": "AO"}


class RFQError(ValueError):
    pass


def _norm(s: str) -> str:
    s = re.sub(r"\s+", "", (s or "").lower())
    return s.replace("reg", "req", 1) if s.startswith("reg") else s


def _num(v) -> float | None:
    v = (v or "").strip().replace(",", "")
    return float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else None


def _range(text: str) -> tuple[float | None, float | None]:
    """'0.9 To 1.25A', '28 - 40A', '1.1A To 1.6A', '100A' → (lo, hi); a single value → (None, value)."""
    t = (text or "").upper().replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)A?(?:TO|-)(\d+(?:\.\d+)?)A?", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)A", t)
    return (None, float(m.group(1))) if m else (None, None)


def _kind(supply: str, item: str, kw: float | None) -> str:
    s, it = (supply or "").upper().replace(" ", ""), (item or "").lower()
    if "PH" in s and kw:
        return "motor_1ph" if s.startswith("1PH") else "motor"
    if "remote switch" in it or "control" in it and "24V" in s and not kw:
        return "remote_switch"
    if "230V" in s and "4-20" in s:
        return "mains_transmitter"
    if "230VAC" in s:
        return "mains_valve"
    if "0-10V" in s:
        return "pneumatic_panel"
    if "4-20" in s:
        return "loop_transmitter"
    if "tower lamp" in it:
        return "tower_lamp"
    if "24V" in s:
        return "dc_signal"
    return "unstated"


def _supply_from_row(cells: list[str]) -> str:
    """Merged cells: the operating voltage can sit in a neighbouring cell of the same row."""
    m = re.search(r"[13]\s*PH\s*\d+\s*V\s*\d+\s*HZ|230\s*V\s*,?\s*4-20\s*mA|230\s*V\s*AC|24\s*V\s*DC\s*/\s*0-10\s*V|24\s*V\s*D\s*C|24VDC|4-20\s*mA",
                  " ".join(cells[:9]), re.I)
    return m.group(0) if m else ""


def read_pdf(data: bytes, filename: str = "rfq.pdf") -> dict:
    """The RFQ as read: {sha256, filename, project_ref, panels: [{name, heading, rows, printed, computed, check}], flags}."""
    import pdfplumber
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(b"%PDF"):
        raise RFQError("not a PDF file")
    if len(data) > MAX_BYTES:
        raise RFQError(f"the PDF is {len(data) / 1e6:.1f} MB; at most {MAX_BYTES // (1024 * 1024)} MB")
    sha = hashlib.sha256(data).hexdigest()
    panels, cur, section, project_ref, header_seen = [], None, "", None, False
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:                               # a damaged or encrypted file: refused, never half-read
        raise RFQError(f"the PDF cannot be read ({type(e).__name__})")
    with pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise RFQError(f"{len(pdf.pages)} pages; at most {MAX_PAGES}")
        for pno, page in enumerate(pdf.pages, 1):
            for t in page.extract_tables():
                for r in t:
                    cells = [re.sub(r"\s+", " ", (c or "")).strip() for c in r]
                    if len(cells) != len(COLS):
                        if any(cells):
                            raise RFQError(f"page {pno}: a table row has {len(cells)} columns, the RFQ layout has {len(COLS)} — "
                                           "this layout is not recognised (send a sample to add it)")
                        continue
                    filled = [c for c in cells if c]
                    if not filled:
                        continue
                    if _norm(cells[0]) == "s.no":                    # the header row: every column checked
                        bad = [f"column {i + 1} '{cells[i]}' (expected '{HEADER[i]}')" for i in range(len(COLS))
                               if not _norm(cells[i]).startswith(HEADER[i][:max(4, len(HEADER[i]) - 3)])]
                        if bad:
                            raise RFQError("this layout is not recognised: " + "; ".join(bad[:4]))
                        header_seen = True
                        continue
                    if not header_seen:
                        raise RFQError(f"page {pno}: no RFQ header row (S.NO, Item, Instrument ID, …) before the first row")
                    head = " ".join(filled).upper()
                    if m := re.match(r"PANEL SPECIFICATION\s+(\S+)", head):
                        project_ref = m.group(1)
                        continue
                    if m := re.match(r"(.+?)\s+PANEL REQUIREMENTS$", head):
                        cur = {"name": filled[0].rsplit(" ", 2)[0].strip(), "heading": filled[0], "page": pno, "rows": [],
                               "printed": None, "sections": []}
                        panels.append(cur)
                        section = ""
                        continue
                    if "PANEL TOTAL" in head:
                        if cur is None:
                            raise RFQError(f"page {pno}: a panel total row before any 'PANEL REQUIREMENTS' heading")
                        nums = [c for c in cells[1:] if _num(c) is not None]
                        if len(nums) != len(TOTAL_COLS):
                            raise RFQError(f"page {pno}: the total row '{filled[0]}' has {len(nums)} values, {len(TOTAL_COLS)} expected")
                        cur["printed"] = dict(zip(TOTAL_COLS, [_num(x) for x in nums]))
                        cur["total_label"] = filled[0]
                        cur = None
                        continue
                    if not cells[0].isdigit():                       # a section heading (and its stray '0')
                        section = filled[0]
                        if cur is not None:
                            cur["sections"].append(section)
                        continue
                    if cur is None:
                        raise RFQError(f"page {pno} row S.NO {cells[0]}: a row outside any panel")
                    rec = dict(zip(COLS, cells))
                    supply = rec["supply"] or _supply_from_row(cells)
                    kw = _num(rec["kw"])
                    row = {"page": pno, "sno": int(rec["sno"]), "section": section, "item": rec["item"], "tag": rec["tag"],
                           "marking": rec["marking"], "supply": supply, "supply_from_row": not rec["supply"] and bool(supply),
                           "kw": kw, "amps": _num(rec["amps"]), "mpcb_rating": rec["mpcb_rating"], "mpcb": rec["mpcb"],
                           "qty": _num(rec["qty"]), "total_kw": _num(rec["total_kw"]),
                           **{k: _num(rec[k]) or 0 for k in ("inv", "dol", "ss", "di", "do", "ai_420", "ai_010", "ao")}}
                    row["kind"] = _kind(supply, rec["item"], kw)
                    cur["rows"].append(row)
    if not header_seen:
        raise RFQError("no RFQ table found (S.NO, Item, Instrument ID, … header)")
    if not panels:
        raise RFQError("no panel found ('… PANEL REQUIREMENTS' heading)")
    for p in panels:
        if p["printed"] is None:
            raise RFQError(f"panel '{p['name']}' has no 'Panel Total' row: its rows cannot be checked")
        comp = {k: round(sum(r[k] or 0 for r in p["rows"]), 2) for k in TOTAL_COLS}
        p["computed"] = comp
        diff = [f"{LABEL[k]}: rows add up to {comp[k]:g}, total row prints {p['printed'][k]:g}" for k in TOTAL_COLS
                if abs(comp[k] - p["printed"][k]) > (0.05 if k == "total_kw" else 1e-9)]
        if diff:
            raise RFQError(f"panel '{p['name']}': the rows do not add up to the printed total — " + "; ".join(diff))
        for r in p["rows"]:
            r["flags"] = _flags(r)
    out = {"sha256": sha, "filename": filename, "project_ref": project_ref, "pages": pno, "panels": panels,
           "n_rows": sum(len(p["rows"]) for p in panels), "n_flags": sum(len(r["flags"]) for p in panels for r in p["rows"])}
    return out


def _flags(r: dict) -> list[str]:
    """What the engine cannot use as printed (shown for review; stage 2 asks or the designer corrects)."""
    from components.motor_flc.select import select as motor_flc
    out = []
    if r["kind"] in ("motor", "motor_1ph"):
        starters = {k: r[k] for k in ("inv", "dol", "ss") if r[k]}
        if not starters:
            out.append("no starter stated (VFD / DOL / soft starter columns empty)")
        elif len(starters) > 1:
            out.append("more than one starter stated: " + ", ".join(f"{LABEL[k]} {v:g}" for k, v in starters.items()))
        elif r["qty"] and sum(starters.values()) != r["qty"]:
            out.append(f"starters {sum(starters.values()):g} ≠ quantity {r['qty']:g}")
        if r["qty"] and r["kw"] and r["total_kw"] is not None and abs(r["qty"] * r["kw"] - r["total_kw"]) > 0.05:
            out.append(f"total kW {r['total_kw']:g} ≠ quantity × kW = {r['qty'] * r['kw']:g}")
        if r["kind"] == "motor_1ph":
            out.append("single-phase motor (1PH 230 V): the panel engine's starters are three-phase — selected in stage 3 with a check")
        f = motor_flc(kw=r["kw"], phases=1 if r["kind"] == "motor_1ph" else 3, voltage_v=230 if r["kind"] == "motor_1ph" else 400)
        if f.status in ("cannot_select", "invalid"):
            out.append(f"{r['kw']:g} kW is not in the guide motor-current table: the nameplate current is needed (RFQ amps {r['amps']:g} A)"
                       if r["amps"] else f"{r['kw']:g} kW is not in the guide motor-current table and the RFQ gives no amps")
        lo, hi = _range(r["mpcb_rating"])
        if hi is None:
            out.append(f"MPCB / MCCB rating '{r['mpcb_rating'] or '—'}' not readable")
        elif r["amps"] is not None and lo is not None and not lo <= r["amps"] <= hi and not r["inv"]:
            out.append(f"motor current {r['amps']:g} A outside the stated setting range {lo:g} … {hi:g} A")
    elif r["kind"] == "unstated":
        out.append("operating voltage not stated: kind of device unknown")
    if r["qty"] is None:
        out.append("quantity not stated")
    return out


# --- the RFQ's MPCB against the engine's calculation (owner 2026-10-18: a colour per row) -----------------------------
FAULT_LEVELS = (10, 25, 36, 50, 65, 100)       # kA: the engine's setting range is used only when it is the same at all of them


def mpcb_check(r: dict) -> dict:
    """Compare the RFQ's MPCB setting range with the engine's: motor current from the guide table (component 1, 400 V)
    → the Siemens 3RV setting range the DOL selection takes (component 2). The setting range does not depend on the
    fault level for the held table — checked at 10 … 100 kA, and not used if it did. → {state, …}:
      match   — the same range as the engine's
      differs — another range, but it contains the calculated motor current
      unsafe  — the calculated motor current is outside the RFQ's range (the motor is not protected as stated)
      unchecked — with the reason (drive / soft starter rows, single-phase, kW not in the guide table, rating not readable)"""
    from components.motor_flc.select import select as motor_flc
    from components.dol_starter.select import select as dol
    lo, hi = _range(r.get("mpcb_rating"))
    if r.get("kind") != "motor":
        return {"state": "unchecked", "why": "single-phase motor: three-phase MPCB table" if r.get("kind") == "motor_1ph" else "not a motor"}
    if r.get("inv") or r.get("ss"):
        return {"state": "unchecked", "why": ("drive" if r.get("inv") else "soft starter") + ": its protection is selected with it (stage 3)"}
    if lo is None or hi is None:
        return {"state": "unchecked", "why": f"rating '{r.get('mpcb_rating') or '—'}' is not a setting range"}
    f = motor_flc(kw=r["kw"], voltage_v=400)
    if f.status in ("cannot_select", "invalid") or not (f.value or {}).get("flc_a"):
        return {"state": "unchecked", "why": f"{r['kw']:g} kW is not in the guide table: give the nameplate current (stage 2)"}
    flc = f.value["flc_a"]
    ranges = set()
    for ka in FAULT_LEVELS:
        d = dol(flc_a=flc, voltage_v=400, fault_ka=ka)
        ranges.add(((d.value or {}).get("mpcb"), (d.value or {}).get("device_range_a")) if d.status not in ("cannot_select", "invalid") else None)
    if len(ranges) != 1 or None in ranges:
        return {"state": "unchecked", "why": "the engine's MPCB depends on the fault level here: checked once it is given (stage 2)", "flc_a": flc}
    (art, rng), = ranges
    elo, ehi = (float(x) for x in rng.replace(" ", "").split("…"))
    base = {"flc_a": flc, "engine_mpcb": art, "engine_range": [elo, ehi], "rfq_range": [lo, hi],
            "basis": "motor current from the guide table at 400 V (component 1) → Siemens 3RV printed setting range (component 2, "
                     "same at 10 … 100 kA); the RFQ's range → its Type 2 row (R-DOL-14)"}
    if abs(lo - elo) < 1e-6 and abs(hi - ehi) < 1e-6:
        return {**base, "state": "match"}
    if not lo <= flc <= hi:
        return {**base, "state": "unsafe", "why": f"{flc:g} A is outside the RFQ's {lo:g} … {hi:g} A"}
    c = dol(flc_a=flc, voltage_v=400, fault_ka=FAULT_LEVELS[0], mpcb_range=f"{lo:g}-{hi:g}")   # the client's MPCB (R-DOL-14)
    if c.status in ("cannot_select", "invalid"):
        return {**base, "state": "differs", "why": f"no 3RV2 with {lo:g} … {hi:g} A in the held Type 2 table: stage 3 cannot select it"}
    base["rfq_mpcb"] = c.value["mpcb"]
    if any(x.rule == "R-DOL-14" and x.verdict == WARN for x in c.checks):
        return {**base, "state": "differs", "why": f"{flc:g} A is above {c.value['mpcb']}'s usable maximum for an IE3 motor "
                f"({c.value['setting_range_a']} A; IE class not given): confirm the motor's IE class"}
    return {**base, "state": "differs"}


CURRENT_TOL = 0.10        # owner 2026-10-18: RFQ amps vs the guide motor current within ±10 % is "the same"
# per motor unit, the engine's I/O (component 23): DI, DO, AI, AO for each variant of the starter (R-IO-02 … R-IO-08)
IO_RULES = {"DOL": [("slim relay", (2, 1, 0, 0), "R-IO-02"), ("latching relay", (2, 2, 0, 0), "R-IO-02")],
            "SD": [("", (2, 1, 0, 0), "R-IO-08")], "SS": [("", (2, 1, 0, 0), "R-IO-03")],
            "VFD": [("on the fieldbus", (0, 0, 0, 0), "R-IO-04"), ("hardwired", (2, 1, 1, 1), "R-IO-04")]}
SIGNAL_NEEDS = {"loop_transmitter": ("AI", "a 4-20 mA transmitter needs an analog input"),
                "mains_transmitter": ("AI", "a 230 V transmitter with a 4-20 mA output needs an analog input"),
                "mains_valve": ("DO", "a 230 V valve is switched by an output"),
                "remote_switch": ("DI", "a remote switch is read by an input"),
                "dc_signal": ("DI|DO", "a 24 V signal is an input or an output"),
                "tower_lamp": ("DO", "a tower lamp is switched by outputs"),
                "pneumatic_panel": ("AI|DI|DO", "a pneumatic panel exchanges signals")}


def current_check(r: dict) -> dict:
    """The RFQ's motor current against the guide table (component 1, 400 V): within ±10 % (owner 2026-10-18) → 'match'."""
    from components.motor_flc.select import select as motor_flc
    if r.get("kind") != "motor" or r.get("amps") is None:
        return {"state": "unchecked", "why": "single-phase motor" if r.get("kind") == "motor_1ph" else "no current stated"}
    f = motor_flc(kw=r["kw"], voltage_v=400)
    if f.status in ("cannot_select", "invalid") or not (f.value or {}).get("flc_a"):
        return {"state": "unchecked", "why": f"{r['kw']:g} kW is not in the guide table"}
    g = f.value["flc_a"]
    d = (r["amps"] - g) / g
    return {"state": "match" if abs(d) <= CURRENT_TOL else "differs", "rfq_a": r["amps"], "guide_a": g, "diff_pct": round(d * 100, 1),
            "basis": f"guide table at 400 V (component 1); tolerance ±{CURRENT_TOL * 100:g} % (owner 2026-10-18)"}


def io_check(r: dict) -> dict:
    """Per motor unit, the RFQ's DI / DO / AI / AO against the engine's I/O for its starter (component 23)."""
    st = "VFD" if r.get("inv") else "SS" if r.get("ss") else "DOL" if r.get("dol") else None
    q = r.get("qty") or 0
    if not st or not q:
        return {"state": "unchecked", "why": "no starter or quantity stated"}
    have = tuple(round((r.get(k) or 0) / q, 3) for k in ("di", "do")) + (round(((r.get("ai_420") or 0) + (r.get("ai_010") or 0)) / q, 3),
                                                                       round((r.get("ao") or 0) / q, 3))
    for label, want, rule in IO_RULES[st]:
        if have == tuple(float(x) for x in want):
            return {"state": "match", "starter": st, "variant": label, "rfq": have, "engine": want, "rule": rule}
    return {"state": "differs", "starter": st, "rfq": have,
            "engine": [{"variant": l, "io": w, "rule": ru} for l, w, ru in IO_RULES[st]]}


def signal_check(r: dict) -> dict:
    """An instrument or signal row: its I/O agrees with the kind its supply column gives."""
    need = SIGNAL_NEEDS.get(r.get("kind"))
    if not need:
        return {"state": "unchecked", "why": "kind not stated" if r.get("kind") == "unstated" else "—"}
    io = {"DI": r.get("di") or 0, "DO": r.get("do") or 0, "AI": (r.get("ai_420") or 0) + (r.get("ai_010") or 0), "AO": r.get("ao") or 0}
    ok = any(io[k] for k in need[0].split("|"))
    return {"state": "match" if ok else "differs", "needs": need[0], "why": need[1] + ("" if ok else " — none stated")}


def panel_checks(read: dict) -> dict:
    """Per panel: tags used twice in the panel, tags also in another panel, the supplies stated, motors without I/O."""
    seen_in = {}
    for p in read["panels"]:
        for r in p["rows"]:
            if r.get("tag"):
                seen_in.setdefault(r["tag"], set()).add(p["name"])
    out = {}
    for p in read["panels"]:
        tags = [r["tag"] for r in p["rows"] if r.get("tag")]
        dup = sorted({t for t in tags if tags.count(t) > 1})
        shared = sorted({t for t in tags if len(seen_in[t]) > 1})
        supplies = {}
        for r in p["rows"]:
            if r.get("kind", "").startswith("motor"):
                supplies[r["supply"]] = supplies.get(r["supply"], 0) + 1
        no_io = [r["tag"] for r in p["rows"] if r.get("kind", "").startswith("motor") and not r.get("inv")
                 and not any(r.get(k) for k in ("di", "do", "ai_420", "ai_010", "ao"))]       # a drive on the fieldbus has none
        out[p["name"]] = [
            {"check": "totals", "state": "match", "text": "every column adds up to the printed panel total"},
            {"check": "tags unique in the panel", "state": "differs" if dup else "match",
             "text": ("used more than once: " + ", ".join(dup)) if dup else "every tag once"},
            {"check": "tags only in this panel", "state": "differs" if shared else "match",
             "text": ("also in another panel: " + ", ".join(shared)) if shared else "no tag in another panel"},
            {"check": "motor supplies", "state": "match", "text": "; ".join(f"{k or 'not stated'} × {v}" for k, v in supplies.items())},
            {"check": "every DOL / soft-starter motor has I/O", "state": "differs" if no_io else "match",
             "text": ("no I/O stated for: " + ", ".join(no_io)) if no_io else "yes (drives without I/O: on the fieldbus)"}]
    return out


def _annotate(read: dict) -> dict:
    for p in read["panels"]:
        for r in p["rows"]:
            if r.get("kind", "").startswith("motor"):
                r["mpcb_check"] = mpcb_check(r)
                r["current_check"] = current_check(r)
                r["io_check"] = io_check(r)
            else:
                r["signal_check"] = signal_check(r)
    read["panel_checks"] = panel_checks(read)
    return read


# --- storage ---------------------------------------------------------------------------------------------------------
def rfq_id(sha: str) -> str:
    return "RFQ-" + sha[:10]


def save(data: bytes, filename: str, user: str | None = None) -> dict:
    """Read, then store the file and what was read (rfq/<id>/). The same file again → the same RFQ."""
    read = read_pdf(data, filename)
    rid = rfq_id(read["sha256"])
    d = RFQS / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.pdf").write_bytes(data)
    meta = {"id": rid, "filename": re.sub(r"[^\w .()\-]+", "_", filename)[:120], "uploaded_by": user,
            "uploaded_at": datetime.now().isoformat(timespec="seconds")}
    if (d / "read.yaml").exists():
        meta = {**_load(rid).get("meta", {}), "id": rid}            # first upload kept
    (d / "read.yaml").write_text("# RFQ as read by core/rfq.py (stage 1): values copied as printed, each with its page and S.NO.\n"
                                 + yaml.safe_dump({"meta": meta, "read": read}, sort_keys=False, allow_unicode=True, width=200))
    return {"id": rid, **meta, **_summary(_annotate(read))}


def _load(rid: str) -> dict:
    if not re.fullmatch(r"RFQ-[0-9a-f]{10}", str(rid or "")):
        raise RFQError(f"no RFQ {rid!r}")
    f = RFQS / rid / "read.yaml"
    if not f.exists():
        raise RFQError(f"no RFQ {rid!r}")
    return yaml.safe_load(f.read_text()) or {}


def get(rid: str) -> dict:
    d = _load(rid)
    src = RFQS / rid / "source.pdf"
    if not src.exists() or hashlib.sha256(src.read_bytes()).hexdigest() != d["read"]["sha256"]:
        raise RFQError(f"{rid}: the stored PDF is missing or changed (SHA-256 differs) — upload it again")
    read = _annotate(d["read"])                       # worked out again on every open: the engine's current tables
    from core.rfq_trial import partition
    for p in read["panels"]:
        p["structure"] = partition(p)                 # the panel's functional sections (owner 2026-10-18)
    return {"id": rid, **d["meta"], **read, **_summary(read)}


def _summary(read: dict) -> dict:
    out = []
    for p in read["panels"]:
        rows = p["rows"]
        kinds = {}
        for r in rows:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        mc = {}
        for r in rows:
            st = (r.get("mpcb_check") or {}).get("state")
            if st:
                mc[st] = mc.get(st, 0) + 1
        out.append({"name": p["name"], "n_rows": len(rows), "n_motor_rows": kinds.get("motor", 0) + kinds.get("motor_1ph", 0), "mpcb": mc,
                    "printed": p["printed"], "n_flags": sum(len(r["flags"]) for r in rows), "kinds": kinds})
    return {"summary": out}


def listing() -> list[dict]:
    out = []
    for f in sorted(RFQS.glob("RFQ-*/read.yaml")):
        try:
            d = yaml.safe_load(f.read_text()) or {}
            out.append({"id": f.parent.name, **d.get("meta", {}), "project_ref": d["read"].get("project_ref"),
                        "panels": [p["name"] for p in d["read"]["panels"]], "n_flags": d["read"].get("n_flags")})
        except Exception:
            continue
    return sorted(out, key=lambda x: x.get("uploaded_at") or "", reverse=True)
