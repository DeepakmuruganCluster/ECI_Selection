"""G6 verification for cable — writes components/cable/VERIFY.md.

1. Independent re-extraction from the maker PDFs, compared with every value in the data files:
   Polycab with pdfplumber table cells (ratings pp. 27/43/55/67 + product lists, R p.11, X p.10, SC p.9,
   factors p.87); KEI with pypdfium2 text (a different PDF engine from the one used to transcribe:
   ratings pp. 36/38/40/42, SC p.49; factors p.33 from pdfplumber cells).
2. Polycab vs KEI: same core count / size / installation — ratings, R, X, 1-s SC rating, temperature factors.
3. WNS2503: every motor feeder through v2 motor_flc → cable (sizes chosen; feeders motor_flc refuses are skipped).
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
import pypdfium2 as pdfium  # noqa: E402

from components.cable.select import _data, select as cable  # noqa: E402
from components.motor_flc.select import select as flc  # noqa: E402
from core.provenance import SOURCES, load_yaml  # noqa: E402
from core.data import data_file  # noqa: E402

HERE = ROOT / "components" / "cable"
V1_JSON = Path("/Users/deepak/Documents/panel-selector/projects/WNS2503/out/WNS2503_layer0.json")
NUM = r"\d+(?:\.\d+)?"
PC_PAGES = {"2": 27, "3": 43, "3.5": 55, "4": 67}
KEI_PAGES = {"2": 36, "3": 38, "3.5": 40, "4": 42}


def _f(s):
    return float(s) if s not in (None, "", "-", "---") else None


# ---------------------------------------------------------------- Polycab (pdfplumber cells)
def _cell_lines(page) -> list[str]:
    out = []
    for t in page.extract_tables():
        for row in t:
            out += [str(c) for c in row if c]
    return out


def polycab(pdf) -> dict:
    got = {"rating": {}, "product": set(), "r_ac90": {}, "x50": {}, "isc1": {}, "temp": {}}
    for cores, p in PC_PAGES.items():
        for line in _cell_lines(pdf.pages[p - 1]):
            m = re.fullmatch(rf"({NUM}) (\d+) (\d+) (\d+) (\S+)", line.strip())
            if m:
                got["rating"][(cores, int(m.group(1)))] = tuple(int(m.group(i)) for i in (2, 3, 4)) + (p,)
            m = re.match(r"LVIS\S+ ([\d.]+) ?x ?(\d+)\b", line.strip())
            if m and m.group(1) == cores:
                got["product"].add((cores, int(m.group(2))))
    # p.11 conductor table: size, 4 wire counts, DC Cu, DC Al, AC90 Cu, AC90 Al
    for line in _cell_lines(pdf.pages[10]):
        m = re.fullmatch(rf"({NUM})\*? (\S+) (\S+) (\S+) (\S+) ({NUM}) ({NUM}) ({NUM}) ({NUM})", line.strip())
        if m:
            got["r_ac90"][float(m.group(1))] = float(m.group(8))
    # p.10: second table (reactance) — size, 1C unarmoured, 1C armoured, multi core
    tables = pdf.pages[9].extract_tables()
    react = next(t for t in tables if t and t[0] and "Multi core" in [str(c) for c in t[0]])
    for row in react:
        m = re.fullmatch(rf"({NUM}) (\S+) (\S+) (\S+)", str(row[0] or "").strip())
        if m and _f(m.group(4)) is not None:
            got["x50"][float(m.group(1))] = float(m.group(4))
    # p.9: SC table — size, PVC Cu, PVC Al, XLPE Cu, XLPE Al
    sc = next(t for t in pdf.pages[8].extract_tables() if t and "PVC Insulated" in [str(c) for c in t[0]])
    for row in sc:
        m = re.fullmatch(rf"({NUM}) (\S+) (\S+) (\S+) (\S+)", str(row[0] or "").strip())
        if m:
            got["isc1"][float(m.group(1))] = _f(m.group(4))
    # p.87: three factor tables in order air, ground, duct
    for kind, t in zip(("air", "ground", "duct"), pdf.pages[86].extract_tables()):
        temps = [int(re.match(r"\d+", c).group()) for c in t[0][1:]]
        got["temp"][kind] = dict(zip(temps, [float(v) for v in t[1][1:]]))
    return got


# ---------------------------------------------------------------- KEI (pypdfium2 text)
def kei(doc) -> dict:
    """Ratings, R, X (pypdfium2 text of the rotated tables) and 1-s SC ratings (p.49)."""
    got = {"rating": {}, "isc1": {}, "temp": {}, "group": {}}
    for cores, p in KEI_PAGES.items():
        text = doc[p - 1].get_textpage().get_text_range()
        for line in text.splitlines():
            m = re.match(rf"\s*{re.escape(cores)}C x (\d+)(?:/\d+)? (.*)$", line)
            if not m:
                continue
            vals = m.group(2).split()
            if len(vals) < 17:
                continue        # unarmoured table on the same PDF page (no armour / strip-wire columns)
            got["rating"][(cores, int(m.group(1)))] = {
                "ground": int(vals[-3]), "duct": int(vals[-2]), "air": int(vals[-1]),
                "r_ac90": float(vals[-6]), "x50": float(vals[-5]), "page": p}
    flat = " ".join(doc[48].get_textpage().get_text_range().split())
    start = flat.index("Sq.mm COPPER")
    table = flat[start:flat.index("Compa", start)]
    for size, cu in re.findall(rf"(?<![\d.])(\d+) ({NUM}) {NUM} {NUM} {NUM} {NUM} {NUM}(?= |$)", table):
        if int(size) >= 4:
            got["isc1"].setdefault(float(size), float(cu))
    return got


def kei_factors(pdf, got) -> None:
    """KEI p.33 right half (upright tables, pdfplumber cells) and p.49 SC table (pypdfium2 text)."""
    pg = pdf.pages[32]
    for t in pg.crop((pg.width / 2, 0, pg.width, pg.height)).extract_tables():
        head = str(t[0][0])
        if head.startswith("Ground temperature"):
            got["temp"]["ground"] = got["temp"]["duct"] = {int(a): float(b) for a, b in zip(t[0][1:], t[1][1:])}
        elif head.startswith("Air temperature"):
            got["temp"]["air"] = {int(a): float(b) for a, b in zip(t[0][1:], t[1][1:])}
        elif head.startswith("No. of Cables"):
            for row in t[2:]:
                got["group"][int(row[0].split()[0])] = dict(zip(("touching", "150", "300", "450"), map(float, row[1:])))


def compare_polycab(pc) -> tuple[list[str], int]:
    diffs, n = [], 0
    for r in load_yaml(data_file("polycab_2xwy_ratings.yaml"))["rows"]:
        key = (r["cores"], r["size"])
        p = pc["rating"].get(key)
        n += 4
        if p is None:
            diffs.append(f"rating {key} not found in the PDF")
            continue
        if (r["ground"], r["duct"], r["air"], r["page"]) != p:
            diffs.append(f"rating {key}: file {(r['ground'], r['duct'], r['air'], r['page'])} / PDF {p}")
        n += 1
        if r["product"] != (key in pc["product"]):
            diffs.append(f"product {key}: file {r['product']} / PDF {key in pc['product']}")
    extra = [k for k in pc["rating"] if not any((r["cores"], r["size"]) == k for r in
                                                load_yaml(data_file("polycab_2xwy_ratings.yaml"))["rows"])]
    if extra:
        diffs.append(f"rating rows in the PDF but not in the file: {extra}")
    for r in load_yaml(data_file("polycab_conductor.yaml"))["rows"]:
        n += 1
        p = pc[r["qty"]].get(float(r["size"]))
        if p is None or abs(p - r["value"]) > 1e-9:
            diffs.append(f"{r['qty']} {r['size']} mm²: file {r['value']} / PDF {p}")
    for r in load_yaml(data_file("polycab_factors.yaml"))["rows"]:
        mine = {int(k): float(v) for k, v in r["factors"].items()}
        n += len(mine)
        if mine != pc["temp"][r["kind"]]:
            diffs.append(f"factors {r['kind']}: file {mine} / PDF {pc['temp'][r['kind']]}")
    return diffs, n


def compare_kei(k) -> tuple[list[str], int]:
    diffs, n = [], 0
    rows = load_yaml(data_file("kei_armoured_ratings.yaml"))["rows"]
    for r in rows:
        key = (r["cores"], r["size"])
        p = k["rating"].get(key)
        if p is None:
            diffs.append(f"rating {key} not found in the PDF text")
            continue
        for f in ("ground", "duct", "air", "r_ac90", "x50", "page"):
            n += 1
            if abs(float(p[f]) - float(r[f])) > 1e-9:
                diffs.append(f"{key} {f}: file {r[f]} / PDF {p[f]}")
    extra = [kk for kk in k["rating"] if not any((r["cores"], r["size"]) == kk for r in rows)]
    if extra:
        diffs.append(f"rating rows in the PDF but not in the file: {extra}")
    for r in load_yaml(data_file("kei_factors.yaml"))["rows"]:
        if r["kind"] in ("air", "ground", "duct"):
            mine = {int(t): float(v) for t, v in r["factors"].items()}
            n += len(mine)
            if mine != k["temp"][r["kind"]]:
                diffs.append(f"factors {r['kind']}: file {mine} / PDF {k['temp'][r['kind']]}")
        elif r["kind"] == "group_ground":
            mine = {str(t): float(v) for t, v in r["factors"].items()}
            n += len(mine)
            if mine != k["group"].get(r["cables"]):
                diffs.append(f"group {r['cables']}: file {mine} / PDF {k['group'].get(r['cables'])}")
        elif r["kind"] == "isc1":
            n += 1
            if k["isc1"].get(float(r["size"])) != float(r["value"]):
                diffs.append(f"isc1 {r['size']}: file {r['value']} / PDF {k['isc1'].get(float(r['size']))}")
    return diffs, n


def spread() -> list[str]:
    pc, ke = _data("polycab"), _data("kei")
    kr = {(r["cores"], r["size"]): r for r in ke["rows"]}
    rat_diff, n, worst = [], 0, {"r": (0, None), "x": (0, None), "isc1": (0, None)}
    for r in pc["rows"]:
        o = kr.get((r["cores"], r["size"]))
        if not o:
            continue
        for col in ("ground", "duct", "air"):
            n += 1
            if r[col] != o[col]:
                rat_diff.append(f"{r['cores']}C×{r['size']} {col}: Polycab {r[col]} / KEI {o[col]}")
        for col in worst:
            d = abs(r[col] - o[col]) / r[col] * 100
            if d > worst[col][0]:
                worst[col] = (d, f"{r['cores']}C×{r['size']}: Polycab {r[col]:g} / KEI {o[col]:g}")
    lines = [f"- current ratings (same core count, size, installation): {n} pairs compared, "
             f"**{len(rat_diff)} differ**" + "".join(f"\n  - {d}" for d in rat_diff)
             + ("" if rat_diff else " (Polycab states its tables follow IS 3961 (Part 6):2016)"),
             f"- AC resistance at 90 °C: largest difference {worst['r'][0]:.1f} % ({worst['r'][1]})",
             f"- reactance at 50 Hz: largest difference {worst['x'][0]:.1f} % ({worst['x'][1]})",
             f"- 1-second short-circuit rating: largest difference {worst['isc1'][0]:.1f} % ({worst['isc1'][1]})",
             "- temperature rating factors:", "",
             "| Table | °C | Polycab (p.87) | KEI (p.33) |", "|---|---|---|---|"]
    for kind in ("air", "ground"):
        a, b = pc["temp"][kind]["factors"], ke["temp"][kind]["factors"]
        for t in sorted(set(a) | set(b)):
            if a.get(t) != b.get(t):
                lines.append(f"| {kind} | {t} | {a.get(t, '—')} | {b.get(t, '—')} |")
    lines += ["", "- grouping: KEI tabulates buried-direct groups of 2 … 6 cables (p.33 Table 3); "
              "Polycab tabulates none, so with Polycab every parallel run or grouped cable is refused (R-CAB-06)."]
    return lines


def wns() -> list[str]:
    if not V1_JSON.exists():
        return ["WNS2503 load list not found."]
    feeders = json.loads(V1_JSON.read_text())["feeders"]
    stats, lines, skipped = Counter(), [], []
    for f in feeders:
        ph = f.get("phases") or 3
        r1 = flc(kw=f["kw"], phases=ph, voltage_v=f.get("voltage") or 400, load_type=f.get("load_type") or "motor")
        if r1.status in ("cannot_select", "invalid"):
            skipped.append(f"{f['id']} ({f['kw']:g} kW {ph}-ph: {r1.checks[-1].value})")
            continue
        ib = r1.value["flc_a"]
        vfd = f.get("starter") == "VFD"
        cells = []
        for make, t in (("polycab", 40), ("polycab", 50), ("kei", 50)):
            kw = dict(ib_a=ib, length_m=f.get("cable_length_m") or 50, voltage_v=f.get("voltage") or 400, phases=ph,
                      pf_run=0.85, installation="air", ambient_c=t, make=make)
            kw.update(overload_device=False) if vfd else kw.update(in_a=ib)
            if f.get("starter") == "DOL" and make == "polycab" and t == 50:
                kw.update(start_multiple=6, pf_start=0.3)
            r = cable(**kw)
            stats[f"{make} {t} °C {r.status}"] += 1
            v = r.value
            cells.append(f"{v['runs']}×{v['cores']}C×{v['size_mm2']} ({v['iz_a']:g} A, {v['vd_pct']:g} %"
                         + (f", start {v['vd_start_pct']:g} %" if v.get("vd_start_pct") is not None else "")
                         + f"; {v['bound_by']})" if v else f"— {r.checks[-1].rule}")
        lines.append(f"| {f['id']} | {f['kw']:g} | {ph} | {f.get('starter')} | {ib:g} | " + " | ".join(cells) + " |")
    return ["Assumptions for this run only (not defaults of the component): installed **in air**, single circuit "
            "(no grouping), cos φ 0.85 running, length from the load list (50 m for every feeder), "
            "In = FLC (overload relay set at FLC) for DOL / soft-starter feeders, overload_device = false for VFD "
            "feeders; DOL starting check at 6 × FLC, cos φ 0.3 in the Polycab 50 °C column; short-circuit "
            "withstand not checked (fault level from component 7 not available).", "",
            "| " + " · ".join(f"{k}: {v}" for k, v in sorted(stats.items())) + " |", "|---|", "",
            "| Feeder | kW | ph | Starter | FLC A | Polycab, air 40 °C | Polycab, air 50 °C (+ DOL start) | KEI, air 50 °C |",
            "|---|---|---|---|---|---|---|---|", *lines, "",
            f"Skipped (motor_flc refuses): {len(skipped)}" + "".join(f"\n- {s}" for s in skipped), ""]


def main():
    out = [f"# Cable — G6 verification ({date.today().isoformat()})", "", "Generated by `scripts/verify_cable.py`.", ""]
    with pdfplumber.open(SOURCES / _data("polycab")["reference"]["file"]) as pdf:
        pc = polycab(pdf)
    kei_file = SOURCES / _data("kei")["reference"]["file"]
    ke = kei(pdfium.PdfDocument(str(kei_file)))
    with pdfplumber.open(kei_file) as pdf:
        kei_factors(pdf, ke)
    d1, n1 = compare_polycab(pc)
    d2, n2 = compare_kei(ke)
    out += ["## 1. Polycab data vs the PDF (pdfplumber table cells)", "",
            f"- values compared: {n1}; mismatches: **{len(d1)}**" + "".join(f"\n  - {d}" for d in d1),
            "- catalogue observations (not used by the tool): p.43 prints the 3C×70 DC resistance as '0268' "
            "(0.268); p.65 (4-core strip-armoured 2XFY) prints aluminium DC resistances in the copper table; "
            "p.53 carries a stray e-mail line inside the table.", "",
            "## 2. KEI data vs the PDF (pypdfium2 text — a different PDF engine)", "",
            f"- values compared: {n2}; mismatches: **{len(d2)}**" + "".join(f"\n  - {d}" for d in d2),
            "- column assignment (ground / duct / air, R 90 °C, X) checked on the rendered page images "
            "of PDF pp. 36, 38, 40, 42 (left halves) and p.33 (right half).",
            "- the first runs reported 17 differences; all were checker errors, not data errors: (a) PDF pp. 36/38/40/42 "
            "also carry the UNARMOURED table, whose R at 90 °C is printed with 2 decimals (0.93 / 0.67) — the "
            "checker now takes only rows with the armour columns; (b) the p.49 short-circuit pattern matched "
            "numbers outside the table — it now reads only the table text. The data values were confirmed on the "
            "page images (e.g. p.38 3C×25: 0.931 Ω/km).", "",
            "## 3. Polycab vs KEI", "", *spread(), "",
            "## 4. WNS2503 motor feeders", "", *wns()]
    (HERE / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
