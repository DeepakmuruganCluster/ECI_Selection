"""G6 verification for control_signalling — writes components/control_signalling/VERIFY.md.

Independent re-extraction from the PDFs, NOT from the data files: the data files were transcribed by
reading pdfplumber text and the page images; this script reads the pages again with a different text
engine (pypdfium2, in the PDF's content order) and, for the multi-column Connectwell terminal and
Finder 13 tables, by word POSITION (pdfplumber words: columns located from the printed column
headers, rows located from the printed row labels). Every value extracted is then compared with the
data-file row, value by value. Printed statements the rules rely on are searched for verbatim, and the
'absence' findings (no latching relay in Connectwell, no AC-15 / DC-13 rating for the CSR relay, no full
40.xx.6 bistable code) are re-checked by whole-document search.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

from components.control_signalling.select import FILES, _data  # noqa: E402
from core.provenance import SOURCES  # noqa: E402

DESCRIPTIVE = {"kind", "page", "note", "text", "reason", "function", "design", "ambient_note", "for_types", "type",
               "coil", "topic", "polarity", "supply", "inputs", "series"}


# ------------------------------------------------------------------ PDF access
def _path(key: str) -> Path:
    return SOURCES / _data(key)["reference"]["file"]


@lru_cache(maxsize=None)
def _doc(key: str):
    return pdfium.PdfDocument(str(_path(key)))


@lru_cache(maxsize=None)
def text(key: str, page: int) -> str:
    return _doc(key)[page - 1].get_textpage().get_text_range().replace("\r", "")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("–", "-").replace("–", "-")).strip()


def lines(key: str, page: int) -> list[str]:
    return [norm(x) for x in text(key, page).split("\n") if x.strip()]


def find(key: str, page: int, pattern: str, group=None, flags=0):
    m = re.search(pattern, norm(text(key, page)), flags)
    if not m:
        return None
    return m if group is None else m.group(group)


def num(s):
    return None if s is None else float(s)


@lru_cache(maxsize=None)
def _plumb(key: str):
    return pdfplumber.open(_path(key))


@lru_cache(maxsize=None)
def words(key: str, page: int) -> list[dict]:
    return _plumb(key).pages[page - 1].extract_words(keep_blank_chars=False)


def label_top(ws, label: str, nth: int = 0, xmax: float = 9e9):
    """top of the n-th line whose consecutive words spell `label`"""
    toks = label.split()
    hits = []
    srt = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
    for i, w in enumerate(srt):
        if w["text"] != toks[0] or w["x0"] > xmax:
            continue
        seq = [x for x in srt if abs(x["top"] - w["top"]) <= 1.5 and x["x0"] >= w["x0"]]
        if [x["text"] for x in seq[:len(toks)]] == toks:
            hits.append(w["top"])
    return hits[nth] if len(hits) > nth else None


def cell(ws, top, x_lo, x_hi, tol=3.0) -> str:
    sel = [w for w in ws if abs(w["top"] - top) <= tol and x_lo <= (w["x0"] + w["x1"]) / 2 < x_hi]
    return " ".join(w["text"] for w in sorted(sel, key=lambda w: w["x0"]))


def columns(ws, names: list[str], top_max=110, half=88):
    """column x-ranges from the header words printed on one line (the line holding the most of `names`);
    bounds are the midpoints between neighbouring headers, the outer ones ± half"""
    by_top: dict[int, list[dict]] = {}
    for w in ws:
        if w["text"] in names and w["top"] < top_max:
            by_top.setdefault(round(w["top"]), []).append(w)
    if not by_top:
        return {}
    hdr = sorted(max(by_top.values(), key=len), key=lambda w: w["x0"])
    cs = [(w["x0"] + w["x1"]) / 2 for w in hdr]
    out = {}
    for i, w in enumerate(hdr):
        lo = (cs[i - 1] + cs[i]) / 2 if i else cs[i] - half
        hi = (cs[i] + cs[i + 1]) / 2 if i + 1 < len(cs) else cs[i] + half
        out[w["text"]] = (lo, hi)
    return out


# ------------------------------------------------------------------ extractors: key → {row id: {field: value}}
def ex_finder(key: str) -> dict:
    out: dict = {}
    s38 = key == "s38"
    # modules (combination tables)
    pages = {18: None} if s38 else {29: "screw", 30: "screwless"}
    for page, conn in pages.items():
        section = conn
        for ln in lines(key, page):
            if s38:
                if ln.startswith("Box clamp - 1 Pole relay 6 A"):
                    section = "screw"
                elif ln.startswith("Screwless terminal - 1 Pole relay 6 A"):
                    section = "screwless"
                elif "16 A" in ln or "8 A" in ln:
                    section = None
            m = re.match(r"^(3[89]\.[0156]1\.\d\.\d{3}\.\d{4}) (.+?) (34\.51\.7\.\d{3}\.\d{4}) (93\.\d\d\.\d\.\d{3})$", ln)
            if m and section and m[1] not in out:
                a = m[1].split(".")
                out[("module", m[1])] = {"article": m[1], "connection": section, "coil_code": f"{a[2]}.{a[3]}",
                                         "relay": m[3], "socket": m[4], "page": page}
    wide = find(key, 5 if s38 else 6, r"6\.2 mm wide", 0)
    for k in out:
        out[k]["width_mm"] = 6.2 if wide else None
    # contact (product page)
    p = 5 if s38 else 6
    t = norm(text(key, p))
    m = re.search(r"Maximum peak current A (\d+)/(\d+)", t)
    v = re.search(r"Maximum switching voltage V AC (\d+)/(\d+)", t)
    dc = re.search(r"Breaking capacity DC1: 24/110/220 V A ([\d.]+)/([\d.]+)/([\d.]+)", t)
    amb = re.search(r"Ambient temperature range.*?°C -(\d+)…\+(\d+)", t)
    out[("contact",)] = {"contacts": find(key, p, r"Contact configuration (1 CO \(SPDT\))", 1), "rated_a": num(m[1]),
                         "peak_a": num(m[2]), "rated_v_ac": num(v[1]), "max_v_ac": num(v[2]),
                         "ac1_va": num(find(key, p, r"Rated load AC1 VA (\d+)", 1)),
                         "ac15_va": num(find(key, p, r"Rated load AC15 \(230 V AC\) VA (\d+)", 1)),
                         "dc1_24v_a": num(dc[1]), "dc1_110v_a": num(dc[2]), "dc1_220v_a": num(dc[3]),
                         "ambient_min_c": -num(amb[1]), "ambient_max_c": num(amb[2]), "page": p}
    # coil data (first table that lists the code = the 1 pole 6 A / MasterBASIC table)
    p = 13 if s38 else 22
    for code in ("7.024", "0.024"):
        for ln in lines(key, p):
            if s38:
                m = re.match(rf"^24 ({re.escape(code)}) ([\d.]+) ([\d.]+) ([\d.]+) (?:[\d.]+/)?([\d.]+)$", ln)
            else:
                m = re.match(rf"^24 ({re.escape(code)}) ([\d.]+) ([\d.]+) [\d.]+ ([\d.]+) (?:[\d.]+/)?([\d.]+)$", ln)
            if m:
                out[("coil", code)] = {"coil_code": code, "un_v": 24.0, "umin_v": num(m[2]), "umax_v": num(m[3]),
                                       "i_ma": num(m[4]), "p_w": num(m[5]), "page": p}
                break
    # accessories
    p = 20 if s38 else 33
    t = norm(text(key, p))
    j = re.search(r"(\d+)-way jumper link for [\d/.]+ (093\.\d\d) \(blue\)", t) if s38 else \
        re.search(r"(\d+)-way jumper link (093\.\d\d) \(blue\)", t)
    r = re.search(r"Rated values (\d+) A\* - (\d+) V", t)
    out[("accessory", "jumper")] = {"use": "jumper", "article": j[2], "ways": num(j[1]), "rated_a": num(r[1]), "rated_v": num(r[2]), "page": p}
    sep = re.search(r"(?:Plastic separator|Dual-purpose plastic separator.*?\)) (093\.\d\d)", t)
    req = "required at the start and the end of a group of interfaces" in t
    out[("accessory", "separator")] = {"use": "separator", "article": sep[1], "per_group": 2.0 if req else 0.0, "page": p}
    mk = re.search(r"Sheet of marker tags(?: for 38\.21/51/61/81/91)?, plastic, (\d+) tags, 6 x 10 mm,? ?(093\.\d\d)?", t)
    out[("accessory", "marker")] = {"use": "marker", "article": mk[2] or find(key, p, r"6 x 10 mm (093\.48)", 1), "tags": num(mk[1]), "page": p}
    return out


def ex_s13() -> dict:
    ws = words("s13", 5)
    cols = columns(ws, ["13.11", "13.12", "13.31"], top_max=200, half=95)
    lo, hi = cols["13.12"]

    def c(label, nth=0):
        return cell(ws, label_top(ws, label, nth), lo, hi)
    cur, volt = c("Rated current"), c("Maximum switching voltage")
    imp = c("Minimum/Maximum impulse duration")
    amb = c("Ambient temperature range")
    rp = c("Rated power AC/DC")
    vdc = cell(ws, label_top(ws, "V DC", xmax=300), lo, hi)
    rated_v, max_v = volt.split("/")
    im = re.match(r"(\d+) s \((\d+) ms minimum\)", imp)
    am = re.match(r"[-–](\d+)…\+(\d+)", amb)
    un = float(vdc.split("-")[-1])
    op = label_top(ws, "Operating range")
    dc_top = min(w["top"] for w in ws if w["text"] == "DC" and w["top"] > op)
    rng = re.match(r"\(([\d.]+)…([\d.]+)\)", cell(ws, dc_top, lo, hi))
    row = {"article": find("s13", 7, r"(13\.12\.0\.024\.0000) \(24 V AC/DC\)", 1), "contacts": c("Contact configuration"),
           "rated_a": num(cur), "rated_v_ac": num(rated_v), "max_v_ac": num(max_v), "ac1_va": num(c("Rated load AC1")),
           "ac15_va": num(c("Rated load AC15 (230 V AC)")), "un_v": un,
           "umin_v": round(float(rng[1]) * un, 2) if rng else None, "umax_v": round(float(rng[2]) * un, 2) if rng else None,
           "p_w_impulse": num(re.match(r"[\d.]+/([\d.]+)\*", rp)[1]), "impulse_min_s": int(im[2]) / 1000,
           "impulse_max_s": num(im[1]), "ambient_min_c": -num(am[1]), "ambient_max_c": num(am[2]),
           "width_mm": 17.5 if find("s13", 5, r"17\.5 mm wide") else None, "page": 5}
    return {("latching",): row, ("code",): {"article": row["article"], "page": 7},
            ("wiring",): {"article": "13.12.0.024.0000" if all(t in text("s13", 11) for t in ("Type 13.12", "Set", "Reset"))
                         else None, "page": 11},
            ("function",): {"article": "13.12.0.024.0000" if "13.12" in text("s13", 8) else None, "page": 8},
            ("rejected", "13.01"): {"article": "13.01.0.024.0000" if "13.01.0.024.0000" in text("s13", 7) else None, "page": 8}}


def ex_s40() -> dict:
    m = re.search(r"^24 (6\.024) ([\d.]+) ([\d.]+) (\d+) (\d+) (\d+)$", "\n".join(lines("s40", 9)), re.M)
    imp = find("s40", 10, r"minimum SET or RESET impulse time is (\d+) ms", 1)
    return {("rejected_coil",): {"coil_code": m[1], "un_v": 24.0, "umin_v": num(m[2]), "umax_v": num(m[3]),
                                 "r_ohm": num(m[4]), "i_ma": num(m[5]), "r_dc_ohm": num(m[6]), "page": 9},
            ("rejected_wiring",): {"min_impulse_ms": num(imp), "page": 10}}


def ex_s20() -> dict:
    m = re.search(r"\b24 (9\.024) ([\d.]+) ([\d.]+) (\d+) (\d+)\b", norm(text("s20", 4)))
    return {("rejected_coil",): {"coil_code": m[1], "un_v": 24.0, "umin_v": num(m[2]), "umax_v": num(m[3]),
                                 "r_ohm": num(m[4]), "i_ma": num(m[5]), "page": 4}}


def ex_cwes() -> dict:
    out = {}
    L = lines("cwes", 44)

    def row(label):
        return next(x[len(label):].strip() for x in L if x.startswith(label))
    volts = re.findall(r"\d+(?:-\d+)? V(?:DC|UC)", row("Coil Voltage"))
    i = volts.index("24 VDC")
    for label, conn in (("Spring Termination", "screwless"), ("Screw Termination", "screw")):
        art = row(label + " ").split()[i]
        out[("module", art)] = {"article": art, "connection": conn,
                                "nominal_input_ma": num(re.findall(r"([\d.]+) mA", row("Nominal input current"))[i]),
                                "pickup_v": num(re.findall(r"([\d.]+) V", row("Pickup voltage"))[i]),
                                "dropout_v": num(re.findall(r"([\d.]+) V", row("Dropout voltage"))[i]),
                                "input_mw": num(re.findall(r"([\d.]+) mW", row("Nominal input power"))[i]),
                                "width_mm": num(find("cwes", 45, r"\(W x H x D\) ([\d.]+) x", 1)), "page": 44}
    sv = re.match(r"(\d+) VAC / (\d+) VDC", row("Switching Voltage"))
    sp = re.match(r"(\d+) VA, (\d+) W", row("Maximum Switching power"))
    amb = find("cwes", 44, r"Ambient Operating Temperature -(\d+) to \+(\d+)")
    out[("contact",)] = {"contacts": find("cwes", 44, r"Contact switching type (1CO) \(SPDT\)", 1) and "1 CO (SPDT)",
                         "rated_a": num(re.match(r"(\d+) A", row("Limiting continuous current"))[1]),
                         "max_v_ac": num(sv[1]), "max_v_dc": num(sv[2]), "max_va": num(sp[1]), "max_w_dc": num(sp[2]),
                         "ambient_min_c": -num(amb[1]), "ambient_max_c": num(amb[2]), "page": 44}
    t45 = norm(text("cwes", 45))
    for poles in re.findall(r"Coil Side & Contact Side - \d+ Pole JX4/(\d+)", t45):
        out[("accessory", f"JX4/{poles}")] = {"use": "jumper", "article": f"JX4/{poles}", "ways": num(poles), "page": 45}
    if re.search(r"Marker Card (MC6) \(Blank\)", t45):
        out[("accessory", "MC6")] = {"use": "marker", "article": "MC6", "page": 45}
    for a in re.findall(r"\b(CA10[34])\b", t45.split("End Clamp", 1)[1][:40]):
        out[("accessory", a)] = {"use": "end_clamp", "article": a, "page": 45}
    return out


TB_ORDER = ["CP1.5", "CP2.5", "CP4", "CP6/10", "CP16"]


def ex_cwtb() -> dict:
    out = {}
    lab = words("cwtb", 12)                 # p.12 carries the row labels; p.13 has the same layout
    first = {}
    for w in sorted(lab, key=lambda w: w["top"]):
        first.setdefault(w["text"], w["top"])
    tops = {"width": first["Width"], "flex": first["Stranded"], "voltage": first["Voltage"],
            "current": first["Current"], "plate": label_top(lab, "End Plate"), "marker": first["Marking"]}
    tops["solid"] = next(w["top"] for w in lab if w["text"] == "Solid")
    tops["ferrule"] = next(w["top"] for w in lab if w["text"] == "Ferrule" and w["top"] > tops["solid"])
    for page in (12, 13, 14):
        ws = words("cwtb", page)
        for name, (lo, hi) in columns(ws, TB_ORDER, top_max=80).items():
            def rng(r):
                m = re.search(r"([\d.]+) - ([\d.]+) mm", cell(ws, tops[r], lo, hi))
                return (num(m[1]), num(m[2])) if m else (None, None)
            fl, so, fe = rng("flex"), rng("solid"), rng("ferrule")
            jser = {"CP16": "JY16"}.get(name, "JX" + name.replace("CP", "").split("/")[0])
            out[("terminal", name)] = {
                "article": name, "width_mm": num(re.match(r"([\d.]+) x", cell(ws, tops["width"], lo, hi))[1]),
                "flex_min": fl[0], "flex_max": fl[1], "solid_min": so[0], "solid_max": so[1],
                "ferrule_min": fe[0], "ferrule_max": fe[1],
                "iec_v": num(re.search(r"(\d+) V", cell(ws, tops["voltage"], lo, hi))[1]),
                "iec_a": num(re.search(r"(\d+) A", cell(ws, tops["current"], lo, hi))[1]),
                "end_plate": next(t for t in cell(ws, tops["plate"], lo, hi).split() if t.startswith("EP")),
                "marker": next(t for t in cell(ws, tops["marker"], lo, hi).split() if t.startswith("MC")),
                "end_clamp": "CA103 / CA104" if "CA103 / CA104" in norm(text("cwtb", page)) else None,
                "jumper_series": jser, "page": page}
            # size_mm2: the largest conductor of the block name (CP6/10 → 10)
            out[("terminal", name)]["size_mm2"] = num(name.replace("CP", "").split("/")[-1])
            # pluggable jumpers of this column (exclude step-down JXS / JYS)
            js = [w for w in ws if lo <= (w["x0"] + w["x1"]) / 2 < hi and re.fullmatch(rf"{jser}/(\d+)", w["text"])]
            poles = sorted(int(w["text"].split("/")[1]) for w in js)
            imax = {cell(ws, w["top"], lo, hi, tol=1.5) for w in js}
            ia = {num(re.search(r"(\d+) A", s)[1]) for s in imax if re.search(r"(\d+) A", s)}
            out[("jumper", jser)] = {"series": jser, "poles": poles, "imax_a": ia.pop() if len(ia) == 1 else sorted(ia), "page": page}
    ws = words("cwtb", 289)
    third = _plumb("cwtb").pages[288].width / 3
    for w in ws:
        if re.fullmatch(r"MC[\d.]+", w["text"]) and w["x1"] < third:
            line_ = [x for x in sorted(ws, key=lambda x: x["x0"]) if abs(x["top"] - w["top"]) <= 1.5 and x["x0"] >= w["x0"]]
            nxt = next((x["x0"] for x in line_[1:] if x["text"].startswith("MC")), 9e9)   # next table's part no.
            row = [x["text"] for x in line_ if x["x0"] < nxt]
            if len(row) >= 6 and row[0] == w["text"]:     # Part, Packet, Rows, Tags, H, W
                out[("marker", w["text"])] = {"article": w["text"], "tags": num(row[3]), "tag_w_mm": num(row[5]), "page": 289}
    ws = words("cwtb", 283)
    cols = columns(ws, ["CA202", "CA103", "CA104"], top_max=9999)
    htop = next(w["top"] for w in ws if w["text"] == "CA103" and cols["CA103"][0] <= (w["x0"] + w["x1"]) / 2 < cols["CA103"][1]
                and any(abs(x["top"] - w["top"]) < 1.5 and x["text"] == "CA104" for x in ws))
    wt = min(w["top"] for w in ws if w["text"] == "Width" and w["top"] > htop)
    for name in ("CA103", "CA104"):
        m = re.search(r"([\d.]+) x [\d.]+ mm", cell(ws, wt, *cols[name]))
        out[("end_clamp", name)] = {"article": name, "width_mm": num(m[1]) if m else None, "page": 283}
    return out


def ex_rittal() -> dict:
    t2 = norm(text("door", 2))
    r = {f"rating_{k}_a": num(find("door", 2, rf"{v}/(\d+) A", 1)) for k, v in
         (("24vdc", "24 V DC"), ("24vac", "24 V AC"), ("125vac", "125 V AC"), ("240vac", "240 V AC"))}
    sw = {"article": find("door", 2, r"(SZ 4127\.010) - Door-operated switch", 1), **r,
          "rated_operating_v": num(find("door", 2, r"Rated operating voltage (\d+) V", 1)),
          "rated_insulation_v_ac": num(find("door", 2, r"Rated insulation voltage (\d+) V AC", 1)),
          "ip": "IP 40" if "IP 40" in t2 else None, "pack_pcs": num(find("door", 2, r"Packs of (\d+) pc", 1)), "page": 2}
    t3 = norm(text("light", 3))
    lt = {"article": find("light", 2, r"(SZ 4140\.820) - LED compact system light", 1),
          "rated_operating_v_dc": num(find("light", 4, r"Rated operating voltage (\d+) V \(DC\)", 1)),
          "current_a": num(find("light", 3, r"With DC ([\d.]+) A", 1)),
          "row_max_a": num(find("light", 3, r"maximum rated current is (\d+) amperes", 1)),
          "leds": num(find("light", 3, r"Number of LEDs (\d+)", 1)),
          "width_mm": num(find("light", 3, r"Width: (\d+) mm", 1)),
          "protection_class": "III (SELV)" if "Protection class III (SELV)" in t3 else None,
          "ip": "IP 20" if "IP 20" in norm(text("light", 4)) else None,
          "pack_pcs": num(find("light", 4, r"Packs of (\d+) pc", 1)), "page": 3}
    return {"door": {("door_switch",): sw}, "light": {("light",): lt}}


# ------------------------------------------------------------------ comparison
def row_id(key: str, r: dict):
    k = r["kind"]
    if key in ("s38", "s39"):
        return {"module": ("module", r.get("article")), "contact": ("contact",), "coil": ("coil", r.get("coil_code")),
                "accessory": ("accessory", r.get("use"))}.get(k)
    if key == "s13":
        return {"latching": ("latching",), "code": ("code",), "wiring": ("wiring",), "function": ("function",),
                "rejected": ("rejected", "13.01")}.get(k)
    if key in ("s40", "s20"):
        return (k,) if k in ("rejected_coil", "rejected_wiring") else None
    if key == "cwes":
        return {"module": ("module", r.get("article")), "contact": ("contact",),
                "accessory": ("accessory", r.get("article"))}.get(k)
    if key == "cwtb":
        return {"terminal": ("terminal", r.get("article")), "jumper": ("jumper", r.get("series")),
                "marker": ("marker", r.get("article")), "end_clamp": ("end_clamp", r.get("article"))}.get(k)
    return (k,)


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, list) and isinstance(b, list):
        return [float(x) for x in a] == [float(x) for x in b]
    return a == b


def statement_found(key: str, r: dict) -> bool:
    t = norm(text(key, r["page"]))
    parts = [norm(p) for p in r["text"].split(" ... ")]
    # tolerate the catalogue's own line breaks / hyphenation and "(RDC)" subscripts
    t2 = t.replace("( R DC )", "(RDC)").replace("R DC", "RDC")
    return all(p in t or p in t2 or p.replace("(RDC)", "(R )") in t for p in parts)


def main():
    extracted = {"s38": ex_finder("s38"), "s39": ex_finder("s39"), "s13": ex_s13(), "s40": ex_s40(), "s20": ex_s20(),
                 "cwes": ex_cwes(), "cwtb": ex_cwtb(), **ex_rittal()}
    out = [f"# Control and signalling — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_control_signalling.py`. Re-extraction with pypdfium2 text (content order) and, for "
           "the Connectwell CP tables and the Finder 13 table, pdfplumber word positions (columns from the printed column "
           "headers, rows from the printed row labels) — independent of the transcription. Every row value is compared.", ""]
    total_mm, total_cmp = 0, 0
    explained: list[str] = []
    for key, fname in FILES.items():
        d = _data(key)
        ex = extracted[key]
        mism, cmp_, unchecked, stm_ok, stm_bad = [], 0, [], 0, []
        for r in d["rows"]:
            if r["kind"] in ("statement", "rejected", "rejected_code") or (key == "s13" and r["kind"] in ("function", "wiring")):
                if r.get("text"):
                    if statement_found(key, r):
                        stm_ok += 1
                    else:
                        stm_bad.append(f"p.{r['page']}: text not found: {r['text'][:70]!r}")
            rid = row_id(key, r)
            p = ex.get(rid) if rid else None
            if rid and p is None and r["kind"] not in ("rejected", "rejected_code", "statement"):
                mism.append(f"{rid}: row not found in the PDF")
                continue
            if p is None:
                continue
            for f, v in r.items():
                if f in DESCRIPTIVE or v is None and f not in p:
                    continue
                if f not in p:
                    unchecked.append(f"{rid[-1]}.{f}")
                    continue
                cmp_ += 1
                if not same(v, p[f]):
                    mism.append(f"{rid[-1]} {f}: file {v!r} / PDF {p[f]!r}")
            if "page" in p and r["page"] != p["page"]:
                mism.append(f"{rid[-1]} page: file {r['page']} / PDF {p['page']}")
        extra = sorted(str(k[-1]) for k in ex if k not in {row_id(key, r) for r in d["rows"]})
        total_mm += len(mism) + len(stm_bad)
        total_cmp += cmp_
        out += [f"## {fname} ({d['source']['ref']})", "",
                f"- rows: {len(d['rows'])}; values compared: {cmp_}; mismatches: **{len(mism)}**; printed statements found "
                f"verbatim: {stm_ok}/{stm_ok + len(stm_bad)}"
                + (f"; printed in the PDF but not transcribed (other coil voltages / types, out of scope): {len(extra)}"
                   f" ({', '.join(extra[:4])}{', …' if len(extra) > 4 else ''})" if extra else "")
                + (f"; not re-extracted (checked on the page image): {', '.join(unchecked)}" if unchecked else "")]
        out += [f"  - {m}" for m in mism + stm_bad]
        out.append("")

    # absence findings
    cw = "\n".join(_doc("cwes")[i].get_textpage().get_text_range() for i in range(len(_doc("cwes"))))
    hits = {w: len(re.findall(w, cw, re.I)) for w in (r"latch", r"bistab", r"monostab", r"\bset\b.{0,20}\breset\b")}
    latch_ctx = [cw[max(0, m.start() - 25):m.end() + 25].replace("\n", " ") for m in re.finditer("latch", cw, re.I)]
    rating_cw = {w: len(re.findall(w, norm(text("cwes", 44)) + norm(text("cwes", 45)))) for w in ("AC15", "AC-15", "AC 15", "DC13", "DC-13", "DC 13")}
    s40_all = "\n".join(_doc("s40")[i].get_textpage().get_text_range() for i in range(len(_doc("s40"))))
    full_bist = re.findall(r"40\.\d\d\.6\.\d{3}\.\d{4}", s40_all)
    s38_39 = {k: len(re.findall(r"bistab|latch", "\n".join(_doc(k)[i].get_textpage().get_text_range()
                                                             for i in range(len(_doc(k)))), re.I)) for k in ("s38", "s39")}
    s13_set = "Only a momentary closure of the Reset switch (R) will open the output contact" in norm(text("s13", 8))
    absent_bad = []
    if any("IDC" not in c for c in latch_ctx) or hits["bistab"] or hits["monostab"]:
        absent_bad.append(f"Connectwell ES: latching wording found outside IDC connectors: {latch_ctx}")
    if any(rating_cw.values()):
        absent_bad.append(f"Connectwell CSR pages carry an AC-15/DC-13 rating: {rating_cw}")
    if full_bist:
        absent_bad.append(f"S40 prints full bistable codes: {full_bist}")
    if any(s38_39.values()):
        absent_bad.append(f"S38/S39 mention bistable/latching: {s38_39}")
    if not s13_set:
        absent_bad.append("S13 p.8: Call & Reset function sentence not found")
    total_mm += len(absent_bad)
    out += ["## Absence findings (whole-document searches)", "",
            f"- Connectwell Electronic Solutions (133 pages): 'latch' ×{hits['latch']} — all in {latch_ctx}; 'bistable' ×{hits['bistab']}, "
            f"'monostable' ×{hits['monostab']}, set…reset ×{hits[r'\bset\b.{0,20}\breset\b']} → **no latching relay**",
            f"- Connectwell CSR slim relay pages 44–45: AC-15 / DC-13 wording: {rating_cw} → **no AC-15 or DC-13 rating**",
            f"- Finder S40: full 40.xx.6 bistable codes printed: {full_bist or 'none'} → code only from the ordering scheme",
            f"- Finder S38 / S39: 'bistable' or 'latch': {s38_39} → **no latching version**",
            f"- Finder S13 p.8 13.11/13.12: 'Only a momentary closure of the Reset switch (R) will open the output contact': {s13_set}"]
    out += [f"  - {m}" for m in absent_bad] + [""]
    out += ["## Notes (explained, not mismatches)", "",
            "- CW-TB p.12 prints Imax 16 A for JX1.5 jumpers on the CP1.5 page; pp. 14–15 print 15 A for the same JX1.5 "
            "jumpers on the CP1.5/3, CP1.5/4 pages. The data file keeps the CP1.5 page value (16 A); the tool only reports it.",
            "- CW-TB p.13 prints end plate EPCX2.5 for CP2.5 (the end-plate list on p.297 names EPCX2.5 for CX2.5); the CP "
            "page is used. CP16's end plate EPCP16 is printed on p.14 only.",
            "- Connectwell prints 'Ambient Operating Temperature -40 to +55 0C' (degree sign as a raised 0); read as +55 °C.",
            "- FINDER-S13 p.11: the '+ (A1)' / '− (A2)' labels of the 13.12 diagram are drawn, not text; the script checks "
            "'Type 13.12', 'Set', 'Reset' as text and the polarity was read on the page image.",
            "- Finder 38 printed page = PDF page − 4; Connectwell printed page = PDF page − 3; Finder 13/20/39/40 and "
            "Rittal printed page = PDF page.", ""]
    out += ["## Result", "", f"Values compared: {total_cmp}. **{total_mm} unexplained mismatches.**", ""]
    (ROOT / "components" / "control_signalling" / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(out))
    return total_mm


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
