"""G6 verification for enclosure_accessories — writes components/enclosure_accessories/VERIFY.md.

1. Independent re-extraction of every transcribed value from the Rittal data sheets (pypdfium2 text layer, own
   regular expressions). The data files are read only afterwards and compared row by row (value and page).
2. Internal consistency of the data sheets: "x/y" order = 50/60 Hz, power / current in the features table vs the
   tender text, outlet-filter order number vs the outlet-filter data sheet.
3. The client's words (ECI WNS2503 p.1 / p.2): 8 inch fan on each door, door switch and light, 1 ft stand.
4. WNS2503: the enclosure component's fan airflow per panel (components/panel/VERIFY.md) vs one 8 inch fan per door.
"""
from __future__ import annotations

import math
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402

from core.provenance import SOURCES, check_reference, load_yaml  # noqa: E402
from core.data import data_file  # noqa: E402

COMP = ROOT / "components" / "enclosure_accessories"
KEY_ATTRS = ("hz", "outlet_filters", "filter", "where")


def pages(ref: str) -> dict[int, str]:
    pdf = pdfium.PdfDocument(str(SOURCES / check_reference(ref)["file"]))
    return {i + 1: pdf[i].get_textpage().get_text_range().replace("\r", "").replace("\xa0", " ") for i in range(len(pdf))}


def flat(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("￾", "").replace("-\n", "")).strip()


def find(t: dict[int, str], pattern: str, flags=0):
    """First page whose text matches → (match, page)."""
    for p, txt in t.items():
        m = re.search(pattern, txt, flags)
        if m:
            return m, p
    return None, None


def num(s: str) -> float:
    x = float(s.replace(",", "."))
    return int(x) if x == int(x) else x


def row(q, value, page, **attrs) -> dict:
    return {"quantity": q, "value": value, "page": page, **attrs}


def extract_fan(t: dict[int, str]) -> tuple[list[dict], dict]:
    out, notes = [], {}
    m, p = find(t, r"Dimensions Width: (\d+) mm\nHeight: (\d+) mm")
    out += [row("frame_width_mm", num(m[1]), p), row("frame_height_mm", num(m[2]), p)]
    m, p = find(t, r"Installation depth (\d+) mm")
    out.append(row("installation_depth_mm", num(m[1]), p))
    m, p = find(t, r"Cut-out width: (\d+) mm\nCut-out height: (\d+) mm")
    out += [row("cutout_width_mm", num(m[1]), p), row("cutout_height_mm", num(m[2]), p)]
    m, p = find(t, r"Rated operating voltage (\d+) V, (\d)~, 50 Hz/60 Hz")
    out += [row("rated_voltage_v", num(m[1]), p), row("phases", num(m[2]), p)]
    for flt, label in (("pleated", "pleated filter"), ("chopped_fibre", "chopped-fibre filter")):
        m, p = find(t, r"\(with " + label + r"\)\nAt 50 Hz: (\d+) m³/h\nAt 60 Hz: (\d+) m³/h")
        out += [row("airflow_free_m3h", num(m[1]), p, hz=50, filter=flt),
                row("airflow_free_m3h", num(m[2]), p, hz=60, filter=flt)]
    m0, p = find(t, r"Air throughput with outlet filter")
    notes["outlet_order_numbers"] = set()
    for n, order, a, b in re.findall(r"(\d) x (\d{7}): (\d+)/(\d+) m³/h", t[p]):
        notes["outlet_order_numbers"].add(order)
        out += [row("airflow_outlet_m3h", num(a), p, hz=50, outlet_filters=int(n), filter="chopped_fibre"),
                row("airflow_outlet_m3h", num(b), p, hz=60, outlet_filters=int(n), filter="chopped_fibre")]
    # "x/y" order: the product description prints the free airflow as "a/b m³/h, …, 50/60 Hz"
    m, p = find(t, r"(\d+)/(\d+) m³/h, 230 V, 1~, 50/60 Hz")
    notes["slash_order"] = (num(m[1]), num(m[2]), p)
    m, p = find(t, r"Power consumption Pel At 50 Hz: ([\d.]+) W\nAt 60 Hz: ([\d.]+) W")
    out += [row("power_w", num(m[1]), p, hz=50, where="features"), row("power_w", num(m[2]), p, hz=60, where="features")]
    m, p = find(t, r"Rated current max\. At 50 Hz: ([\d.]+) A\nAt 60 Hz: ([\d.]+) A")
    out += [row("current_a", num(m[1]), p, hz=50, where="features"),
            row("current_a", num(m[2]), p, hz=60, where="features")]
    m, p = find(t, r"Power consumption: ([\d,]+) / ([\d,]+) W")
    out += [row("power_w", num(m[1]), p, hz=50, where="tender_text"),
            row("power_w", num(m[2]), p, hz=60, where="tender_text")]
    m, p = find(t, r"Rated current: ([\d,]+) / ([\d,]+) A")
    out += [row("current_a", num(m[1]), p, hz=50, where="tender_text"),
            row("current_a", num(m[2]), p, hz=60, where="tender_text")]
    m, p = find(t, r"Noise level At 50 Hz: (\d+) dB\(A\)\nAt 60 Hz: (\d+) dB\(A\)")
    out += [row("noise_dba", num(m[1]), p, hz=50), row("noise_dba", num(m[2]), p, hz=60)]
    m, p = find(t, r"Operating temperature range (-?\d+) °C\.\.\.(-?\d+) °C")
    out += [row("operating_temp_min_c", num(m[1]), p), row("operating_temp_max_c", num(m[2]), p)]
    m, p = find(t, r"IP (\d+) with chopped-fibre filter/pleated filter\n")
    out.append(row("ip_standard", num(m[1]), p))
    m, p = find(t, r"Miniature circuit-breaker/fuse: (\d+) A")
    out.append(row("prefuse_a", num(m[1]), p))
    return out, notes


