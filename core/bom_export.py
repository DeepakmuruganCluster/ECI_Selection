"""Excel BOM: the panel assembly result + the client-specified items, with status and source per line.

Every line says where it came from: an engineering component (awaiting sign-off), the client
specification (page), or "not selected" (component not built yet). Nothing is filled in here.
"""
from __future__ import annotations

from .bom_layout import ordered, section_of
from .makes import make_of

import re
from datetime import date

from components.client_items.select import select as client_items
from components.panel.select import select as panel_select

from . import project as P
from .provenance import register
from .xlsx import workbook

# owner instruction 2026-10-11: enclosures (and their accessories) and heater feeders are left out of the BOM
OUT_OF_SCOPE = {"panel_layout", "enclosure", "enclosure_accessories"}


def build(panel_inputs: dict, client_panel: str | None = None, title: str = "Panel",
          load_list_result=None, project: str | None = None) -> tuple[bytes, dict]:
    p = panel_select(**panel_inputs)
    if p.status == "invalid":
        raise ValueError(next(c.value for c in p.checks if c.verdict == "fail"))
    c = client_items(panel=client_panel, project=project) if client_panel else None
    v = p.value

    bom = [["Group", "Article / model", "Description", "Make", "Qty", "Unit", "Status", "Source / basis", "Used by"]]
    for b in v["bom"]:
        cable = "cable" in b["description"]
        bom.append(["Cables" if cable else "Feeders", b["article"], b["description"], make_of(b) or "—", b["qty"], "m" if cable else "no",
                    "engineered — awaiting sign-off", "panel assembly (components 1, 2, 4, 5, 6)", ", ".join(b["used_by"])])
    out_of_scope = []
    if c:
        for it in c.value["items"]:
            if it.get("verify_by") in OUT_OF_SCOPE:
                out_of_scope.append(f"{it['panel']}: {it['item']}")
                continue
            bom.append([f"Client spec ({it['panel']})", it["model"] or "", it["item"], it["make"] or "—",
                        it["qty"] if it["qty"] is not None else "not stated", it["unit"], it["status"],
                        it["source"], ""])
    for n in v["not_selected"]:
        why = "not selected — question open" if "answer" in n else "not selected — component not built"
        bom.append(["Not selected", "", n, "", "", "", why, "", ""])

    feeders = [["Tag", "kW", "Starter", "Qty", "Running", "Status", "FLC A", "Devices", "Cable"]]
    feeders += [[f["tag"], f["kw"], f["starter"], f["qty"], f["running"], f["status"], f["flc_a"], f["devices"],
                 f["cable"]] for f in v["feeders"]]

    opens = [["Tag", "Component", "Rule", "Kind", "Open point"]]
    opens += [[o["tag"], o["component"], o["rule"], o["kind"], o["point"]] for o in v["open_points"]]
    if c:
        for ch in c.checks:
            if ch.verdict == "warn":
                opens.append(["client spec", "client_items", ch.rule, "warning", f"{ch.requirement}: {ch.value}"])

    if load_list_result is not None:
        for ch in load_list_result.checks:
            if ch.verdict == "warn":
                opens.append(["load list", "load_list", ch.rule, "warning", f"{ch.requirement}: {ch.value}"])

    reg = register()
    used = ["SIE-SIRIUS-CM", "SIE-PM240-2", "SIE-G120-PROT", "POLYCAB-LT-V9", "KEI-TH-2023", "RITTAL-TSC-3124300"]
    if c:
        used.append(P.doc("automation", project))
    if load_list_result is not None:
        used += [P.doc("load_list", project), P.doc("equipment", project)]
    sources = [["Reference", "Document", "Edition", "File", "SHA-256"]]
    sources += [[r, reg[r]["title"], reg[r].get("edition", ""), reg[r].get("file", ""), reg[r].get("sha256", "")]
                for r in used if r in reg]

    summary = [["Item", "Value"],
               ["Title", title], ["Date", date.today().isoformat()],
               ["Status", "DRAFT — components awaiting sign-off; not for ordering"],
               ["Load lines / units", f"{v['n_lines']} / {v['n_units']}"],
               ["Lines fully selected", v["n_selected"]], ["Open points", len(opens) - 1],
               ["Panel heat from sourced losses (W)", v["heat_known_w"]],
               ["Cooling", v["cooling_method"] or "not assessed"]]
    summary += [[f"Input: {k}", str(val)] for k, val in panel_inputs.items() if k != "load_list"]
    if client_panel:
        summary.append(["Client panel", client_panel])
    summary.append(["Out of scope (owner instruction)", "enclosures, enclosure accessories, heater feeders"
                    + (f" — client lines left out: {'; '.join(out_of_scope)}" if out_of_scope else "")])

    data = workbook([("Summary", summary, [38, 70]),
                     ("BOM", bom, [22, 34, 52, 10, 6, 40, 30, 30]),
                     ("Feeders", feeders, [14, 7, 8, 5, 8, 9, 8, 60, 50]),
                     ("Open points", opens, [14, 14, 11, 9, 100]),
                     ("Sources", sources, [20, 70, 22, 60, 66])])
    return data, {"bom_lines": len(bom) - 1, "open_points": len(opens) - 1}


