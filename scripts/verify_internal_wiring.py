"""G6 verification for internal_wiring — writes components/internal_wiring/VERIFY.md.

1. Independent re-extraction from the Lapp PDF with pdfplumber WORD POSITIONS (the data files were transcribed
   from pypdfium2 text read against the page images): each value is placed in its row by the y position of the
   row label and in its column by the x position of the column header, then compared with every value in the
   data files — Table 12-1 columns A and C (PDF p.1), footnote 3 factors (p.2), Tables 12-2 / 12-3 / 12-4 (p.3),
   Table 12-6 (p.4). A '-' in the PDF must be a missing value in the file, and the reverse.
2. WNS2503 examples: the largest drive feeder (37 kW, LO input 70 A, 3NA3830 gG fuse 100 A) and a 7.5 kW DOL
   (15.5 A, MPCB 13 … 16 A) at 55 °C and 35 °C inside the panel.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from components.internal_wiring.select import select  # noqa: E402
from core.provenance import SOURCES, check_reference, load_yaml  # noqa: E402
from core.data import data_file  # noqa: E402

HERE = ROOT / "components" / "internal_wiring"
NUM = re.compile(r"^\d+(?:\.\d+)?$")


def _words(page, x0, x1, y0=0, y1=1e9):
    """Main-size words only (superscript footnote marks are smaller than 5 pt)."""
    return [w for w in page.extract_words(extra_attrs=["size"])
            if w["size"] >= 5.5 and x0 <= w["x0"] < x1 and y0 <= w["top"] < y1]


def _grid(page, label_x, centres, y0, y1, x1=None):
    """{label: {column index: text}} — a value joins the row whose label is nearest in y (≤ 4 pt) and the
    column whose centre is nearest in x (≤ 12 pt)."""
    lo, hi = label_x
    xmax = x1 if x1 is not None else max(centres) + 20
    ws = _words(page, lo, xmax, y0, y1)
    labels = [w for w in ws if lo <= w["x0"] < hi and NUM.match(w["text"])]
    out = {float(w["text"]): {} for w in labels}
    for w in ws:
        if w in labels or not (NUM.match(w["text"]) or w["text"] == "-"):
            continue
        cx = (w["x0"] + w["x1"]) / 2
        ci = min(range(len(centres)), key=lambda i: abs(centres[i] - cx))
        lab = min(labels, key=lambda lw: abs(lw["top"] - w["top"]))
        if abs(centres[ci] - cx) <= 12 and abs(lab["top"] - w["top"]) <= 4:
            out[float(lab["text"])][ci] = w["text"]
    return out


def _centres(page, texts, x0, x1, y0, y1):
    ws = [w for w in _words(page, x0, x1, y0, y1) if w["text"] in texts]
    return [(w["x0"] + w["x1"]) / 2 for w in sorted(ws, key=lambda w: w["x0"])]


def _val(t):
    return None if t in (None, "-") else float(t)


def extract(pdf) -> dict:
    got: dict = {}
    # Table 12-1 (PDF p.1): column A = first value column of the left half, C = first of the right half
    p1 = pdf.pages[0]
    for col, (lx, cx) in {"A": ((40, 70), 107), "C": ((295, 330), 371)}.items():
        g = _grid(p1, lx, [cx], 210, 392)
        for size, cells in g.items():
            got[("t12_1", col, size)] = _val(cells.get(0))
    # footnote 3 (PDF p.2): 'on surfaces' (left half) and 'free in air' (right half) factors, in reading order
    p2 = pdf.pages[1]
    left = " ".join(p2.crop((0, 0, p2.width / 2, p2.height)).extract_text().split())
    right = " ".join(p2.crop((p2.width / 2, 0, p2.width, p2.height)).extract_text().split())
    m = re.search(r"on surfaces:.*?factor of (\d\.\d+).*?factor of (\d\.\d+)", left)
    got[("bundle", "surface", "1ac")] = got[("bundle", "surface", "dc")] = float(m.group(1))
    got[("bundle", "surface", "3ac")] = float(m.group(2))
    m = re.search(r"free in air or on cable trays:.*?factor of (\d\.\d+).*?factor of (\d\.\d+)", right)
    got[("bundle", "free_air", "1ac")] = got[("bundle", "free_air", "dc")] = float(m.group(1))
    got[("bundle", "free_air", "3ac")] = float(m.group(2))
    # Table 12-2 (PDF p.3 left): header '60 °C' … '90 °C'
    p3 = pdf.pages[2]
    heads = ["60", "70", "80", "85", "90"]
    cen = _centres(p3, set(heads), 70, 255, 85, 100)
    hdr = [w["text"] for w in sorted((w for w in _words(p3, 70, 255, 85, 100) if w["text"] in heads),
                                     key=lambda w: w["x0"])]
    for t, cells in _grid(p3, (44, 52), cen, 120, 240).items():
        for i, txt in cells.items():
            got[("temp", hdr[i], int(t))] = _val(txt)
    # Table 12-3 (PDF p.3 left, below 12-2): free air / earth
    for n, cells in _grid(p3, (56, 66), [131, 196], 310, 372).items():
        got[("cores", int(n), "free_air")] = _val(cells.get(0))
        got[("cores", int(n), "earth")] = _val(cells.get(1))
    # Table 12-4 (PDF p.3 right): column order as printed — H07V2-K/H07Z-K 90, H07Z-K 110, HEAT 145, HEAT 180
    names = ["heat_90", "heat_110", "heat_145", "heat_180"]
    for t, cells in _grid(p3, (298, 310), [345, 384, 424, 464], 140, 330).items():
        for i, txt in cells.items():
            got[("heat", names[i], int(t))] = _val(txt)
    # Table 12-6 (PDF p.4): headers 1 … 8 (left) and 9 … 20 (right); five rows in printed order
    p4 = pdf.pages[3]
    methods = ["bunched", "wall_touching", "wall_spaced", "ceiling_touching", "ceiling_spaced"]
    for x0, x1, y0, y1 in ((100, 255, 85, 100), (360, 510, 48, 58)):
        hw = sorted((w for w in _words(p4, x0, x1, y0, y1) if NUM.match(w["text"])), key=lambda w: w["x0"])
        cen = [(w["x0"] + w["x1"]) / 2 for w in hw]
        vals = [w for w in _words(p4, x0, x1, y1, 400) if re.match(r"^\d\.\d\d$", w["text"])]
        rows: list[list] = []
        for w in sorted(vals, key=lambda w: w["top"]):
            if not rows or w["top"] - rows[-1][0]["top"] > 4:
                rows.append([])
            rows[-1].append(w)
        for meth, row in zip(methods, rows):
            for w in row:
                cx = (w["x0"] + w["x1"]) / 2
                i = min(range(len(cen)), key=lambda k: abs(cen[k] - cx))
                got[("group", meth, int(hw[i]["text"]))] = float(w["text"])
    return got


def from_files() -> dict:
    mine: dict = {}
    for r in load_yaml(data_file("lapp_t12_1_ratings.yaml"))["rows"]:
        mine[("t12_1", r["column"], float(r["size"]))] = None if r["amps"] is None else float(r["amps"])
    for r in load_yaml(data_file("lapp_t12_factors.yaml"))["rows"]:
        k = r["kind"]
        if k == "bundle":
            for c, f in r["factors"].items():
                mine[("bundle", r["place"], c)] = float(f)
        elif k in ("temp", "heat"):
            for t, f in r["factors"].items():
                mine[(k, str(r["insulation"]), int(t))] = float(f)
        elif k == "cores":
            mine[("cores", int(r["n"]), "free_air")] = float(r["free_air"])
            mine[("cores", int(r["n"]), "earth")] = float(r["earth"])
        elif k == "group":
            for n, f in r["factors"].items():
                mine[("group", r["method"], int(n))] = float(f)
    return mine


def compare(got: dict, mine: dict) -> tuple[list[str], int]:
    diffs, n = [], 0
    for key in sorted(set(got) | set(mine), key=str):
        g, m = got.get(key, "absent"), mine.get(key, "absent")
        if g is None and m == "absent":
            continue        # '-' in the PDF where the file simply ends the column: same meaning
        n += 1
        if g != m:
            diffs.append(f"{key}: file {m} / PDF {g}")
    return diffs, n


def _fmt(r) -> str:
    if r.status != "ok":
        fail = next(c for c in r.checks if c.verdict == "fail")
        return f"refused ({fail.rule}: {fail.value})"
    v = r.value
    return (f"**{v['size_mm2']:g} mm²** — Iz {v['iz_a']:g} A = {v['i_table_a']:g} × {v['k_temp']:g} × "
            f"{v['k_bundle']:g} × {v['k_group']:g}" + (f" × {v['k_cores']:g}" if v["k_cores"] != 1 else "")
            + f" ({v['bound_by']})")


def wns2503() -> list[str]:
    lines = ["| Connection | Assumption | 55 °C inside | 35 °C inside |", "|---|---|---|---|"]
    cases = [
        ("37 kW drive feeder (LO input 70 A, 3NA3830 gG 100 A)", "single cores (PVC 70 °C) in a duct, alone",
         dict(ib_a=70, in_a=100, insulation="70", installation="duct", circuits=1)),
        ("", "same, with 3 circuits in the duct",
         dict(ib_a=70, in_a=100, insulation="70", installation="duct", circuits=3)),
        ("", "single cores H07V2-K (heat resistant 90 °C) in a duct, alone",
         dict(ib_a=70, in_a=100, insulation="heat_90", installation="duct", circuits=1)),
        ("", "single cores (PVC 70 °C) free in air, spaced ≥ d",
         dict(ib_a=70, in_a=100, insulation="70", installation="air_spaced")),
        ("", "if the fuse gave no overload protection (aR): Iz ≥ 70 A, duct, alone",
         dict(ib_a=70, overload_device=False, insulation="70", installation="duct", circuits=1)),
        ("7.5 kW DOL (15.5 A, MPCB 13–16 A)", "In = 16 A (top of the setting range), PVC 70 °C, duct, alone",
         dict(ib_a=15.5, in_a=16, insulation="70", installation="duct", circuits=1)),
        ("", "In = 16 A, duct shared with 6 circuits",
         dict(ib_a=15.5, in_a=16, insulation="70", installation="duct", circuits=6)),
        ("", "In = 15.5 A (set to FLC), duct, alone",
         dict(ib_a=15.5, in_a=15.5, insulation="70", installation="duct", circuits=1)),
        ("24 V DC I/O wire (0.5 A, 2 A fuse)", "PVC 70 °C, duct with 20 circuits",
         dict(ib_a=0.5, in_a=2, circuit="dc", insulation="70", installation="duct", circuits=20)),
    ]
    for name, how, kw in cases:
        lines.append(f"| {name} | {how} | {_fmt(select(ambient_c=55, **kw))} | {_fmt(select(ambient_c=35, **kw))} |")
    return lines


def main():
    ref = check_reference("LAPP-POWER")
    with pdfplumber.open(SOURCES / ref["file"]) as pdf:
        got = extract(pdf)
    mine = from_files()
    diffs, n = compare(got, mine)
    out = [f"# Internal wiring — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_internal_wiring.py`.", "",
           "## 1. Data files vs the Lapp PDF (independent re-extraction)", "",
           "Method: pdfplumber word positions — each number is placed by the y position of its row label and the x "
           "position of its column header (Tables 12-2 and 12-6 take the column centres from the printed headers). "
           "The data files were typed from pypdfium2 text read against the page images, so the two paths share "
           "no extraction code.", "",
           f"- values compared: {n} (Table 12-1 columns A and C, footnote 3, Tables 12-2, 12-3, 12-4, 12-6, "
           "each '-' must be a missing value in the file); mismatches: **" + str(len(diffs)) + "**"]
    out += [f"  - {d}" for d in diffs]
    out += ["- resolved during G6 (checker side, not data): the first run reported 7 differences — Table 12-1 "
            "column C, 120 … 500 mm² 'absent in the PDF'. The checker's label window started at x = 300 pt and the "
            "three-digit size labels sit at x = 299 … 300 pt; widened to 295 pt. The file values were confirmed on "
            "the PDF p.1 image (printed p.145: 120 → 292, 150 → 335, 185 → 382, 240 → 453, 300 → 523, 400 / 500 '-')."]
    out += ["- page images checked (rendered with pypdfium2): PDF p.1 (Table 12-1, column A = '1 3)' conductor, "
            "column C = '2 or 3'), p.2 (footnote 3 wording: 'on surfaces' 0.76 / 0.67 → Table 12-6; 'free in air or "
            "on cable trays' 0.8 / 0.7 → Table 12-8), p.3 (Table 12-2 column order 60 / 70 / 80 / 85 / 90 °C; "
            "Table 12-4 column order; no 145 °C row), p.4 (Table 12-6 row order; the duct is drawn in row 1).",
            "- page numbers: the PDF has 8 pages, each a spread of two printed pages: printed = 2·PDF page + 142 "
            "(left) / + 143 (right). There is no single `printed_page_offset`; every data row carries `printed`.",
            "", "## 2. What the source says (and does not say)", "",
            "- Table 12-1 is printed for 30 °C ambient; the guide does not print a conductor temperature for it. The "
            "rated conductor temperature only enters through Table 12-2 (60 … 90 °C) or Table 12-4 (heat-resistant "
            "types). It must come from the Lapp product page (not held) — so it is an input with no default.",
            "- Single cores bundled in a duct: Lapp's footnote 3 gives 0.67 (3~AC) / 0.76 (1~AC, DC) 'on surfaces' "
            "before Table 12-6, whose first row names conduits and wireways. Lapp's 'Attention' note sends single "
            "cores in conduits in buildings (methods A1 / B1) to DIN VDE 0298-4 Tables 3 / 5, which are not held. "
            "The tool uses the footnote-3 route for panel ducts (R-WIR-05, decision W-1).",
            "- Wires free in air touching each other (not in a duct): footnote 3 sends them to Table 12-8, which is "
            "for cable trays — refused.",
            "- No resistance, voltage-drop or short-circuit data are printed: these are not checked.",
            "", "## 3. WNS2503 examples (ECI: 'LAP Cable Internal Wiring')", "",
            "Assumptions for this run only: 3~AC, In from the device shown, single cores unless stated. The duct "
            "count (circuits sharing the duct) is not in the client documents — the designer must give it.", ""]
    out += wns2503()
    out += ["", "Reading: at 55 °C inside, PVC (70 °C) single cores in a duct lose 0.67 × 0.61 = 0.41 of their "
            "Table 12-1 rating, so the 100 A fuse needs 70 mm² (35 °C: 50 mm²). A heat-resistant H07V2-K wire "
            "(Table 12-4: 0.94 at 55 °C) brings it back to 50 mm². The DOL motor circuit needs 4 mm² at 55 °C "
            "(2.5 mm² at 35 °C)."]
    (HERE / "VERIFY.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
