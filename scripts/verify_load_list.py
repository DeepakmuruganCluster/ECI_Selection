"""G6 for the load-list import — writes components/load_list/VERIFY.md.

1. Row by row against v1's Layer 0 feeders (an independent implementation that read the PDF master):
   tag, panel, starter, kW, qty, standby, phases, client FLC, client MPCB range.
2. Against the client's equipment PDF (ECI-WNS2503-EQUIP), field by field and item wording.
3. The imported load list through the panel component, next to scripts/verify_panel.py's v1 load list,
   with the same inputs. Every difference must have an explanation below, else the script exits 1.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from components.load_list.select import _members, select  # noqa: E402
from components.panel.select import select as panel_select  # noqa: E402
from scripts.verify_panel import V1_JSON, load_lists as v1_load_lists  # noqa: E402

PANEL_KW = dict(fault_ka=50, panel_internal_c=35, motor_pf=0.85, cable_ambient_c=40, site_ambient_c=50,
                line_reactor_up_to_kw=15)

# Every expected difference, with the document cells that decide it.
EXPLAIN = {
    ("v1", "K101A/B"): "Word table 1 row 3 says 18.5 kW / 35.17 A / Total KW 37; the PDF (p.1 S.NO 3) says 15 kW / 28.52 A / "
                       "30, and its BIO/UF Total KW 264.1 adds up only with 15 kW. Each document is consistent with itself, "
                       "so neither can be called right: **ask ECI** (decision L-1). v1 used the PDF; v2 uses the Word list "
                       "it imports and warns (R-LL-15).",
    ("v1", "P102A/B"): "Word table 1 row 31 says 3PH 400V 50HZ; the PDF (p.1 S.NO 9) says 1PH 230V 50HZ in a shaded cell (an "
                       "edit). Both give 1.43 A, which is the client's figure for a 0.75 kW **three-phase** motor (P413A/B, "
                       "3PH, 0.75 kW: 1.43 A too); a 0.75 kW single-phase 230 V motor draws several times that. The Word value agrees "
                       "with the current, but the PDF edit looks deliberate: **ask ECI** (decision L-2). v1 used the PDF.",
    ("v1", "P410A/B"): "Word table 1 row 40 'Sodium Hydroxide Dosing For UF CEB' is P410A/B (marking P410A & P410B); the PDF "
                       "p.1 S.NO 16 calls the same item P411A/B (marking P411A & P411B). Each consistent with itself: "
                       "**ask ECI** (L-6). v1 used the PDF tag. Same kW, qty, supply, current.",
    ("v1", "P701A/B"): "Word table 1 row 49 is P701A/B (marking P701A&P701B, 'Coagulant Dosing Pump'); the PDF p.2 S.NO 7 "
                       "writes Instrument ID P419A/B but **its own Group Marking is P701A&P701B** ('ferrichloride Dosing "
                       "Pump'). Three of four cells say P701: the Word tag is the better reading. v1 used P419A/B.",
    ("v1", "P703A/B"): "Word table 1 row 51 is P703A/B (marking P703A&P703B); the PDF p.2 S.NO 9 writes P418A/B but its own "
                       "Group Marking is P703A&P703B. The Word tag is the better reading. v1 used P418A/B.",
    ("pdf", "K101A/B"): "see v1 K101A/B",
    ("pdf", "P102A/B"): "see v1 P102A/B",
    ("pdf", "P410A/B"): "see v1 P410A/B",
    ("pdf", "P701A/B"): "see v1 P701A/B",
    ("pdf", "P703A/B"): "see v1 P703A/B",
    ("item", "P701A/B"): "Ferric chloride is a coagulant: wording only (the tag question is in section 1).",
    ("item", "P502A/B"): "Wording only; kW, current and tags agree. Different chemicals, so worth a line in the ECI query.",
    ("item", "P505A/B"): "Wording only; kW, current and tags agree. Worth a line in the ECI query.",
    ("panel", "BIO_UF"): "n_selected 27 vs 26: P102A/B is 3-phase in the Word list, so the motor-current component gives a "
                         "guide value and the DOL starter is selected; v1's list made it single-phase, which needs a "
                         "nameplate current and stays open. Heat 4320 vs 4120 W: K101A/B is an 18.5 kW drive (running "
                         "loss larger) instead of 15 kW. Open-point count equal (47): P102A/B's refusal is replaced by "
                         "the selected DOL's 'confirm with the nameplate' warning.",
    ("panel", "RO"): "32 vs 31 lines, 58 vs 54 units, n_selected 21 vs 20: verify_panel.py drops v1's spare row, but ECI "
                     "counts 'Extra DOL' P507A/B/C/D (4 × 4 kW) in its 'RO Panel Total DOL … 40', so v2 keeps it "
                     "(R-LL-04, decision L-5) and its 4 DOL starters are selected (+2 open points: the DOL component's link-module note R-DOL-08 and 'confirm with the nameplate' R-DOL-09). "
                     "Heat equal.",
}


def compare_v1(rows: list[dict]) -> tuple[list[list[str]], list[tuple]]:
    v1 = json.loads(V1_JSON.read_text())["feeders"]
    used, table, diffs = set(), [], []
    for o in rows:
        base = o["tag"].rsplit("_", 1)[0] if o["tag"].endswith(("_2", "_3")) else o["tag"]
        i = next((i for i, f in enumerate(v1) if i not in used and f["panel"].replace("/", "_") == o["panel"]
                  and set(f["tags"]) == set(_members(base))), None)
        if i is None:   # the same row under another tag (v1 read the PDF)
            i = next((i for i, f in enumerate(v1) if i not in used and f["panel"].replace("/", "_") == o["panel"]
                      and o.get("pdf_tag") and set(f["tags"]) == set(_members(o["pdf_tag"]))), None)
        if i is None:
            diffs.append(("v1", o["tag"], "row not in v1"))
            continue
        used.add(i)
        f = v1[i]
        v1_starter = "HEATER" if f["load_type"] == "heater" else f["starter"]
        rc = tuple(f["range_client"]) if f["range_client"] else (None, None)
        d = [f"{lbl} {a} ≠ v1 {b}" for lbl, a, b in (
            ("tag", base, "/".join(f["tags"]) if set(f["tags"]) != set(_members(base)) else base),
            ("starter", o["starter"], v1_starter), ("kW", o["kw"], f["kw"]), ("qty", o["qty"], f["qty"]),
            ("standby", o["standby"], f["standby"]), ("phases", o["phases"], f["phases"]),
            ("client A", o["client_flc_a"], f["flc_client"]), ("load type", o["load_type"], f["load_type"]),
            ("range", (o["client_range_min"], o["client_range_max"]), rc)) if a != b]
        table.append([o["tag"], o["panel"], o["starter"], f"{o['kw']:g}", str(o["qty"]), str(o["phases"]),
                      f"{o['client_flc_a']:g}", f["id"], "; ".join(d) or "same"])
        if d:
            diffs.append(("v1", o["tag"], "; ".join(d)))
    for i, f in enumerate(v1):
        if i not in used:
            diffs.append(("v1", f["id"], f"v1 row {'/'.join(f['tags'])} not in the Word list"))
    return table, diffs


def main() -> int:
    out = [f"# Load-list import — G6 verification ({date.today().isoformat()})", "",
           "Generated by `scripts/verify_load_list.py`. Oracles: (1) v1's Layer 0 feeders "
           "(`panel-selector/projects/WNS2503/out/WNS2503_layer0.json`, an independent implementation that read the "
           "PDF master), (2) the client's equipment PDF (`ECI-WNS2503-EQUIP`), (3) the panel component run on v1's "
           "load list by `scripts/verify_panel.py`. Every difference is explained; the script fails on any "
           "difference it has no explanation for.", ""]
    res = select(panel="all", standby_per_group=1)      # standby 1 per group: what v1 assumed
    rows = res.value["rows"]
    unexplained = []

    # 1. v1
    table, diffs = compare_v1(rows)
    out += ["## 1. Row by row against v1 (standby_per_group = 1, as v1 assumed)", "",
            f"{len(rows)} Word rows, {len(table)} matched to a v1 feeder, "
            f"{sum(1 for r in table if r[-1] == 'same')} identical in tag, panel, starter, kW, qty, standby, phases, "
            "client current and client MPCB range.", "",
            "| Tag | Panel | Starter | kW | Qty | Ph | Client A | v1 feeder | Difference |", "|---|---|---|---|---|---|---|---|---|",
            *["| " + " | ".join(r) + " |" for r in table], "", "### Differences and who is right", ""]
    for kind, tag, what in diffs:
        why = EXPLAIN.get((kind, tag))
        if not why:
            unexplained.append(f"v1 {tag}: {what}")
        out.append(f"- **{tag}**: {what}. {why or '**UNEXPLAINED**'}")
    out.append("")

    # 2. PDF master
    pdf_checks = [c for c in res.checks if c.rule == "R-LL-15"]
    out += ["## 2. Against the client's equipment PDF (R-LL-15)", "",
            "Matched by panel + tag, then by Group Marking, then by item wording + kW. All 67 Word rows find a PDF "
            "row in the **same panel** (this confirms R-LL-02's reading of the 'Panel Total' rows), the six panel "
            "starter totals agree (22/1/36 BIO/UF, 16/2/40 RO), and no PDF motor row is left over.", ""]
    for c in pdf_checks:
        out.append(f"- R-LL-15 {c.verdict}: {c.value}")
    for o in rows:
        if o["tag"] in ("K101A/B", "P102A/B", "P410A/B", "P701A/B", "P703A/B"):
            if ("pdf", o["tag"]) not in EXPLAIN:
                unexplained.append(f"pdf {o['tag']}")
    n_pdf = res.value["n_pdf_differences"]
    if n_pdf != 5:
        unexplained.append(f"expected 5 PDF differences, got {n_pdf}")
    out += ["", "Who is right: see section 1 (K101A/B, P102A/B, P410A/B, P701A/B, P703A/B are the same five rows).", "",
            "Item wording that differs (not compared by the tool; tags, kW and currents agree):", ""]
    for o in rows:
        if o.get("pdf_item") and o["pdf_item"].lower().split() != o["item"].lower().split():
            why = EXPLAIN.get(("item", o["tag"]))
            if not why:
                unexplained.append(f"item {o['tag']}: {o['item']!r} vs {o['pdf_item']!r}")
            out.append(f"- {o['tag']} ({o['source']}): Word '{o['item']}', PDF '{o['pdf_item']}'. {why or '**UNEXPLAINED**'}")
    out.append("")

    # 3. through the panel component
    old = v1_load_lists()
    out += ["## 3. Through the panel component", "",
            "Inputs for this run only: fault 50 kA, 35 °C inside the panel, 50 °C site, motor pf 0.85, cable route "
            "40 °C, line reactor ≤ 15 kW, **cable 50 m on every line (`default_cable_m=50`, not from ECI)**, one "
            "standby per A/B group (`standby_per_group=1`, as v1). Same inputs for v1's list (`verify_panel.py`).", "",
            "| Panel | Lines (v2 / v1) | Units | Selected | Open points | Heat W |", "|---|---|---|---|---|---|"]
    notes = []
    for p, key in (("BIO_UF", "BIO/UF"), ("RO", "RO")):
        ll = select(panel=p, default_cable_m=50, standby_per_group=1).value["load_lists"][p]
        a = panel_select(load_list=ll, **PANEL_KW).value
        b = panel_select(load_list=old[key], **PANEL_KW).value
        keys = ("n_lines", "n_units", "n_selected", "n_open", "heat_known_w")
        out.append(f"| {p} | " + " | ".join(f"{a[k]:g} / {b[k]:g}" for k in keys) + " |")
        if any(a[k] != b[k] for k in keys):
            why = EXPLAIN.get(("panel", p))
            if not why:
                unexplained.append(f"panel {p}")
            notes.append(f"- **{p}**: {why or '**UNEXPLAINED**'}")
        opened = [r["tag"] for r in a["feeders"] if r["status"] == "open"]
        notes.append(f"  - v2 open lines ({len(opened)}): {', '.join(opened)}")
    out += ["", *notes, ""]

    # 4. document's own checks
    out += ["## 4. The document checked against itself", ""]
    for c in res.checks:
        if c.rule in ("R-LL-09", "R-LL-10", "R-LL-11", "R-LL-12", "R-LL-13", "R-LL-14"):
            out.append(f"- **{c.rule}** ({c.verdict}): {c.value}")
    out += ["", "MX502's Group Marking is written 'Mx502' (case only: not a difference).", ""]

    out += ["## Result", "", "**Every difference is explained.**" if not unexplained else
            "**UNEXPLAINED differences:** " + "; ".join(unexplained), ""]
    (ROOT / "components" / "load_list" / "VERIFY.md").write_text("\n".join(out))
    print("\n".join(l for l in out if l.startswith(("## ", "| BIO", "| RO", "- **", "**"))))
    return 1 if unexplained else 0


if __name__ == "__main__":
    sys.exit(main())