IO_WIDTHS = [9, 26, 8, 12, 60, 10]
LOGIC_WIDTHS = [14, 18, 9, 11, 56, 60, 30]


def io_sheet(rows: list[dict]) -> list[list]:
    """One I/O list (inputs, or outputs, or bus devices and STO): channel, name (I_… / O_…), type, unit, signal, rule."""
    return [["Channel", "Name", "Type", "Unit", "Signal", "Rule"]] + [
        [r.get("channel", ""), r.get("name", ""), r["type"], r["unit"], r["signal"], r["rule"]] for r in rows]


def io_sheets(io_list: list[dict], trace: list[dict] | None = None) -> list[tuple]:
    """R-IO-11: inputs and outputs on separate sheets, bus devices and STO apart; the I/O trace when given (R-REQ-26)."""
    by = lambda d: [r for r in io_list if r.get("dir") == d]
    order = {"DI": 0, "AI": 1, "DO": 0, "AO": 1}
    out = [("Inputs", io_sheet(sorted(by("input"), key=lambda r: order[r["type"]])), IO_WIDTHS),
           ("Outputs", io_sheet(sorted(by("output"), key=lambda r: order[r["type"]])), IO_WIDTHS)]
    if by("bus") or by("safety"):
        out.append(("Bus and STO", io_sheet(by("bus") + by("safety")), IO_WIDTHS))
    if trace:
        out.append(("I-O trace", [["I/O", "Count", "Used in", "Value", "Matches"]]
                    + [[t["io"], t["count"], t["used_in"], t["value"], "yes" if t["ok"] else "NO"] for t in trace], [16, 8, 46, 60, 9]))
    return out


def logic_sheet(rows: list[dict]) -> list[list]:
    """Every check behind every value: the design logic, with its rule and source page."""
    return [["Tag", "Component", "Verdict", "Rule", "Requirement", "Value", "Source"]] + [
        [r["tag"], r["component"], r["verdict"], r["rule"], r["requirement"], r["value"], r["source"]] for r in rows]


def sources_used(rows: list[dict]) -> list[list]:
    """The registered documents a design-logic list cites, with edition, file and SHA-256."""
    reg = register()
    cited = sorted({ref for r in rows for ref in reg if ref in (r.get("source") or "")})
    return [["Reference", "Document", "Edition", "File", "SHA-256"]] + [
        [x, reg[x]["title"], reg[x].get("edition", ""), reg[x].get("file", ""), reg[x].get("sha256", "")] for x in cited]


def _conventions() -> dict:
    """Company drawing conventions (OWN-PROPEL-SCH160): index, tag letters, wire colours, SAP codes."""
    from pathlib import Path
    from core.data import data_file
    from core.provenance import load_sourced_table
    d = load_sourced_table(data_file("propel_drawing_conventions.yaml"), ("kind",))
    out = {}
    for r in d["rows"]:
        out.setdefault(r["kind"], []).append(r)
    return out