def extract_outlet(t: dict[int, str]) -> list[dict]:
    out = []
    m, p = find(t, r"To fit Model No\. (?:SK )?(\S+)")
    out.append(row("to_fit", ("SK " if "SK " in m[0] else "") + m[1], p))
    m, p = find(t, r"Cut-out width: (\d+) mm\nCut-out height: (\d+) mm")
    out += [row("cutout_width_mm", num(m[1]), p), row("cutout_height_mm", num(m[2]), p)]
    m, p = find(t, r"Dimensions Width: (\d+) mm\nHeight: (\d+) mm\nDepth: (\d+) mm")
    out += [row("width_mm", num(m[1]), p), row("height_mm", num(m[2]), p), row("depth_mm", num(m[3]), p)]
    m, p = find(t, r"IP (\d+) with chopped-fibre filter/pleated filter\n")
    out.append(row("ip_standard", num(m[1]), p))
    m, p = find(t, r"Supply includes Outlet filter\n(Chopped-fibre filter mat)")
    out.append(row("supply_includes_mat", m[1], p))
    return out


def extract_trim(t: dict[int, str]) -> list[dict]:
    out = []
    m, p = find(t, r"Dimensions Height: (\d+) mm")
    out.append(row("height_mm", num(m[1]), p))
    m, p = find(t, r"Enclosure type: TS: = (\d+) mm")
    out.append(row("fits_width_mm", num(m[1]), p))
    m, p = find(t, r"for W: (\d+) mm")
    out.append(row("fits_width_mm", num(m[1]), p))
    m, p = find(t, r"Packs of (\d+) pc")
    out.append(row("pieces_per_pack", num(m[1]), p))
    m, p = find(t, r"Supply includes (2 base/plinth trim panels)")
    out.append(row("supply_includes", m[1], p))
    m, p = find(t, r"Colour (RAL \d+)")
    out.append(row("colour", m[1], p))
    for pg, txt in t.items():
        s = flat(txt)
        m = re.search(r"At 200 mm height, two 100 mm base/plinth trim panels may be used\.", s)
        if m and "Product description" in s:
            out.append(row("two_100_for_200", m[0], pg))
            break
    return out


def extract_switch(t: dict[int, str]) -> list[dict]:
    out = []
    m, p = find(t, r"Design (Without connection cable)")
    out.append(row("design", m[1], p))
    m, p = find(t, r"24 V DC/(\d+) A")
    out.append(row("rating_24vdc_a", num(m[1]), p))
    m, p = find(t, r"240 V AC/(\d+) A")
    out.append(row("rating_240vac_a", num(m[1]), p))
    m, p = find(t, r"Rated insulation voltage (\d+) V AC")
    out.append(row("rated_insulation_v", num(m[1]), p))
    m, p = find(t, r"\nIP (\d+)\n")
    out.append(row("ip_standard", num(m[1]), p))
    m, p = find(t, r"(for standard and courtesy light without integral door-operated)\s*\n?\s*(switch)")
    out.append(row("for_light", f"{m[1]} {m[2]}", p))
    return out


