"""The schematic drawing set of a panel (owner 2026-10-17: "work more on the single line diagram … make sure this is better"
than the company sample AVELCPSDL08WPLC, OWN-PROPEL-SCH160, 17 sheets).

Same sheets, same order and the same frame as the company set — cover, index, legends & symbols, technical details,
power wiring (R, Y, B, N), control wiring, digital input & output, analog input, terminal details, bill of material —
plus a single line overview. Better than the hand-drawn sample in what a generator can guarantee:
  * one tag per device everywhere: the power sheet, the ladder, the I/O sheet, the terminals and the BOM share
    core/drawing_tags.plan, so a BOM tag can never disagree with the drawing;
  * live cross references (sheet.column-row, e.g. 7.3B) between a coil and its main contacts, and between sheets;
  * the index, the legend and the terminal numbers are worked out from the sheets actually drawn;
  * the revision block and drawn / checked / approved come from the design's version history (four eyes), not typed;
  * whatever is not selected is drawn dashed and says why; nothing is drawn that the selection does not hold.
Company sheets the tool does not make (general arrangement, block diagram) are listed in the index as not made.
Sources: layout and conventions OWN-PROPEL-SCH160 (p.3 legend and wire colours, p.6-7 power, p.8-11 control,
p.12-13 I/O, p.14-15 BOM, p.16 terminals). Standard library only.
"""
from __future__ import annotations

import re
from datetime import date
from html import escape

from .drawing_tags import plan as tag_plan, _compact

W, H = 1190, 842
GX0, GY0, GX1, GY1 = 30, 30, 1160, 812             # grid area (columns 1-6, rows A-D)
CW, RH = (GX1 - GX0) / 6, (GY1 - GY0) / 4
TB_X, TB_Y = 600, 700                              # title block, bottom right
TOP = 104                                          # first drawing line under the header

STYLE = """<style>
text{font-family:Arial,Helvetica,sans-serif;fill:#111}
.b{font-weight:bold} .it{font-style:italic} .warn{fill:#a15c00} .red{fill:#c62828} .mut{fill:#555}
.fr{fill:none;stroke:#111;stroke-width:1.1} .th{fill:none;stroke:#111;stroke-width:.5} .w{fill:none;stroke:#111;stroke-width:1}
.bus{stroke:#111;stroke-width:2.6} .sym{fill:#fff;stroke:#111;stroke-width:.9} .dash{fill:none;stroke:#a15c00;stroke-width:.9;stroke-dasharray:4 3}
.mech{stroke:#111;stroke-width:.7;stroke-dasharray:3 2} .tagb{fill:#fff;stroke:#111;stroke-width:.9} .dot{fill:#111}
.r24{stroke:#1f4fbf;stroke-width:1} .rail{stroke:#111;stroke-width:1.3} .ac{stroke:#c62828;stroke-width:1.3}
.ink{fill:#111} .warn-t{fill:#a15c00} .nsel-t{fill:#a15c00;font-style:italic} .frame{fill:none;stroke:#111;stroke-width:1.2}
.thin{fill:none;stroke:#111;stroke-width:.5} .wire{stroke:#111;stroke-width:1.1} .tag{fill:#fff;stroke:#111;stroke-width:.9}
.nsel{fill:none;stroke:#a15c00;stroke-width:1;stroke-dasharray:4 3}
</style>"""


# --- primitives -------------------------------------------------------------------------------------------------------
def t(x, y, s, size=7, anchor="start", cls="", rot=None):
    tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot is not None else ""
    c = f' class="{cls}"' if cls else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}"{c}{tr}>{escape(str(s))}</text>'


def ln(x1, y1, x2, y2, cls="w"):
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"/>'


def rect(x, y, w, h, cls="sym"):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" class="{cls}"/>'


def circ(x, y, r, cls="sym"):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" class="{cls}"/>'


def dot(x, y):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" class="dot"/>'


def tagbox(x, y, tag, size=8):
    w = 6 + 5.4 * len(tag) * size / 8
    return rect(x, y - size - 1, w, size + 4, "tagb") + t(x + w / 2, y, tag, size, "middle", "b")