def drawing_bom(bom: list[dict], tags: dict | None = None) -> list[list]:
    """Drawing-format BOM: the company columns, tag names by the legend, SAP code where the part is in the sample.
    tags = {bom index: tag text} from core/drawing_tags.plan — the same tags as on the drawing set."""
    if tags is None:
        from .drawing_tags import plan
        tags = plan({"bom": bom, "feeders": []})["line_tags"]
    conv = _conventions()
    sap = {r["article"]: r["sap_code"] for r in conv.get("sap", [])}
    rows = [["S.NO", "DESCRIPTION", "TAG NAME", "PART NO.", "SAP PART CODE", "MAKE", "QTY", "UOM",
                           "INDICATIVE UNIT PRICE (INR)"]]
    n = 0
    for i, b in enumerate(bom):
        if b["group"] == "Not selected" or not b["article"]:
            continue
        n += 1
        tag = tags.get(i, "")
        tag = "" if tag == "—" else tag
        make = (make_of(b) or "").upper()            # the recorded make (company drawings print makes in capitals)
        if not make and b["article"].startswith(("6SL", "6ES", "3RV", "3RT", "3RA", "3NA", "3NP", "3VM", "3VA", "7KM", "3SU")):
            make = "SIEMENS"
        rows.append([n, b["description"], tag, b["article"], sap.get(b["article"], ""), make, b["qty"],
                     "M" if b["unit"] == "m" else "NOS", b.get("unit_price_inr") if b.get("unit_price_inr") is not None else ""])
    return rows


def _plan_tags(v: dict) -> dict:
    from .drawing_tags import plan
    return plan(v)["line_tags"]


def drawing_index(scope: dict | None = None) -> list[list]:
    """The company drawing index; with a template (R-REQ-31) the I/O pages say 'not in this panel' when it has no PLC."""
    conv = _conventions()
    no_plc = (scope or {}).get("plc") is False
    made = lambda r: "not in this panel (no PLC)" if no_plc and ("input" in r["title"].lower() or "output" in r["title"].lower()) else r["made_by_tool"]
    return [["S.NO", "PAGE DESCRIPTION (company drawing set)", "Made by the tool?"]] + [
        [r["item"], r["title"], made(r)] for r in conv["index"]] + [
        ["+", "Single line diagram (not in the company set; added by the tool)", "yes (drawing set, sheet after the technical details)"]]


def wiring_conventions() -> list[list]:
    conv = _conventions()
    rows = [["Device", "Tag letter (company legend)"]] + [[r["device"], r["tag"]] for r in conv["tag"]]
    rows += [["", ""], ["Circuit", "Wire colour", "Ferrules"]] + [[r["circuit"], r["colour"], r["ferrules"]] for r in conv["wire"]]
    rows += [["", ""], ["Source", "OWN-PROPEL-SCH160 (drawing AVELCPSDL08WPLC rev 08), legend page 3"]]
    return rows


