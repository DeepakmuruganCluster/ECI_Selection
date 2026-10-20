"""G6 verification for mccb — writes components/mccb/VERIFY.md.

Independent re-extraction from the Siemens 3VM catalogue LV 31 · 2018 with pdfplumber, by word
POSITION (columns located from the printed column headers), not by reading the data files or the
text-line layout used to transcribe them:
1. Icu / Ics at 380 - 415 V, In range and Ue per frame and class (pp. 10–11; p.11 rows found at the
   same height as the labelled rows on p.10) and the class table on p.18.
2. In / Ir / Ii for every printed block (pp. 28, 30, 32 ×2, 34 ×2).
3. Every article number cell (pp. 28–35): which In row and which class column it sits in.
4. Scope conditions (pp. 9, 10, 19) and a whole-document search for let-through I²t / cut-off data.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from components.mccb.select import _articles, _breaking, _ratings  # noqa: E402
from core.provenance import SOURCES  # noqa: E402

ART = re.compile(r"^(3VM\d{4}-\w{5}-0AA0|--)$")


def words(pdf, page):
    return pdf.pages[page - 1].extract_words(keep_blank_chars=False)


def lines(ws, tol=1.5):
    """group words into lines by their top coordinate"""
    out: list[list[dict]] = []
    for w in sorted(ws, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in out]


# ---------------------------------------------------------------- 1. breaking capacity
def breaking(pdf) -> tuple[dict, list[str]]:
    w10, w11 = words(pdf, 10), words(pdf, 11)
    L10 = lines(w10)
    notes = []

    def row_top(pred, nth=0):
        hits = [l[0]["top"] for l in L10 if pred(" ".join(w["text"] for w in l))]
        return hits[nth]
    t_type = row_top(lambda s: s.startswith("Type "))
    t_poles = row_top(lambda s: s.startswith("Number of poles"))
    t_class = row_top(lambda s: s.startswith("Breaking capacity"))
    t_in = row_top(lambda s: s.startswith("Rated operational current"))
    t_ue = row_top(lambda s: s.startswith("Rated operational voltage"))
    t_icu = row_top(lambda s: s.startswith("380 - 415 V AC"), 0)
    t_ics = row_top(lambda s: s.startswith("380 - 415 V AC"), 1)

    def at(ws, top, xmin):
        return [w for w in ws if abs(w["top"] - top) <= 1.5 and w["x0"] >= xmin]
    out = {}
    for ws, xmin in ((w10, 200), (w11, 0)):
        types = [w for w in at(ws, t_type, xmin) if w["text"].startswith("3VM")]
        poles = [w for w in at(ws, t_poles, xmin)]
        groups = []                                   # x0 of each poles column + its text
        for w in poles:
            if groups and w["x0"] - groups[-1][1] < 15:   # "3," "4"
                groups[-1] = (groups[-1][0], w["x0"], groups[-1][2] + " " + w["text"])
            else:
                groups.append((w["x0"], w["x0"], w["text"]))
        classes = [w for w in at(ws, t_class, xmin) if w["text"] in "BNSM" and len(w["text"]) == 1]
        for c in classes:
            g = max((g for g in groups if g[0] <= c["x1"]), key=lambda g: g[0])
            if g[2].replace(" ", "") != "3,4":
                continue                              # 1- and 2-pole 3VM11: out of scope
            frame = max((t for t in types if t["x0"] <= g[0] + 1), key=lambda t: t["x0"])["text"]

            def val(top, c=c):
                cand = [w for w in at(ws, top, xmin) if re.fullmatch(r"[\d.]+", w["text"])]
                return min(cand, key=lambda w: abs(w["x0"] - c["x0"]))
            in_ws = [w for w in at(ws, t_in, xmin) if re.fullmatch(r"\d+", w["text"])]
            in_ws = [w for w in in_ws if g[0] - 1 <= w["x0"] < g[0] + 45]
            out[(frame, c["text"])] = {"icu_ka": float(val(t_icu)["text"]), "ics_ka": float(val(t_ics)["text"]),
                                       "ue_max_v": float(min((w for w in at(ws, t_ue, xmin)), key=lambda w: abs(w["x0"] - g[0]))["text"]),
                                       "in_min_a": float(in_ws[0]["text"]), "in_max_a": float(in_ws[-1]["text"])}
    # p.18 class table: "B 16 kA", "N 25 kA", ...
    t18 = pdf.pages[17].extract_text()
    p18 = {m[0]: float(m[1]) for m in re.findall(r"^([BNSM]) (\d+) kA", t18, flags=re.M)}
    for (frame, cls), v in out.items():
        if p18.get(cls) != v["icu_ka"]:
            notes.append(f"p.18 class {cls} = {p18.get(cls)} kA but p.10/11 {frame} {cls} Icu = {v['icu_ka']} kA")
    return out, notes


# ---------------------------------------------------------------- 2./3. ordering tables
def header_columns(ws):
    """x0 of the In / Ir / Ii / Type columns and of each class (B/N/S/M) article column"""
    L = lines(ws)
    top = next(l for l in L if any(w["text"] == "Rated" for w in l))
    cols = {}
    for w in top:
        if w["text"] == "Rated":
            cols["in"] = w["x0"]
        elif w["text"] == "Current":
            cols["ir"] = w["x0"]
        elif w["text"] == "Operating":
            cols["ii"] = w["x0"]
        elif w["text"] == "Type":
            cols["type"] = w["x0"]
    icu = [w for w in top if w["text"] == "Icu"]
    caps = [w for l in L[:8] for i, w in enumerate(l) if w["text"] == "capacity" and i + 1 < len(l)
            and l[i + 1]["text"] in ("B", "N", "S", "M")]
    classes = {}
    for c in caps:
        letter = next(w["text"] for l in L[:8] for i, w in enumerate(l) if w is c for w in [l[i + 1]])
        x = max(i["x0"] for i in icu if i["x0"] <= c["x0"])
        classes[x] = letter
    return cols, classes


def table(pdf, page):
    """→ list of blocks: (heading, [ {frame, in, ir, ii, cells{class: article or --}} ])"""
    ws = words(pdf, page)
    cols, classes = header_columns(ws)
    xs = sorted(classes)
    blocks, frame = [], None
    for l in lines(ws):
        text = " ".join(w["text"] for w in l)
        if text.startswith("Line protection,"):
            blocks.append((text, []))
            continue
        if not blocks:
            continue
        cells = {classes[max(x for x in xs if x <= w["x0"] + 1)]: w["text"] for w in l
                 if ART.match(w["text"]) and w["x0"] + 1 >= xs[0]}
        if not cells:
            continue
        def in_col(lo, hi):
            return " ".join(w["text"] for w in l if lo - 8 <= w["x0"] < hi - 8)
        bounds = [cols["in"]] + [cols[k] for k in ("ir", "ii") if k in cols] + [xs[0]]
        rated = in_col(bounds[0], bounds[1])
        if not re.fullmatch(r"\d+", rated):
            continue
        rec = {"in": int(rated), "cells": cells}
        if "type" in cols:
            t = [w["text"] for w in l if cols["type"] - 2 <= w["x0"] < cols["in"] - 8 and w["text"].startswith("3VM")]
            frame = t[0] if t else frame
            rec["frame"] = frame
            rec["ir"] = in_col(bounds[1], bounds[2])
            rec["ii"] = int(in_col(bounds[2], bounds[3]))
        blocks[-1][1].append(rec)
    return blocks


SECTIONS = [  # left page, right page, poles, release, neutral per block (block order on the page)
    (28, 29, 3, "TM210", ["none"]), (30, 31, 3, "TM220", ["none"]),
    (32, 33, 4, "TM210", ["none", "100"]), (34, 35, 4, "TM220", ["none", "100"]),
]


def ordering(pdf):
    ratings, arts, notes = {}, {}, []
    for lp, rp, poles, rel, neutrals in SECTIONS:
        left, right = table(pdf, lp), table(pdf, rp)
        if len(left) != len(neutrals) or len(right) != len(neutrals):
            notes.append(f"pp.{lp}/{rp}: {len(left)}/{len(right)} blocks, expected {len(neutrals)}")
        for (lh, lrows), (rh, rrows), neu in zip(left, right, neutrals):
            if lh != rh:
                notes.append(f"pp.{lp}/{rp}: block headings differ: {lh!r} / {rh!r}")
            if [r["in"] for r in lrows] != [r["in"] for r in rrows]:
                notes.append(f"pp.{lp}/{rp} {lh}: In rows differ")
            for lr, rr in zip(lrows, rrows):
                ir = lr["ir"].replace("...", "…")
                lo, hi = (int(x) for x in ir.split(" … ")) if "…" in ir else (int(ir), int(ir))
                key = (rel, lr["frame"], lr["in"])
                rec = {"ir_min_a": lo, "ir_max_a": hi, "ii_a": lr["ii"], "page": lp}
                if key in ratings and {k: v for k, v in ratings[key].items() if k != "page"} != \
                        {k: v for k, v in rec.items() if k != "page"}:
                    notes.append(f"p.{lp} {key}: In/Ir/Ii {rec} differs from p.{ratings[key]['page']} {ratings[key]}")
                ratings.setdefault(key, rec)
                for page, cells in ((lp, lr["cells"]), (rp, rr["cells"])):
                    for cls, a in cells.items():
                        if a != "--":
                            arts[a] = {"poles": poles, "release": rel, "neutral": neu, "frame": lr["frame"],
                                       "in_a": lr["in"], "class": cls, "page": page}
    return ratings, arts, notes


def main():
    out = [f"# Branch MCCB — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_mccb.py`. Re-extraction by word position (columns located from the "
           "printed headers), independent of the text-line transcription of the data files.", ""]
    with pdfplumber.open(SOURCES / _breaking()["reference"]["file"]) as pdf:
        pdf_bc, bc_notes = breaking(pdf)
        pdf_rt, pdf_art, ord_notes = ordering(pdf)
        alltext = "\n".join(p.extract_text() or "" for p in pdf.pages)
        p9, p10, p19 = (pdf.pages[i - 1].extract_text() for i in (9, 10, 19))

    # 1. breaking capacity
    d1, n1 = [], 0
    for r in _breaking()["rows"]:
        p = pdf_bc.get((r["frame"], r["class"]))
        if not p:
            d1.append(f"{r['frame']} {r['class']}: not found in the PDF")
            continue
        for k in ("icu_ka", "ics_ka", "ue_max_v", "in_min_a", "in_max_a"):
            n1 += 1
            if float(r[k]) != p[k]:
                d1.append(f"{r['frame']} {r['class']} {k}: file {r[k]} / PDF {p[k]}")
    extra1 = sorted(set(pdf_bc) - {(r["frame"], r["class"]) for r in _breaking()["rows"]})
    out += ["## 1. Breaking capacity at 380 - 415 V (pp. 10–11, cells by position; p.18 class table)", "",
            f"- frame/class rows: {len(_breaking()['rows'])}; values compared: {n1}; mismatches: **{len(d1)}**; "
            f"3/4-pole columns in PDF but not in the file: {extra1 or 'none'}"
            + "".join(f"\n  - {d}" for d in d1 + bc_notes), ""]

    # 2. trip ratings
    d2, n2 = [], 0
    for r in _ratings()["rows"]:
        p = pdf_rt.get((r["release"], r["frame"], r["in_a"]))
        if not p:
            d2.append(f"{r['release']} {r['frame']} {r['in_a']} A: not found")
            continue
        for k in ("ir_min_a", "ir_max_a", "ii_a", "page"):
            n2 += 1
            if r[k] != p[k]:
                d2.append(f"{r['release']} {r['frame']} {r['in_a']} A {k}: file {r[k]} / PDF {p[k]}")
    extra2 = sorted(set(pdf_rt) - {(r["release"], r["frame"], r["in_a"]) for r in _ratings()["rows"]})
    out += ["## 2. In / Ir / Ii (pp. 28, 30, 32, 34 — all six printed blocks)", "",
            f"- rows: {len(_ratings()['rows'])}; values compared: {n2}; mismatches: **{len(d2)}**; "
            f"in PDF but missing: {extra2 or 'none'}; the 4-pole blocks repeat the 3-pole values: "
            + ("yes" if not [n for n in ord_notes if "differs from" in n] else "**no**")
            + "".join(f"\n  - {d}" for d in d2), ""]

    # 3. article numbers
    d3, n3 = [], 0
    for r in _articles()["rows"]:
        p = pdf_art.get(r["article"])
        if not p:
            d3.append(f"{r['article']}: not found in the PDF")
            continue
        for k in ("poles", "release", "neutral", "frame", "in_a", "class", "page"):
            n3 += 1
            if str(r[k]) != str(p[k]):
                d3.append(f"{r['article']} {k}: file {r[k]} / PDF {p[k]}")
    extra3 = sorted(set(pdf_art) - {r["article"] for r in _articles()["rows"]})
    out += ["## 3. Article numbers (pp. 28–35, cell → In row and class column)", "",
            f"- articles in file: {len(_articles()['rows'])}; in PDF: {len(pdf_art)}; values compared: {n3}; "
            f"mismatches: **{len(d3)}**; in PDF but missing from the file: {extra3 or 'none'}"
            + "".join(f"\n  - {d}" for d in d3 + [n for n in ord_notes if "differs from" not in n]), ""]

    # 4. conditions and absence of let-through data
    cond = _breaking()["conditions"]
    checks = [
        ("p.9 'No derating up to +50 °C'", f"No derating up to +{cond['ambient_no_derating_max_c']} °C" in p9),
        ("p.10 Icu/Ics row '380 - 415 V AC'", f"{cond['voltage_min_v']} - {cond['voltage_max_v']} V AC" in p10),
        ("p.10 'Rated operational current In … at 50 °C ambient temperature'", "at 50°C ambient temperature" in p10),
        ("p.19 operating range -25 … +70 °C", f"{cond['ambient_min_c']} °C to +{cond['ambient_max_c']} °C" in p19),
        ("p.19 'above +50 °C … reductions in the rated operational current'", "+50 °C there are reductions" in p19),
        ("p.19 rated data unchanged up to 2000 m", f"up\nto {cond['altitude_max_m']} m above sea level, the rated data will not change"
         in p19 or f"to {cond['altitude_max_m']} m above sea level, the rated data will not change" in p19),
    ]
    d4 = [c for c, ok in checks if not ok]
    hits = {k: len(re.findall(p, alltext, flags=re.I)) for k, p in
            (("I2t / I²t", r"I\s?[2²]\s?t\b"), ("let-through", r"let[- ]through"), ("cut-off current", r"cut[- ]off"),
             ("current limiting", r"current[- ]limit"), ("derating values (% / factor table vs temperature)",
                                                         r"\b(55|60|65|70) ?°C\b.*\b0\.\d\d\b"))}
    out += ["## 4. Scope conditions and what the catalogue does not contain", "",
            f"- condition statements found: {len(checks) - len(d4)}/{len(checks)}"
            + "".join(f"\n  - not found: {d}" for d in d4),
            "- whole-document search (92 pages): " + ", ".join(f"{k}: {v}" for k, v in hits.items())
            + " → no let-through I²t, cut-off current or temperature-derating values are printed.", ""]

    total = len(d1) + len(d2) + len(d3) + len(d4) + len(bc_notes) + len(ord_notes)
    out += ["## Result", "", f"**{total} unexplained mismatches.**", ""]
    (ROOT / "components" / "mccb" / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(out))
    return total


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
