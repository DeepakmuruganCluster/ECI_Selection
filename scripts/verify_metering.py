"""G6 verification for metering — writes components/metering/VERIFY.md.

Independent re-extraction from the source PDFs with pdfplumber (never from the data files'
text), compared value by value with data/makers/{siemens,rishabh,selec}/ (the metering tables):
1. SENTRON PAC3220 manual: each value used (burden, CT inputs, voltage, ambient, CT primary range,
   article numbers, PROFINET module, 3P4W CT count) found by regex on its cited page.
2. 7KM PROFINET module manual: devices and slots (p.21), module article (p.79).
3. Rishabh LTRP: table rows by word position, only words inside the page (the PDF carries a hidden,
   off-page copy of older tables at negative x).
4. Rishabh TW: ruled tables (pdfplumber find_tables), class columns from the header row.
5. Selec SPCT / TWCT: ruled tables, each named by the type code printed above it; window sizes
   from the printed nomenclature.
6. Values that cannot be re-extracted (drawn window dimensions, image-only Selec CT catalogue):
   listed with the page images they were read from.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from components.metering.select import _ltrp, _pac, _pn, _rish_cond, _selec, _selec_ambient, _tw  # noqa: E402
from core.provenance import SOURCES  # noqa: E402

OUT = ROOT / "components" / "metering" / "VERIFY.md"


def _open(table):
    return pdfplumber.open(SOURCES / table["reference"]["file"])


def _num(s: str) -> float:
    return float(s.replace("VA", "").strip())


# ---------------------------------------------------------------- 1. PAC3220 manual
def pac_facts(pdf) -> dict:
    t = {p: re.sub(r"\s+", " ", pdf.pages[p - 1].extract_text() or "") for p in (10, 15, 17, 48, 73, 75, 98, 99, 106, 107)}
    f = {}
    m = re.search(r"Max\. power consumption per phase (\d+) mVA at (\d+) A", t[98])
    f["meter_burden_va"] = (float(m[1]) / 1000, 98) if m else None
    m = re.findall(r"Rated current \d x/(\d) A", t[98])
    f["ct_secondary_a"] = (sorted(int(x) for x in m), 98) if m else None
    m = re.search(r"Rated voltage [\d.]+/\d+ … (\d+)/(\d+) V \(IEC\)", t[98])
    f["rated_voltage_ull_max_v"] = (int(m[2]), 98) if m else None
    m = re.search(r"Max\. permissible continuous current (\d+) A", t[98])
    f["max_continuous_a"] = (int(m[1]), 98) if m else None
    m = re.search(r"rated voltage UL-N of (\d+) V", t[15])
    f["direct_connection_uln_max_v"] = (int(m[1]), 15) if m else None
    m = re.search(r"Active energy ([\d.]+)", t[99])
    f["active_energy_class"] = (m[1], 99) if m else None
    m = re.search(r"CT PRIMARY .*? (\d+) … (\d+) A", t[75])
    f["ct_primary_range_a"] = ([int(m[1]), int(m[2])], 75) if m else None
    m = re.search(r"CT SECONDARY .*?• (\d) A • (\d) A", t[75])
    f["ct_secondary_setting_a"] = ([int(m[1]), int(m[2])], 75) if m else None
    m = re.search(r"(7KM3x20-\w+-\w+) Article number of the device", t[73])
    f["article_pattern"] = (m[1], 73) if m else None
    m = re.search(r"PAC3220 \(https://\S+/ps/(7KM3220-\S+) ?(\w+)/cert\)", t[107])
    f["article_on_certificate_link"] = (m[1] + m[2], 107) if m else None
    m = re.search(r"Ambient temperature (−?-?\d+) … \+(\d+) °C \(K55\) during operation", t[106])
    f["ambient_c"] = ([int(m[1].replace("−", "-")), int(m[2])], 106) if m else None
    m = re.search(r"Switched Ethernet PROFINET expansion module \((7KM9300-\w+-\w+)\)", t[10])
    f["profinet_module_article"] = (m[1], 10) if m else None
    f["accessories_only_pac3220"] = None  # free-text row: checked by the module article on the same page
    m = re.search(r"3P4W, without voltage transformer, with (three) current transformers", t[48])
    f["cts_for_3p4w"] = (3, 48) if m else None
    m = re.search(r"supports two expansion modules\. One of these may be a communication module", t[17])
    f["max_comm_modules"] = (1, 17) if m else None
    return f


# ---------------------------------------------------------------- 2. PROFINET module manual
def pn_facts(pdf) -> dict:
    t21 = re.sub(r"\s+", " ", pdf.pages[20].extract_text())
    t79 = pdf.pages[78].extract_text()
    out = {}
    for m in re.finditer(r"With ((?:7KM PAC\d+(?: and )?)+), (?:only ever insert|you can insert) the expansion module in the "
                         r"(\"MOD1\"(?: or the \"MOD2\")?) slot", t21):
        for dev in re.findall(r"PAC\d+", m[1]):
            out[dev] = (re.findall(r"MOD\d", m[2]), 21)
    m = re.search(r"Switched Ethernet PROFINET expansion module (7KM9300-0AE02-0AA0)", t79)
    out["module"] = (m[1], 79) if m else None
    return out


# ---------------------------------------------------------------- 3. Rishabh LTRP (word positions)
def ltrp(pdf) -> set:
    rows = set()
    for p in range(3, 12):
        page = pdf.pages[p - 1]
        ws = [w for w in page.extract_words() if 0 <= w["x0"] < page.width and 0 <= w["top"] < page.height]
        size = None
        lines: list[list[dict]] = []
        for w in sorted(ws, key=lambda w: (round(w["top"]), w["x0"])):
            if lines and abs(lines[-1][0]["top"] - w["top"]) <= 2:
                lines[-1].append(w)
            else:
                lines.append([w])
        for l in lines:
            txt = [w["text"] for w in sorted(l, key=lambda w: w["x0"])]
            if txt[:3] == ["Dimensions", ":", "Rish"]:
                size = "LTRP " + txt[4]
            elif len(txt) == 5 and re.fullmatch(r"\d+", txt[0]) and all(re.fullmatch(r"[\d.]+|-", x) for x in txt[1:]):
                for va, cl in ((txt[1], txt[2]), (txt[3], txt[4])):
                    if va != "-":
                        rows.add((size, int(txt[0]), float(va), cl, p))
    return rows


# ---------------------------------------------------------------- 4. Rishabh TW (ruled tables)
def tw(pdf) -> set:
    rows = set()
    for p in (3, 4):
        for t in pdf.pages[p - 1].find_tables():
            cells = t.extract()
            if not cells or not cells[0] or len(cells[0]) < 2 or not (cells[0][1] or "").startswith("RISH CT TW"):
                continue
            size = re.sub(r"RISH CT TW - (\d)", r"TW-\1", cells[0][1])
            classes = [c.replace("1.0", "1") for c in cells[2][1:]]
            for r in cells[3:]:
                for cl, v in zip(classes, r[1:]):
                    if v and v != "-":
                        rows.add((size, int(r[0].rstrip("A")), _num(v), cl, p))
    return rows


# ---------------------------------------------------------------- 5. Selec (ruled tables + nomenclature)
def selec(pdf) -> tuple[set, dict, list[str]]:
    rows, windows, notes = set(), {}, []
    for p in (9, 10):
        page = pdf.pages[p - 1]
        words = page.extract_words()
        for t in page.find_tables():
            x0, top, x1, _ = t.bbox
            above = [w for w in words if x0 - 3 <= w["x0"] < x1 and 0 < top - w["bottom"] < 20
                     and re.match(r"^(SPCT|TWCT|SCCT|RCT)-", w["text"])]
            if not above:
                continue
            code = max(above, key=lambda w: w["top"])["text"]
            fam = code.split("-")[0]
            if fam not in ("SPCT", "TWCT"):
                continue
            size = code.split("-")[1] if fam == "SPCT" else code.split("-")[2]
            cells = t.extract()
            halves = sum(1 for c in cells[0] if c == "Primary current")     # SPCT-140/100: two halves side by side
            stride = len(cells[0]) // halves
            one_row = re.search(r"Accuracy \(([\d.]+)\)", cells[0][1] or "")      # TWCT-D120: 'Accuracy (0.5)'
            if one_row:
                classes, body = [None, one_row[1]], cells[1:]
            else:
                classes, body = cells[1][:stride], cells[2:]
            for r in body:
                for i in range(0, len(r), stride):
                    prim = r[i]
                    if not prim or not re.fullmatch(r"\d+", prim.strip()):
                        continue
                    for cl, v in zip(classes[1:], r[i + 1:i + len(classes)]):
                        if v and v.strip() != "-":
                            key = (fam, size, int(prim), _num(v), cl, p)
                            if key in rows:
                                notes.append(f"p.{p} {code}: {prim} A {cl} {v} printed twice")
                            rows.add(key)
        text = re.sub(r"\s+", " ", page.extract_text())
        if p == 9:
            for m in re.finditer(r"(\d+/\d+)\s*:\s*(?:(\d+)x(\d+)mm|DIA (\d+))", text):
                windows[("SPCT", m[1])] = ("round", int(m[4])) if m[4] else ("rect", int(m[2]), int(m[3]))
        else:
            for m in re.finditer(r"(D\d+)\s*:\s*DIA\s*(\d+)", text.split("TWCT-T-D35-30/5 A")[-1]):
                windows[("TWCT", m[1])] = ("round", int(m[2]))
    return rows, windows, notes


def main():
    out = [f"# Metering — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_metering.py`. Independent re-extraction from the PDFs (regex on the cited "
           "page text, ruled-table cells, word positions), compared value by value with the metering tables in `data/makers/`.", ""]
    total_mis = 0

    # 1. PAC3220
    with _open(_pac()) as pdf:
        facts = pac_facts(pdf)
    d1, n1 = [], 0
    for r in _pac()["rows"]:
        got = facts.get(r["item"])
        if r["item"] == "accessories_only_pac3220":
            continue
        n1 += 1
        if got is None:
            d1.append(f"{r['item']}: not found on p.{r['page']}")
        elif (got[0] != r["value"] and str(got[0]) != str(r["value"])) or got[1] != r["page"]:
            d1.append(f"{r['item']}: file {r['value']} p.{r['page']} / PDF {got[0]} p.{got[1]}")
    total_mis += len(d1)
    out += ["## 1. SENTRON PAC3220 manual (SIE-PAC3220, PDF page = printed + 2)", "",
            f"- values compared: {n1} (the free-text accessory row is covered by the module article on p.10); "
            f"mismatches: **{len(d1)}**" + "".join(f"\n  - {d}" for d in d1), ""]

    # 2. PROFINET module
    with _open(_pn()) as pdf:
        pn = pn_facts(pdf)
    d2, n2 = [], 0
    for r in _pn()["rows"]:
        n2 += 1
        got = pn.get(r["device"])
        want = r.get("article") if r["device"] == "module" else r.get("slots")
        if got is None or got[0] != want or got[1] != r["page"]:
            d2.append(f"{r['device']}: file {want} p.{r['page']} / PDF {got}")
    extra = sorted(set(pn) - {r["device"] for r in _pn()["rows"]})
    total_mis += len(d2)
    out += ["## 2. 7KM PROFINET module manual (SIE-7KM-PN, PDF page = printed + 2)", "",
            f"- rows compared: {n2}; mismatches: **{len(d2)}**; devices in the PDF but not in the file: {extra or 'none'}; "
            "PAC3120 not named on p.21: " + ("yes" if "PAC3120" not in pn else "**no**")
            + "".join(f"\n  - {d}" for d in d2), ""]

    # 3./4. Rishabh
    for title, fn, tab, key in (("3. Rishabh LTRP (RISH-LTRP, word positions on pp. 3–11)", ltrp, _ltrp(), "LTRP"),
                                ("4. Rishabh TW (RISH-TW, ruled tables pp. 3–4)", tw, _tw(), "TW")):
        with _open(tab) as pdf:
            pdf_rows = fn(pdf)
        file_rows = {(r["size"], r["primary_a"], float(r["va"]), r["class"], r["page"]) for r in tab["rows"]}
        miss, extra = sorted(file_rows - pdf_rows), sorted(pdf_rows - file_rows)
        total_mis += len(miss) + len(extra)
        out += [f"## {title}", "",
                f"- (size, primary, VA, class, page) rows: file {len(file_rows)}, PDF {len(pdf_rows)}; "
                f"in file not in PDF: **{len(miss)}**; in PDF not in file: **{len(extra)}**"
                + "".join(f"\n  - file only: {m}" for m in miss) + "".join(f"\n  - PDF only: {m}" for m in extra), ""]

    # 5. Selec
    with _open(_selec()) as pdf:
        s_rows, s_win, s_notes = selec(pdf)
    file_rows = {(r["family"], r["size"], r["primary_a"], float(r["va"]), r["class"], r["page"]) for r in _selec()["rows"]}
    miss, extra = sorted(file_rows - s_rows), sorted(s_rows - file_rows)
    dw = []
    for r in _selec()["rows"]:
        w = s_win.get((r["family"], r["size"]))
        mine = ("round", r["window_d_mm"]) if r["window"] == "round" else ("rect", r["window_w_mm"], r["window_h_mm"])
        if w != mine and f"{r['family']} {r['size']}: file {mine} / PDF {w}" not in dw:
            dw.append(f"{r['family']} {r['size']}: file {mine} / PDF {w}")
    total_mis += len(miss) + len(extra) + len(dw)
    out += ["## 5. Selec SPCT / TWCT (SELEC-MEAS pp. 9–10, ruled tables named by the type code above them)", "",
            f"- (family, size, primary, VA, class, page) rows: file {len(file_rows)}, PDF {len(s_rows)}; "
            f"in file not in PDF: **{len(miss)}**; in PDF not in file: **{len(extra)}**"
            + "".join(f"\n  - file only: {m}" for m in miss) + "".join(f"\n  - PDF only: {m}" for m in extra),
            f"- window sizes from the printed nomenclature: {len({(r['family'], r['size']) for r in _selec()['rows']})} sizes "
            f"compared; mismatches: **{len(dw)}**" + "".join(f"\n  - {d}" for d in dw),
            "- explained (printed as such, not a transcription error): "
            + ("; ".join(s_notes) if s_notes else "none") + " — kept once in the data file.", ""]

    # 6. by eye
    lt = {}
    for r in _ltrp()["rows"]:
        lt.setdefault(r["size"], (r["page"], f"Ø{r['window_d_mm']}" if r["window"] == "round" else f"{r['window_w_mm']} × {r['window_h_mm']}"))
    twd = {}
    for r in _tw()["rows"]:
        twd.setdefault(r["size"], (r["page"], f"Ø{r['window_d_mm']}"))
    out += ["## 6. Not re-extractable: checked on the page images", "",
            "The window dimensions on the Rishabh drawings are vector graphics (no text), and the Selec CT catalogue "
            "2024 (SELEC-CT) is image-only. These values were read on page images rendered with pypdfium2 "
            "(scale 1.5–2.5) and are listed here for the reviewer to compare with the pictures on the review page:", "",
            "- RISH-LTRP windows (mm): " + "; ".join(f"{s} {v[1]} (p.{v[0]})" for s, v in lt.items()),
            "- RISH-TW windows (mm): " + "; ".join(f"{s} {v[1]} (p.{v[0]})" for s, v in twd.items()),
            "- SELEC-CT ambient: " + "; ".join(f"{r['family']} {r['ambient_min_c']} … +{r['ambient_max_c']} °C "
                                              f"(PDF p.{r['page']})" for r in _selec_ambient()["rows"]),
            ""]
    cond_ok = []
    for fam in ("LTRP", "TW"):
        tab = _rish_cond(fam)
        with _open(tab) as pdf:
            t2 = re.sub(r"\s+", " ", pdf.pages[1].extract_text())
        m_amb = re.search(r"Ambient Temperature (-?\d+)°C to \+(\d+)°C", t2)
        m_sec = re.search(r"(\d)A (?:standard )?\(1A on request\)", t2)
        m_um = re.search(r"System voltage ([\d.]+) kV|\(Um\) (\d+)V", t2)
        pdf_v = {"ambient_c": [int(m_amb[1]), int(m_amb[2])] if m_amb else None,
                 "secondary_a": int(m_sec[1]) if m_sec else None,
                 "um_max_v": (round(float(m_um[1]) * 1000) if m_um[1] else int(m_um[2])) if m_um else None}
        bad = [f"{r['item']}: file {r['value']} / PDF {pdf_v.get(r['item'])}" for r in tab["rows"]
               if pdf_v.get(r["item"]) != r["value"] or r["page"] != 2]
        cond_ok.append(bad)
        total_mis += len(bad)
    with _open(_selec()) as pdf:
        t9 = re.sub(r"\s+", " ", pdf.pages[8].extract_text())
    sel_ok = "OUTPUT 5A" in t9 and "SYSTEM VOLTAGE 720V max" in t9
    total_mis += 0 if sel_ok else 1
    out += [f"- Rishabh conditions (secondary, Um, ambient) compared with p.2: RISH-LTRP mismatches **{len(cond_ok[0])}**, "
            f"RISH-TW mismatches **{len(cond_ok[1])}**" + "".join(f"\n  - {d}" for d in cond_ok[0] + cond_ok[1]),
            f"- SELEC-MEAS p.9 secondary 5 A and 720 V found: {'yes' if sel_ok else '**no**'}", ""]

    out += ["## Result", "", f"**{total_mis} unexplained mismatches.**", ""]
    OUT.write_text("\n".join(out))
    print("\n".join(out))
    return total_mis


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