def build_requirement(inputs: dict, design_log: list | None = None, level: str | None = None) -> tuple[bytes, dict]:
    """Document pack for a confirmed requirement: requirement, BOM, VFD BOM, I/O list, design logic, sources."""
    from components.requirement.select import select as requirement

    r = requirement(**inputs)
    if r.status == "invalid":
        raise ValueError(next(c.value for c in r.checks if c.verdict == "fail"))
    v = r.value
    if not v["selected"]:
        raise ValueError("answer the open questions and confirm before the document pack is made")
    req = [["Fact", "Value", "How", "Words in the requirement"]]
    req += [[f["fact"], str(f["value"]), f["how"], f["from"]] for f in v["facts"]]
    req += [["", "", "", ""], ["Recorded, not used", "Value", "Why", "Words"]]
    req += [[x["fact"], str(x["value"]), x["use"], x["from"]] for x in v["recorded"]]
    req += [["", "", "", ""], ["Requirement text", inputs["text"], "", ""], ["Load list", v["load_list"], "", ""],
            ["Date", date.today().isoformat(), "", ""],
            ["Status", "DRAFT — components awaiting sign-off; not for ordering", "", ""],
            ["Designed by", {"fresher": "fresher (guided walk)", "experienced": "experienced designer"}.get(level or "", "not stated"), "", ""]]
    req += [["Check: " + c.rule, c.requirement, c.verdict, c.value] for c in r.checks]
    bom = [["Section", "Group", "Article / model", "Description", "Make", "Qty", "Unit", "Used by", "Source / basis",
            "Indicative unit price (INR)"]]
    bom += [[section_of(b["group"]), b["group"], b["article"], b["description"], b.get("make") or ("" if not b["article"] else "—"),
             b["qty"], b["unit"], b["used_by"], b["source"],
             b["unit_price_inr"] if b.get("unit_price_inr") is not None else ""] for b in ordered(v["bom"])]
    bom += [["", "", "", f"Indicative total of priced lines ({v['n_priced']} of {v['n_bom_lines']}; company sheets, INR)", "",
             "", "", "", "", v["indicative_inr"]]]
    # VFD BOM in the company's VFD selection structure, one block per drive line
    vfd = [["Tag", "#", "Component", "Part Number", "Category", "Specifications", "Qty per drive", "Drives", "Total qty"]]
    for d in v["vfd_boms"]:
        for i, x in enumerate(d["items"], 1):
            vfd.append([d["tag"] if i == 1 else "", i, x["component"], x["part_number"] or "—", x["category"],
                        x["specifications"], x["qty"], d["qty"] if i == 1 else "", x["qty"] * d["qty"]])
    opens = [["Tag", "Component", "Rule", "Kind", "Open point"]]
    opens += [[o["tag"], o["component"], o["rule"], o["kind"], o["point"]] for o in v["open_points"]]
    sheets = [("Requirement", req, [34, 50, 16, 60]), ("Drawing index", drawing_index(v.get("scope")), [8, 60, 50]),
              ("BOM (drawing format)", drawing_bom(v["bom"], _plan_tags(v)), [6, 56, 16, 26, 20, 14, 8, 6, 14]),
              ("BOM", bom, [22, 36, 56, 12, 6, 18, 26, 14])]
    if v["vfd_boms"]:
        sheets.append(("VFD BOM", vfd, [8, 4, 34, 32, 16, 64, 12, 8, 10]))
    inc = next((b for b in v["bom"] if b["group"] == "Incomer"), None)
    sheets += [("Power", machine_power_sheet(v.get("power"), {"project": "New machine", "machine": str(inputs.get("text", ""))[:80],
                                                               "incomer": f"{inc['article']} — {inc['description']}" if inc else None,
                                                               "fault_ka": v.get("fault_ka")}),
                [8, 34, 40, 8, 10, 10, 10, 11, 44, 16, 9, 9, 9, 40])]
    if (v.get("scope") or {}).get("plc") is False:          # R-REQ-31: no PLC listed → no I/O sheets, one line that says so
        sheets += [("I-O list", [["No PLC in this panel: " + ("the template lists none" if v.get("template") else "'No PLC' chosen")
                                  + ", so there are no PLC inputs or outputs, "
                                  "interface relays or I/O terminals (R-REQ-31)."]], [120])]
    else:
        sheets += io_sheets(v["io_list"], v.get("io_trace"))
    sheets += [("Design logic", logic_sheet(v["design_logic"]), LOGIC_WIDTHS),
               ("Not selected", [["Item", "Category", "Why / waits for"]] +
                [[x["item"], x["category"], x["why"]] for x in v["not_selected_detail"]], [60, 40, 110]),
               ("Open points", opens, [10, 14, 11, 9, 100]),
               ("Wiring conventions", wiring_conventions(), [40, 26, 20]),
               ("Sources", sources_used(v["design_logic"]), [22, 70, 24, 60, 66])]
    if design_log:
        # the designer's walk: every step accepted and every change tried, with what it changed
        log = [["When", "Step", "What the designer did", "Parts / what changed"]]
        log += [[str(l.get("when", "")), str(l.get("step", "")), str(l.get("action", "")), str(l.get("detail", ""))]
                for l in design_log if isinstance(l, dict)]
        sheets.insert(1, ("Design log", log, [18, 46, 60, 80]))
    return workbook(sheets), {"bom_lines": len(bom) - 1, "io_rows": len(v["io_list"]), "open_points": len(opens) - 1}