def wrap(s: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in str(s).split():
        if len(cur) + len(w) + 1 > n and cur:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return out + ([cur] if cur else [])


def ref_of(x, y) -> str:
    col = min(6, max(1, int((x - GX0) // CW) + 1))
    row = "ABCD"[min(3, max(0, int((y - GY0) // RH)))]
    return f"{col}{row}"


# poles of 3-phase devices (vertical, top → bottom), at x, x+P, x+2P
P = 12


def pole_breaker(x, y):
    return ln(x, y - 14, x, y - 6) + ln(x, y - 6, x + 7, y + 6) + ln(x, y + 6, x, y + 14) + \
        f'<path d="M{x - 3} {y - 9} l6 6 M{x + 3} {y - 9} l-6 6" class="w"/>'


def pole_contactor(x, y):
    return ln(x, y - 14, x, y - 6) + ln(x, y - 6, x + 7, y + 6) + ln(x, y + 6, x, y + 14) + \
        f'<path d="M{x - 3} {y - 6} a3 3 0 0 0 6 0" class="w"/>'


def three(fn, x, y, mech=True, n=3):
    g = "".join(fn(x + i * P, y) for i in range(n))
    return g + (ln(x + 3, y, x + (n - 1) * P + 6, y, "mech") if mech else "")


def mpcb3(x, y):
    """Motor protection circuit breaker (3P): contacts, thermal and magnetic trips (legend p.3)."""
    return three(pole_breaker, x, y) + rect(x - 30, y - 7, 22, 14) + t(x - 19, y + 3, "I> ⌇", 6, "middle")


def mccb3(x, y):
    return three(pole_breaker, x, y) + rect(x - 34, y - 7, 26, 14) + t(x - 21, y + 3, "I> I>", 6, "middle")


def fuse3(x, y):
    return "".join(ln(x + i * P, y - 14, x + i * P, y - 7) + rect(x + i * P - 3, y - 7, 6, 14) + ln(x + i * P, y + 7, x + i * P, y + 14)
                   for i in range(3))


def olr3(x, y):
    g = rect(x - 6, y - 9, 2 * P + 12, 18)
    for i in range(3):
        xx = x + i * P
        g += ln(xx, y - 14, xx, y - 9) + f'<path d="M{xx} {y - 9} v4 h3 v6 h-3 v4" class="w"/>' + ln(xx, y + 9, xx, y + 14)
    return g


def motor(x, y, r=19):
    return circ(x, y, r) + t(x, y - 1, "M", 10, "middle", "b") + t(x, y + 10, "3~", 7, "middle")


def term(x, y, n=None, size=5.5):
    return circ(x, y, 2.4) + (t(x, y + 9, n, size, "middle") if n is not None else "")


def lamp(x, y, r=6):
    return circ(x, y, r) + f'<path d="M{x - r * .7} {y - r * .7} L{x + r * .7} {y + r * .7} M{x + r * .7} {y - r * .7} L{x - r * .7} {y + r * .7}" class="w"/>'


def coil(x, y):
    """Vertical rung coil centred at (x, y) with A1 / A2."""
    return rect(x - 8, y - 5, 16, 10) + t(x + 11, y - 5, "A1", 5) + t(x + 11, y + 9, "A2", 5)


def no_v(x, y, mark=""):
    """Normally open contact on a vertical rung, centred at (x, y)."""
    g = ln(x, y - 12, x, y - 6) + ln(x, y + 6, x - 7, y - 7) + ln(x, y + 6, x, y + 12)
    if mark == "timer":
        g += f'<path d="M{x - 9} {y - 1} a4 4 0 0 1 6 -4" class="w"/>'
    if mark == "pb":
        g += ln(x - 4, y, x - 14, y, "mech") + ln(x - 14, y - 4, x - 14, y + 4)
    return g


def nc_v(x, y):
    return ln(x, y - 12, x, y - 6) + ln(x, y - 6, x + 7, y - 6) + ln(x, y + 6, x + 7, y - 8) + ln(x, y + 6, x, y + 12)


def dashbox(x, y, w, h, text, size=6.5):
    lines = wrap(text, max(8, int(w / (size * 0.55))))
    return rect(x, y, w, h, "dash") + "".join(t(x + w / 2, y + h / 2 + 3 + (i - (len(lines) - 1) / 2) * (size + 2), s, size, "middle", "warn it")
                                              for i, s in enumerate(lines))


def box(x, y, w, h, text, size=7, bold=True):
    lines = wrap(text, max(6, int(w / (size * 0.58))))
    return rect(x, y, w, h) + "".join(t(x + w / 2, y + h / 2 + 3 + (i - (len(lines) - 1) / 2) * (size + 2), s, size, "middle", "b" if bold else "")
                                      for i, s in enumerate(lines))


# --- the set ----------------------------------------------------------------------------------------------------------
class Sheet:
    def __init__(self, title: str, kind: str):
        self.title, self.kind, self.g, self.anchors = title, kind, [], {}

    def add(self, *parts):
        self.g.extend(parts)

    def anchor(self, name, x, y):
        self.anchors.setdefault(name, (x, y))


def REF(name: str) -> str:
    return f"\x00{name}\x00"


def _num(x, nd=1):
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, (int, float)) else "—"


class DrawingSet:
    def __init__(self, v: dict, meta: dict):
        v = dict(v)                    # a client-project value keeps its choices under 'options' and its inputs in meta
        if v.get("control_supply") is None and (v.get("options") or {}).get("control_supply"):
            v["control_supply"] = v["options"]["control_supply"]
        for k, x in (meta.get("inputs") or {}).items():
            if v.get(k) is None and x is not None:
                v[k] = x
        self.v, self.meta = v, meta
        self.p = tag_plan(v)
        self.bom = v.get("bom") or []
        self.scope = v.get("scope") or {}
        self.sheets: list[Sheet] = []
        self.units = self.p["units"]
        self.dev = self.p["devices"]
        io = v.get("io_list") or []
        self.dis = [r for r in io if r.get("type") == "DI"]
        self.dos = [r for r in io if r.get("type") == "DO"]
        self.ais = [r for r in io if r.get("type") == "AI"]
        self.aos = [r for r in io if r.get("type") == "AO"]
        self.relay_tags = sorted((k for k, d in self.dev.items() if d["kind"] == "relay"), key=lambda s: int(re.sub(r"\D", "", s) or 0))
        self.do_relay = {r["name"]: (self.relay_tags[i] if i < len(self.relay_tags) else None) for i, r in enumerate(self.dos)}
        self.plc_ok = self.scope.get("plc") is not False and any(d["kind"] == "plc" for d in self.dev.values())

    def by_kind(self, kind):
        return [d for d in self.dev.values() if d["kind"] == kind]

    def new(self, title, kind) -> Sheet:
        s = Sheet(title, kind)
        self.sheets.append(s)
        return s

    # ---- sheets ----------------------------------------------------------------------------------------------------
    def build(self) -> list[str]:
        self.cover()
        self.index_sheet = self.new("INDEX SHEET", "index")
        self.legend_sheet = self.new("LEGENDS, ABBREVIATIONS & SYMBOLS", "legend")
        self.technical()
        self.overview()
        self.power()
        self.control_supply()
        self.ladder()
        self.io_digital()
        self.io_analog()
        self.terminals()
        self.bom_sheets()
        self.fill_index()
        self.fill_legend()
        return self.render()

    def cover(self):
        s = self.new("COVER SHEET", "cover")
        m = self.meta
        s.add(f'<rect x="130" y="124" width="950" height="460" rx="22" class="fr"/>',
              f'<rect x="146" y="584" width="950" height="14" class="dot"/>', f'<rect x="1080" y="138" width="16" height="460" class="dot"/>')
        rows = [("ITEM/OBJECT", "MOTOR CONTROL PANEL" if self.units else "CONTROL PANEL"),
                ("PANEL NAME", m.get("title") or "—"),
                ("PROJECT REF. NO", " › ".join(x for x in (m.get("project"), m.get("panel")) if x) or "— (not saved to a project)"),
                ("DOCUMENT TITLE", "SCHEMATIC WIRING DIAGRAM, SINGLE LINE DIAGRAM & BILL OF MATERIAL"),
                ("MADE FROM", f"design version {m['version']['v']} ({m['version'].get('state', 'draft')})" if m.get("version") else
                 "the selection on screen (not a saved version)"),
                ("STATUS", "APPROVED" if (m.get("version") or {}).get("state") == "approved" else
                 "DRAFT — not for construction until checked and approved")]
        for i, (k, val) in enumerate(rows):
            y = 240 + i * 46
            s.add(t(170, y, k, 10), t(360, y, ":", 10), t(420, y, val, 10, cls="b" if k == "PANEL NAME" else ""))

    def technical(self):
        v = self.v
        s = self.new("TECHNICAL DETAILS", "tech")
        inc = self.dev.get("1SQ1")
        left = [("ELECTRICAL", None),
                ("Supply", f"{_num(v.get('voltage_v'))} V AC, 3 phase + N + PE, {_num(v.get('frequency_hz') or 50)} Hz"),
                ("Fault level (as given)", f"{_num(v.get('fault_ka'))} kA — short-circuit study not built"),
                ("Incomer", f"{inc['line']['article']} — {inc['line']['description'][:46]}" if inc else
                 ("none — fed from the main panel" if self.scope.get("incomer") is False else "not selected")),
                ("Design current (Σ running, no diversity)", f"{_num(v.get('incomer_ib_a'))} A"),
                ("Control voltage", "230 V AC (" + ("control transformer" if self.by_kind("transformer") else "phase–neutral"
                                                    if v.get("control_supply") == "phase_neutral" else "control transformer — not sized yet") + "), 24 V DC"
                 if self.scope.get("control_transformer") is not False else "230 V AC from the main panel, 24 V DC"),
                ("24 V DC supply", (self.by_kind("smps")[0]["line"]["article"] if self.by_kind("smps") else "none in this panel")),
                ("PLC", (", ".join(d["line"]["article"] for d in self.by_kind("plc")) if self.plc_ok else "none in this panel")),
                ("I/O (from the I/O list)", f"DI {len(self.dis)} · DO {len(self.dos)} · AI {len(self.ais)} · AO {len(self.aos)}"
                 if self.plc_ok else "no PLC"),
                ("SITE", None),
                ("Temperature inside the panel", f"{_num(v.get('panel_internal_c'))} °C"),
                ("Cable route temperature", f"{_num(v.get('cable_ambient_c'))} °C"),
                ("ENCLOSURE", None),
                ("Enclosure, base, gland plate, finish", "outside the tool's scope (company GA drawing, sheet 5 of the sample)")]
        y = TOP + 20
        for k, val in left:
            if val is None:
                s.add(t(60, y + 8, k, 9, cls="b"), ln(60, y + 11, 520, y + 11, "th"))
                y += 24
            else:
                s.add(t(70, y, k, 7.5), t(270, y, "- " + str(val)[:70], 7.5))
                y += 15
        # motors table
        x0, y = 620, TOP + 20
        cols = [(0, "TAG"), (46, "LOAD"), (170, "kW"), (205, "STARTER"), (265, "FLC A"), (310, "MOTOR CABLE")]
        s.add(t(x0, y + 8, "MOTORS", 9, cls="b"), ln(x0, y + 11, 1150, y + 11, "th"))
        y += 26
        s.add(*[t(x0 + dx, y, h, 7, cls="b") for dx, h in cols])
        for u in self.units[:30]:
            y += 13
            f = u["feeder"]
            vals = [u["tag"], (u["app"] or "")[:22], _num(u["kw"]), u["starter"] or "—",
                    _num(u["flc_a"]), (u["cable"] or "not selected")[:46]]
            s.add(*[t(x0 + dx, y, val, 7, cls="warn it" if val in ("not selected", "—") else "") for (dx, _), val in zip(cols, vals)])

    # ---- single line overview ----------------------------------------------------------------------------------------
    def overview(self):
        """Single line overview, drawn from the same device plan as every other sheet: one drop per feeder (a feeder of
        several motors shows '× n'), each auxiliary feeder of a template its own drop."""
        v = self.v
        groups, seen = [], {}
        for u in self.units:                          # M3.1 and M3.2 → one drop 'M3 × 2'; auxiliary feeders apart
            key = u["tag"] if u["status"] == "template-aux" else u["feeder"]["tag"]
            if key not in seen:
                seen[key] = {"key": key, "units": []}
                groups.append(seen[key])
            seen[key]["units"].append(u)
        per, BUS, X0, PITCH = 7, 250, 250, 122
        chunks = [groups[i:i + per] for i in range(0, max(len(groups), 1), per)] or [[]]
        for ci, chunk in enumerate(chunks):
            s = self.new("SINGLE LINE DIAGRAM" + (f"-{ci + 1}" if len(chunks) > 1 else ""), "sld")
            if ci == 0:
                self._ov_incoming(s, BUS)
            else:
                s.add(t(60, BUS - 8, f"from sheet {REF(f'sld{ci}')}", 6.5))
            s.anchor(f"sld{ci + 1}", 80, BUS)
            bus_end = max(X0 + PITCH * max(len(chunk) - 1, 0) + 60, 1080)
            s.add(ln(130 if ci == 0 else 60, BUS, bus_end, BUS, "bus"))
            bb = ("template line 'Busbar & accessories' (size not stated)"
                  if any("busbar" in str(b.get("description")).lower() and b.get("status") == "template" for b in self.bom)
                  else "size not selected (busbar waits for the 3VA manual / IEC 61439-1)")
            s.add(t(150, BUS - 6, "MAIN BUSBAR R, Y, B, N — " + bb, 6.5, cls="warn it"))
            if ci + 1 < len(chunks):
                s.add(t(bus_end - 4, BUS - 8, f"to {REF(f'sld{ci + 2}')} →", 6.5, "end"))
            for i, gr in enumerate(chunk):
                self._ov_drop(s, gr["units"], X0 + PITCH * i, BUS)
            if ci == 0:
                ns = [f"{x['item']} — {x['category']}" for x in (v.get("not_selected_detail") or []) if x["category"] != "out of scope"] \
                    or (v.get("not_selected") or [])
                if v.get("template"):                 # a template line already covers some of what the rules did not select
                    have = {"control transformer": bool(self.by_kind("transformer")), "control power": bool(self.by_kind("smps")),
                            "24 v supply": bool(self.by_kind("smps")), "internal wiring": any(b["group"] == "Internal wiring" for b in self.bom),
                            "hmi": bool(self.by_kind("hmi")), "busbar": any("busbar" in str(b.get("description")).lower() for b in self.bom)}
                    ns = [x for x in ns if not any(ok and k in x.lower() for k, ok in have.items())]
                if ns:
                    s.add(rect(40, 712, 548, 92, "th"), t(46, 724, "NOT SELECTED (drawn dashed or not drawn):", 7, cls="b warn"))
                    s.add(*[t(46, 735 + 8 * i, "• " + n[:112], 5.8, cls="warn it") for i, n in enumerate(ns[:8])])
                    if len(ns) > 8:
                        s.add(t(46, 735 + 64, f"… and {len(ns) - 8} more: see the 'Not selected' sheet of the document pack", 5.8, cls="warn it"))
            pool = list(dict.fromkeys(tg for gr in chunk for u in gr["units"] for m in self.units
                                      if m["tag"] == u.get("aux_of") for tg in (m.get("aux_prot") or [])))
            if pool:
                s.add(t(250, 690, "AUXILIARY FEEDERS: overload relays listed by the template without their motor — " +
                        ", ".join(f"{tg} {self.dev[tg]['line']['article']}" for tg in pool)[:110], 6, cls="warn"))

    def _ov_incoming(self, s: Sheet, BUS):
        v = self.v
        s.add(t(70, 92 + 12, "INCOMING SUPPLY", 9, cls="b"),
              t(70, 116, f"{_num(v.get('voltage_v'))} V, 3 PH, {_num(v.get('frequency_hz') or 50)} Hz", 8),
              t(70, 127, f"fault level {_num(v.get('fault_ka'))} kA (as given; short-circuit study not built)", 6.5))
        x, y = 130, 186
        inc = self.dev.get("1SQ1")
        s.add(ln(x, 134, x, y - 14))
        if inc:
            s.add(pole_breaker(x, y), rect(x - 26, y - 6, 16, 12), t(x - 18, y + 3, "I>", 6, "middle"), tagbox(x + 14, y - 6, "1SQ1"),
                  t(x + 14, y + 10, inc["line"]["article"][:28], 6.5, cls="b"), t(x + 14, y + 19, inc["line"]["description"][:44], 6),
                  t(x + 14, y + 28, f"design current {_num(v.get('incomer_ib_a'))} A (Σ running, no diversity)", 6))
        elif self.scope.get("incomer") is False:
            s.add(ln(x, y - 14, x, y + 14), box(x + 10, y - 13, 170, 26, "NO INCOMER — FED FROM THE MAIN PANEL", 6))
        else:
            s.add(ln(x, y - 14, x, y + 14), dashbox(x + 10, y - 13, 120, 26, "INCOMER — NOT SELECTED"))
        s.add(ln(x, y + 14, x, BUS))
        side = [("ENERGY METER + CTs", self.by_kind("ct") + self.by_kind("meter") + self.by_kind("ct_sensor")),
                ("SURGE ARRESTER", self.by_kind("spd")), ("PHASE MONITORING", self.by_kind("pmr")),
                ("UV / OV RELAY", self.by_kind("uvov")), ("24 V DC SUPPLY", self.by_kind("smps"))]
        sx = 1040
        for label, ds in side:
            if not ds:
                continue
            tags = _compact([d["tag"] for d in ds])
            arts = list(dict.fromkeys(d["line"]["article"] for d in ds if d["line"].get("article")))
            s.add(ln(sx, BUS, sx, BUS - 44, "th"), box(sx - 54, BUS - 70, 108, 26, label, 6.5), tagbox(sx - 54, BUS - 73, tags[:14], 6.5),
                  *[t(sx, BUS - 86 - 9 * k, a[:24], 6, "middle") for k, a in enumerate(arts[:3])])
            sx -= 124

    def _ov_drop(self, s: Sheet, units: list, x: int, BUS: int):
        u0 = units[0]
        n = len(units)
        aux = u0["status"] == "template-aux"
        tags = lambda key: _compact([tg for u in units for tg in (u["dev"].get(key) or [])])
        art = lambda tg: self.dev[tg]["line"]["article"]
        s.add(ln(x, BUS, x, 282), dot(x, BUS))
        # protection
        y = 300
        if u0["dev"].get("mpcb"):
            q = u0["dev"]["mpcb"][0]
            s.add(pole_breaker(x, y), rect(x - 26, y - 6, 16, 12), t(x - 18, y + 3, "I>", 6, "middle"), tagbox(x + 12, y - 6, tags("mpcb")),
                  t(x + 12, y + 10, art(q)[:18], 6), t(x + 12, y + 19, f"MPCB · FLC {_num(u0['flc_a'])} A", 6))
        elif u0["dev"].get("fuse"):
            f = u0["dev"]["fuse"][0]
            s.add(ln(x, y - 14, x, y - 8), rect(x - 4, y - 8, 8, 16), ln(x, y + 8, x, y + 14), tagbox(x + 12, y - 6, tags("fuse")),
                  t(x + 12, y + 10, art(f)[:18], 6), t(x + 12, y + 19, "LV HRC fuse", 6))
        elif aux:
            s.add(ln(x, y - 14, x, y + 14), t(x + 8, y, "protection: see note", 6, cls="warn it"))
        elif u0["dev"].get("olr") or u0["dev"].get("mpr"):
            s.add(ln(x, y - 14, x, y + 14), t(x + 8, y, "short-circuit: by the incomer", 6, cls="warn it"))
        else:
            s.add(ln(x, y - 14, x, y - 11), dashbox(x - 46, y - 11, 92, 22, "PROTECTION NOT SELECTED", 6), ln(x, y + 11, x, y + 14))
        s.add(ln(x, y + 14, x, 368))
        if u0.get("wire") and not aux:
            s.add(t(x - 4, 340, str(u0["wire"]["article"]).replace("Lapp ", "")[:22], 5.5, "end"), t(x - 4, 348, "internal wiring", 5, "end"))
        # switching
        y = 390
        ks = [tg for u in units for tg in (u["dev"].get("k") or [])]
        st = u0["starter"]
        if st == "SD" and len(u0["dev"].get("k") or []) >= 3:
            rows = {}
            for tg in ks:
                rows[art(tg)] = rows.get(art(tg), 0) + 1
            tm = tags("timer")
            s.add(box(x - 40, y - 17, 80, 34, "STAR-DELTA", 7), t(x, y + 11, "main · delta · star", 6, "middle"), tagbox(x + 44, y - 13, _compact(ks)),
                  *[t(x + 44, y + 4 + 9 * k, f"{a} × {c}", 6) for k, (a, c) in enumerate(rows.items())])
            if tm:
                s.add(t(x + 44, y + 4 + 9 * len(rows), f"{tm} {art(u0['dev']['timer'][0])} timer", 6))
        elif st == "SD" and ks:
            s.add(dashbox(x - 50, y - 17, 100, 34, f"STAR-DELTA incomplete in the template ({_compact(ks)})", 5.5))
        elif u0["dev"].get("u"):
            uu = u0["dev"]["u"][0]
            arts = [self.bom[i]["article"] for i in range(len(self.bom)) if self.p["line_tags"].get(i) == uu]
            s.add(box(x - 24, y - 22, 48, 44, "VFD ~ / ~", 8), tagbox(x + 28, y - 18, tags("u")),
                  *[t(x + 28, y - 2 + 9 * k, a[:20], 6) for k, a in enumerate(arts[:3])])
        elif u0["dev"].get("ss"):
            s.add(box(x - 32, y - 15, 64, 30, "SOFT START", 7), tagbox(x + 36, y - 11, tags("ss")), t(x + 36, y + 5, art(u0["dev"]["ss"][0])[:18], 6))
        elif ks:
            s.add(pole_contactor(x, y), tagbox(x + 12, y - 6, _compact(ks)), t(x + 12, y + 10, art(ks[0])[:18], 6), t(x + 12, y + 19, "contactor AC-3", 6))
        else:
            s.add(ln(x, y - 22, x, y - 15), dashbox(x - 46, y - 15, 92, 30, "STARTER NOT SELECTED", 6), ln(x, y + 15, x, y + 22))
        if u0["dev"].get("olr") or u0["dev"].get("mpr"):
            pr = ", ".join(f"{tg} {art(tg)}" for tg in (u0["dev"].get("olr") or []) + (u0["dev"].get("mpr") or []))
            s.add(t(x + 8, 342, ("overload / " if u0["dev"].get("olr") else "") + "protection:", 5.5), t(x + 8, 351, pr[:30], 5.5, cls="b"))
        s.add(ln(x, y + 22, x, 528))
        # motor cable, motor
        cab = u0["cable"]
        if cab:
            size, _, length = cab.rpartition(", ")
            s.add(t(x + 6, 456, "MOTOR CABLE", 6, cls="b"), t(x + 6, 465, size.replace(" Cu XLPE armoured", "")[:30], 6), t(x + 6, 474, length, 6))
        elif not aux:
            s.add(t(x + 6, 456, "MOTOR CABLE", 6, cls="b warn"),
                  t(x + 6, 465, "NOT SELECTED" + ("" if isinstance(u0["kw"], (int, float)) else " (kW not stated)"), 6, cls="warn it"),
                  t(x + 6, 474, "2 runs at FLC/√3 (star-delta)" if st == "SD" else "", 6, cls="warn it"))
        tag = u0["feeder"]["tag"] if not aux else u0["tag"]
        s.add(motor(x, 546, 17), t(x, 576, tag + (f" × {n}" if n > 1 else ""), 8, "middle", "b"))
        if aux:
            s.add(t(x, 587, "AUXILIARY DRIVE", 6, "middle"), t(x, 596, "motor not stated in the template", 5.5, "middle", "warn it"))
        else:
            s.add(t(x, 587, (u0["app"] or "").upper()[:22], 6, "middle"),
                  t(x, 597, (f"{_num(u0['kw'])} kW" if isinstance(u0["kw"], (int, float)) else "kW not stated") + f" · {st or '—'}", 7, "middle"),
                  t(x, 607, f"FLC {_num(u0['flc_a'])} A" if isinstance(u0["flc_a"], (int, float)) else "FLC —", 7, "middle"))
        if ks:
            s.add(t(x, 618, f"coil {REF(ks[0] + '.coil')} · power {REF(ks[0] + '.main')}", 5.5, "middle", "mut"))
        lamps = [d["tag"] for d in self.dev.values() if d["kind"] == "lamp" and d["unit"] in {u["tag"] for u in units}]
        if lamps:
            s.add(t(x, 628, f"kit lamps {_compact(lamps)}", 5.5, "middle", "mut"))
        io_rows = [r for r in self.v.get("io_list") or [] if r.get("unit") == u0["tag"]]
        if io_rows:
            s.add(t(x - 50, 642, "PLC I/O" + (f" (per motor, × {n})" if n > 1 else ""), 6, cls="b"))
            s.add(*[t(x - 50, 651 + 8 * k, f"{(r.get('channel') or {'PN': 'bus', 'SAFETY': 'STO'}.get(r['type'], r['type'])):<5} {r.get('name', '')}"[:30], 5.8)
                    for k, r in enumerate(io_rows[:5])])

    # ---- power wiring --------------------------------------------------------------------------------------------------
    def _unit_width(self, u):
        return 200 if u["starter"] == "SD" else 120

    def power(self):
        v = self.v
        BUS = {"R": TOP + 18, "Y": TOP + 30, "B": TOP + 42, "N": TOP + 54}
        # sheet 1: incoming, metering, phase lamps, protection relays; then feeders across sheets
        n_side = sum(len(self.by_kind(k)) for k in ("pmr", "uvov", "spd"))
        lamps = any(self.dev.get(k) for k in ("R-PHASE", "Y-PHASE", "B-PHASE"))
        first = max(330, 290 + (130 if lamps else 0) + 76 * n_side + 40)     # feeders start right of the incoming section
        pages, cur, x = [[]], 0, first
        for u in self.units:
            w = self._unit_width(u)
            if x + w > 1100:
                pages.append([])
                x = 110
            pages[-1].append((u, x))
            x += w
        self.term_no = {}            # power terminal 1X1 numbers per unit (sheet 'terminal details' uses them)
        n_term = 0
        for pi, page in enumerate(pages):
            s = self.new(f"POWER WIRING DIAGRAM-{pi + 1}", "power")
            xs = 60 if pi else 90
            for ph, y in BUS.items():
                s.add(ln(xs, y, 1100, y, "bus" if ph != "N" else "w"),
                      t(1104, y + 3, f"{ph}" + (f" → {REF(f'bus{pi + 2}')}" if pi + 1 < len(pages) else ""), 6.5))
                if not pi:
                    s.add(t(xs - 6, y + 3, ph, 7, "end", "b"))
                if pi:
                    s.add(t(20 + 12, y + 3, ph, 7), t(36, y - 3, f"{REF(f'bus{pi}')} →", 5.5, "start"))
            s.anchor(f"bus{pi + 1}", 70, BUS["R"])
            bb = "MAIN BUSBAR R, Y, B, N — " + ("template line 'Busbar & accessories' (size not stated)"
                                                if any("busbar" in str(b.get("description")).lower() and b.get("status") == "template"
                                                       for b in self.bom)
                                                else "size not selected (busbar waits for the 3VA manual / IEC 61439-1)")
            s.add(t(xs + 140, BUS["R"] - 6, bb, 6.5, cls="warn it"))
            if pi == 0:
                self._incoming(s, BUS)
            for u, ux in page:
                n_term = self._feeder(s, u, ux, BUS, n_term)
            pool = [tg for u, _ in page for tg in next((m.get("aux_prot") or [] for m in self.units if m["tag"] == u.get("aux_of")), [])]
            if pool and any(u["status"] == "template-aux" for u, _ in page):
                pool = list(dict.fromkeys(pool))
                s.add(t(250, 758, "AUXILIARY FEEDERS: the template lists these overload relays without the motor each protects —", 6.5, cls="warn"),
                      t(250, 769, "  " + ", ".join(f"{tg} {self.dev[tg]['line']['article']} {self.dev[tg]['line']['description'][:14]}" for tg in pool)[:120], 6.5, cls="warn"),
                      t(250, 780, "  give the auxiliary motors (kW) in the design to assign them.", 6.5, cls="warn"))
            # notes like the sample: cable colours, terminal note
            s.add(rect(40, 712, 200, 82, "th"), t(46, 724, "CABLE COLOUR", 7, cls="b"),
                  *[t(46, 736 + 11 * i, r, 6.5) for i, r in enumerate(["RD - RED", "BK - BLACK", "OR - ORANGE", "BU - BLUE", "WH - WHITE"])],
                  t(250, 724, "NOTE:", 7, cls="b"), t(250, 736, "1X1 - power terminal block (motor outgoing), see terminal details", 6.5),
                  t(250, 747, "Feeder devices and settings as selected; FLC = motor full-load current", 6.5))

    def _incoming(self, s: Sheet, BUS):
        v = self.v
        x = 100                                        # R pole; Y, B at +P; N at +3P
        bottom = 690
        s.add(t(46, bottom - 2, "INCOMING", 8, cls="b"),
              t(46, bottom + 9, f"POWER SUPPLY {_num(v.get('voltage_v'))} V, {_num(v.get('frequency_hz') or 50)} Hz, 3PH, 4 WIRE", 6.5),
              t(46, bottom + 19, f"fault level {_num(v.get('fault_ka'))} kA (as given)", 6.5))
        for i, ph in enumerate("RYBN"):
            xx = x + i * P
            s.add(ln(xx, bottom - 30, xx, bottom - 14), t(xx, bottom - 34, ph, 6.5, "middle", "b"))
        inc = self.dev.get("1SQ1")
        yi = 560
        if inc:
            s.add(*[ln(x + i * P, bottom - 14, x + i * P, yi + 14) for i in range(3)], mccb3(x, yi),
                  tagbox(x - 34, yi - 18, "1SQ1"), t(x + 3 * P + 10, yi - 4, inc["line"]["article"][:24], 6, cls="b"),
                  t(x + 3 * P + 10, yi + 5, inc["line"]["description"][:34], 5.5),
                  t(x + 3 * P + 10, yi + 14, f"design current {_num(v.get('incomer_ib_a'))} A", 5.5))
            s.anchor("1SQ1", x, yi)
        elif self.scope.get("incomer") is False:
            s.add(*[ln(x + i * P, bottom - 14, x + i * P, yi - 14) for i in range(3)])
            late = box(x - 56, yi - 14, 150, 28, "NO INCOMER — FED FROM THE MAIN PANEL", 6)
        else:
            s.add(dashbox(x - 40, yi - 14, 110, 28, "INCOMER — NOT SELECTED"))
        s.add(ln(x + 3 * P, bottom - 14, x + 3 * P, BUS["N"]))
        for i, ph in enumerate("RYB"):
            s.add(ln(x + i * P, yi - 14, x + i * P, BUS[ph]), dot(x + i * P, BUS[ph]))
        s.add(dot(x + 3 * P, BUS["N"]))
        if self.scope.get("incomer") is False and not inc:
            s.add(late)                                  # over the supply lines
        # metering CTs on the incomer
        cts, meter, sensor = self.by_kind("ct"), self.by_kind("meter"), self.by_kind("ct_sensor")
        yc = 440
        if cts or meter:
            for i in range(3):
                s.add(f'<ellipse cx="{x + i * P}" cy="{yc}" rx="5" ry="3" class="sym"/>')
            ct_tags = _compact([d["tag"] for d in cts]) or "CT"
            s.add(tagbox(x - 46, yc + 3, ct_tags[:12], 7),
                  t(x - 46, yc + 14, (cts[0]["line"]["description"][:26] if cts else ""), 5.5))
            if meter:
                s.add(ln(x + 2 * P + 5, yc, 190, yc, "th"), box(190, yc - 16, 70, 32, "VAF / ENERGY METER", 6),
                      tagbox(190, yc - 20, meter[0]["tag"], 7), t(190, yc + 26, meter[0]["line"]["article"][:20], 5.5))
            if sensor:
                s.add(t(190, yc + 36, f"{sensor[0]['tag']}: {sensor[0]['line']['description'][:30]}", 5.5))
        # phase indication lamps, protection relays and SPD as taps from the busbar
        tx = 290
        lamps = [self.dev.get(k) for k in ("R-PHASE", "Y-PHASE", "B-PHASE") if self.dev.get(k)]
        fuses = [d for d in self.by_kind("fuse") if not d["unit"]]
        if lamps:
            for i, d in enumerate(lamps):
                xx, ph = tx + i * 34, "RYB"[i]
                s.add(ln(xx, BUS[ph], xx, 300), dot(xx, BUS[ph]), lamp(xx, 312), ln(xx, 318, xx, 340), ln(xx, 340, tx + 102, 340),
                      t(xx, 296, d["tag"], 5.5, "middle", "b"))
            s.add(ln(tx + 102, BUS["N"], tx + 102, 340), dot(tx + 102, BUS["N"]),
                  t(tx, 356, "PHASE INDICATION", 6.5, cls="b"), t(tx, 365, lamps[0]["line"]["article"] + " …", 5.5),
                  t(tx, 374, (f"fuses {_compact([d['tag'] for d in fuses])} (template)" if fuses else "lamp fuses: none listed"), 5.5, cls="" if fuses else "warn it"))
            tx += 130
        for kind, label in (("pmr", "PHASE MONITORING RELAY"), ("uvov", "UV / OV RELAY"), ("spd", "SURGE ARRESTER")):
            for d in self.by_kind(kind):
                for i, ph in enumerate("RYB"):
                    s.add(ln(tx + i * 10, BUS[ph], tx + i * 10, 300), dot(tx + i * 10, BUS[ph]))
                if kind == "spd":
                    s.add(ln(tx + 30, BUS["N"], tx + 30, 300), dot(tx + 30, BUS["N"]))
                s.add(box(tx - 8, 300, 56, 30, label, 5.5), tagbox(tx - 8, 296, d["tag"], 6.5),
                      t(tx - 8, 342, d["line"]["article"][:22], 5.5))
                if kind == "spd":
                    s.add(ln(tx + 20, 330, tx + 20, 352), t(tx + 24, 356, "PE", 6))
                tx += 76

    def _feeder(self, s: Sheet, u: dict, x: int, BUS, n_term: int) -> int:
        """One motor's power circuit, poles at x, x+P, x+2P: protection → switching → (overload) → 1X1 → motor."""
        tag, d = u["tag"], u["dev"]
        y = BUS["B"] + 30
        for i, ph in enumerate("RYB"):
            s.add(ln(x + i * P, BUS[ph], x + i * P, y + 10), dot(x + i * P, BUS[ph]))
        s.add(t(x - 4, y + 24, "R Y B", 5, "end"))
        y = 230
        # protection
        if d.get("mpcb"):
            q = self.dev[d["mpcb"][0]]
            s.add(mpcb3(x, y), tagbox(x - 32, y - 14, q["tag"]), t(x + 2 * P + 10, y - 4, q["line"]["article"][:16], 5.5),
                  t(x + 2 * P + 10, y + 4, "MPCB", 5.5), t(x + 2 * P + 10, y + 12, f"FLC {_num(u['flc_a'])} A", 5.5, cls="b"))
            s.anchor(q["tag"], x, y)
        elif d.get("fuse"):
            f = self.dev[d["fuse"][0]]
            s.add(fuse3(x, y), tagbox(x - 30, y - 14, f["tag"]), t(x + 2 * P + 10, y - 2, f["line"]["article"][:16], 5.5),
                  t(x + 2 * P + 10, y + 6, "LV HRC fuse", 5.5))
            s.anchor(f["tag"], x, y)
        elif u["status"] == "template-aux":
            s.add(*[ln(x + i * P, y - 14, x + i * P, y + 14) for i in range(3)],
                  t(x + 2 * P + 8, y - 2, "protection: see note", 5.5, cls="warn it"), t(x + 2 * P + 8, y + 6, "(template)", 5.5, cls="warn it"))
        elif u["starter"] == "SD" and (d.get("olr") or d.get("mpr")):
            s.add(*[ln(x + i * P, y - 14, x + i * P, y + 14) for i in range(3)],
                  t(x + 2 * P + 10, y, "short-circuit protection: by the incomer", 5.5, cls="warn it"))
        else:
            s.add(*[ln(x + i * P, y - 14, x + i * P, y + 14) for i in range(3)],
                  dashbox(x - 22, y - 11, 2 * P + 44, 22, "PROTECTION NOT SELECTED", 5) if u["status"] != "template" else "")
        y2 = 320
        s.add(*[ln(x + i * P, y + 14, x + i * P, y2 - 14) for i in range(3)])
        ks = d.get("k") or []
        out_x = x                              # where the outgoing lines (to 1X1) leave
        if u["starter"] == "SD" and len(ks) >= 3:
            km, kd, ks_ = (self.dev[k] for k in ks[:3])
            xd, xs = x + 64, x + 128
            # main: from the protection, to U1 V1 W1; delta: from the protection, to W2 U2 V2; star: shorts W2 U2 V2
            s.add(three(pole_contactor, x, y2), tagbox(x - 30, y2 - 12, km["tag"]),
                  t(x - 30, y2 + 22, f"{km['line']['article']}", 5.5), t(x - 30, y2 + 30, "MAIN", 5.5, cls="b"))
            s.add(*[ln(x + i * P, y + 22 + i * 4, xd + i * P, y + 22 + i * 4, "w") for i in range(3)],
                  *[dot(x + i * P, y + 22 + i * 4) for i in range(3)],
                  *[ln(xd + i * P, y + 22 + i * 4, xd + i * P, y2 - 14) for i in range(3)],
                  three(pole_contactor, xd, y2), tagbox(xd + 3 * P - 2, y2 - 12, kd["tag"]),
                  t(xd + 3 * P - 2, y2 + 22, kd["line"]["article"], 5.5), t(xd + 3 * P - 2, y2 + 30, "DELTA", 5.5, cls="b"))
            yb = y2 + 44
            s.add(*[ln(xd + i * P, y2 + 14, xd + i * P, 470) for i in range(3)],
                  *[ln(xd + i * P, yb + i * 4, xs + i * P, yb + i * 4) for i in range(3)], *[dot(xd + i * P, yb + i * 4) for i in range(3)],
                  *[ln(xs + i * P, yb + i * 4, xs + i * P, y2 + 60) for i in range(3)],
                  three(pole_contactor, xs, y2 + 74), ln(xs, y2 + 88, xs + 2 * P, y2 + 88), *[ln(xs + i * P, y2 + 88, xs + i * P, y2 + 88) for i in range(3)],
                  tagbox(xs + 3 * P - 2, y2 + 62, ks_["tag"]), t(xs + 3 * P - 2, y2 + 96, ks_["line"]["article"], 5.5),
                  t(xs + 3 * P - 2, y2 + 104, "STAR", 5.5, cls="b"), t(xs + P, y2 + 98, "star point", 5, "middle"))
            for k in ks[:3]:
                s.anchor(k + ".main", x if k == km["tag"] else xd if k == kd["tag"] else xs, y2)
        elif u["starter"] == "SD" and ks:
            s.add(dashbox(x - 14, y2 - 22, 2 * P + 80, 44, f"STAR-DELTA: the template lists only {_compact(ks)} for this motor — check the template", 5.5))
            for k in ks:
                s.anchor(k + ".main", x, y2)
            ks = []
        elif ks:
            k = self.dev[ks[0]]
            s.add(three(pole_contactor, x, y2), tagbox(x - 30, y2 - 12, k["tag"]),
                  t(x + 2 * P + 10, y2 - 2, k["line"]["article"][:16], 5.5), t(x + 2 * P + 10, y2 + 6, "contactor AC-3", 5.5))
            s.anchor(k["tag"] + ".main", x, y2)
            if len(ks) > 1 and u["starter"] == "DOL_FR":
                k2 = self.dev[ks[1]]
                s.add(tagbox(x + 2 * P + 10, y2 + 22, k2["tag"]), t(x + 2 * P + 10, y2 + 34, "reverse (L1 / L3 swapped)", 5.5))
                s.anchor(k2["tag"] + ".main", x, y2)
        elif d.get("u"):
            uu = self.dev[d["u"][0]]
            pm = next((self.bom[i] for i in u["feeder"].get("_none", []) if False), None)
            arts = [self.bom[i]["article"] for i in range(len(self.bom)) if self.p["line_tags"].get(i) == uu["tag"]]
            s.add(rect(x - 14, y2 - 30, 2 * P + 28, 64), t(x + P, y2 - 12, "VFD", 9, "middle", "b"), t(x + P, y2, "~ / ~", 7, "middle"),
                  t(x - 10, y2 - 22, "L1 L2 L3", 5), t(x - 10, y2 + 30, "U  V  W", 5),
                  tagbox(x + 2 * P + 18, y2 - 26, uu["tag"]), *[t(x + 2 * P + 18, y2 - 10 + 8 * i, a[:20], 5.5) for i, a in enumerate(arts[:3])])
            if self.v.get("cu_fieldbus") == "profinet":
                s.add(t(x + 2 * P + 18, y2 + 18, "PROFINET → PLC", 5.5, cls="b"))
            s.anchor(uu["tag"] + ".main", x, y2)
            y2 += 20
        elif d.get("ss"):
            q = self.dev[d["ss"][0]]
            s.add(box(x - 14, y2 - 20, 2 * P + 28, 40, "SOFT START", 6.5), tagbox(x + 2 * P + 18, y2 - 16, q["tag"]),
                  t(x + 2 * P + 18, y2, q["line"]["article"][:18], 5.5))
            s.anchor(q["tag"] + ".main", x, y2)
        else:
            why = "starter not selected" if u["status"] != "template" else "starter: per template lines"
            s.add(dashbox(x - 14, y2 - 18, 2 * P + 30, 36, why.upper(), 5.5))
        y3 = 410
        s.add(*[ln(x + i * P, y2 + 14 if ks or d.get("ss") or d.get("u") else y2 + 18, x + i * P, y3 - 14) for i in range(3)])
        if d.get("olr"):
            o = self.dev[d["olr"][0]]
            s.add(olr3(x, y3), tagbox(x - 34, y3 - 4, o["tag"]), t(x + 2 * P + 10, y3, o["line"]["article"][:16], 5.5),
                  t(x + 2 * P + 10, y3 + 8, o["line"]["description"][:20], 5.5))
        else:
            s.add(*[ln(x + i * P, y3 - 14, x + i * P, y3 + 14) for i in range(3)])
        sd_left = u["starter"] == "SD"
        for k, m in enumerate(d.get("mpr", [])):                 # CT-operated: beside the line, not in it
            dm = self.dev[m]
            yc = y3 - 30 if d.get("olr") else y3 - 4
            bx = x - 84 if sd_left else x + 2 * P + (74 if d.get("olr") else 16)
            s.add(*[f'<ellipse cx="{x + i * P}" cy="{yc}" rx="4" ry="2.5" class="sym"/>' for i in range(3)],
                  ln(x - 4 if sd_left else x + 2 * P + 4, yc, bx + (40 if sd_left else 0), yc, "mech"),
                  box(bx, yc - 12, 40, 24, "MPR", 6.5), tagbox(bx, yc - 16, dm["tag"], 6.5),
                  t(bx, yc + 22, dm["line"]["article"][:16], 5.5), t(bx, yc + 30, "CT-operated", 5))
        # power terminal 1X1 and the motor
        sd = u["starter"] == "SD" and len(ks) >= 3
        yt = 470
        names = ["U1", "V1", "W1", "W2", "U2", "V2", "PE"] if sd else ["U", "V", "W", "PE"]
        nums = list(range(n_term + 1, n_term + 1 + len(names)))
        self.term_no[tag] = list(zip(nums, names))
        xs_ = [x, x + P, x + 2 * P] + ([x + 64, x + 64 + P, x + 64 + 2 * P] if sd else []) + [x + (64 + 3 * P if sd else 3 * P)]
        s.add(*[ln(xx, y3 + 14 if i < 3 else (y3 + 14 if not sd or i == len(xs_) - 1 else 470), xx, yt - 3) for i, xx in enumerate(xs_[:-1])])
        for xx, (nn, nm) in zip(xs_, zip(nums, names)):
            s.add(term(xx, yt, f"{nn:02d}"), t(xx, yt - 6, nm, 4.5, "middle"))
        s.add(tagbox(x - 34, yt + 4, "1X1", 6.5))
        n_term = nums[-1]
        # cable
        cab = u["cable"]
        xm = x + (32 + P if sd else P)
        if cab:
            size, _, length = cab.rpartition(", ")
            s.add(t(x + 2 * P + 10, 500, "MOTOR CABLE", 5.5, cls="b"), t(x + 2 * P + 10, 508, size[:30], 5.5), t(x + 2 * P + 10, 516, length, 5.5))
        else:
            s.add(t(x + 2 * P + 10, 500, "MOTOR CABLE", 5.5, cls="b warn"),
                  t(x + 2 * P + 10, 508, "NOT SELECTED" + ("" if isinstance(u["kw"], (int, float)) else " (kW not stated)"), 5.5, cls="warn it"),
                  t(x + 2 * P + 10, 516, "2 runs at FLC/√3" if sd else "", 5.5, cls="warn it"))
        for xx in xs_[:-1]:
            s.add(ln(xx, yt + 3, xx, 530), ln(xx, 530, xm + (xx - xs_[0] - (32 + P if sd else P)) * 0.45, 545))
        s.add(ln(xs_[-1], yt + 3, xs_[-1], 560), ln(xs_[-1], 560, xm + 22, 560), t(xs_[-1] + 3, 556, "PE", 5))
        if u["status"] == "template-aux":
            s.add(motor(xm, 566), t(xm, 598, tag, 7, "middle", "b"), t(xm, 608, "AUXILIARY DRIVE", 5.5, "middle"),
                  t(xm, 617, "motor not stated", 5.5, "middle", "warn it"), t(xm, 626, "in the template", 5.5, "middle", "warn it"))
            if ks:
                s.add(t(xm, 638, f"coil: {REF(ks[0] + '.coil')}", 5.5, "middle", "mut"))
            return n_term
        s.add(motor(xm, 566), t(xm, 598, tag, 8, "middle", "b"),
              t(xm, 608, (u["app"] or "")[:22].upper(), 5.5, "middle"),
              t(xm, 617, (f"{_num(u['kw'])} kW" if isinstance(u["kw"], (int, float)) else "kW not stated") + f" · {u['starter'] or '—'}", 6, "middle"),
              t(xm, 626, f"FLC {_num(u['flc_a'])} A", 6, "middle"))
        if ks:
            s.add(t(xm, 638, f"coil: {REF(ks[0] + '.coil')}", 5.5, "middle", "mut"))
        s.anchor(tag + ".motor", xm, 566)
        return n_term

    # ---- control supply (sample p.7 right and p.8) -----------------------------------------------------------------
    def control_supply(self):
        s = self.new("CONTROL SUPPLY 230 V AC / 24 V DC", "csupply")
        all_mcb = sorted(self.by_kind("mcb"), key=lambda d: int(re.sub(r"\D", "", d["tag"][2:]) or 0))
        three_p = lambda d: bool(re.search(r"\b3\s*-?\s*P(OLE)?\b|3POLE", d["line"]["description"].upper()))
        mcbs = [d for d in all_mcb if not three_p(d)]          # control supply: 2-pole MCBs (3-pole ones feed power branches)
        tr = self.by_kind("transformer")
        pn = self.v.get("control_supply") == "phase_neutral" and not tr      # designer chose phase-neutral: no transformer
        x = 140
        s.add(t(60, TOP + 14, f"{'R1, N' if pn else 'R1, Y1'} from the main busbar ({REF('bus1')})", 7), ln(x, TOP + 24, x, TOP + 60), ln(x + 30, TOP + 24, x + 30, TOP + 60),
              t(x - 4, TOP + 34, "R", 6.5, "end"), t(x + 34, TOP + 34, "N" if pn else "Y", 6.5))
        y = TOP + 80
        mi = 0
        if self.scope.get("control_transformer") is False:
            s.add(box(x - 30, y + 20, 120, 40, "NO CONTROL TRANSFORMER IN THIS PANEL — control supply from the main panel", 6))
            y += 80
        elif pn:
            if mcbs:
                m = mcbs[mi]; mi += 1
                s.add(pole_breaker(x, y), pole_breaker(x + 30, y), ln(x + 3, y, x + 33, y, "mech"), tagbox(x - 42, y - 4, m["tag"]),
                      t(x - 42, y + 8, m["line"]["description"][:20], 5.5), t(x - 42, y + 16, m["line"]["article"], 5.5))
            else:
                s.add(ln(x, y - 14, x, y + 14), ln(x + 30, y - 14, x + 30, y + 14), t(x + 40, y, "MCB: none listed", 6, cls="warn it"))
            s.add(t(x + 44, y + 30, "PHASE-NEUTRAL 230 V — no control transformer (designer's choice)", 6.5, cls="b"))
            y += 20
        else:
            if mcbs:
                m = mcbs[mi]; mi += 1
                s.add(pole_breaker(x, y), pole_breaker(x + 30, y), ln(x + 3, y, x + 33, y, "mech"), tagbox(x - 42, y - 4, m["tag"]),
                      t(x - 42, y + 8, m["line"]["description"][:20], 5.5), t(x - 42, y + 16, m["line"]["article"], 5.5))
            else:
                s.add(ln(x, y - 14, x, y + 14), ln(x + 30, y - 14, x + 30, y + 14), t(x + 40, y, "MCB: none listed", 6, cls="warn it"))
            y += 40
            if tr:
                d = tr[0]
                s.add(ln(x, y - 26, x, y), ln(x + 30, y - 26, x + 30, y), rect(x - 10, y, 50, 22), t(x + 15, y + 14, "PRIMARY", 6, "middle"),
                      *[f'<path d="M{x - 4 + 9 * i} {y + 30} a4.5 4.5 0 0 1 9 0" class="w"/>' for i in range(5)],
                      *[f'<path d="M{x - 4 + 9 * i} {y + 40} a4.5 4.5 0 0 0 9 0" class="w"/>' for i in range(5)],
                      rect(x - 10, y + 48, 50, 22), t(x + 15, y + 62, "SECONDARY", 6, "middle"),
                      tagbox(x + 50, y + 30, d["tag"]), t(x + 50, y + 44, d["line"]["description"][:40], 6),
                      t(x + 50, y + 53, d["line"]["article"][:30], 5.5),
                      t(x - 14, y + 82, "230 V", 6.5, "end"), t(x + 44, y + 82, "0 V", 6.5), ln(x + 30, y + 70, x + 30, y + 92))
                y += 92
            else:
                gone = any("control transformer" in str(b.get("description")).lower() and isinstance(b.get("qty"), (int, float))
                           and b["qty"] <= 0 for b in self.bom)
                s.add(dashbox(x - 10, y, 120, 46, "CONTROL TRANSFORMER — REMOVED by a BOM edit" if gone else
                              "CONTROL TRANSFORMER — NOT SIZED: give the coil and lamp VA, or choose phase-neutral", 5.5),
                      ln(x + 30, y + 46, x + 30, y + 60))
                y += 60
            if mi < len(mcbs):
                m = mcbs[mi]; mi += 1
                s.add(pole_breaker(x, y + 16), pole_breaker(x + 30, y + 16), ln(x + 3, y + 16, x + 33, y + 16, "mech"),
                      tagbox(x - 42, y + 12, m["tag"]), t(x - 42, y + 24, m["line"]["description"][:20], 5.5))
                y += 34
        # 230 V rails 02 / 100 to the control wiring
        yr = y + 20
        s.add(ln(x, y, x, yr), ln(x + 30, y, x + 30, yr + 14),
              ln(x, yr, 560, yr, "ac"), ln(x + 30, yr + 14, 560, yr + 14, "rail"),
              t(566, yr + 3, f"02 → {REF('rail02')}", 7), t(566, yr + 17, f"100 → {REF('rail02')}", 7),
              t(x + 50, yr - 4, "02 · 230 V AC phase (red 0.75 mm²)", 6), t(x + 50, yr + 24, "100 · neutral (black 0.75 mm²)", 6))
        s.anchor("rail_src", x, yr)
        # 24 V: MCB → SMPS → MCB → 9X2 → rails 201 / 200
        sm = self.by_kind("smps")
        x2, y2 = 720, TOP + 60
        s.add(t(x2 - 60, TOP + 14, "24 V DC", 9, cls="b"))
        if self.scope.get("smps") is False or not sm:
            s.add((box if self.scope.get("smps") is False else dashbox)(x2 - 30, y2 + 40, 140, 40,
                  "NO 24 V SUPPLY IN THIS PANEL" if self.scope.get("smps") is False else "24 V SUPPLY — NOT SELECTED"))
        else:
            d = sm[0]
            s.add(t(x2 - 10, y2 - 20, f"from 02 / 100 ({REF('rail_src')})", 6.5), ln(x2, y2 - 14, x2, y2), ln(x2 + 30, y2 - 14, x2 + 30, y2))
            if mi < len(mcbs):
                m = mcbs[mi]; mi += 1
                s.add(pole_breaker(x2, y2 + 14), pole_breaker(x2 + 30, y2 + 14), ln(x2 + 3, y2 + 14, x2 + 33, y2 + 14, "mech"),
                      tagbox(x2 - 42, y2 + 10, m["tag"]), t(x2 - 42, y2 + 22, m["line"]["description"][:20], 5.5))
            else:
                s.add(ln(x2, y2, x2, y2 + 28), ln(x2 + 30, y2, x2 + 30, y2 + 28), t(x2 + 40, y2 + 16, "MCB before the supply: none listed", 6, cls="warn it"))
            ys = y2 + 50
            s.add(ln(x2, y2 + 28, x2, ys), ln(x2 + 30, y2 + 28, x2 + 30, ys), rect(x2 - 20, ys, 70, 46),
                  ln(x2 - 20, ys + 46, x2 + 50, ys), t(x2 - 16, ys + 10, "~", 8), t(x2 + 44, ys + 42, "=", 8, "end"),
                  tagbox(x2 + 58, ys + 8, d["tag"]), t(x2 + 58, ys + 22, d["line"]["article"][:30], 6),
                  t(x2 + 58, ys + 31, d["line"]["description"][:44], 5.5),
                  t(x2 + 58, ys + 40, f"24 V load {_num((self.v.get('power') or {}).get('dc_load_a'), 2)} A (power calculation)"
                    if isinstance((self.v.get("power") or {}).get("dc_load_a"), (int, float)) else "", 5.5))
            yo = ys + 46
            s.add(ln(x2, yo, x2, yo + 30), ln(x2 + 30, yo, x2 + 30, yo + 30), t(x2 - 4, yo + 12, "+24V", 5.5, "end"), t(x2 + 34, yo + 12, "0V", 5.5))
            yr2 = yo + 60
            s.add(term(x2, yo + 34, "1"), term(x2 + 30, yo + 34, "2"), tagbox(x2 - 40, yo + 38, "9X2", 6.5),
                  ln(x2, yo + 37, x2, yr2), ln(x2 + 30, yo + 37, x2 + 30, yr2 + 14),
                  ln(x2, yr2, 1120, yr2, "r24"), ln(x2 + 30, yr2 + 14, 1120, yr2 + 14, "rail"),
                  t(x2 + 50, yr2 - 4, "201 · +24 V DC (blue 0.75 mm²)", 6), t(x2 + 50, yr2 + 24, "200 · 0 V DC (white 0.75 mm²)", 6),
                  t(1124, yr2 + 3, "→ " + (REF("io_di") if self.plc_ok else "—"), 6.5))
            s.anchor("smps", x2, ys)
        # other 230 V consumers listed in the BOM (hour meter on the ladder)
        rest = mcbs[mi:] + [d for d in all_mcb if three_p(d)]
        if rest:
            s.add(t(60, 560, "Other MCBs in the BOM (not on this sheet): " + ", ".join(f"{m['tag']} {m['line']['description'][:18]}" for m in rest)[:150], 6.5, cls="mut"),
                  t(60, 571, "3-pole MCBs feed power branches of the template (auxiliary drives, heaters); their circuits are not stated.", 6.5, cls="mut"))

    # ---- control wiring (ladder), sample p.9-11 -------------------------------------------------------------------
    def _rungs(self):
        rungs = []
        if not self.plc_ok and self.dev.get("EPB"):
            rungs.append({"kind": "estop"})
        hm = self.by_kind("hour_meter")
        big = max(self.units, key=lambda u: u["kw"] if isinstance(u["kw"], (int, float)) else -1, default=None)
        for u in self.units:
            rungs.append({"kind": "unit", "u": u, "hm": hm[0] if hm and u is big else None})
        return rungs

    def _cmd(self, u, s, x, y):
        """The command contact of a motor: the PLC relay of its run output, else a dashed 'not selected'."""
        run = next((r for r in self.dos if r.get("unit") == u["tag"] and r.get("name", "").endswith("_Run")), None) or \
              next((r for r in self.dos if r.get("unit") == u["tag"]), None)
        rel = self.do_relay.get(run["name"]) if run else None
        if rel:
            s.add(no_v(x, y), t(x - 10, y - 2, rel, 6.5, "end", "b"), t(x - 10, y + 6, "11-14", 5, "end"),
                  t(x + 6, y - 2, run["name"][:16], 5, cls="mut"), t(x + 6, y + 5, f"coil {REF(rel + '.coil')}", 5, cls="mut"))
            return True
        if not self.plc_ok and (self.by_kind("pb") or u["kit"]):
            s.add(no_v(x, y, "pb"), t(x - 16, y - 2, "START", 5.5, "end"), t(x - 16, y + 6, "(per kit)", 5, "end", "mut"))
            return True
        s.add(ln(x, y - 12, x, y + 12), dashbox(x + 4, y - 10, 46, 20, "command not selected", 5))
        return False

    def ladder(self):
        rungs = self._rungs()
        x_first, top, bot = 110, 160, 600
        widths = [(210 if r.get("u") and r["u"]["starter"] == "SD" and len(r["u"]["dev"].get("k") or []) >= 3 else 80) for r in rungs]
        pages, x = [[]], x_first
        for r, w in zip(rungs, widths):
            if x + w > 1110:
                pages.append([])
                x = x_first
            pages[-1].append((r, x, w))
            x += w
        ferr = [2]

        def fno():
            ferr[0] += 1
            return f"{ferr[0]:02d}"
        for pi, page in enumerate(pages):
            s = self.new(f"CONTROL WIRING DIAGRAM-{pi + 1}", "ladder")
            s.add(ln(70, top, 1110, top, "ac"), ln(70, bot, 1110, bot, "rail"),
                  t(44, top - 6, "02", 7, cls="b red"), t(44, top + 10, REF("rail_src") if pi == 0 else REF(f"ladder{pi}"), 5.5),
                  t(44, bot - 6, "100", 7, cls="b"), t(1114, top + 3, ("02 → " + REF(f"ladder{pi + 2}")) if pi + 1 < len(pages) else "02", 6.5),
                  t(1114, bot + 3, "100", 6.5))
            s.anchor("rail02" if pi == 0 else f"ladder{pi + 1}", 80, top)
            if pi:
                s.anchor(f"ladder{pi + 1}", 80, top)
            for r, x, w in page:
                cx = x + 30
                if r["kind"] == "estop":
                    d = self.dev["EPB"]
                    s.add(ln(cx, top, cx, 280), dot(cx, top), nc_v(cx, 292), tagbox(cx + 10, 292, "EPB", 6.5),
                          ln(cx, 304, cx, bot), t(cx, bot + 14, "EMERGENCY STOP", 5.5, "middle", "b"),
                          t(cx, bot + 22, "(breaks the coil supply: no PLC)", 5, "middle", "mut"))
                    continue
                u = r["u"]
                ks = u["dev"].get("k") or []
                s.add(ln(cx, top, cx, 230), dot(cx, top), t(cx + 3, 200, fno(), 5))
                self._cmd(u, s, cx, 242)
                yy = 254
                if u["dev"].get("olr"):
                    o = u["dev"]["olr"][0]
                    s.add(ln(cx, yy, cx, 282), nc_v(cx, 294), t(cx + 9, 292, o, 6, cls="b"), t(cx + 9, 299, "95-96", 5))
                    yy = 306
                s.add(t(cx + 3, yy + 30, fno(), 5))
                label = (u["app"] or "").upper()[:16] if u["status"] != "template-aux" else "AUX"
                if u["dev"].get("u") and self.v.get("cu_fieldbus") == "profinet":     # a drive on the fieldbus: no control wiring
                    s.add(box(cx - 30, 330, 60, 60, f"{u['tag']} ({u['dev']['u'][0]}): RUN / STOP / SPEED VIA PROFINET — no control wiring", 5),
                          t(cx, bot + 14, f"{u['tag']} {label}".strip()[:20], 5.5, "middle", "b"))
                    continue
                if u["starter"] == "SD" and len(ks) >= 3:
                    km, kd, kst = ks[:3]
                    tm = (u["dev"].get("timer") or [None])[0]
                    bx = [cx, cx + 48, cx + 96, cx + 144]
                    s.add(ln(cx, yy, cx, 330), ln(cx, 330, bx[3], 330), dot(cx, 330))
                    # timer, star (T star NO + delta NC), delta (T delta NO + star NC), main
                    s.add(ln(bx[0], 330, bx[0], 530))
                    if tm:
                        s.add(coil(bx[0], 540), t(bx[0] - 10, 538, tm, 6.5, "end", "b"), t(bx[0], bot + 14, "TIMER", 5.5, "middle", "b"),
                              t(bx[0], bot + 22, "star/delta", 5, "middle"))
                        s.anchor(tm + ".coil", bx[0], 540)
                    else:
                        s.add(dashbox(bx[0] - 18, 520, 36, 30, "timer not listed", 5))
                    s.add(ln(bx[1], 330, bx[1], 380), no_v(bx[1], 392, "timer"), t(bx[1] - 12, 390, f"{tm or 'T'}", 5.5, "end"),
                          t(bx[1] - 12, 397, "S", 5, "end"), ln(bx[1], 404, bx[1], 440), nc_v(bx[1], 452), t(bx[1] + 9, 452, kd, 5.5, cls="b"),
                          ln(bx[1], 464, bx[1], 530), coil(bx[1], 540), t(bx[1] - 10, 538, kst, 6.5, "end", "b"),
                          t(bx[1], bot + 14, "STAR", 5.5, "middle", "b"), t(bx[1], bot + 22, f"main {REF(kst + '.main')}", 5, "middle", "mut"))
                    s.add(ln(bx[2], 330, bx[2], 380), no_v(bx[2], 392, "timer"), t(bx[2] - 12, 390, f"{tm or 'T'}", 5.5, "end"),
                          t(bx[2] - 12, 397, "D", 5, "end"), ln(bx[2], 404, bx[2], 440), nc_v(bx[2], 452), t(bx[2] + 9, 452, kst, 5.5, cls="b"),
                          ln(bx[2], 464, bx[2], 530), coil(bx[2], 540), t(bx[2] - 10, 538, kd, 6.5, "end", "b"),
                          t(bx[2], bot + 14, "DELTA", 5.5, "middle", "b"), t(bx[2], bot + 22, f"main {REF(kd + '.main')}", 5, "middle", "mut"))
                    s.add(ln(bx[3], 330, bx[3], 530), coil(bx[3], 540), t(bx[3] - 10, 538, km, 6.5, "end", "b"),
                          t(bx[3], bot + 14, "MAIN", 5.5, "middle", "b"), t(bx[3], bot + 22, f"main {REF(km + '.main')}", 5, "middle", "mut"),
                          t(bx[0], bot + 32, f"{u['tag']} {label} — {_num(u['kw'])} kW STAR/DELTA".replace("  ", " "), 5.5, cls="b"),
                          t(bx[0], bot + 40, "sequence as company drawing AVELCPSDL08WPLC p.11", 5, cls="mut"))
                    for xb, k in zip(bx[1:], (kst, kd, km)):
                        s.anchor(k + ".coil", xb, 540)
                    kit_l = [d for d in self.dev.values() if d["kind"] == "lamp" and d["unit"] == u["tag"]]
                    if kit_l:
                        s.add(t(bx[0], bot + 48, "kit lamps " + ", ".join(f"{d['tag']} ({d.get('colour') or '?'})" for d in kit_l)
                                + ": wiring per the company kit", 5, cls="mut"))
                    for xb in bx:
                        s.add(ln(xb, 550, xb, bot), dot(xb, bot))
                    if r.get("hm"):
                        h = r["hm"]
                        s.add(ln(bx[3], 500, bx[3] + 30, 500), ln(bx[3] + 30, 500, bx[3] + 30, 530), rect(bx[3] + 22, 530, 16, 16),
                              t(bx[3] + 30, 541, "h", 7, "middle"), t(bx[3] + 40, 528, h["tag"], 6, cls="b"), ln(bx[3] + 30, 546, bx[3] + 30, bot),
                              dot(bx[3] + 30, bot), dot(bx[3], 500))
                    continue
                sd_gap = u["starter"] == "SD" and ks
                if sd_gap:
                    ks = []
                s.add(ln(cx, yy, cx, 530 if ks or u["dev"].get("u") or u["dev"].get("ss") else 505))
                if ks:
                    s.add(coil(cx, 540), t(cx - 10, 538, ks[0], 6.5, "end", "b"))
                    s.anchor(ks[0] + ".coil", cx, 540)
                    s.add(t(cx, bot + 22, f"main {REF(ks[0] + '.main')}", 5, "middle", "mut"))
                    if r.get("hm"):
                        h = r["hm"]
                        s.add(ln(cx, 500, cx + 26, 500), dot(cx, 500), ln(cx + 26, 500, cx + 26, 530), rect(cx + 18, 530, 16, 16),
                              t(cx + 26, 541, "h", 7, "middle"), t(cx + 36, 528, h["tag"], 6, cls="b"), ln(cx + 26, 546, cx + 26, bot), dot(cx + 26, bot))
                elif u["dev"].get("u"):
                    uu = u["dev"]["u"][0]
                    if self.v.get("cu_fieldbus") == "profinet":
                        s.add(box(cx - 26, 500, 52, 40, f"{uu} RUN / STOP VIA PROFINET", 5))
                    else:
                        s.add(box(cx - 26, 510, 52, 30, f"{uu} DI0 (run)", 5.5))
                elif u["dev"].get("ss"):
                    s.add(box(cx - 26, 510, 52, 30, f"{u['dev']['ss'][0]} IN1 (run)", 5.5))
                else:
                    s.add(dashbox(cx - 26, 505, 52, 40, "star-delta incomplete in the template" if sd_gap else "coil: starter not selected", 5),
                          ln(cx, 545, cx, 550))
                s.add(ln(cx, 550, cx, bot), dot(cx, bot), t(cx, bot + 14, f"{u['tag']} {label}".strip()[:20], 5.5, "middle", "b"),
                      t(cx, bot + 32, (f"{_num(u['kw'])} kW " if isinstance(u['kw'], (int, float)) else "") + (u["starter"] or ""), 5, "middle"))
                kit_l = [d for d in self.dev.values() if d["kind"] == "lamp" and d["unit"] == u["tag"]]
                if kit_l:
                    s.add(t(cx, bot + 40, "kit lamps " + ", ".join(f"{d['tag']} ({d.get('colour') or '?'})" for d in kit_l), 5, "middle", "mut"))
            s.add(rect(40, 712, 200, 82, "th"), t(46, 724, "CABLE COLOUR", 7, cls="b"),
                  *[t(46, 736 + 11 * i, r, 6.5) for i, r in enumerate(["RD - RED (02, 230 V phase)", "BK - BLACK (100, neutral)",
                                                                         "OR - ORANGE (potential free)", "BU - BLUE (201, +24 V)", "WH - WHITE (200, 0 V)"])],
                  t(250, 724, "NOTE:", 7, cls="b"), t(250, 736, "Ferrules 01-99 / 101-199 on the 230 V phase side (company legend p.3).", 6.5),
                  t(250, 747, "Under each coil: the sheet and column of its main contacts.", 6.5))

    # ---- digital input & output (sample p.12) ---------------------------------------------------------------------
    def _field_device(self, r):
        """The device whose contact drives a digital input (by the I/O list's signal text)."""
        unit = next((u for u in self.units if u["tag"] == r.get("unit")), None)
        sig = str(r.get("signal") or "").lower()
        if unit:
            d = unit["dev"]
            if "running" in sig and d.get("k"):
                return f"{d['k'][0]} 13-14"
            if "trip" in sig:
                if d.get("olr"):
                    return f"{d['olr'][0]} 97-98"
                if d.get("mpcb"):
                    return f"{d['mpcb'][0]} aux"
            if d.get("u"):
                return f"{d['u'][0]}"
        if "emergency" in sig and self.dev.get("EPB"):
            return "EPB"
        if "reset" in sig:
            pb = self.by_kind("pb")
            return pb[0]["tag"] if pb else None
        if "phase" in sig:
            for k in ("PMR", "UV/OV"):
                if self.dev.get(k):
                    return k
        return None

    def io_digital(self):
        if not self.plc_ok:
            if self.scope.get("plc") is False:
                s = self.new("DIGITAL INPUT & OUTPUT", "io")
                s.add(box(400, 300, 380, 60, "NO PLC IN THIS PANEL — " + ("the template lists none" if self.v.get("template") else "'No PLC' chosen")
                          + ", so there are no PLC inputs or outputs", 8))
            return
        per = 34
        n = max(len(self.dis), len(self.dos))
        pages = max(1, -(-n // per))
        cpu = next((d for d in self.by_kind("plc") if d.get("cpu")), None) or self.by_kind("plc")[0]
        for pi in range(pages):
            s = self.new("DIGITAL INPUT & OUTPUT" + (f"-{pi + 1}" if pages > 1 else ""), "io")
            if pi == 0:
                s.anchor("io_di", 120, 232)
            x0, dx = 110, 30
            s.add(ln(70, 232, 1120, 232, "r24"), ln(70, 244, 1120, 244, "rail"), ln(70, 520, 1120, 520, "rail"),
                  t(40, 235, "201", 6.5, cls="b"), t(40, 247, "200", 6.5, cls="b"), t(40, 523, "200", 6.5, cls="b"),
                  t(60, 247, "from " + REF("smps"), 5))
            # PLC block
            mods = self.by_kind("plc")
            nmax = max(len(self.dis[pi * per:(pi + 1) * per]), len(self.dos[pi * per:(pi + 1) * per]), 8)
            s.add(rect(x0 - 20, 330, max(380, nmax * dx + 20), 90), t(x0 - 14, 344, " + ".join(f"{d['tag']} {d['line']['article']}" for d in mods)[:120], 6.5, cls="b"),
                  t(x0 - 14, 414, cpu["line"]["description"][:90], 6))
            for k, r in enumerate(self.dis[pi * per:(pi + 1) * per]):
                x = x0 + k * dx
                dev = self._field_device(r)
                nc = r.get("unit") == "panel" and "emergency" in str(r.get("signal")).lower()
                s.add(dot(x, 232), ln(x, 232, x, 262), nc_v(x, 274) if nc else no_v(x, 274), ln(x, 286, x, 296), term(x, 300), ln(x, 302, x, 330),
                      t(x + 4, 306, f"X2:{pi * per + k + 1}", 4.5), t(x, 352, r.get("channel", ""), 5, "middle"),
                      t(x + 2, 226, r.get("name", "")[:26], 5.5, "start", "", -90))
                if dev:
                    s.add(t(x - 8, 278, dev, 4.5, "end"))

            for k, r in enumerate(self.dos[pi * per:(pi + 1) * per]):
                x = x0 + k * dx
                rel = self.do_relay.get(r.get("name"))
                s.add(t(x, 404, r.get("channel", ""), 5, "middle"), ln(x, 420, x, 442), term(x, 446), ln(x, 448, x, 470),
                      t(x + 4, 452, f"X2:{len(self.dis) + pi * per + k + 1}", 4.5))
                if rel:
                    s.add(rect(x - 6, 474, 12, 12), t(x + 8, 478, "A1", 4), t(x + 8, 490, "A2", 4), t(x + 3, 500, rel, 5.5, cls="b"),
                          ln(x, 486, x, 520), dot(x, 520))
                    s.anchor(rel + ".coil", x, 480)
                else:
                    s.add(dashbox(x - 12, 470, 24, 22, "relay?", 4.5), ln(x, 492, x, 520))
                s.add(t(x + 2, 530, r.get("name", "")[:26], 5.5, "start", "", 90))
            s.add(t(52, 330, "FIELD / PANEL CONTACTS", 6, cls="b", rot=-90), t(52, 510, "INTERFACE RELAYS", 6, cls="b", rot=-90),
                  rect(40, 712, 300, 60, "th"), t(46, 724, "NOTE:", 7, cls="b"),
                  t(46, 736, "Names from the I/O list (inputs I_…, outputs O_…). X2 = PLC field terminals.", 6.5),
                  t(46, 747, "Relay contacts drive the coils on the control wiring sheets.", 6.5),
                  t(46, 758, f"Channel order as the I/O list; module addressing per the PLC configuration.", 6.5))

    def io_analog(self):
        if not self.plc_ok or not (self.ais or self.aos):
            return
        s = self.new("ANALOG INPUT & OUTPUT", "ai")
        s.add(ln(70, 200, 1120, 200, "r24"), ln(70, 214, 1120, 214, "rail"), t(40, 203, "201", 6.5, cls="b"), t(40, 217, "200", 6.5, cls="b"))
        x0 = 140
        for k, r in enumerate((self.ais + self.aos)[:24]):
            x = x0 + k * 40
            ai = r["type"] == "AI"
            s.add(dot(x, 200), ln(x, 200, x, 280), rect(x - 10, 280, 20, 26, "dash" if ai else "sym"), t(x, 297, "4-20", 4.5, "middle"),
                  ln(x, 306, x, 380), term(x, 384), ln(x, 386, x, 440), t(x, 452, r.get("channel", ""), 5, "middle"),
                  t(x + 2, 190, r.get("name", "")[:26], 5.5, "start", "", -90),
                  t(x + 12, 296, "transmitter" if ai else "drive", 4.5))
        s.add(rect(x0 - 30, 440, 40 * min(24, len(self.ais) + len(self.aos)) + 20, 50),
              t(x0 - 24, 484, "PLC analog channels (module per the PLC selection)", 6))

    # ---- terminal details (sample p.16) -----------------------------------------------------------------------------
    def terminals(self):
        s = self.new("TERMINAL DETAILS", "terminals")
        def strip(x, y, label, rows, title):
            s.add(t(x, y - 34, title, 7.5, cls="b"), tagbox(x - 34, y + 14, label, 7))
            for i, (num, top, bottom) in enumerate(rows):
                xx = x + i * 18
                s.add(rect(xx, y, 18, 30), circ(xx + 9, y + 8, 3), circ(xx + 9, y + 22, 3), t(xx + 9, y + 16, num, 5, "middle", "b"),
                      t(xx + 11, y - 3, top[:14], 4.8, "start", "", -90), t(xx + 7, y + 34, bottom[:20], 4.8, "start", "", 90))
            return x + 18 * len(rows)
        y = 170
        pw = [(f"{n:02d}", nm, u) for u, nums in self.term_no.items() for n, nm in nums]
        for i in range(0, max(len(pw), 1), 54):
            chunk = pw[i:i + 54]
            strip(80, y, "1X1", chunk, "POWER TERMINAL — motor outgoing (cable side below)" if i == 0 else "POWER TERMINAL (cont.)")
            y += 150
            if y > 470:
                break
        if not pw:
            s.add(t(80, 170, "no motor terminals: no feeder drawn", 6.5, cls="warn it"))
        if self.plc_ok:
            io = [(str(k + 1), r.get("channel", ""), r.get("name", "")) for k, r in enumerate(self.dis + self.dos + self.ais + self.aos)]
            yy = max(y, 320)
            for i in range(0, len(io), 54):
                if yy > 560:
                    s.add(t(80, yy, f"+ {len(io) - i} more I/O terminals: see the I/O list", 6.5, cls="mut"))
                    break
                strip(80, yy, "X2", io[i:i + 54], "PLC FIELD TERMINALS (channel above, signal below)" if i == 0 else "PLC FIELD TERMINALS (cont.)")
                yy += 150
        dist = []
        if self.scope.get("control_transformer") is not False:
            dist.append(("9X1", [("1", "02", "phase"), ("2", "02", "phase"), ("3", "100", "neutral"), ("4", "100", "neutral")],
                         "230 V DISTRIBUTION"))
        if self.by_kind("smps") and self.scope.get("smps") is not False:
            dist.append(("9X2", [("1", "201", "+24V"), ("2", "201", "+24V"), ("3", "200", "-24V"), ("4", "200", "-24V")], "24 V DISTRIBUTION"))
        x = 820
        for lab, rows, title in dist:
            x = strip(x, 640, lab, rows, title) + 70

    # ---- bill of material (sample p.14-15) --------------------------------------------------------------------------
    def bom_sheets(self):
        from .bom_export import drawing_bom
        rows = drawing_bom(self.bom, self.p["line_tags"])
        head, body = rows[0][:8], rows[1:]
        per = 40
        cols = [(40, 34), (74, 330), (404, 110), (514, 160), (674, 120), (794, 120), (914, 56), (970, 44)]
        for pi in range(max(1, -(-len(body) // per))):
            s = self.new(f"BILL OF MATERIAL-{pi + 1}", "bom")
            y = TOP + 6
            s.add(rect(40, y - 10, 974, 16, "th"), *[t(x + w / 2, y + 2, h, 6.5, "middle", "b") for (x, w), h in zip(cols, head)])
            for i, r in enumerate(body[pi * per:(pi + 1) * per]):
                yy = y + 16 + i * 14
                s.add(ln(40, yy + 4, 1014, yy + 4, "th"))
                for (x, w), val in zip(cols, r[:8]):
                    txt = "" if val is None else (f"{val:g}" if isinstance(val, float) else str(val))
                    s.add(t(x + 3, yy + 1, txt[:int(w / 3.6)], 6))
            for x, w in cols:
                s.add(ln(x, y - 10, x, y + 6 + 14 * min(per, len(body) - pi * per) + 4, "th"))
            s.add(ln(1014, y - 10, 1014, y + 6 + 14 * min(per, len(body) - pi * per) + 4, "th"))

    # ---- index and legend, from the sheets drawn ------------------------------------------------------------------
    def fill_index(self):
        s = self.index_sheet
        groups, order = {}, []
        for i, sh in enumerate(self.sheets, 1):
            base = re.sub(r"-\d+$", "", sh.title)
            if base not in groups:
                groups[base] = []
                order.append(base)
            groups[base].append(i)
        rows = [(b, (f"{groups[b][0]:02d}" if len(groups[b]) == 1 else f"{groups[b][0]:02d}-{groups[b][-1]:02d}")) for b in order]
        rows.insert(4, ("GENERAL ARRANGEMENT DRAWING — EXTERNAL & INTERNAL VIEW", "not made by the tool (enclosure out of scope)"))
        rows.append(("BLOCK DIAGRAM & SENSOR PIN / WIRE COLOUR CODE DETAILS", "not made by the tool"))
        x0, y0 = 250, TOP + 30
        s.add(rect(x0, y0 - 18, 720, 30, "th"), t(x0 + 40, y0, "S.NO", 9, "middle"), t(x0 + 340, y0, "PAGE DESCRIPTION", 9, "middle"),
              t(x0 + 640, y0, "SHEET NO.", 9, "middle"))
        for i, (title, sh) in enumerate(rows):
            y = y0 + 30 + i * 28
            s.add(rect(x0, y - 18, 720, 28, "th"), ln(x0 + 80, y - 18, x0 + 80, y + 10, "th"), ln(x0 + 560, y - 18, x0 + 560, y + 10, "th"),
                  t(x0 + 40, y, i + 1, 8, "middle"), t(x0 + 100, y, title, 8),
                  t(x0 + 640, y, sh, 8 if sh[:1].isdigit() else 6, "middle", "" if sh[:1].isdigit() else "mut it"))
        s.add(ln(x0 + 80, y0 - 18, x0 + 80, y0 + 12, "th"), ln(x0 + 560, y0 - 18, x0 + 560, y0 + 12, "th"))

    def fill_legend(self):
        s = self.legend_sheet
        names = {"incomer": "MOULDED CASE CIRCUIT BREAKER", "mpcb": "MOTOR PROTECTION CIRCUIT BREAKER", "contactor": "POWER CONTACTOR",
                 "mcb": "MINIATURE CIRCUIT BREAKER", "ct": "CURRENT TRANSFORMER", "ct_sensor": "CURRENT SENSOR", "pb": "PUSH BUTTON",
                 "ipb": "ILLUMINATED PUSH BUTTON", "estop": "EMERGENCY STOP PUSH BUTTON", "meter": "VAF / ENERGY METER",
                 "hour_meter": "HOUR METER", "hmi": "OPERATOR PANEL (HMI)", "uvov": "PHASE FAILURE & UV/OV RELAY", "pmr": "PHASE MONITORING RELAY", "spd": "SURGE ARRESTER",
                 "fuse": "FUSE", "lamp": "INDICATION LAMP", "transformer": "CONTROL TRANSFORMER", "smps": "24 V DC POWER SUPPLY (SMPS)",
                 "plc": "PLC CPU / MODULE", "relay": "INTERFACE RELAY (24 V)", "relay230": "RELAY BOARD (230 V)", "timer": "STAR / DELTA TIMER", "olr": "OVERLOAD RELAY",
                 "mpr": "MOTOR PROTECTION RELAY", "drive": "FREQUENCY CONVERTER (VFD)", "ss": "SOFT STARTER", "selector": "SELECTOR SWITCH"}
        by = {}
        for d in self.dev.values():
            if d["kind"] in names:
                by.setdefault(d["kind"], []).append(d["tag"])
        order = list(names)
        key = lambda x: (0 if "PHASE" in x else 1, re.sub(r"\d", "", x), int(re.sub(r"\D", "", x) or 0))
        rows = [(_compact(sorted(tags, key=key))[:44], names[k]) for k, tags in sorted(by.items(), key=lambda kv: order.index(kv[0]))]
        if self.term_no:
            rows.append(("1X1", "POWER TERMINAL BLOCK (motors)"))
        if self.plc_ok:
            rows.append(("X2", "PLC FIELD TERMINALS"))
        rows += [("9X1, 9X2", "230 V / 24 V DISTRIBUTION TERMINALS")] if self.by_kind("smps") else []
        x0, y0 = 60, TOP + 30
        s.add(t(x0 + 240, y0 - 10, "LEGENDS & ABBREVIATIONS (tags used in this panel)", 9, "middle", "b"))
        for i, (tg, nm) in enumerate(rows[:26]):
            y = y0 + 6 + i * 17
            s.add(rect(x0, y, 200, 17, "th"), rect(x0 + 200, y, 300, 17, "th"), t(x0 + 4, y + 12, tg, 6.5), t(x0 + 204, y + 12, nm, 7))
        # symbols
        sx, sy = 600, TOP + 30
        s.add(t(sx + 250, sy - 10, "SYMBOLS & ABBREVIATIONS", 9, "middle", "b"))
        syms = [(mccb3, "MOULDED CASE CIRCUIT BREAKER (3P)"), (mpcb3, "MOTOR PROTECTION CIRCUIT BREAKER (3P)"),
                (lambda x, y: three(pole_contactor, x, y), "POWER CONTACTOR (3P)"), (olr3, "OVERLOAD RELAY (3P)"), (fuse3, "FUSE (3P)"),
                (lambda x, y: motor(x + P, y, 13), "MOTOR (3P)"), (lambda x, y: no_v(x + P, y), "NORMALLY OPEN CONTACT"),
                (lambda x, y: nc_v(x + P, y), "NORMALLY CLOSED CONTACT"), (lambda x, y: no_v(x + P, y, "timer"), "TIMER CONTACT"),
                (lambda x, y: no_v(x + P, y, "pb"), "PUSH BUTTON (NO)"), (lambda x, y: coil(x + P, y), "CONTACTOR / RELAY COIL"),
                (lambda x, y: lamp(x + P, y), "INDICATION LAMP"), (lambda x, y: term(x + P, y), "TERMINAL")]
        for i, (fn, nm) in enumerate(syms):
            col, row = divmod(i, 7)
            x, y = sx + col * 280, sy + 10 + row * 50
            s.add(rect(x, y, 90, 50, "th"), rect(x + 90, y, 190, 50, "th"), fn(x + 36, y + 25), t(x + 96, y + 28, nm, 6.5))
        # wire colours (p.3)
        from .bom_export import _conventions
        wires = _conventions().get("wire", [])
        y = 560
        s.add(rect(80, y - 14, 440, 18, "th"), t(86, y, "POWER SUPPLY", 7, cls="b"), t(306, y, "COLOUR", 7, cls="b"), t(436, y, "FERRULES", 7, cls="b"))
        for i, w in enumerate(wires):
            yy = y + 4 + i * 16
            s.add(rect(80, yy, 440, 16, "th"), t(86, yy + 11, w["circuit"], 6.5), t(306, yy + 11, w["colour"], 6.5), t(436, yy + 11, w["ferrules"], 6.5))

    # ---- frame, references, SVG -------------------------------------------------------------------------------------
    def frame(self, no: int, total: int, sh: Sheet) -> str:
        m = self.meta
        ver = m.get("version") or {}
        g = [rect(18, 18, W - 36, H - 36, "fr"), rect(GX0, GY0, GX1 - GX0, GY1 - GY0, "fr")]
        for i in range(6):
            x = GX0 + CW * (i + 0.5)
            g += [t(x, 27, i + 1, 9, "middle"), t(x, H - 21, i + 1, 9, "middle")]
            if i:
                g += [ln(GX0 + CW * i, 18, GX0 + CW * i, GY0, "th"), ln(GX0 + CW * i, GY1, GX0 + CW * i, H - 18, "th")]
        for i, ch in enumerate("ABCD"):
            y = GY0 + RH * (i + 0.5)
            g += [t(24, y, ch, 9, "middle"), t(W - 24, y, ch, 9, "middle")]
            if i:
                g += [ln(18, GY0 + RH * i, GX0, GY0 + RH * i, "th"), ln(GX1, GY0 + RH * i, W - 18, GY0 + RH * i, "th")]
        g += [rect(GX0, GY0, 150, 16, "th"), t(GX0 + 4, GY0 + 11, "Do Not Scale the Drawing", 7), t(GX0 + 160, GY0 + 13, sh.title, 9.5),
              ln(GX0 + 160, GY0 + 16, GX0 + 160 + 5.6 * len(sh.title), GY0 + 16, "th")]
        # revision block (from the design's versions)
        rx = 590
        g += [rect(rx, GY0, GX1 - rx, 66, "th"), ln(rx, GY0 + 14, GX1, GY0 + 14, "th")]
        for x, h in ((rx, "VERSION"), (rx + 90, "STATE"), (rx + 160, "DESCRIPTION"), (rx + 440, "Sign & Date")):
            g += [ln(x, GY0, x, GY0 + 66, "th"), t(x + 4, GY0 + 10, h, 6.5)]
        revs = m.get("revisions") or []
        for i, r in enumerate(revs[:3]):
            y = GY0 + 26 + i * 16
            g += [t(rx + 4, y, f"v{r['v']}" + (f" · {r['label']}" if r.get("label") else ""), 6.5),
                  t(rx + 94, y, r.get("state", "draft"), 6.5), t(rx + 164, y, str(r.get("summary") or "")[:58], 6),
                  t(rx + 444, y, f"{r.get('by') or '—'}/{str(r.get('at') or '')[:10]}", 6)]
        if not revs:
            g += [t(rx + 164, GY0 + 30, "not saved to a project: no version yet", 6.5, cls="mut it")]
        # title block
        x, y = TB_X, TB_Y
        g += [rect(x, y, GX1 - x, GY1 - y, "fr"),
              t(x + 10, y + 20, (m.get("client") or "Panel Selector v2").upper()[:44], 13, cls="b"),
              t(x + 10, y + 33, "Schematic drawing set generated from the design — every tag shared with the BOM", 6.5, cls="mut"),
              ln(x, y + 38, GX1, y + 38, "th")]
        cols = [(x, "Drawn by-Date", ver.get("by"), ver.get("at")), (x + 186, "Checked by-Date", ver.get("checked_by"), ver.get("checked_at")),
                (x + 372, "Approved by-Date", ver.get("approved_by"), ver.get("approved_at"))]
        for cx, h, who, when in cols:
            g += [ln(cx, y + 38, cx, y + 66, "th"), t(cx + 6, y + 48, h, 6.5),
                  t(cx + 6, y + 61, f"{who or '—'}  {str(when or '')[:10]}", 7.5)]
        state = ver.get("state") or "draft"
        g += [ln(x, y + 66, GX1, y + 66, "th"), ln(x + 300, y + 66, x + 300, GY1, "th"), ln(x + 430, y + 66, x + 430, GY1, "th"),
              ln(x + 495, y + 66, x + 495, GY1, "th"),
              t(x + 6, y + 76, "TITLE:", 6.5), t(x + 6, y + 92, (m.get("title") or "Panel")[:52], 8, cls="b"),
              t(x + 6, y + 104, "APPROVED" if state == "approved" else "DRAFT — not for construction", 6.5,
                cls="" if state == "approved" else "warn b"),
              t(x + 306, y + 76, "DRG NO:", 6.5), t(x + 306, y + 92, m.get("drg") or "—", 8),
              t(x + 436, y + 76, "REV NO", 6.5), t(x + 462, y + 92, f"{ver.get('v', 0):02d}" if ver else "00", 8, "middle"),
              t(x + 501, y + 76, "SHEET NO", 6.5), t(x + 528, y + 92, f"{no}/{total}", 8, "middle")]
        return "".join(g)

    def render(self) -> list[str]:
        where = {}
        for i, sh in enumerate(self.sheets, 1):
            for k, (x, y) in sh.anchors.items():
                where.setdefault(k, f"{i}.{ref_of(x, y)}")
        total = len(self.sheets)
        out = []
        for i, sh in enumerate(self.sheets, 1):
            body = "".join(sh.g)
            body = re.sub("\x00([^\x00]+)\x00", lambda m: where.get(m.group(1), "—"), body)
            out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" data-title="{escape(sh.title)}">'
                       f'<rect width="{W}" height="{H}" fill="#fff"/>{STYLE}{self.frame(i, total, sh)}{body}</svg>')
        return out


def meta_for_design(project: str, panel: str) -> dict:
    """Title-block data of a saved design panel: its versions (newest first), project and client."""
    from . import designs
    revs = designs.history(project, panel)
    p = next((x for x in designs.listing() if x["id"] == project), {})
    return {"version": revs[0] if revs else None, "revisions": revs, "project": p.get("name") or project, "panel": panel,
            "client": p.get("client") or ""}


def meta_for_project(project: str, panel: str) -> dict:
    """Title-block data of a client project panel (versions of its overrides.yaml)."""
    from . import bom_edit, versions
    revs = versions.listing(bom_edit._file(project))
    return {"version": revs[0] if revs else None, "revisions": revs, "project": project, "panel": panel, "client": project}


def build_set(v: dict, title: str = "Panel", meta: dict | None = None) -> list[str]:
    m = {"title": title, "drg": f"SCH-{date.today().strftime('%Y%m%d')}", **(meta or {})}
    return DrawingSet(v, m).build()
