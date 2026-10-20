"""Load-list import from a client's Word load list (project.yaml documents: load_list, equipment). Rules: rules.yaml (R-LL-01 … 15).

Reads the registered .docx directly (zipfile + XML, standard library) at run time; every value
cites 'table T row R' of that file. The client's equipment PDF is read for the cross-check only.
Produces load-list text in the panel component's format (components.panel.select.parse).
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from core import project as P
from core.provenance import SOURCES, check_reference, load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "load_list"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Word / PDF columns (grid positions): the header of table 1
C_SNO, C_ITEM, C_ID, C_MARK, C_VOLT, C_KW, C_AMPS, C_RATING, C_DEVICE, C_QTY, C_TKW = range(11)
REQ_COLS = {11: "VFD", 12: "DOL", 13: "SS"}
SECTION_WORDS = {"VFD REQUIREMENT": "VFD", "SOFT STARTER REQUIREMENT": "SS", "DOL REQUIREMENT": "DOL"}
NUM = r"(\d+(?:\.\d+)?)"
RE_RANGE = re.compile(rf"^{NUM}\s*A?\s*(?:-|to)\s*{NUM}\s*A?$", re.I)
RE_SINGLE = re.compile(rf"^{NUM}\s*A$", re.I)
RE_DEVICE = re.compile(r"(MPCB|MCCB)\s*-\s*(3RV|3VM)", re.I)
RE_SUPPLY = re.compile(r"(\d)\s*PH\s*(\d+)\s*V", re.I)


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


def _num(s):
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def _g(x: float) -> str:
    return f"{x:g}"


def _members(text: str) -> list[str]:
    """'P201A/B/C' → [P201A, P201B, P201C]; 'P101A&P101B' / 'RS_K201A and RS_201B' → listed tags."""
    out = []
    for part in re.split(r"&|\band\b", text or "", flags=re.I):
        p = re.sub(r"\s+", "", part).upper()
        if not p:
            continue
        bits = p.split("/")
        if len(bits) > 1 and bits[0][-1:].isalpha() and all(len(b) == 1 and b.isalpha() for b in bits[1:]):
            out += [bits[0]] + [bits[0][:-1] + b for b in bits[1:]]
        else:
            out.append(p)
    return out


# ---------------------------------------------------------------- Word reader
def _word_tables(path: Path) -> list[list[list[str]]]:
    """Every table as rows of 14 grid cells (a cell spanning n columns fills the first, the rest '')."""
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    tables = []
    for tbl in root.iter(W + "tbl"):
        rows = []
        for tr in tbl.findall(W + "tr"):
            grid = []
            for tc in tr.findall(W + "tc"):
                txt = " ".join("".join(t.text or "" for t in p.iter(W + "t")).strip() for p in tc.findall(W + "p"))
                span = tc.find(f"{W}tcPr/{W}gridSpan")
                grid += [re.sub(r"\s+", " ", txt).strip()] + [""] * (int(span.get(W + "val")) - 1 if span is not None else 0)
            rows.append((grid + [""] * 14)[:14])
        tables.append(rows)
    return tables


def _rating(rating: str, device: str) -> tuple[dict, str | None]:
    """Split the MPCB rating / device cells. Returns the parsed fields and a repair note (or None)."""
    repair = None
    dev = RE_DEVICE.search(device) or RE_DEVICE.search(rating)
    if RE_DEVICE.search(rating):
        repair = f"rating cell '{rating}' holds range and device together → split"
    rng_text = RE_DEVICE.sub("", rating).strip()
    if not rng_text and device and RE_DEVICE.sub("", device).strip():
        rng_text = RE_DEVICE.sub("", device).strip()
        repair = f"rating written one column right ('{device}') → split"
    f = {"client_mpcb": rng_text or None, "client_device": f"{dev.group(1).upper()}-{dev.group(2).upper()}" if dev else None,
         "client_range_min": None, "client_range_max": None}
    m = RE_RANGE.match(rng_text)
    if m:
        f["client_range_min"], f["client_range_max"] = float(m.group(1)), float(m.group(2))
    return f, repair


@lru_cache(maxsize=None)
def _document(project: str) -> dict:
    """Parse the Word load list once: rows, total rows and every issue (rule, row uid, panel, message)."""
    ref = check_reference(P.doc("load_list", project))
    PANELS, client = P.panels(project), P.client(project)
    tables = _word_tables(SOURCES / ref["file"])
    rows, totals, issues, pending, section = [], [], [], [], None

    def issue(rule, msg, row=None, panel=None):
        issues.append({"rule": rule, "uid": row["uid"] if row else None,
                       "panel": row["panel"] if row else panel, "msg": msg})

    for t, tbl in enumerate(tables, 1):
        for r, c in enumerate(tbl, 1):
            ref_txt = f"table {t} row {r}"
            joined = " ".join(x for x in c if x)
            if c[C_SNO].upper().startswith("S.NO"):
                continue
            head = joined.upper()
            if head in SECTION_WORDS or any(head.startswith(k) for k in SECTION_WORDS):
                section = next(v for k, v in SECTION_WORDS.items() if head.startswith(k))
                continue
            if "PANEL TOTAL" in head:
                m = re.search(r"(.+?)\s+PANEL TOTAL\s+(\w+)", head)
                pname = m.group(1).replace("/", "_").strip() if m else "?"
                starter = {"VFD": "VFD", "SS": "SS", "DOL": "DOL"}.get(m.group(2) if m else "", section)
                stated = next((_num(c[k]) for k in REQ_COLS if _num(c[k]) is not None), None)
                tot = {"panel": pname, "starter": starter, "stated": stated, "ref": ref_txt,
                       "label": next(x for x in c if "PANEL TOTAL" in x.upper()),
                       "sum_req": sum(x["qty"] for x in pending),
                       "sum_total_qty": sum(x["total_qty"] for x in pending if x["total_qty"] is not None)}
                totals.append(tot)
                if pname not in PANELS:
                    issue("R-LL-02", f"{ref_txt}: total row names an unknown panel '{m.group(1) if m else joined}'")
                for x in pending:
                    x["panel"] = pname if pname in PANELS else None
                pending = []
                continue
            kw = _num(c[C_KW])
            if kw is None:
                if c[C_ID] or c[C_ITEM]:
                    issues.append({"rule": "R-LL-01", "uid": None, "panel": None,
                                   "msg": f"{ref_txt} '{c[C_ITEM]} {c[C_ID]}': kW '{c[C_KW]}' not readable → left out"})
                continue
            row = {"uid": len(rows), "table": t, "row": r, "source": ref_txt, "section": section, "panel": None,
                   "item": c[C_ITEM], "id": re.sub(r"\s+", "", c[C_ID]), "marking": c[C_MARK], "supply": c[C_VOLT],
                   "kw": kw, "client_flc_a": _num(c[C_AMPS]), "total_qty": _num(c[C_QTY]), "total_kw": _num(c[C_TKW]),
                   "req": {s: int(_num(c[k])) for k, s in REQ_COLS.items() if _num(c[k])}}
            rows.append(row)
            pending.append(row)
            f, repair = _rating(c[C_RATING], c[C_DEVICE])
            row.update(f)
            row["repair"] = repair
            # starter and quantity (R-LL-03)
            if len(row["req"]) != 1:
                row["starter"], row["qty"] = None, 0
                row["problem"] = f"Req columns {row['req'] or 'all empty'}: no single starter count"
            else:
                (row["starter"], row["qty"]), = row["req"].items()
                row["problem"] = None
            row["section_disagrees"] = bool(row["starter"] and section and row["starter"] != section)
            # load type (R-LL-04)
            it = row["item"].lower()
            row["load_type"] = ("heater" if "heater" in it else
                                "spare" if re.search(r"\b(extra|spare)\b", it) else "motor")
            # supply (R-LL-05)
            m = RE_SUPPLY.search(row["supply"])
            row["phases"], row["voltage_v"] = (int(m.group(1)), float(m.group(2))) if m else (None, None)
            row["members"] = _members(row["id"])
    for x in pending:
        issue("R-LL-02", f"{x['id']} ({x['source']}): no 'Panel Total' row closes it → no panel", x)

    # tags (R-LL-09) — document order, stable whatever panel is asked for
    seen: dict[str, int] = {}
    for row in rows:
        n = seen[row["id"]] = seen.get(row["id"], 0) + 1
        row["tag"] = row["id"] if n == 1 else f"{row['id']}_{n}"
        row["renamed"] = n > 1

    for row in rows:
        tag, src = row["tag"], row["source"]
        if row["problem"]:
            issue("R-LL-03", f"{tag} ({src}): {row['problem']} → left out", row)
        elif row["section_disagrees"]:
            issue("R-LL-03", f"{tag} ({src}): Req column says {row['starter']} but the section is {row['section']}", row)
        if row["phases"] is None:
            issue("R-LL-05", f"{tag} ({src}): Operating Voltage '{row['supply']}' not readable → left out", row)
        if row["load_type"] == "heater":
            issue("R-LL-04", f"{tag} ({src}): '{row['item']}' → HEATER line ({client}'s Req column: {row['starter']} × "
                             f"{row['qty']}; the heater feeder is a separate component)", row)
        elif row["load_type"] == "spare":
            issue("R-LL-04", f"{tag} ({src}): '{row['item']}' read as spare starters ({row['starter']} × {row['qty']}); "
                             f"kept in the load list because {client} counts them in its totals", row)
        if row["renamed"]:
            issue("R-LL-09", f"{row['id']} used again at {src} ('{row['item']}') → written as {tag}", row)
        mk = _members(row["marking"])
        if row["marking"] and set(mk) != set(row["members"]):
            issue("R-LL-10", f"{tag} ({src}): Instrument ID '{row['id']}' ≠ Group Marking '{row['marking']}'", row)
        arith = []
        if row["total_qty"] is not None and row["total_kw"] is not None \
                and abs(row["kw"] * row["total_qty"] - row["total_kw"]) > 0.011:
            arith.append(f"KW {_g(row['kw'])} × Total Qty {_g(row['total_qty'])} ≠ Total KW {_g(row['total_kw'])}")
        if row["qty"] and row["total_qty"] is not None and row["total_qty"] != row["qty"]:
            arith.append(f"Total Qty {_g(row['total_qty'])} ≠ Req {row['starter']} {row['qty']} (Req count used)")
        if row["qty"] and len(row["members"]) > 1 and len(row["members"]) != row["qty"]:
            arith.append(f"{len(row['members'])} tags in '{row['id']}' ≠ {row['qty']}")
        if arith:
            issue("R-LL-11", f"{tag} ({src}): " + "; ".join(arith), row)
        if row["repair"]:
            issue("R-LL-13", f"{tag} ({src}): {row['repair']} '{row['client_mpcb']}' + '{row['client_device']}'", row)
        lo, hi, flc = row["client_range_min"], row["client_range_max"], row["client_flc_a"]
        if lo is not None and flc is not None and not lo <= flc <= hi:
            issue("R-LL-14", f"{tag} ({src}): client current {_g(flc)} A outside client MPCB range "
                             f"{_g(lo)}–{_g(hi)} A", row)

    for tot in totals:
        msgs = []
        if tot["stated"] != tot["sum_req"]:
            msgs.append(f"rows' Req counts add up to {tot['sum_req']}")
        if tot["stated"] != tot["sum_total_qty"]:
            msgs.append(f"rows' Total Qty add up to {_g(tot['sum_total_qty'])}")
        tot["mismatch"] = msgs
        if msgs:
            issue("R-LL-12", f"'{tot['label']}' ({tot['ref']}) says "
                             f"{_g(tot['stated']) if tot['stated'] is not None else '?'}; " + ", ".join(msgs),
                  panel=tot["panel"])

    _cross_check(project, rows, totals, issue)
    return {"rows": rows, "totals": totals, "issues": issues, "ref": ref}


# ---------------------------------------------------------------- PDF master (cross-check only)
@lru_cache(maxsize=None)
def _pdf_rows(project: str) -> tuple[list[dict], list[dict]]:
    import pdfplumber
    ref = check_reference(P.doc("equipment", project))
    headings = [(re.compile(rx), pn) for rx, pn in P.setting("equipment_panel_headings", project, [])]
    rows, totals, panel, section = [], [], None, ""
    with pdfplumber.open(SOURCES / ref["file"]) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for tbl in page.extract_tables():
                for c in tbl:
                    c = [re.sub(r"\s+", " ", x or "").strip() for x in c] + [""] * 19
                    head = " ".join(x for x in c if x).upper()
                    if "PANEL REQUIREMENTS" in head:
                        panel = next((pn for rx, pn in headings if rx.search(head)), None)
                        continue
                    if "PANEL TOTAL" in head:
                        totals.append({"panel": panel, "page": pno,
                                       **{s: _num(c[k]) for k, s in REQ_COLS.items()}})
                        continue
                    kw = _num(c[C_KW])
                    if c[C_SNO] and not any(c[C_ITEM:C_TKW]) and not c[C_SNO].isdigit():
                        section = c[C_SNO]
                        continue
                    if kw is None or not c[C_ID]:
                        continue
                    rows.append({"panel": panel, "page": pno, "sno": c[C_SNO], "section": section, "item": c[C_ITEM],
                                 "id": re.sub(r"\s+", "", c[C_ID]), "marking": c[C_MARK], "supply": c[C_VOLT],
                                 "kw": kw, "amps": _num(c[C_AMPS]), "total_qty": _num(c[C_QTY]),
                                 "req": {s: int(_num(c[k])) for k, s in REQ_COLS.items() if _num(c[k])}})
    return rows, totals


def _cross_check(project, rows, totals, issue):
    pdf, pdf_totals = _pdf_rows(project)
    used, match = set(), {}
    norm = lambda s: re.sub(r"\s+", " ", (s or "").lower()).strip()  # noqa: E731
    tests = [lambda w, p: p["id"] == w["id"],
             lambda w, p: (set(_members(p["marking"])) == set(w["members"])
                           or set(_members(w["marking"])) == set(_members(p["id"]))),
             lambda w, p: norm(p["item"]) == norm(w["item"]) and p["kw"] == w["kw"]]
    for test in tests:
        for w in rows:
            if w["uid"] in match:
                continue
            for i, p in enumerate(pdf):
                if i not in used and p["panel"] == w["panel"] and test(w, p):
                    used.add(i)
                    match[w["uid"]] = p
                    break
    for w in rows:
        p = match.get(w["uid"])
        if p is None:
            issue("R-LL-15", f"{w['tag']} ({w['source']}, '{w['item']}'): not in the equipment PDF", w)
            continue
        cite = f"PDF p.{p['page']} '{p['section']}' S.NO {p['sno']}"
        d = []
        if p["id"] != w["id"]:
            d.append(f"tag {p['id']} in the PDF (PDF marking '{p['marking']}')")
        for key, label in (("kw", "kW"), ("total_qty", "Total Qty")):
            if p[key] != w[key]:
                d.append(f"{label} {_g(w[key])} ≠ {_g(p[key]) if p[key] is not None else '—'}")
        if p["amps"] != w["client_flc_a"]:
            d.append(f"Amps {_g(w['client_flc_a'])} ≠ {_g(p['amps']) if p['amps'] is not None else '—'}")
        if p["req"] != w["req"]:
            d.append(f"starter count {w['req']} ≠ {p['req']}")
        if norm(p["supply"]).replace(" ", "") != norm(w["supply"]).replace(" ", ""):
            d.append(f"supply '{w['supply']}' ≠ '{p['supply']}'")
        w["pdf"], w["pdf_item"], w["pdf_tag"] = cite, p["item"], p["id"]
        if d:
            issue("R-LL-15", f"{w['tag']} ({w['source']}) vs {cite}: " + "; ".join(d), w)
    for i, p in enumerate(pdf):
        if i not in used:
            issue("R-LL-15", f"PDF p.{p['page']} '{p['section']}' S.NO {p['sno']} {p['id']} ('{p['item']}', {p['panel']}): "
                             "not in the Word load list", panel=p["panel"])
    for pt in pdf_totals:
        for s in ("VFD", "DOL", "SS"):
            wt = next((t for t in totals if t["panel"] == pt["panel"] and t["starter"] == s), None)
            if wt and pt[s] is not None and pt[s] != wt["stated"]:
                issue("R-LL-15", f"{pt['panel']} total {s}: Word {_g(wt['stated'])} ≠ PDF p.{pt['page']} {_g(pt[s])}",
                      panel=pt["panel"])


# ---------------------------------------------------------------- output
def _line(row: dict, standby: int, cable_m: float | None) -> str:
    starter = "HEATER" if row["load_type"] == "heater" else row["starter"]
    s = f"{row['tag']} {_g(row['kw'])} {starter}"
    if row["qty"] > 1:
        s += f" qty={row['qty']}"
    if standby:
        s += f" standby={standby}"
    if not (row["phases"] == 3 and row["voltage_v"] == 400):
        s += f" ph={row['phases']} v={_g(row['voltage_v'])}"
    if cable_m is not None:
        s += f" cable={_g(cable_m)}"
    return s


def select(project: str | None = None, panel: str = "all", default_cable_m: float | None = None,
           standby_per_group: int | None = None, tag: str | None = None, standby: dict | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    try:
        project = P.resolve(project)
        PANELS, client, src, equip = P.panels(project), P.client(project), P.doc("load_list", project), P.doc("equipment", project)
    except P.ProjectError as e:
        return res.invalid(f"no load list held: {e}")
    if panel not in (*PANELS, "all"):
        return res.invalid(f"panel must be one of {', '.join(PANELS)} or all (got {panel})")
    if default_cable_m is not None and not default_cable_m > 0:
        return res.invalid(f"default_cable_m must be positive (got {default_cable_m})")
    if standby_per_group is not None and (int(standby_per_group) != standby_per_group or standby_per_group < 0):
        return res.invalid(f"standby_per_group must be a whole number ≥ 0 (got {standby_per_group})")
    if standby is not None and (not isinstance(standby, dict) or not all(
            isinstance(k, str) and not isinstance(v, bool) and isinstance(v, (int, float)) and v == int(v) and v >= 0
            for k, v in standby.items())):
        return res.invalid("standby must map a tag group to a whole number of standby units ≥ 0")
    doc = _document(project)
    panels = PANELS if panel == "all" else (panel,)
    rows = [r for r in doc["rows"] if r["panel"] in panels or (panel == "all" and r["panel"] is None)]
    if tag is not None:
        rows = [r for r in rows if r["tag"] == tag]
        if not rows:
            return res.invalid(f"tag {tag!r} is not an Instrument ID of a {panel if panel != 'all' else ''} row in "
                               f"{src} (a repeated ID is written TAG_2)")
    uids = {r["uid"] for r in rows}
    issues = [i for i in doc["issues"]
              if (i["uid"] in uids) or (tag is None and i["uid"] is None and (i["panel"] in panels or panel == "all"))]

    usable = [r for r in rows if r["starter"] and r["phases"] and r["panel"]]
    groups = [r for r in usable if len(r["members"]) > 1 and r["qty"] > 1 and r["load_type"] != "spare"]
    lines, out_rows, by_panel = [], [], OrderedDict((p, []) for p in panels)
    if standby:
        known = {r["tag"]: r["qty"] for r in groups}
        for k, v in standby.items():
            if k not in known:
                return res.invalid(f"standby: {k} is not a tag group of this panel (groups: {', '.join(known) or 'none'})")
            if v >= known[k]:
                return res.invalid(f"standby: {k} has {known[k]} units — standby must be below that (got {v:g})")
    for r in usable:
        sb = min(int(standby_per_group), r["qty"] - 1) if (standby_per_group is not None and r in groups) else 0
        if standby and r["tag"] in standby:              # the designer's reading per group wins (R-LL-08)
            sb = int(standby[r["tag"]])
        line = _line(r, sb, default_cable_m)
        out_rows.append({**{k: r[k] for k in ("tag", "panel", "item", "kw", "qty", "phases", "voltage_v", "load_type",
                                              "client_flc_a", "client_mpcb", "client_range_min", "client_range_max",
                                              "client_device", "source")},
                         "starter": line.split()[2], "standby": sb, "line": line,
                         **{k: r.get(k) for k in ("pdf", "pdf_item", "pdf_tag")}})
        by_panel.setdefault(r["panel"], []).append(f"{line}  # {r['source']}: {r['item']}")
        lines.append(line)

    # ---- checks
    by_rule: dict[str, list[str]] = OrderedDict()
    for i in issues:
        by_rule.setdefault(i["rule"], []).append(i["msg"])

    def report(rule, requirement, ok_text, verdict_if_issues=WARN, src_txt=src):
        if rule in by_rule:
            res.add(rule, requirement, "; ".join(by_rule[rule]), verdict_if_issues, src_txt)
        elif ok_text is not None:
            res.add(rule, requirement, ok_text, PASS, src_txt)

    report("R-LL-01", "every row read from the client's Word table (SHA-256 checked)",
           f"{len(usable)} row(s), each cited as table/row")
    report("R-LL-02", "panel from the document's 'Panel Total' rows", None)
    if "R-LL-02" not in by_rule:
        res.add("R-LL-02", "panel from the document's 'Panel Total' rows (our reading of the layout)",
                ", ".join(f"{p}: {sum(1 for r in usable if r['panel'] == p)} row(s)" for p in panels), INFO, src)
    report("R-LL-03", "starter and quantity from the Req columns, agreeing with the section", "yes")
    report("R-LL-04", "load type from the item wording", "all rows are motors", WARN)
    report("R-LL-05", "phases / voltage from 'Operating Voltage'", None)
    if "R-LL-05" not in by_rule:
        sp = [r["tag"] for r in usable if r["phases"] == 1]
        res.add("R-LL-05", "phases / voltage from 'Operating Voltage'",
                f"{len(sp)} single-phase row(s) written ph=1 v=230" + (f": {', '.join(sp)}" if sp else ""), INFO, src)
    res.add("R-LL-06", "client Amps / MPCB range kept for comparison only",
            "never written as flc= (formula values, not nameplates)", INFO)
    if default_cable_m is not None:
        res.add("R-LL-07", "cable length from the client",
                f"none given by {client}: cable={_g(default_cable_m)} m on all {len(usable)} line(s) is the user's value", WARN)
    else:
        res.add("R-LL-07", "cable length from the client",
                f"none given by {client} and none typed: no cable= (the panel leaves cables unsized and drive lines open)", INFO)
    if groups:
        names = ", ".join(f"{r['tag']} ({r['qty']})" for r in groups)
        set_ = {r["tag"]: int(standby[r["tag"]]) for r in groups if standby and r["tag"] in standby}
        open_ = [r for r in groups if r["tag"] not in set_]
        if set_:
            res.add("R-LL-08", "duty / standby (designer's reading per group)",
                    ", ".join(f"{t}: {n} standby" for t, n in set_.items()) + f" (confirm with {client})", WARN)
        if standby_per_group is None and open_:
            res.add("R-LL-08", "duty / standby", f"{client} gives totals only: {len(open_)} tag group(s) shown all running "
                                                 f"(confirm with {client}; set standby units per group on the Power tab): "
                                                 + ", ".join(f"{r['tag']} ({r['qty']})" for r in open_), WARN)
        elif standby_per_group is not None:
            res.add("R-LL-08", "duty / standby", f"user's reading: standby={int(standby_per_group)} written for "
                                                 f"{len(groups)} group(s) (confirm with {client}): {names}", WARN)
    else:
        res.add("R-LL-08", "duty / standby", "no tag groups among these rows", INFO)
    report("R-LL-09", "tags unique", "yes")
    report("R-LL-10", "Instrument ID matches Group Marking", "yes")
    report("R-LL-11", "row arithmetic (Total KW, Total Qty, tag count)", "holds")
    sel_totals = [t for t in doc["totals"] if t["panel"] in panels]
    if tag is None:
        report("R-LL-12", "panel total rows equal the sum of their rows",
               "; ".join(f"{t['panel']} {t['starter']} {_g(t['stated'])}" for t in sel_totals))
    report("R-LL-13", "cells read without repair", "no repair needed")
    report("R-LL-14", "client current inside client MPCB range", "yes")
    report("R-LL-15", "agrees with the client's equipment PDF", "every row and panel total agrees",
           src_txt=equip)

    def count(rule):
        return sum(1 for i in issues if i["rule"] == rule and i["uid"] is not None)

    if tag is not None:
        if not out_rows:
            return res.refuse("R-LL-03", "row usable", "; ".join(i["msg"] for i in issues), src)
        o = out_rows[0]
        res.value = {k: o[k] for k in ("panel", "kw", "starter", "qty", "standby", "phases", "voltage_v", "load_type",
                                       "client_flc_a", "client_mpcb", "client_range_min", "client_range_max",
                                       "client_device", "source", "line")}
        res.value["pdf"] = o["pdf"]
    else:
        def n(starter):
            return sum(1 for o in out_rows if o["starter"] == starter)

        def units(starter):
            return sum(o["qty"] for o in out_rows if o["starter"] == starter)

        res.value = {
            "n_rows": len(out_rows), "n_units": sum(o["qty"] for o in out_rows),
            "n_dol": n("DOL"), "n_vfd": n("VFD"), "n_ss": n("SS"), "n_heater": n("HEATER"),
            "n_spare": sum(1 for o in out_rows if o["load_type"] == "spare"),
            "n_single_phase": sum(1 for o in out_rows if o["phases"] == 1),
            "units_vfd": units("VFD"), "units_dol": units("DOL"), "units_ss": units("SS"),
            "n_standby": sum(o["standby"] for o in out_rows),
            "n_duplicate_tags": count("R-LL-09"), "n_tag_mismatch": count("R-LL-10"), "n_repairs": count("R-LL-13"),
            "n_flc_outside_range": count("R-LL-14"),
            "n_pdf_differences": sum(1 for i in issues if i["rule"] == "R-LL-15"),
            "n_total_mismatch": sum(1 for t in sel_totals if t["mismatch"]),
            "load_list": "\n".join(f"# {p} panel — {src} (Word load list)\n" + "\n".join(ls)
                                   for p, ls in by_panel.items() if ls),
            "load_lists": {p: "\n".join(ls) for p, ls in by_panel.items()},
            "rows": out_rows, "totals": sel_totals,
            "groups": [{"tag": r["tag"], "panel": r["panel"], "qty": r["qty"], "kw": r["kw"],
                        "standby": next((o["standby"] for o in out_rows if o["tag"] == r["tag"]), 0),
                        "set": bool(standby and r["tag"] in standby)} for r in groups],
        }
    res.basis = "client document"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