def template_power(pw: dict | None, head: dict | None = None) -> list[list]:
    """The company template's layout (OWN-SWG-CALC): header, 'Power calculation and main switchgear selection' (AC, one
    row per load with L1 / L2 / L3), 'SMPS selection' (24 V DC with FOS) and 'Power requirement'."""
    if not pw:
        return [["no power calculation in this result"]]
    h = head or {}
    n = lambda x: "" if x is None else x
    rows = [["Customer", n(h.get("customer")), "Project", n(h.get("project")), "Location", n(h.get("location")),
             "Machine / panel", n(h.get("machine"))], [],
            ["Power calculation and main switchgear selection (AC)"],
            ["Sl.no", "AC load", "Description", "Phase", "Min voltage", "Max voltage", "Power (kW)", "Current (A)",
             "Protection device", "Accessory", "L1 (A)", "L2 (A)", "L3 (A)", "Source"]]
    for k, r in enumerate(pw["ac_rows"], 1):
        rows.append([k, r["load"], r["description"], 3 if r["phase"] == 3 else f"1 · {r.get('lines', '')} ({'line–line' if r.get('connection') == 'LL' else 'L–N'})", n(r["min_v"]), n(r["max_v"]), n(r["kw"]), r["current_a"],
                     n(r["protection"]), n(r["accessory"]), n(r["l1"]), n(r["l2"]), n(r["l3"]), r["source"]])
    sums = [round(sum(r[k] or 0 for r in pw["ac_rows"]), 3) for k in ("l1", "l2", "l3")]
    rows += [["", "Phase current (with phase balancing)", f"imbalance {pw['imbalance_pct']} %, neutral {round(pw['neutral_a'], 2)} A",
              "", "", "", "", "", "", "", *sums, "R-PWR-03/04/05"],
             ["", f"Load current with FOS {n(pw.get('main_fos'))}", "largest phase × FOS", "", "", "", "", n(pw.get("main_load_a")), "", "", "", "", "",
              "OWN-SWG-CALC 'U1_Main_Switchgear' L27"],
             ["", "Selected main switchgear", n(h.get("incomer")) or "—"], []]
    d = pw.get("dc")
    if d:
        rows += [["SMPS selection (24 V DC)"],
                 ["Sl.no", "Load", "Qty", "Power (VA)", "Current (A)", "Total current (A)", "Protection device", "Accessory", "Source"]]
        rows += [[k, r["item"], n(r["qty"]), "", n(r["per_unit"]) if r["per_unit"] is not None else "open",
                  r["total"] if r["total"] is not None else "open", "", "", r["source"]] for k, r in enumerate(d["rows"], 1)]
        rows += [["", f"Grand total (A) with FOS {d['factor']}" + (" (partial)" if d["partial"] else ""), "", "", "", d["required_a"], "", "",
                  d["factor_source"]],
                 ["", "SMPS spec", f"{d.get('supply') or 'not selected'}, output 24 V DC" + (f", {d['available_a']} A" if d["available_a"] is not None else "")
                  + (f", draws {d['input_w']} W" if d.get("input_w") else "")], []]
    rows += [["Power requirement"],
             ["Input voltage (V)", pw["voltage_v"]], ["Frequency (Hz)", n(pw.get("frequency_hz"))],
             ["Full load current (A)", max(sums), "largest phase"],
             ["Input power (kVA)", n(pw.get("input_kva_fos")), f"× FOS {n(pw.get('main_fos'))}; {pw['s_kva']} kVA without"],
             ["Short circuit current (kA)", n(h.get("fault_ka"))],
             ["Recommended incoming power cable", "not sized by the tool"],
             ["Not counted (no data)", ", ".join(pw["not_counted"]) or "—"]]
    return rows


def machine_power_sheet(pw: dict | None, head: dict | None = None) -> list[list]:
    return template_power(pw, head)