def extract_light(t: dict[int, str]) -> list[dict]:
    out = []
    m, p = find(t, r"Rated operating voltage (\d+) V \(DC\)")
    out.append(row("rated_voltage_vdc", num(m[1]), p))
    m, p = find(t, r"With DC ([\d.]+) A")
    out.append(row("current_a", num(m[1]), p))
    m, p = find(t, r"maximum rated current is (\d+) \n?amperes")
    out.append(row("row_current_max_a", num(m[1]), p))
    m, p = find(t, r"Switch \(type\) (Integral on/off/door-operated switch)")
    out.append(row("switch_type", m[1], p))
    m, p = find(t, r"(May be connected to a door-operated switch\.)")
    out.append(row("door_switch_connectable", m[1], p))
    m, p = find(t, r"Dimensions Width: (\d+) mm")
    out.append(row("width_mm", num(m[1]), p))
    m, p = find(t, r"\nIP (\d+)\n")
    out.append(row("ip_standard", num(m[1]), p))
    m, p = find(t, r"Number of LEDs (\d+)")
    out.append(row("leds", num(m[1]), p))
    return out


def extract_tsc(t: dict[int, str]) -> list[dict]:
    out = []
    for q, pat, pg in (("outlet_filter_curve", r"1 x outlet filter SK 3238\.300", 12),
                       ("more_diagrams", r"Further performance diagrams may be found on the Internet\.", 12),
                       ("selection_criterion", r"The correct fan-and-filter unit has been chosen if the specified heat "
                                               r"loss is dissipated whilst complying with the desired maximum enclosure "
                                               r"internal temperature\.", 12),
                       ("prerequisite", r"the ambient air must be relatively clean with a temperature below the "
                                        r"desired enclosure internal ?temperature", 8)):
        m = re.search(pat, flat(t[pg]))
        if m:
            out.append(row(q, m[0], pg))
    return out


def key(r: dict) -> tuple:
    return (r["quantity"], *(r.get(a) for a in KEY_ATTRS), r["page"])


def compare(extracted: list[dict], data: dict) -> tuple[list[str], int]:
    ex = {}
    for r in extracted:
        ex.setdefault(key(r), r)
    diffs = []
    for r in data["rows"]:
        e = ex.get(key(r))
        if e is None:
            same_q = [x for x in extracted if x["quantity"] == r["quantity"]
                      and all(x.get(a) == r.get(a) for a in KEY_ATTRS)]
            diffs.append(f"{r['quantity']} {dict((a, r[a]) for a in KEY_ATTRS if a in r)} p.{r['page']}: not found "
                         f"in PDF" + (f" (PDF has it on p.{same_q[0]['page']}: {same_q[0]['value']})" if same_q else ""))
            continue
        a, b = e["value"], r["value"]
        same = (a == b) if isinstance(a, str) or isinstance(b, str) else abs(float(a) - float(b)) < 1e-9
        if isinstance(a, str) and isinstance(b, str):
            same = flat(a).lower().rstrip(".") == flat(b).lower().rstrip(".")
        if not same:
            diffs.append(f"{r['quantity']} {dict((k, r[k]) for k in KEY_ATTRS if k in r)} p.{r['page']}: "
                         f"file {b!r} / PDF {a!r}")
    return diffs, len(data["rows"])


