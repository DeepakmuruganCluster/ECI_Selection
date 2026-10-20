"""G6 verification of the 3RW52 tables: re-read every value with a second text engine (pdfium) and compare.

    .venv/bin/python scripts/verify_soft_starter.py

The importer reads pdftotext -layout; this script reads the same pages through pypdfium2 and checks that every
value in data/makers/siemens/ic10_3rw52_*.yaml is printed on the page it cites, on the line of its own type.
"""
from __future__ import annotations

import re
from pathlib import Path

import pypdfium2 as pdfium
import yaml

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "sources" / "pdf" / "manufacturer" / "siemens" / "SIRIUS_IC10_complete_English_2026_202601291128292156.pdf"
D = ROOT / "data" / "makers" / "siemens"
doc = pdfium.PdfDocument(str(PDF))
text = {}


def page(p):
    if p not in text:
        text[p] = doc[p - 1].get_textpage().get_text_range().replace("\r", "")
    return text[p]


g = lambda x: f"{x:g}"
bad, n = [], 0
for r in yaml.safe_load((D / "ic10_3rw52_ratings.yaml").read_text())["rows"]:
    t = page(r["page"])
    for c in ("10A", "10E", "20E"):
        im = r[f"im_{c}_a"]
        s = "/".join(g(im[k]) for k in ("40", "50", "60"))
        n += 1
        if s not in t:
            bad.append(f"{r['type']} IM {c} {s} not on p.{r['page']}")
    for s in (f"{g(r['im_min_a'])}/{g(r['im_max_a'])}", f"{g(r['im_min_delta_a'])}/{g(r['im_max_delta_a'])}"):
        n += 1
        if s not in t:
            bad.append(f"{r['type']} range {s} not on p.{r['page']}")
# starts per hour: every row re-read with pdfium, plus the table's own structure (added after the regression audit
# 2026-10-14 found 350 % values filed under 300 % keys where the chapter tab '6' preceded the line)
rat = yaml.safe_load((D / "ic10_3rw52_ratings.yaml").read_text())["rows"]
for pg in sorted({r["page"] for r in rat}):
    types = [r for r in rat if r["page"] == pg]
    cls = pct = None
    for ln in page(pg).split("\n"):
        s = re.sub(r"^6\s+(?=\S)", "", ln.strip())
        cls = "10A" if "(Class 10A)" in s else "10E" if "(Class 10E)" in s else "20E" if "(Class 20E)" in s else cls
        if s.startswith("• 300%") or s.startswith("• 350%"):
            pct = s[2:6]
        m = re.match(r"- Startup time (\d+) s\s+1/h\s+(.*)$", s)
        if m and cls and pct:
            printed = m.group(2).split()
            want = [g(t[f"starts_{cls}_per_h"].get(f"{pct} {m.group(1)} s", -1)) for t in types]
            n += 1
            if printed != want:
                bad.append(f"p.{pg} Class {cls} {pct} {m.group(1)} s: printed {printed}, data {want}")
for r in rat:
    for c in ("10A", "10E", "20E"):
        st = r[f"starts_{c}_per_h"]
        times = sorted({int(k.split()[1]) for k in st})
        n += 1
        if len(st) != 4 or len(times) != 2:
            bad.append(f"{r['type']} Class {c}: starts table has keys {sorted(st)}")
            continue
        for t in times:
            if st[f"300% {t} s"] < st[f"350% {t} s"]:
                bad.append(f"{r['type']} Class {c} {t} s: fewer starts at 300 % than at 350 %")
        for pc in ("300%", "350%"):
            if st[f"{pc} {times[0]} s"] < st[f"{pc} {times[1]} s"]:
                bad.append(f"{r['type']} Class {c} {pc}: fewer starts for the shorter start")
for o in yaml.safe_load((D / "ic10_3rw52_ordering.yaml").read_text())["rows"]:
    line = next((ln for ln in page(o["page"]).split("\n") if o["article"] in ln), "")
    n += 1
    if not (line and o["article_spring"] in line and re.match(rf"\s*{g(o['ie_40_a'])}\s", line)
            and f" {g(o['kw_400v'])} " in f" {line} "):
        bad.append(f"{o['article']} not printed with Ie {o['ie_40_a']} / {o['kw_400v']} kW on p.{o['page']}: {line!r}")
for c in yaml.safe_load((D / "ic10_3rw52_coordination.yaml").read_text())["rows"]:
    line = next((ln for ln in page(c["page"]).split("\n") if ln.strip().startswith(c["type"])), "")
    n += 1
    want = [c["protection"]] + ([str(c["iq_400v_ka"])] if c["kind"] == "mpcb_type1" else [c["line_contactor_480v"]])
    if not line or not all(w in line for w in want):
        bad.append(f"{c['type']} {c['kind']} {want} not on its line p.{c['page']}: {line!r}")
print(f"{n} values checked, {len(bad)} mismatch(es)")
for b in bad:
    print(" ", b)