def power_sheet(pc: dict | None) -> list[list]:
    """R-PRJ-15: the power calculation as its own sheet — 24 V DC and 230 V AC control, every line with its source."""
    rows = [["Section", "Item", "Qty", "Per unit", "Unit", "Total", "Source / basis"]]
    if not pc:
        return rows + [["", "no power calculation in this result", "", "", "", "", ""]]
    d = pc["dc24"]
    for r in d["rows"]:
        rows.append(["24 V DC", r["item"], r["qty"] if r["qty"] is not None else "", r["per_unit"] if r["per_unit"]
                     is not None else "open", r["unit"], r["total"] if r["total"] is not None else "open", r["source"]])
    rows += [["24 V DC", "Subtotal", "", "", "A", d["subtotal_a"], "sum of the lines above" + (" (partial)" if d["partial"] else "")],
             ["24 V DC", "Factor of safety", "", d["factor"], "", "", d["factor_source"]],
             ["24 V DC", "Required supply", "", "", "A", d["required_a"], "subtotal × factor"],
             ["24 V DC", "Client's stated supplies", "", "", "A", d["available_a"], d["available_source"]],
             ["24 V DC", "Result", "", "", "", "enough" if d["available_a"] >= d["required_a"] else
              f"short by {d['required_a'] - d['available_a']:.2f} A", f"not counted: {d['not_counted']}"],
             ["", "", "", "", "", "", ""]]
    a = pc["ac230"]
    for r in a["rows"]:
        rows.append(["230 V AC control", r["item"], r["qty"] if r["qty"] is not None else "", r["per_unit"] if r["per_unit"]
                     is not None else ("open" if r["total"] is None else ""), r["unit"],
                     r["total"] if r["total"] is not None else "open", r["source"]])
    rows += [["230 V AC control", "Control load", "", "", "VA", a["load_va"], "sum of the lines above" + (" (partial)" if a["partial"] else "")],
             ["230 V AC control", "Factor", "", a["factor"], "", "", "OWN-SWG-CALC 'U1_Transformer' G13"],
             ["230 V AC control", "Required transformer", "", "", "VA", a["required_va"] if not a["partial"] else "open",
              "load × factor"],
             ["230 V AC control", "Transformer chosen", "", "", "VA", a["transformer_va"] or "not sized",
              f"control supply: {a['supply']} (company standard ratings)"]]
    return rows


def _bom_index(lines: list[dict]) -> dict:
    idx = {}
    for l in lines:
        if l["group"] in ("Not selected",):
            continue
        key = (l["group"], l["article"] or l["description"])
        q = l["qty"]
        idx[key] = (idx.get(key, (0,))[0] + q if isinstance(q, (int, float)) else q, l["description"])
    return idx


def _project_head(base: dict, v: dict) -> dict:
    from core import project as P
    inc = next((b for b in v["bom"] if b["group"] == "Incomer"), None)
    return {"customer": P.client(base.get("project")), "project": P.resolve(base.get("project")), "machine": v.get("panel"),
            "incomer": f"{inc['article']} — {inc['description']}" if inc else None, "fault_ka": base.get("fault_ka")}