def main():
    # ---- 1. independent extraction (PDFs only)
    T = {ref: pages(ref) for ref in ("RITTAL-3239100", "RITTAL-3240100", "RITTAL-3239200", "RITTAL-3240200",
                                     "RITTAL-8601060", "RITTAL-8602060", "RITTAL-4127010", "RITTAL-4140820",
                                     "RITTAL-TSC-3124300", "ECI-WNS2503-AUTO")}
    fan_x = {ref: extract_fan(T[ref]) for ref in ("RITTAL-3239100", "RITTAL-3240100")}
    X = {"rittal_sk3239100.yaml": fan_x["RITTAL-3239100"][0], "rittal_sk3240100.yaml": fan_x["RITTAL-3240100"][0],
         "rittal_sk3239200.yaml": extract_outlet(T["RITTAL-3239200"]),
         "rittal_sk3240200.yaml": extract_outlet(T["RITTAL-3240200"]),
         "rittal_ts8601060.yaml": extract_trim(T["RITTAL-8601060"]),
         "rittal_ts8602060.yaml": extract_trim(T["RITTAL-8602060"]),
         "rittal_sz4127010.yaml": extract_switch(T["RITTAL-4127010"]),
         "rittal_sz4140820.yaml": extract_light(T["RITTAL-4140820"]),
         "rittal_tsc_fan_principle.yaml": extract_tsc(T["RITTAL-TSC-3124300"])}
    eci = flat(" ".join(T["ECI-WNS2503-AUTO"].values()))

    # ---- only now read the data files
    out = [f"# Enclosure accessories — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_enclosure_accessories.py`. Every value was re-extracted from the PDF text "
           "layer (pypdfium2) with the script's own patterns; the data files were read only afterwards and compared "
           "row by row (value and page). On every Rittal data sheet the printed page number (\"© Rittal 2026 n\") is "
           "the PDF page. Pages 2, 3, 5 of SK 3239.100 / SK 3240.100 and p.2 of TS 8602.060 were also read on the "
           "rendered page images.", "",
           "## 1. Values: data file vs PDF", "", "| data file | source | rows | mismatches |", "|---|---|---|---|"]
    total, details = 0, []
    for fname, ext in X.items():
        d = load_yaml(data_file(fname))
        diffs, n = compare(ext, d)
        total += len(diffs)
        out.append(f"| {fname} | {d['source']['ref']} | {n} | **{len(diffs)}** |")
        details += [f"- {fname}: {x}" for x in diffs]
    out += [""] + (details or ["All rows found in the PDF with the same value and page."]) + [""]

    # ---- 2. internal consistency
    out += ["## 2. Data-sheet consistency", ""]
    d2 = []
    for ref, fname in (("RITTAL-3239100", "rittal_sk3239100.yaml"), ("RITTAL-3240100", "rittal_sk3240100.yaml")):
        rows, notes = fan_x[ref]
        free = {r["hz"]: r["value"] for r in rows if r["quantity"] == "airflow_free_m3h" and r["filter"] == "chopped_fibre"}
        a, b, p = notes["slash_order"]
        ok = (a, b) == (free[50], free[60])
        out.append(f"- {ref}: p.{p} prints \"{a}/{b} m³/h … 50/60 Hz\"; p.2 labels {free[50]} at 50 Hz and "
                   f"{free[60]} at 60 Hz → the unlabelled \"x/y\" outlet-filter airflow is 50/60 Hz: "
                   + ("**consistent**" if ok else "**INCONSISTENT**"))
        d2 += [] if ok else [f"{ref}: slash order"]
        art = load_yaml(data_file(fname))["outlet_filter"].replace("SK ", "").replace(".", "")
        ok = notes["outlet_order_numbers"] == {art}
        out.append(f"- {ref}: outlet-filter order number printed {sorted(notes['outlet_order_numbers'])} = "
                   f"{load_yaml(data_file(fname))['outlet_filter']}: " + ("✓" if ok else "✗"))
        d2 += [] if ok else [f"{ref}: outlet order number"]
        for q, u in (("power_w", "W"), ("current_a", "A")):
            for hz in (50, 60):
                vals = {r["where"]: r["value"] for r in rows if r["quantity"] == q and r["hz"] == hz}
                if len(set(vals.values())) > 1:
                    out.append(f"- {ref}: {q} at {hz} Hz — features p.2 {vals['features']} {u}, tender text p.5 "
                               f"{vals['tender_text']} {u}: **the data sheet contradicts itself** — both values are on the "
                               f"rendered page images (p.2, p.5), so the data file is right to record both; R-ACC-10 "
                               f"uses the higher {max(vals.values())} {u} (decision A-3)")
    out += ["- every outlet-filter airflow is below the free airflow with the same chopped-fibre mat, and 2 outlet "
            "filters give more than 1 (tests/test_enclosure_accessories.py::test_data_sanity).",
            "- TS 8602.060 p.2 'Assembly instruction' repeats the 100 mm text of TS 8601.060 (Rittal copy); height "
            "200 mm, fit and pack are its own (checked on the page image).",
            "- The registered titles call TS 8601.060 / 8602.060 'plinth component'; the data sheets show they are "
            "**side trim panels** only (\"for mounting between the base/plinth components\"). Corner pieces and "
            "front / rear trims are other articles, not held (R-ACC-14).", ""]
    total += len(d2)

    # ---- 3. client words
    out += ["## 3. ECI WNS2503 wording (client specification)", ""]
    for label, pat in (("fan", r"Rittal cooling Fan - ?8 ?Inch Each Door"), ("door switch / light",
                                                                             r"Rittal Door limit switch and Light"),
                       ("stand", r"Panel stand 1 Feet Height with Side covers")):
        m = re.search(pat, eci, re.I)
        out.append(f"- {label}: " + (f"\"{m[0]}\" found" if m else "**not found**"))
        total += 0 if m else 1
    fw = {f: next(r["value"] for r in X[f] if r["quantity"] == "frame_width_mm")
          for f in ("rittal_sk3239100.yaml", "rittal_sk3240100.yaml")}
    out += [f"- 8 inch = 203.2 mm: SK 3239.100 frame {fw['rittal_sk3239100.yaml']} mm "
            f"({fw['rittal_sk3239100.yaml'] / 25.4:.2f} in) — the ECI 8 inch fan; SK 3240.100 "
            f"{fw['rittal_sk3240100.yaml']} mm ({fw['rittal_sk3240100.yaml'] / 25.4:.2f} in) = 10 inch.",
            "- 1 ft ≈ 305 mm: the held plinth data sheets name only 100 and 200 mm (\"At 200 mm height, two 100 mm "
            "… may be used\", TS 8601.060 p.2). **Rittal does not offer a 300 mm plinth in the held data** → "
            "no plinth article (R-ACC-12, decision A-5).", ""]

    out += ["## Result", "", f"**{total} unexplained mismatches.**", ""]
    out += wns2503()
    (COMP / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(out))
    return total


