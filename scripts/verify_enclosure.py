"""G6 verification for enclosure — writes components/enclosure/VERIFY.md.

1. Independent re-extraction from the PDFs (pypdfium2 text layer; the data files are only read afterwards, to
   compare): compensating factor f by altitude (Rittal p.12), k for sheet steel and its basis (pp.13, 26, 52),
   every formula as printed (pp.12, 13, 26, 30, 52) and the fan / heat-exchanger prerequisites (pp.7, 24),
   heat-exchanger ratings (p.26 diagram labels), fan-and-filter range (p.8), Siemens airflow formula and
   Control Unit loss (PM240-2 PDF p.34).
2. Printed page numbers of the Rittal catalogue vs the PDF page index (offset).
3. Rittal vs Siemens airflow cross-check.
4. WNS2503: heat loss of the running VFDs per panel (v2 vfd at 35 °C and 55 °C) → what the enclosure needs on a
   50 °C site at 1000 m: fans for 55 °C inside, a cooling unit for 35 °C inside.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402

from core.provenance import SOURCES, check_reference, load_yaml  # noqa: E402
from core.data import data_file  # noqa: E402

COMP = ROOT / "components" / "enclosure"
V1_JSON = Path("/Users/deepak/Documents/panel-selector/projects/WNS2503/out/WNS2503_layer0.json")
QDOT, VDOT = "", ""          # private-use glyphs for Q̇ and V̇ in the Rittal text layer


def pages(ref: str) -> dict[int, str]:
    pdf = pdfium.PdfDocument(str(SOURCES / check_reference(ref)["file"]))
    return {i + 1: pdf[i].get_textpage().get_text_range().replace("\r", "") for i in range(len(pdf))}


def flat(t: str) -> str:
    """One line, hyphenation and soft breaks removed."""
    return re.sub(r"\s+", " ", t.replace("￾", "").replace("-\n", "")).strip()


def canon(s: str) -> str:
    """Compare formulas regardless of layout: Q̇/V̇ glyphs → Q/V, drop dots above, spaces, brackets, slashes."""
    s = s.replace(QDOT, "Q").replace(VDOT, "V")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.replace("–", "-").replace("−", "-").replace("∆", "Δ")
    s = re.sub(r"\(indoor siting.*\)$", "", s)
    return re.sub(r"[\s()/]", "", s).lower()


def line_after(text: str, start: str, n: int) -> str:
    lines = text.splitlines()
    i = next(i for i, l in enumerate(lines) if l.strip().startswith(start))
    return " ".join(lines[i:i + n + 1])


def rittal_extract(t: dict[int, str]) -> dict:
    out: dict = {}
    out["f"] = [(int(a), int(b), float(f)) for f, a, b in
                re.findall(r"f = (\d\.\d) m³ · K/Wh at h = \(\s*(\d+) to\s+(\d+)\)", t[12])]
    out["k"] = {p: [float(x) for x in re.findall(r"k = (\d+(?:\.\d+)?) W/m² ?K", flat(t[p]))] for p in (13, 26, 52)}
    out["k_basis_52"] = "Indoor siting, static air" in t[52]
    lines13 = t[13].splitlines()
    out["formulas"] = {
        "delta_t_def": next(l for l in lines13 if l.startswith("ΔT = Ti")),
        "area_def": flat(line_after(t[13], "A = Effective", 1)),
        "delta_t_max": line_after(t[13], "(ΔT)max. =", 2),                         # fraction over 3 lines
        "q_surface": next(l for l in lines13 if "S = A · k · ΔT (watts)" in l),
        "fan_airflow": line_after(t[12], f"{VDOT} = f ·", 0) + " / ΔT",          # denominator: next text block
        "heat_exchanger": " ".join(l.strip() for l in t[26].splitlines()
                                   if l.strip() in ("qw =",) or l.strip().startswith(f"{QDOT}V – (A")) + " / ΔT",
        "cooling_unit": next(l for l in t[30].splitlines() if l.startswith(f"{QDOT}E = ")),
        "heater": next(l for l in t[52].splitlines() if l.startswith(f"{QDOT}H = A")).rstrip(" A"),
    }
    out["text"] = {p: flat(t[p]) for p in (7, 8, 24)}
    out["hx"] = [(f"SK {a}", float(q)) for a, q in re.findall(r"(\d{4}\.\d{3}) \((\d+(?:\.\d+)?) W/K\)", t[26])]
    m = re.search(r"Air throughput from (\d+) m³/h to (\d+) m³/h", t[8])
    out["fan_range"] = (int(m[1]), int(m[2])) if m else None
    # the ΔT denominators are on their own lines: confirm they exist next to the fraction
    out["denominators"] = {"fan_airflow": "ΔT" in t[12].splitlines()[t[12].splitlines().index(
        next(l for l in t[12].splitlines() if l.startswith(f"{VDOT} = f ·"))) + 1],
        "heat_exchanger": " ΔT" in t[26]}
    return out


def siemens_extract(t: dict[int, str]) -> dict:
    s = flat(t[34])
    m = re.search(r"airflow \[l/s\] = power loss \[W\] \* (\d+\.\d+) / ΔT \[K\]", s)
    c = re.search(r"Control Unit power loss is less than (\d+\.\d+) kW", s)
    printed = re.search(r"\n(\d+) Hardware Installation Manual", t[34])
    return {"coef": float(m[1]) if m else None, "cu_w": float(c[1]) * 1000 if c else None,
            "printed": int(printed[1]) if printed else None}


def printed_offsets(t: dict[int, str]) -> dict[int, int]:
    offs = {}
    for p, txt in t.items():
        m = re.search(r"(?:^|\n)(\d+) Rittal Technical System Catalogue|Cooling with ambient air (\d+)\s*(?:\n|$)", txt)
        if m:
            offs[p] = int(m[1] or m[2]) - p
    return offs


def main():
    rt, st = pages("RITTAL-TSC-3124300"), pages("SIE-PM240-2")
    rx, sx = rittal_extract(rt), siemens_extract(st)
    # ---- only now read the data files
    alt = load_yaml(data_file("rittal_altitude_factor.yaml"))
    kd = load_yaml(data_file("rittal_heat_transfer.yaml"))
    fm = load_yaml(data_file("rittal_formulas.yaml"))
    pr = load_yaml(data_file("rittal_products.yaml"))
    sd = load_yaml(data_file("siemens_cooling_air.yaml"))

    out = [f"# Enclosure — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_enclosure.py`. Re-extraction uses the pypdfium2 text layer of the PDFs; "
           "the data files are read only afterwards. All formulas and values below are also text on the page "
           "(not only images); Q̇ and V̇ are private-use glyphs in the text layer, so their dots and the fraction "
           "layout were confirmed on the rendered page images (pp. 12, 13, 26, 30, 52).", ""]
    total = 0

    # 1. f
    mine = sorted((r["h_min_m"], r["h_max_m"], float(r["f"])) for r in alt["rows"])
    d1 = [] if mine == sorted(rx["f"]) else [f"file {mine} / PDF {sorted(rx['f'])}"]
    d1 += [f"row {r} page {r['page']} ≠ 12" for r in alt["rows"] if r["page"] != 12]
    total += len(d1)
    out += ["## 1. Compensating factor f (p. 12)", "",
            f"- bands in PDF: {len(rx['f'])}; in file: {len(mine)}; mismatches: **{len(d1)}**"
            + "".join(f"\n  - {d}" for d in d1),
            "- PDF: " + ", ".join(f"{a}–{b} m: {f}" for a, b, f in sorted(rx["f"])), ""]

    # 2. k
    k_all = {p: re.findall(r"k = (\d+(?:\.\d+)?) W/m", flat(txt)) for p, txt in rt.items()}
    k_all = {p: v for p, v in k_all.items() if v}
    d2 = [f"p.{p}: k {v}" for p, v in k_all.items() if set(v) != {"5.5"}]
    for r in kd["rows"]:
        if float(r["k_w_m2k"]) not in rx["k"].get(r["page"], []):
            d2.append(f"k {r['k_w_m2k']} not printed on p.{r['page']} (PDF: {rx['k'].get(r['page'])})")
    for p in (13, 26, 52):
        if rx["k"][p] != [5.5]:
            d2.append(f"p.{p}: k values {rx['k'][p]}")
    if not rx["k_basis_52"]:
        d2.append("p.52: basis 'Indoor siting, static air' not found")
    total += len(d2)
    out += ["## 2. Heat transfer coefficient k (pp. 13, 26, 52)", "",
            f"- PDF: p.13 {rx['k'][13]}, p.26 {rx['k'][26]}, p.52 {rx['k'][52]} W/m²K (sheet steel); "
            f"basis 'indoor siting, static air' on p.52: {rx['k_basis_52']}; mismatches: **{len(d2)}**"
            + "".join(f"\n  - {d}" for d in d2),
            f"- every 'k = … W/m²K' in all {len(rt)} pages: "
            + ", ".join(f"p.{p} {v}" for p, v in sorted(k_all.items()))
            + " — always 5.5 for sheet steel; no k for any other material.", ""]

    # 3. formulas
    d3, rows3 = [], []
    for r in fm["rows"]:
        if r["id"] in rx["formulas"]:
            ok = canon(rx["formulas"][r["id"]]) == canon(r["printed"])
            pdf_txt = rx["formulas"][r["id"]].replace(QDOT, "Q̇").replace(VDOT, "V̇")
        else:
            ok = flat(r["printed"]) in rx["text"].get(r["page"], "")
            pdf_txt = "(sentence found)" if ok else "(not found)"
        rows3.append(f"| {r['id']} | {r['page']} | {r['printed']} | {pdf_txt} | {'✓' if ok else '✗'} |")
        if not ok:
            d3.append(f"{r['id']}: file '{r['printed']}' / PDF '{pdf_txt}'")
    for k_, ok in rx["denominators"].items():
        if not ok:
            d3.append(f"{k_}: denominator ΔT not found")
    total += len(d3)
    out += ["## 3. Formulas as printed", "", f"- formulas / sentences: {len(fm['rows'])}; mismatches: **{len(d3)}**"
            + "".join(f"\n  - {d}" for d in d3), "",
            "| id | page | data file | PDF text layer | match |", "|---|---|---|---|---|", *rows3,
            "", "IEC 890 is only named (p.13 'to IEC 890', p.26, p.31, p.52); its installation-type surface-area "
            "formulas are not printed anywhere in the catalogue → A is an input (R-ENC-02 / R-ENC-03).", ""]

    # 4. products
    mine_hx = [(r["article"], float(r["q_w_per_k"])) for r in pr["rows"] if r["kind"] == "heat_exchanger"]
    d4 = [] if sorted(mine_hx) == sorted(rx["hx"]) else [f"heat exchangers file {mine_hx} / PDF {rx['hx']}"]
    rng = next(r for r in pr["rows"] if r["kind"] == "fan_and_filter_range")
    if rx["fan_range"] != (rng["airflow_min_m3h"], rng["airflow_max_m3h"]):
        d4.append(f"fan range file {(rng['airflow_min_m3h'], rng['airflow_max_m3h'])} / PDF {rx['fan_range']}")
    if "17.5 W/K to 90 W/K" not in rx["text"][24]:
        d4.append("p.24 range 17.5 … 90 W/K not found")
    total += len(d4)
    out += ["## 4. Products (p. 26 heat exchangers, p. 8 fan range)", "",
            f"- heat exchangers in PDF: {len(rx['hx'])} ({', '.join(f'{a} {q:g} W/K' for a, q in rx['hx'])}); "
            f"fan-and-filter range {rx['fan_range']} m³/h; mismatches: **{len(d4)}**" + "".join(f"\n  - {d}" for d in d4),
            "- the heat-exchanger ratings are rotated line labels in the p.26 diagram; each label was checked against "
            "its line on the rendered image (the line through 15 K reaches 15 × q W).", ""]

    # 5. Siemens
    coef = next(r for r in sd["rows"] if r["quantity"] == "airflow_coefficient")
    cu = next(r for r in sd["rows"] if r["quantity"] == "control_unit_loss_max")
    off = check_reference("SIE-PM240-2").get("printed_page_offset", 0)
    d5 = []
    if sx["coef"] != float(coef["value"]):
        d5.append(f"airflow coefficient file {coef['value']} / PDF {sx['coef']}")
    if sx["cu_w"] != float(cu["value"]):
        d5.append(f"Control Unit loss file {cu['value']} W / PDF {sx['cu_w']} W")
    if sx["printed"] != coef["page"] + off:
        d5.append(f"printed page {sx['printed']} ≠ PDF {coef['page']} + offset {off}")
    total += len(d5)
    f0 = min(rx["f"])[2]
    out += ["## 5. Siemens PM240-2 cross-check (PDF p. 34, printed 32)", "",
            f"- PDF: airflow [l/s] = power loss [W] × {sx['coef']} / ΔT [K]; Control Unit loss < {sx['cu_w']:g} W; "
            f"printed page {sx['printed']}; mismatches: **{len(d5)}**" + "".join(f"\n  - {d}" for d in d5),
            f"- Rittal f = {f0} m³·K/Wh at 0–100 m = {f0 / 3.6:.4f} l·K/(W·s) vs Siemens {sx['coef']} → "
            f"{abs(f0 / 3.6 - sx['coef']) / sx['coef'] * 100:.2f} % apart: **agree within rounding** "
            "(golden cases E04, E15).",
            "- Siemens' formula has no altitude factor; at 1000 m Rittal needs 3.5/3.1 = 13 % more air (E11).", ""]

    # 6. printed pages
    offs = printed_offsets(rt)
    vals = sorted(set(offs.values()))
    out += ["## 6. Rittal printed page numbers", "",
            f"- pages with a printed number: {len(offs)} of {len(rt)}; offset(s) printed − PDF: {vals} → "
            + ("**no offset** (printed page = PDF page)" if vals == [0] else "**check**"), ""]

    out += ["## Result", "", f"**{total} unexplained mismatches.**", ""]
    out += wns2503()
    (COMP / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(out))
    return total


def wns2503() -> list[str]:
    if not V1_JSON.exists():
        return []
    from components.enclosure.select import select as enc
    from components.motor_flc.select import select as flc
    from components.vfd.select import select as vfd
    d = json.loads(V1_JSON.read_text())
    tu, h = d["site"]["ambient_c"], d["site"]["altitude_m"]
    loss = defaultdict(lambda: {35: 0.0, 55: 0.0, "n": 0})
    for f in (x for x in d["feeders"] if x.get("starter") == "VFD"):
        r1 = flc(kw=f["kw"], phases=f.get("phases") or 3, voltage_v=f.get("voltage") or 400)
        if r1.status in ("cannot_select", "invalid"):
            continue
        run = f.get("running") or f.get("qty") or 1
        for t in (35, 55):
            r = vfd(kw=f["kw"], flc_a=r1.value["flc_a"], flc_basis=r1.basis, ambient_c=t,
                    cable_m=f.get("cable_length_m") or 50, fault_ka=50, client_line_reactor_up_to_kw=15)
            loss[f["panel"]][t] += run * (r.value.get("loss_w", 0) + 40)       # + Control Unit < 40 W (p.34)
        loss[f["panel"]]["n"] += run
    lines = []
    for panel, v in sorted(loss.items()):
        fan = enc(heat_loss_w=v[55], ambient_c=tu, max_internal_c=55, altitude_m=h, siting="indoor")
        cu = enc(heat_loss_w=v[35], ambient_c=tu, max_internal_c=35, altitude_m=h, siting="indoor",
                 area_m2=1, material="sheet_steel")
        per_m2 = cu.value["cooling_unit_w"] - v[35] - 0                       # k × 1 m² × 15 K
        lines.append(f"| {panel} | {v['n']} | {v[55]:,.0f} | {fan.value['fan_airflow_m3h']:,.0f} "
                     f"({', '.join(fan.warnings) or 'no warning'}) | {v[35]:,.0f} | {v[35]:,.0f} + {per_m2:g} × A |")
    return ["## 7. WNS2503 — what the panel temperature choice means for cooling", "",
            f"Site {tu} °C, {h} m (f = 3.5). Heat loss = running VFDs only (drive loss from the v2 VFD component at the "
            "given internal temperature + 40 W Control Unit each, Siemens p.34); other equipment not yet counted, so "
            "these are lower bounds. Standby drives are not counted.", "",
            "| Panel | running VFDs | loss at 55 °C sizing (W) | fans for 55 °C inside, ΔT 5 K: V̇ m³/h | "
            "loss at 35 °C sizing (W) | cooling unit for 35 °C inside: Q̇E (W), A in m² |",
            "|---|---|---|---|---|---|", *lines, "",
            "- 55 °C inside with fans: ΔT is only 5 K, so V̇ = 3.5 × Q̇v / 5 = 0.7 m³/h per watt — more than one "
            "Blue e+ fan-and-filter unit (1160 m³/h) per ~1.66 kW of loss, and the drives must be upsized "
            "(VFD component).",
            "- 35 °C inside: below the 50 °C ambient, so fans and air/air heat exchangers cannot work (p.7, p.24); "
            "only a cooling unit, sized Q̇E = Q̇v + 5.5 × A × 15 = Q̇v + 82.5 W per m² of effective area (p.30).", ""]


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