def build_project(base: dict, title: str) -> tuple[bytes, dict]:
    """Main BOM (first option of every decision) + Options sheet (what each alternative changes)."""
    from components.project.select import DECISIONS, select as project

    r = project(**base)
    if r.status == "invalid":
        raise ValueError(next(c.value for c in r.checks if c.verdict == "fail"))
    v = r.value
    if v.get("questions"):                       # R-PRJ-20: nothing is exported on assumed values
        raise ValueError("answer this panel's questions first (project page): " + ", ".join(q["input"] for q in v["questions"]))
    saved = v.get("settings") or {}               # the panel's saved answers, unless given in this call
    base = {**{k: saved[k] for k in ("fault_ka", "panel_internal_c", "motor_pf", "cable_ambient_c", "default_cable_m")
               if saved.get(k) is not None}, **{k: x for k, x in v["options"].items()}, **base}
    head = ["Section", "Group", "Article / model", "Description", "Make", "Qty", "Unit", "Status", "Source / basis", "Used by"]
    bom = [head] + [[section_of(l["group"]), l["group"], l["article"], l["description"], l.get("make") or ("" if not l["article"] else "—"),
                     l["qty"], l["unit"], l["status"], l["source"], l["used_by"]] for l in ordered(v["bom"])]

    base_idx = _bom_index(v["bom"])
    options = [["Decision", "Option", "In main BOM?", "Change", "Group", "Article / model", "Qty main → option",
                "Description"]]
    scenarios = list(DECISIONS.items()) + [("panel_internal_c", ("Panel internal temperature (enclosure out of "
                                                                  "scope; affects drive and wire sizes)",
                                                                  [(base["panel_internal_c"], f"{base['panel_internal_c']:g} °C"),
                                                                   (55, "55 °C (fan-cooled panel, 50 °C site)")]))]
    for key, (question, opts) in scenarios:
        chosen = v["options"].get(key, base.get(key))
        for val, label in opts:
            if val == chosen:
                options.append([question, label, "yes (main BOM)", "", "", "", "", ""])
                continue
            alt = project(**{**base, key: val})
            idx = _bom_index(alt.value["bom"])
            changes = 0
            for k in sorted(set(base_idx) | set(idx), key=str):
                a, b = base_idx.get(k, (0, ""))[0], idx.get(k, (0, ""))[0]
                if a != b:
                    kind = "added" if not a else ("removed" if not b else "quantity")
                    options.append([question, label, "no", kind, k[0], k[1], f"{a} → {b}",
                                    (idx.get(k) or base_idx.get(k))[1]])
                    changes += 1
            if not changes:
                options.append([question, label, "no", "no BOM change", "", "", "", ""])

    # VFD BOM in the company's VFD selection structure: per drive, Power Module → Control Unit → Memory Card → Operator Panel
    vfd = [["Tag", "#", "Component", "Part Number", "Category", "Specifications", "Qty per drive", "Drives", "Total qty"]]
    for f in v["feeders"]:
        if not f.get("vfd_bom"):
            continue
        for i, x in enumerate(f["vfd_bom"], 1):
            vfd.append([f["tag"] if i == 1 else "", i, x["component"], x["part_number"] or "—", x["category"],
                        x["specifications"], x["qty"], f["qty"] if i == 1 else "", x["qty"] * f["qty"]])
    feeders = [["Tag", "kW", "Starter", "Qty", "Running", "Status", "FLC A", "Devices", "Motor cable", "Internal wire"]]
    feeders += [[f["tag"], f["kw"], f["starter"], f["qty"], f["running"], f["status"], f["flc_a"], f["devices"],
                 f["cable"], f.get("internal_wire") or ""] for f in v["feeders"]]
    opens = [["Tag", "Component", "Rule", "Kind", "Open point"]]
    opens += [[o["tag"], o["component"], o["rule"], o["kind"], o["point"]] for o in v["open_points"]]

    reg = register()
    used = sorted({x for x in reg if not x.startswith(("RITTAL-3", "RITTAL-4", "RITTAL-8"))})
    sources = [["Reference", "Document", "Edition", "File", "SHA-256"]]
    sources += [[x, reg[x]["title"], reg[x].get("edition", ""), reg[x].get("file", ""), reg[x].get("sha256", "")]
                for x in used]
    summary = [["Item", "Value"], ["Title", title], ["Date", date.today().isoformat()],
               ["Status", "DRAFT — components awaiting sign-off; not for ordering"],
               ["Main BOM", "first option of every decision; alternatives on the Options sheet"],
               ["BOM lines / open points", f"{len(bom) - 1} / {len(opens) - 1}"],
               ["Out of scope (owner instruction)", "enclosures, enclosure accessories, heater feeders"]]
    summary += [[f"Design input: {k}", str(x)] for k, x in base.items()]
    summary += [[f"Option: {k}", str(x)] for k, x in v["options"].items()]
    data = workbook([("Summary", summary, [40, 70]), ("BOM", bom, [24, 40, 56, 12, 6, 34, 34, 30]),
                     ("VFD BOM", vfd, [12, 4, 34, 32, 16, 64, 12, 8, 10]),
                     ("Options", options, [46, 46, 14, 12, 22, 38, 18, 50]),
                     *io_sheets(v["io_list"]),
                     ("Power (template)", template_power((v.get("power_calc") or {}).get("ac3"), _project_head(base, v)),
                      [8, 34, 40, 8, 10, 10, 10, 11, 44, 16, 9, 9, 9, 40]),
                     ("Power calculation", power_sheet(v.get("power_calc")), [18, 48, 7, 10, 6, 10, 66]),
                     ("Coverage", [["Kind", "Panel", "Item", "Status", "Where / why", "Source"]] +
                      [[r["kind"], r["panel"], r["item"], r["status"], r["where"], r["source"]] for r in v.get("coverage", [])],
                      [16, 8, 50, 26, 90, 26]),
                     ("Feeders", feeders, [16, 7, 8, 5, 8, 9, 8, 60, 46, 40]),
                     ("Design logic", logic_sheet(v["design_logic"]), LOGIC_WIDTHS),
                     ("Open points", opens, [14, 18, 11, 9, 100]), ("Sources", sources, [22, 70, 24, 60, 66])])
    return data, {"bom_lines": len(bom) - 1, "option_rows": len(options) - 1, "open_points": len(opens) - 1}
