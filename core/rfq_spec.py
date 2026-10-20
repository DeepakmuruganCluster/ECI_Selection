"""RFQ import, the client's automation / panel specification (owner 2026-10-20: "upload it with the RFQ").

The equipment PDF (core/rfq.py) lists the loads; the incoming section, makes, PLC and panel practice are in a second
client document: a two-column table "requirement → value" plus a PLC block per panel. Each row is read as printed, with
its page, and matched to what it decides:
  - answers to RFQ questions (e.g. surge arrester make, energy meter and its communication) — shown as "client spec p.N"
    and winning over the company standard (the designer's own answer still wins over both);
  - client-specified BOM lines for what the engine does not select (busbar, earth bars): listed, not engine-checked;
  - compliance checks of what the engine selects against the client's words (core/rfq_bom: client_checks);
  - rows for a later part (PLC, drives, relays …), and rows outside the panel scope (enclosure, SCADA PC, UPS, display).
Part by part (owner 2026-10-20): part 1 = incoming & distribution is wired; the other rows are read and kept for their part.
Stored beside the RFQ: rfq/<id>/spec.pdf and spec.yaml.
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime

import yaml

from core import rfq

MAX_BYTES = 12 * 1024 * 1024
OUT_OF_SCOPE = "outside the panel scope (owner 2026-10-11 / 2026-10-13: enclosure, accessories, SCADA PC, WinCC, display, UPS)"
# (label pattern, what the row is, part it belongs to); the first match wins
ROW_KINDS = [
    (r"surge\s*arrester.*ups", "spd_ups", None), (r"surge\s*arrester", "spd", 1), (r"main\s*incom", "incomer", 1),
    (r"energy\s*meter", "meter", 1), (r"current\s*transformer", "ct", 1), (r"bus\s*bar", "busbar", 1),
    (r"earthing", "earthing", 1),
    (r"plc\s*cpu", "plc_cpu", 6), (r"etherent|ethernet\s*hub|ethernet", "network", 6), (r"power\s*supply", "smps", 5),
    (r"relay", "relays", 6), (r"connector", "terminals", 6), (r"panel\s*wiring", "wiring", 8),
    (r"profinet\s*cable", "profinet_cable", 6), (r"tower\s*lamp", "tower_lamp", 5),
    (r"inverter|vfd", "vfd", 2), (r"^dol", "dol", 3), (r"soft\s*star", "soft_starter", 4), (r"^mccb", "mccb", 3),
    (r"scada|pc\s*config|display|^ups$|panel\s*requirement|panel\s*size|panel\s*stand", "out_of_scope", None),
]
PARTS_DONE = {1, 2, 3, 4}          # the parts whose rows answer questions and are checked (owner 2026-10-20: part by part)
PART = {1: "Incoming & distribution", 2: "VFD section", 3: "DOL / MCC section", 4: "Soft starter section",
        5: "Control supply & control circuit", 6: "PLC & I/O", 7: "Motor cables", 8: "Internal wiring"}
MAKES = {"phoenix": "Phoenix", "phoneix": "Phoenix", "obo": "OBO", "siemens": "Siemens"}


def _cell(x) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def _panels_in(label: str, panels: list[str]) -> list[str]:
    """The RFQ panels a row names ('Main Incommer For Bio MBR Panel' → BIO/UF); none named → every panel."""
    hit = [p for p in panels if re.search(rf"\b{re.escape(re.split(r'[/_ ]', p)[0])}", label, re.I)]
    return hit or list(panels)


def _kind(label: str):
    for pat, kind, part in ROW_KINDS:
        if re.search(pat, label, re.I):
            return kind, part
    return None, None


def _row_use(kind: str, value: str) -> dict:
    """What a part-1 row decides: answers, client lines and the requirement checked against the engine's result."""
    v = value.lower()
    if kind == "incomer":
        req = {"series": (re.search(r"\b(3V[AMLT])\b", value, re.I) or [None, None])[1],
               "in_a": float(m[1]) if (m := re.search(r"(\d+)\s*A\b", value, re.I)) else None,
               "icu_ka": float(m[1]) if (m := re.search(r"(\d+)\s*kA", value, re.I)) else None,
               "adjustable": "adjustable" in v}
        if req["series"]:
            req["series"] = req["series"].upper()
        ans = {"incomer_series": req["series"]} if req["series"] in ("3VA", "3VM") else {}
        if req["series"] == "3VM" and req["adjustable"]:
            ans["incomer_release"] = "TM220"            # 3VM: the adjustable release (3VA1 is TM240, adjustable, by itself)
        return {"answers": ans, "require": req}
    if kind == "spd":
        make = next((MAKES[k] for k in MAKES if k in v), None)
        return {"answers": {"spd": "true", **({"spd_make": make} if make else {})}, "require": {"make": make}}
    if kind == "meter":
        return {"answers": {"meter": "true", **({"meter_comm": "profinet"} if "profinet" in v else {})},
                "require": {"family": "7KM" if "7km" in v else None, "profinet": "profinet" in v}}
    if kind == "ct":
        makes = sorted({m for k, m in {"rishabh": "rishabh", "selec": "selec", "select": "selec"}.items() if k in v})
        return {"answers": {"ct_make": makes[0]} if len(makes) == 1 else {}, "require": {"makes": makes}}
    if kind == "vfd":                                # part 2 (owner 2026-10-20): drive family, duty, line reactors
        kw = re.search(r"(\d+(?:\.\d+)?)\s*(?:kw)?\s*and\s*below|below\s*(\d+(?:\.\d+)?)\s*kw|up\s*to\s*(\d+(?:\.\d+)?)\s*kw", v)
        lim = float(next(g for g in kw.groups() if g)) if kw and re.search(r"choke|reactor", v) else None
        ans = {}
        if "normal load" in v:
            ans["duty"] = "normal"
        elif "heavy" in v:
            ans["duty"] = "heavy"
        if lim is not None:
            ans["line_reactor_up_to_kw"] = lim
        return {"answers": ans, "require": {"family": "G120" if "g120" in v else None, "duty": ans.get("duty"), "reactor_up_to_kw": lim}}
    if kind == "dol":                                # part 3 (owner 2026-10-20): 3RV, link modules, surge suppressor
        art = re.search(r"3RT29\d6-1J[A-Z]00", value, re.I)
        return {"answers": {"contactor_suppressor": "varistor"} if "suppress" in v else {},
                "require": {"mpcb_family": "3RV" if "3rv" in v else None, "link_module": "link module" in v,
                            "suppressor": art[0].upper() if art else ("varistor" if "suppress" in v else None)}}
    if kind == "soft_starter":                       # part 4 (owner 2026-10-20): 3RW52 with display and communication
        com = next((c for k, c in (("profinet", "profinet"), ("profibus", "profibus"), ("ethernet/ip", "ethernet_ip"),
                                   ("modbus tcp", "modbus_tcp"), ("modbus", "modbus_rtu")) if k in v), None)
        return {"answers": {"ss_comm": com} if com else {},
                "require": {"family": "3RW52" if "3rw-52" in v or "3rw52" in v else None, "display": "display" in v, "comm": com}}
    if kind == "busbar":
        return {"lines": [{"group": "Client-specified", "item": "Busbar", "description": f"Busbar: {value}"}]}
    if kind == "earthing":
        lines = [{"group": "Client-specified", "item": "Earth busbar", "description": "Earthing busbar, copper"}]
        if "analog" in v:
            lines.append({"group": "Client-specified", "item": "Analog earth bar", "description": "Separate earth bar for the analog signal screens"})
        return {"lines": lines}
    return {}


