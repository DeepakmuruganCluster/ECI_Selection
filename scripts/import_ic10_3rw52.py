"""Import the SIRIUS 3RW52 General Performance soft starter tables of Catalog IC 10 · 2026 (pages 6/59 to 6/70).

    .venv/bin/python scripts/import_ic10_3rw52.py

Source: SIE-IC10-2026 (stored PDF), text layer read with pdftotext -layout one page at a time; every row keeps its
PDF page and printed page. Three tables, one per kind of data:
  ic10_3rw52_ratings.yaml       "General data" (PDF pp. 491-494, printed 6/59-6/62): rated operational current Ie,
                                rated motor current IM at 40/50/60 °C for Class 10A / 10E / 20E, permissible starts per
                                hour (ON period 70 %, motor protection on), adjustable IM range inline and inside-delta.
  ic10_3rw52_ordering.yaml      "Selection and ordering data", standard (inline) circuit, Class 10A (PDF pp. 499-502,
                                printed 6/67-6/70): article (screw / spring), Ie at 40 °C, kW at 230/400/500 V,
                                control supply, operational voltage range, analog output or thermistor version.
  ic10_3rw52_coordination.yaml  Motor feeders according to IEC (PDF pp. 495-497, printed 6/63-6/65): Type 1 with
                                3RV2 / 3VA (Q1 + Iq at 400 V), Type 1 with 3NA3 gG fuses (Iq 65 kA), Type 2 with 3NE1
                                gR/gS fuses (Iq 65 kA), with the optional line contactor type for systems up to 480 V.
Values are copied as printed; nothing is interpolated.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "sources" / "pdf" / "manufacturer" / "siemens" / "SIRIUS_IC10_complete_English_2026_202601291128292156.pdf"
OUT = ROOT / "data" / "makers" / "siemens"
TYPE = r"3RW52\d\d"


def page(p: int) -> str:
    return subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(PDF), "-"],
                          capture_output=True, text=True, check=True).stdout


def printed(text: str) -> str:
    m = re.search(r"(6/\d+)\s+Siemens IC 10|Siemens IC 10 · 2026\s+(6/\d+)", text)
    return (m.group(1) or m.group(2)) if m else None


def triple(s: str) -> list[float]:
    return [float(x) for x in s.split("/")]


def num(s: str):
    return None if s in ("--", "") else (float(s) if "." in s else int(s))


# ---------------------------------------------------------------- ratings (General data)
def ratings():
    out = []
    for p in range(491, 495):
        t = page(p)
        if "Rated operational current Ie" not in t:
            continue
        lines = t.split("\n")
        types = []
        for ln in lines:
            if "Rated operational current Ie" in ln:
                break
            types += re.findall(TYPE, ln)
        n = len(types)
        vals = lambda ln: re.findall(r"(?<![\w/.])(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)*)(?![\w/])", ln.split("  ", 1)[-1])[-n:]
        blocks, cls, rec, ie, rng, rng_d = {}, None, None, None, None, None
        for i, ln in enumerate(lines):
            # the chapter tab '6' printed in the margin sits in front of some lines ("6   • 350% IM"): drop it
            s = re.sub(r"^6\s{2,}(?=\S)", "", ln.strip())
            if s.startswith("Rated operational current Ie"):
                ie = vals(ln)
            elif s.startswith("Normal starting (Class 10A)"):
                cls = "10A"
            elif s.startswith("Normal starting (Class 10E)"):
                cls = "10E"
            elif s.startswith("Heavy starting (Class 20E)"):
                cls = "20E"
            elif s.startswith("Rated motor current IM") and cls:
                blocks[cls] = {"im": vals(ln), "starts": {}}
            elif s.startswith("• 300% IM") or s.startswith("• 350% IM"):
                rec = s[2:6]
            elif s.startswith("- Startup time") and cls and rec:
                t_s = re.search(r"Startup time (\d+) s", s).group(1)
                blocks[cls]["starts"][f"{rec} {t_s} s"] = vals(ln)
            elif s.startswith("• Minimum/maximum in inside-delta"):
                rng_d = vals(ln)
            elif s.startswith("• Minimum/maximum"):
                rng = vals(ln)
        assert len(ie) == n and rng and rng_d, (p, types, ie)
        for k, ty in enumerate(types):
            row = {"type": ty, "ie_a": num(ie[k])}
            for c, b in blocks.items():
                im = triple(b["im"][k])
                row[f"im_{c}_a"] = {"40": im[0], "50": im[1], "60": im[2]}
                row[f"starts_{c}_per_h"] = {key: float(v[k]) if "." in v[k] else int(v[k]) for key, v in b["starts"].items()}
            lo, hi = triple(rng[k]); dlo, dhi = triple(rng_d[k])
            row.update({"im_min_a": lo, "im_max_a": hi, "im_min_delta_a": dlo, "im_max_delta_a": dhi,
                        "page": p, "printed": printed(t)})
            out.append(row)
    return out


# ---------------------------------------------------------------- ordering (inline, Class 10A)
ORD = re.compile(rf"^\s*(?P<ie>\d+(?:\.\d+)?)\s+(?P<kw230>\S+)\s+(?P<kw400>\S+)\s+(?P<kw500>\S+)\s+(?P<ie50>\S+)\s+"
                 rf"\S+\s+\S+\s+\S+\s+\S+\s+(?P<screw>{TYPE}-\d[AT]C\d\d)\s+(?P<spring>{TYPE}-\d[AT]C\d\d)\s*$")


def ordering():
    out = []
    for p in range(499, 503):
        t = page(p)
        ue = "200-600" if "Operational voltage 200 ... 600 V" in t else "200-480"
        func = "thermistor" if "Thermistor motor protection" in t else "analog output"
        us = None
        for ln in t.split("\n"):
            if "Control supply voltage 24 V AC/DC" in ln:
                us = "24 V AC/DC"
            elif "Control supply voltage 110" in ln:
                us = "110-250 V AC"
            elif m := ORD.match(ln):
                out.append({"article": m["screw"], "article_spring": m["spring"], "type": m["screw"][:7],
                            "model": f"SIRIUS 3RW52 soft starter {m['screw'][:7]}, Ie {m['ie']} A, {func}, Us {us}, Ue {ue} V",
                            "ie_40_a": num(m["ie"]), "ie_50_a": num(m["ie50"]), "kw_230v": num(m["kw230"]),
                            "kw_400v": num(m["kw400"]), "kw_500v": num(m["kw500"]), "control_supply": us,
                            "operational_voltage": ue, "function": func, "circuit": "inline", "page": p,
                            "printed": printed(t)})
    return out


# ---------------------------------------------------------------- coordination
def coordination():
    out = []
    for p in range(494, 499):
        t = page(p)
        if "3RV2 motor starter protectors/3VA circuit breakers" in t and "Type of coordination \"1\"" in t:
            kind = "mpcb_type1"
        elif "3NA3 fuses" in t:
            kind = "gG_fuse_type1"
        elif "3NE1 SITOR fuses" in t:
            kind = "gRgS_fuse_type2"
        else:
            continue
        for ln in t.split("\n"):
            s = ln.strip()
            if not re.match(TYPE + r"\s", s):
                continue
            f = re.split(r"\s{2,}", s)
            ty = f[0]
            if kind == "mpcb_type1":
                # Q1 400 V, Iq, Q1 500 V, Iq | inside-delta: Q1 400 V, Iq, Q1 500 V, Iq
                out.append({"type": ty, "kind": kind, "circuit": "inline", "protection": f[1], "iq_400v_ka": num(f[2]),
                            "protection_500v": None if f[3] == "--" else f[3], "iq_500v_ka": num(f[4]),
                            "protection_delta": f[5], "iq_delta_400v_ka": num(f[6]), "page": p, "printed": printed(t)})
            elif kind == "gG_fuse_type1":
                fuse = f[1]
                n = 2 if fuse.startswith("2 x ") else 1
                out.append({"type": ty, "kind": kind, "circuit": "inline", "protection": fuse.removeprefix("2 x "),
                            "fuses_in_parallel": n, "iq_400v_ka": 65, "line_contactor_480v": f[2],
                            "line_contactor_600v": f[3], "page": p, "printed": printed(t)})
            else:
                fuse = f[1]
                note = "for systems up to 500 V (footnote 1)" if fuse.endswith("1)") else None
                out.append({"type": ty, "kind": kind, "circuit": "inline", "protection": fuse.removesuffix("1)"),
                            "fuses_in_parallel": 1, "iq_400v_ka": 65, "line_contactor_480v": f[2],
                            "line_contactor_600v": f[3], "note": note, "page": p, "printed": printed(t)})
    return out


def write(name: str, section: str, note: str, rows: list[dict]) -> None:
    head = f"# Generated by scripts/import_ic10_3rw52.py — do not edit by hand.\n"
    body = yaml.safe_dump({"source": {"ref": "SIE-IC10-2026", "section": section, "note": note}, "rows": rows},
                          sort_keys=False, allow_unicode=True, width=160)
    (OUT / name).write_text(head + body)
    print(name, len(rows), "rows")


if __name__ == "__main__":
    write("ic10_3rw52_ratings.yaml", "SIRIUS 3RW52 soft starters > General data: power electronics, permissible rated motor current and starts/h",
          "'page' = PDF page, 'printed' = catalogue page. IM in A at Tu = 40/50/60 °C, individual mounting; starts/h at ON period 70 %, "
          "motor protection activated, keyed '<starting current> <startup time>'.", ratings())
    write("ic10_3rw52_ordering.yaml", "SIRIUS 3RW52 soft starters > Standard (inline) circuit: selection and ordering data, normal starting (Class 10A)",
          "'page' = PDF page, 'printed' = catalogue page. kW are Siemens' rough guide values (p. 6/8); selection is on current.", ordering())
    write("ic10_3rw52_coordination.yaml", "SIRIUS 3RW52 soft starters > General data: motor feeders according to IEC (types of coordination)",
          "'page' = PDF page, 'printed' = catalogue page. Line contactor (Q21) is optional; its coil code is not in this table.", coordination())