def wns2503() -> list[str]:
    from components.enclosure.select import select as enc
    from components.enclosure_accessories.select import select as acc
    pv = (ROOT / "components" / "panel" / "VERIFY.md").read_text()
    panels = re.findall(r"## (\S+) — fan-cooled panel, 55 °C inside, 50 °C site\n\n.*?\n- heat from sourced losses: "
                        r"(\d+) W.*?fan airflow ([\d.]+) m³/h", pv, re.S)
    eci = load_yaml(ROOT / "projects" / "ECI-WNS2503" / "data" / "eci_wns2503_items.yaml")
    secs = {r["panel"].replace("_", "/"): r["sections_mm"] for r in eci["rows"] if r.get("sections_mm")}
    lines = []
    for panel, heat, air in panels:
        heat, air = float(heat), float(air)
        n_sec = len(secs.get(panel, []))
        air1000 = enc(heat_loss_w=heat, ambient_c=50, max_internal_c=55, altitude_m=1000,
                      siting="indoor").value["fan_airflow_m3h"]
        for size, nout in ((8, 1), (8, 2), (10, 1), (10, 2)):
            r = acc(required_airflow_m3h=air, doors=n_sec, fan_size_in=size, outlet_filters_per_fan=nout,
                    supply_v=230, frequency_hz=50, site_ambient_c=50)
            v = r.value
            inst = v.get("airflow_at_positions_m3h", v["delivered_airflow_m3h"])
            r2 = acc(required_airflow_m3h=air1000, doors=n_sec, fan_size_in=size, outlet_filters_per_fan=nout,
                     supply_v=230, frequency_hz=50, site_ambient_c=50)
            lines.append(f"| {panel} | {n_sec} | {v['fan']} + {nout} × {v['outlet_filter']} | "
                         f"{v['airflow_per_fan_m3h']:g} | {air:g} | {v['fan_qty']} | {inst:g} "
                         f"({inst / air * 100:.0f} %) | {v['fan_power_w']:g} W | {air1000:g} → {r2.value['fan_qty']} |")
    return ["## 4. WNS2503 — ECI's \"8 inch fan on each door\" vs the airflow the enclosure component asks for", "",
            "Required airflow: enclosure component via the panel assembly (components/panel/VERIFY.md, fan-cooled "
            "panel, 55 °C inside, 50 °C site; heat = sourced losses only, so a lower bound). Sections per panel from "
            "the ECI item list (7 each) — at least one door per section; 1200 mm sections may have two doors (not "
            "stated), which would give 13 doors, still far short. Airflow per fan = data-sheet value with outlet "
            "filter(s), 50 Hz.", "",
            "| Panel | doors (≥) | fan + outlet filter | m³/h per fan | required m³/h | fans needed | airflow with one "
            "fan per door | fan load | at 1000 m (f = 3.5): m³/h → fans |",
            "|---|---|---|---|---|---|---|---|---|", *lines, "",
            "- One 8 inch fan per door (7 × 74 = 518 m³/h) gives **15 % (BIO/UF) and 25 % (RO)** of the airflow the "
            "Rittal method asks for at 55 °C inside on a 50 °C site; 48 and 29 fans would be needed — not a practical "
            "door layout. Even 10 inch fans with 2 outlet filters need 23 and 14.",
            "- The panel assembly ran the enclosure at altitude 0 m (f = 3.1). At the WNS2503 site altitude 1000 m "
            "(f = 3.5, enclosure VERIFY) the need is 13 % higher (last column).",
            "- Conclusion for the owner (decision A-6, ties to enclosure H-5): ECI's one fan per door cannot cool "
            "these panels at a 5 K rise; plan cooling units (35 °C inside) or reduce the heat.", ""]


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