def read_pdf(data: bytes, filename: str, panels: list[str]) -> dict:
    """Every row of the specification as printed (label, value, page), what it is, its part and what it decides."""
    import pdfplumber
    if not data.startswith(b"%PDF"):
        raise ValueError("not a PDF file")
    rows, plc, cur = [], {}, None
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for raw in table:
                    cells = [_cell(c) for c in raw]
                    if not any(cells):
                        continue
                    label, value = cells[0], next((c for c in cells[1:] if c), "")
                    m = re.match(r"(.+?)\s+panel\s+(?:plc\s+)?requirements$", label, re.I)
                    if m:                                   # a panel's PLC block begins
                        cur = _panels_in(m[1], panels)[0] if _panels_in(m[1], panels) != panels or len(panels) == 1 else None
                        plc.setdefault(cur or m[1], {"label": label, "page": pno, "io": {}, "counts": {}})
                        continue
                    if cur is not None and re.match(r"(digital|analog)", label, re.I) and len(cells) >= 4:
                        num = lambda x: float(x) if re.fullmatch(r"\d+(\.\d+)?", x) else None
                        plc[cur]["io"][label] = {"required": num(cells[1]), "spare": num(cells[2]), "final": num(cells[3])}
                        continue
                    if cur is not None and label in ("CPU1513", "HMI", "IM Station-ET200SP") or re.match(r"(CPU|IM Station)", label):
                        nums = [c for c in cells[1:] if re.fullmatch(r"\d+", c)]
                        if cur is not None:
                            plc[cur]["counts"][label] = int(nums[0]) if nums else 0
                        continue
                    if label.lower() in ("plc req", "total plc requirements") or not value:
                        continue
                    cur = None
                    kind, part = _kind(label)
                    rows.append({"label": label, "value": value, "page": pno, "kind": kind, "part": part,
                                 "part_name": PART.get(part), "panels": _panels_in(label, panels),
                                 "status": ("out of scope" if kind in ("out_of_scope", "spd_ups") else
                                            f"used (part {part})" if part in PARTS_DONE else f"kept for part {part}" if part else "not matched"),
                                 **_row_use(kind or "", value)})
    if not rows:
        raise ValueError("no 'requirement → value' table found: is this the client's automation / panel specification?")
    return {"filename": filename, "rows": rows, "plc": plc}


