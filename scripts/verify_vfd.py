"""G6 verification for vfd — writes components/vfd/VERIFY.md.

1. Independent re-extraction from the PM240-2 manual (pdfplumber), compared with the data files:
   module data (text rows of Tables 6-15 … 6-28), derating (Tables 6-37 … 6-40, cells),
   line / output reactor assignment (Tables 8-4, 8-11, 8-15, cells), cable lengths (Tables 4-1 … 4-3, text).
2. WNS2503: every VFD feeder through v2 motor_flc → vfd, at 35 °C (air-conditioned panel) and
   55 °C (fans, 50 °C site + 5 K), ECI rule "line reactor up to 15 kW", cable length from the load list.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from components.motor_flc.select import select as flc  # noqa: E402
from components.vfd.select import _derating, _lengths, _modules, _protection, _reactors, _stem, select as vfd  # noqa: E402
from core.provenance import SOURCES  # noqa: E402

V1_JSON = Path("/Users/deepak/Documents/panel-selector/projects/WNS2503/out/WNS2503_layer0.json")
NUM = r"(\d+(?:\.\d+)?)"
LABELS = {"Article No. without filter": "order_no", "Article No. with filter": "order_no_c2",
          "LO base load power": "lo_kw", "LO base load input current": "lo_in", "LO base load output current": "lo_out",
          "HO base load power": "ho_kw", "HO base load input current": "ho_in", "HO base load output current": "ho_out",
          "Power loss": "loss_w", "Required cooling air flow": "air_ls"}


def module_data(pdf) -> dict[str, dict]:
    out = {}
    for page in range(99, 106):
        lines = (pdf.pages[page - 1].extract_text() or "").splitlines()
        block: dict[str, list] = {}

        def flush():
            for i, o in enumerate(block.get("order_no", [])):
                rec = {k: v[i] for k, v in block.items() if i < len(v)}
                rec["page"] = page
                out[o] = rec

        for line in lines:
            if line.startswith("Table 6-"):
                flush()
                block = {}
            for label, key in LABELS.items():
                if label == "Power loss" and line.startswith("Power loss without filter "):
                    rest = line[len("Power loss without filter"):]
                elif line.startswith(label + " ") and not (label == "Power loss" and "filter" in line):
                    rest = line[len(label):]
                else:
                    continue
                if key.startswith("order_no"):
                    block[key] = re.findall(r"6SL3210-\S+", rest)
                else:
                    vals = [float(x) for x in re.findall(NUM, rest)]
                    if key == "loss_w":
                        vals = [round(v * 1000) for v in vals]       # printed in kW
                    block[key] = vals
            if line.startswith("Fuse according to IEC"):
                block["fuse"] = re.findall(r"(3NA\d{4}) \((\d+) A\)", line)
        flush()
    for rec in out.values():
        if "fuse" in rec:
            rec["fuse"], rec["fuse_a"] = rec["fuse"][0], float(rec["fuse"][1])
    return out


def cells(pdf, page):
    rows = []
    for t in pdf.pages[page - 1].extract_tables():
        rows += t
    return rows


def derating(pdf) -> dict[tuple, dict]:
    out = {}
    for page, group in ((118, "FSD-FSF"), (119, "FSA-FSC")):
        duty = None
        for r in cells(pdf, page):
            if r[1] and "loading to" in str(r[1]):
                duty = "LO" if r[1].strip().endswith("LO") else "HO"
            if r[0] == "1000" and duty:
                vals, last = {}, None
                for t, v in zip(range(20, 65, 5), r[1:]):
                    last = float(v) if v not in (None, "") else last
                    vals[t] = last
                out[(group, duty)] = vals
    return out


def reactors(pdf) -> dict[tuple, str]:
    out = {}
    for page, kind in ((146, "line"), (163, "output"), (165, "output")):
        last = None
        for r in cells(pdf, page):
            if not r or not r[0]:
                continue
            if kind == "line" and str(r[0]).startswith("6SL3203") and len(r) == 5 and r[1]:
                for mod in re.findall(r"6SL321[0.]?-1PE\d\d-\d", r[1].replace(" ", "")):
                    out[(kind, mod.replace("6SL321.", "6SL3210"))] = r[0]
            if kind == "output" and len(r) == 4 and r[1] and "1PE" in r[1]:
                art = r[3] or last
                last = art
                for mod in re.findall(r"6SL321[0.]?-1PE\d\d-\d", r[1].replace(" ", "")):
                    out[(kind, mod.replace("6SL321.", "6SL3210"))] = art
    return out


def protection_cells() -> list[tuple]:
    """(module stem, type, article, max_a, icc_ka, phased_out) from the table cells of pp. 5, 11, 14."""
    out = []
    with pdfplumber.open(SOURCES / _protection()["reference"]["file"]) as pdf:
        for page, kind in ((5, "fuse"), (11, "msp"), (14, "breaker")):
            mod, amps = None, None
            for t in pdf.pages[page - 1].extract_tables():
                for r in t:
                    cells = [c for c in r if c not in (None, "")]
                    text = " ".join(str(c) for c in r if c)
                    m = re.search(r"6SL3210-1PE\d\d-\d", text.replace(" ", ""))
                    if m:
                        mod = m.group(0)
                    a = re.search(r"(\d+) A\b", text)
                    if a:
                        amps = float(a.group(1))
                    for dev in re.finditer(r"(3NA\d{4}|3RV\d{4}-\w{3}[.…]*|3VA\d{4}-\w+[.…]*|3VL\d{4}-\w+[.…]*)"
                                           r"\s*(1\)|¹⁾)?\s*(\d+) kA", text):
                        if mod:
                            out.append((mod, kind, dev.group(1), amps, float(dev.group(3)), bool(dev.group(2))))
    return out


def main():
    out = [f"# VFD — G6 verification ({date.today().isoformat()})", "", "Generated by `scripts/verify_vfd.py`.", ""]
    with pdfplumber.open(SOURCES / _modules()["reference"]["file"]) as pdf:
        pdf_mod, pdf_der, pdf_rx = module_data(pdf), derating(pdf), reactors(pdf)
        t62 = pdf.pages[61].extract_text() + pdf.pages[62].extract_text()

    diffs, n = [], 0
    for m in _modules()["rows"]:
        p = pdf_mod.get(m["order_no"])
        if not p:
            diffs.append(f"{m['order_no']} not found in the PDF")
            continue
        for k in ("order_no_c2", "lo_kw", "lo_in", "lo_out", "ho_kw", "ho_in", "ho_out", "fuse", "fuse_a", "loss_w",
                  "air_ls", "page"):
            n += 1
            a, b = m[k], p.get(k)
            if (float(a) != float(b)) if isinstance(a, (int, float)) and b is not None else a != b:
                diffs.append(f"{m['order_no']} {k}: file {a} / PDF {b}")
    out += ["## 1. Module data vs the PDF (Tables 6-15 … 6-28, text rows)", "",
            f"- modules: {len(_modules()['rows'])}; values compared: {n}; mismatches: **{len(diffs)}**"
            + "".join(f"\n  - {d}" for d in diffs), ""]

    dd = []
    for r in _derating()["rows"]:
        p = pdf_der.get((r["group"], r["duty"]))
        mine = {int(k): float(v) for k, v in r["pct"].items()}
        if p != mine:
            dd.append(f"{r['group']} {r['duty']}: file {mine} / PDF {p}")
    out += ["## 2. Derating ≤ 1000 m (Tables 6-37 … 6-40, cells; merged 100 % filled forward)", "",
            f"- rows: {len(_derating()['rows'])}; mismatches: **{len(dd)}**" + "".join(f"\n  - {d}" for d in dd), ""]

    rd = []
    for r in _reactors()["rows"]:
        p = pdf_rx.get((r["kind"], r["module"]))
        if p != r["article"]:
            rd.append(f"{r['kind']} {r['module']}: file {r['article']} / PDF {p}")
    extra = [k for k in pdf_rx if k[1] in {_stem(m["order_no"]) for m in _modules()["rows"]}
             and not any(r["kind"] == k[0] and r["module"] == k[1] for r in _reactors()["rows"])]
    out += ["## 3. Reactor assignment (Tables 8-4, 8-11, 8-15, cells)", "",
            f"- assignments: {len(_reactors()['rows'])}; mismatches: **{len(rd)}**; in PDF but missing: {extra or 'none'}"
            + "".join(f"\n  - {d}" for d in rd), ""]

    cells_ = protection_cells()
    norm = lambda a: re.sub(r"[.…]+$", "", a)
    mine = {(r["module"], r["type"], norm(r["article"]), float(r["max_a"]), float(r["icc_ka"]), r["phased_out"])
            for r in _protection()["rows"]}
    theirs = {(m, k, norm(a), x, i, p) for m, k, a, x, i, p in cells_}
    missing, extra_p = sorted(mine - theirs), sorted(t for t in theirs - mine if t[0] in {r["module"] for r in _protection()["rows"]})
    out += ["## 3b. Protective devices (Protective Devices PM240-2 07/2021, pp. 5, 11, 14, cells)", "",
            f"- rows in data file: {len(mine)}; rows read from the PDF for these modules: {len(theirs)}; "
            f"in file but not matched in PDF: **{len(missing)}**; in PDF but not in file: **{len(extra_p)}**"
            + "".join(f"\n  - file only: {x}" for x in missing) + "".join(f"\n  - PDF only: {x}" for x in extra_p), ""]

    # cable lengths: check every value appears in the 400 V row of its table
    rows400 = re.findall(r"^400 V (.+)$", t62, flags=re.M)
    cd = []
    table_of = {"FSA-FSC": 0, "FSD-FSE": 1, "FSF": 2}
    for r in _lengths()["rows"]:
        line = rows400[table_of[r["group"]]] if len(rows400) > table_of[r["group"]] else ""
        notes = re.findall(r"(\d+) m for voltages in the range (\d+) V (?:\.\.\.|…) (\d+) V", t62)
        ok = f"{r['max_m']} m" in line or any(int(m_) == r["max_m"] and int(lo) == r["v_min"] for m_, lo, _ in notes)
        if not ok:
            cd.append(f"{r['group']} {r['filter']} {'shielded' if r['shielded'] else 'unshielded'} "
                      f"{r['reactors']} reactor(s) {r['max_m']} m not found")
    out += ["## 4. Cable lengths (Tables 4-1 … 4-3, 400 V rows and footnotes)", "",
            f"- rows: {len(_lengths()['rows'])}; values not found in the PDF text: **{len(cd)}**"
            + "".join(f"\n  - {d}" for d in cd),
            "- column assignment (which value belongs to which filter / reactor / cable combination) was checked "
            "against the rendered page image of p. 62 (Table 4-1, 4-2) and p. 63 (Table 4-3).", ""]

    if V1_JSON.exists():
        feeders = [f for f in json.loads(V1_JSON.read_text())["feeders"] if f.get("starter") == "VFD"]
        lines, stats = [], Counter()
        for f in feeders:
            r1 = flc(kw=f["kw"], phases=f.get("phases") or 3, voltage_v=f.get("voltage") or 400)
            if r1.status in ("cannot_select", "invalid"):
                stats["FLC not available"] += 1
                continue
            cells_ = []
            for t in (35, 55):
                r = vfd(kw=f["kw"], flc_a=r1.value["flc_a"], flc_basis=r1.basis, ambient_c=t,
                        cable_m=f.get("cable_length_m") or 50, fault_ka=50, client_line_reactor_up_to_kw=15)
                stats[f"{t} °C {r.status}"] += 1
                v = r.value
                cells_.append(f"{v.get('power_module', '—')} {v.get('rating', '')}"
                              + (f" + LR {v['line_reactor']}" if v.get("line_reactor") else "")
                              + (" ⚠ upsized" if "R-VFD-04" in r.warnings else ""))
            lines.append(f"| {f['id']} | {', '.join(f.get('tags', [])[:2])} | {f['kw']:g} | {r1.value['flc_a']:g} | "
                         f"{cells_[0]} | {cells_[1]} |")
        out += [f"## 5. WNS2503 VFD feeders ({len(feeders)})", "",
                "FLC from component 1 (guide values → R-VFD-13 warning on every line), fault level 50 kA, ECI rule "
                "line reactor ≤ 15 kW, cable length from the load list.", "",
                "| " + " · ".join(f"{k}: {v}" for k, v in sorted(stats.items())) + " |", "|---|", "",
                "| Feeder | Tags | kW | FLC A | Panel at 35 °C (air-conditioned) | Panel at 55 °C (fans, 50 °C site) |",
                "|---|---|---|---|---|---|", *lines, ""]
    (ROOT / "components" / "vfd" / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