def _dir(rid: str):
    return rfq._dir(rid) if hasattr(rfq, "_dir") else rfq.RFQS / rid


def save(rid: str, data: bytes, filename: str, user: str | None = None) -> dict:
    """Read and keep the client's specification beside the RFQ (needs the designer role)."""
    from core import auth
    auth.require("designer")
    if len(data) > MAX_BYTES:
        raise ValueError(f"the file is {len(data) / 1e6:.1f} MB; at most {MAX_BYTES // 2**20} MB")
    r = rfq.get(rid)
    read = read_pdf(data, filename, [p["name"] for p in r["panels"]])
    d = rfq.RFQS / rid
    (d / "spec.pdf").write_bytes(data)
    read.update(sha256=hashlib.sha256(data).hexdigest(), uploaded_at=datetime.now().isoformat(timespec="seconds"), uploaded_by=user)
    (d / "spec.yaml").write_text("# The client's automation / panel specification, as read (core/rfq_spec.py).\n"
                                 + yaml.safe_dump(read, sort_keys=False, allow_unicode=True, width=200))
    return get(rid)


def get(rid: str) -> dict | None:
    f = rfq.RFQS / rid / "spec.yaml"
    if not re.fullmatch(r"RFQ-[0-9a-f]{10}", str(rid or "")) or not f.exists():
        return None
    d = yaml.safe_load(f.read_text()) or {}
    pdf = rfq.RFQS / rid / "spec.pdf"
    if not pdf.exists() or hashlib.sha256(pdf.read_bytes()).hexdigest() != d.get("sha256"):
        raise ValueError(f"{rid}: the stored specification does not match its record (changed outside the tool)")
    return d


def answers_for(rid: str, panel: str) -> dict:
    """{key: (value, 'client spec p.N: <label>')} — the answers the client's specification gives for one panel; and the
    RFQ's own protection column (owner 2026-10-20, part 3): every drive row 'MPCB…' → drives protected by an MSP."""
    d = get(rid)
    out = {}
    try:
        p = next(x for x in rfq.get(rid)["panels"] if x["name"] == panel)
        prot = {str(r.get("mpcb") or "").upper().split("-")[0] for r in p["rows"] if r["kind"] == "motor" and r.get("inv")}
        if prot == {"MPCB"}:
            out["vfd_protection"] = ("msp", f"RFQ {panel}: protection column 'MPCB-3RV' on every drive row")
        sp = {str(r.get("mpcb") or "").upper().split("-")[0] for r in p["rows"] if r["kind"] == "motor" and r.get("ss")}
        if sp == {"MPCB"}:
            out["ss_protection"] = ("mpcb", f"RFQ {panel}: protection column 'MPCB-3RV' on every soft-starter row")
    except (StopIteration, ValueError):
        pass
    for r in (d or {}).get("rows", []):
        if r.get("part") in PARTS_DONE and panel in r["panels"]:
            for k, v in (r.get("answers") or {}).items():
                out[k] = (v, f"client spec p.{r['page']}: {r['label']}")
    return out


def lines_for(rid: str, panel: str) -> list[dict]:
    d = get(rid)
    return [{**ln, "source": f"client spec p.{r['page']}: {r['label']} — '{r['value']}'", "row": r["label"]}
            for r in (d or {}).get("rows", []) if panel in r["panels"] for ln in (r.get("lines") or [])]


def requirements_for(rid: str, panel: str) -> list[dict]:
    d = get(rid)
    return [r for r in (d or {}).get("rows", []) if panel in r["panels"] and r.get("require")]
