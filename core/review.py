"""Review and sign-off for a non-programmer: every golden case as a plain sentence,
the source pages to compare by eye, the open decisions, and a sign-off record.

The sign-off record (components/<name>/signoff.json) stores who signed, when, the
decisions, the test result and SHA-256 of every data file. If the data changes
later, the review page shows the sign-off as out of date.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime
from pathlib import Path

from . import golden
from .provenance import ROOT, SOURCES, load_yaml, register

COMPONENTS_DIR = ROOT / "components"
EXCERPTS = SOURCES / "excerpts"

STATUS_WORDS = {"ok": "gives an answer", "warning": "gives an answer with a caution",
                "cannot_select": "refuses (outside what the sources cover)", "invalid": "rejects the input"}

INPUT_WORDS = {
    "kw": "{} kW", "load_type": "{}", "phases": "{}-phase", "voltage_v": "{} V", "frequency_hz": "{} Hz",
    "poles": "{}-pole", "nameplate_flc_a": "nameplate {} A", "nameplate_source": "(from the {})",
    "efficiency_pct": "efficiency {} %", "power_factor": "power factor {}", "client_flc_a": "client's list {} A",
    "flc_a": "motor current {} A", "flc_basis": "(current from: {})", "ie_class": "{} motor",
    "fault_ka": "fault level {} kA", "starting_current_a": "starting current {} A", "coil": "{} coil",
    "duty": "{} duty", "ambient_c": "{} °C ambient", "altitude_m": "altitude {} m", "cable_m": "{} m motor cable",
    "cable_shielded": "shielded cable: {}", "emc_filter": "EMC filter {}", "network_uk_pct": "supply uk {} %",
    "client_line_reactor_up_to_kw": "client: line reactor up to {} kW", "protection": "protected by {}",
    "preferred_family": "preferred family {}", "earthing": "{} system",
    "ib_a": "load current {} A", "poles": "{}-pole", "neutral_protection": "neutral protection {}",
    "release": "trip unit {}", "margin": "margin × {}", "breaking_basis": "checked against {}",
    "length_m": "{} m long", "pf_run": "pf {}", "installation": "in {}", "in_a": "protective device {} A",
    "overload_device": "overload device: {}", "cores": "{}-core", "make": "{} cable", "other_cables": "{} other cables",
    "group_spacing": "spacing {}", "vd_limit_pct": "voltage-drop limit {} %", "start_multiple": "start × {}",
    "pf_start": "start pf {}", "clearing_s": "cleared in {} s", "i2t_a2s": "I²t {} A²s",
    "heat_loss_w": "{} W heat inside", "max_internal_c": "max {} °C inside", "siting": "{}", "area_m2": "A = {} m²",
    "material": "{}", "sections": "{} sections",
    "load_list": "load list: {}", "panel_internal_c": "{} °C inside", "motor_pf": "motor pf {}",
    "cable_ambient_c": "cable route {} °C", "site_ambient_c": "site {} °C", "cable_installation": "cables in {}",
    "cable_make": "{} cable", "vfd_protection": "drives protected by {}", "line_reactor_up_to_kw": "line reactor up to {} kW",
    "enclosure_area_m2": "A = {} m²",
    "project": "project {}", "panel": "panel {}", "default_cable_m": "cable {} m (designer)",
    "standby_per_group": "{} standby per group", "tag": "tag {}",
    "required_airflow_m3h": "{} m³/h needed", "doors": "{} doors", "supply_v": "{} V", "fans_per_door": "{} fan(s) per door",
    "fan_size_in": "{} inch fan", "outlet_filters_per_fan": "{} outlet filter(s) per fan", "plinth_height_mm": "plinth {} mm",
    "enclosure_depth_mm": "depth {} mm", "suites": "{} panel line(s)", "section_widths_mm": "sections {} mm",
    "fan_supply_v": "fans at {} V", "insulation": "{} °C wire", "conductor_type": "{} wire", "circuit": "{} circuit",
    "circuits": "{} circuits in the duct", "circuit_a": "circuit {} A", "ct_make": "{} CTs", "system": "{}",
    "accuracy_class": "class {}", "ct_secondary_a": "x/{} A", "busbar_w_mm": "busbar {} mm wide", "busbar_t_mm": "× {} mm",
    "cable_od_mm": "cable Ø{} mm", "lead_length_m": "{} m wires", "lead_mm2": "of {} mm²", "lead_temp_c": "wires at {} °C",
    "communication": "{}", "dol_outputs": "{} DOL outputs", "other_outputs": "{} other outputs",
    "coil_v_dc": "{} V DC coil", "relay_make": "{} relays", "latch_make": "latching relay make {}",
    "finder_series": "Finder {} series", "relay_connection": "{} relay terminals", "relay_groups": "{} relay groups",
    "spare_pct": "spare {} %", "contact_v": "load {} V", "contact_a": "load {} A", "contact_load": "{} load",
    "do_available": "{} DO available", "terminal_make": "{} terminals", "io_terminals": "{} I/O terminals",
    "io_conductor_mm2": "{} mm² I/O wire", "jumper_groups": "commoned groups {}", "power_terminals": "power terminals {}",
    "terminal_strips": "{} strips", "relays": "{} relays", "ct_make_opt": "{}", "wire_insulation": "wire {} °C",
    "terminals_per_channel": "{} terminal(s) per channel", "cu_safety": "safety {}", "loaded_cores": "{} loaded cores", "min_size_mm2": "min {} mm²",
}
VALUE_WORDS = {"flc_a": "{} A", "mpcb": "MPCB {}", "contactor": "contactor {}", "link_module": "link module {}",
               "power_module": "drive {}", "output_a_derated": "{} A after derating", "fuse": "fuse {}",
               "line_reactor": "line reactor {}", "output_reactor": "output reactor {}", "output_reactor_qty": "× {}",
               "protection_device": "protection {}", "protection_icc_ka": "{} kA", "min_enclosure_m3": "enclosure ≥ {} m³",
               "article_no": "breaker {}", "in_a": "In {} A", "breaking_class": "class {}", "icu_ka": "Icu {} kA",
               "ics_ka": "Ics {} kA", "cable": "{}", "size_mm2": "{} mm²", "runs": "{} run(s)",
               "vd_pct": "voltage drop {} %", "method": "cooling: {}",
               "n_lines": "{} lines", "n_selected": "{} selected", "n_open": "{} open points", "heat_known_w": "{} W heat",
               "cooling_method": "cooling {}", "fan_airflow_m3h": "{} m³/h",
               "n_rows": "{} rows", "n_vfd": "{} VFD rows", "n_dol": "{} DOL rows", "n_ss": "{} SS rows",
               "n_heater": "{} heater", "n_spare": "{} spare", "n_single_phase": "{} single-phase",
               "units_vfd": "{} drives", "units_dol": "{} DOL units", "units_ss": "{} soft starters",
               "n_duplicate_tags": "{} repeated tags", "n_tag_mismatch": "{} tag mismatches",
               "n_repairs": "{} repaired cells", "n_flc_outside_range": "{} currents outside ECI's range",
               "n_pdf_differences": "{} differences to the PDF", "n_total_mismatch": "{} total mismatches",
               "kw": "{} kW", "starter": "{}", "qty": "qty {}", "phases": "{}-phase", "client_flc_a": "ECI {} A",
               "line": "line: {}", "fan": "fan {}", "fan_qty": "× {}", "outlet_filter": "outlet filter {}",
               "delivered_airflow_m3h": "{} m³/h delivered", "fan_power_w": "{} W", "door_switch": "door switch {}",
               "door_light": "light {}", "iz_a": "Iz {} A", "wire": "{}", "bound_by": "set by {}",
               "ct_designation": "CT {}", "ct_ratio": "ratio {}", "ct_class": "class {}", "ct_va": "{} VA",
               "burden_va": "burden {} VA", "ct_qty": "× {}", "comm_module": "module {}", "meter": "{}",
               "latch_relay": "latching relay {}", "latch_relay_qty": "× {}", "slim_relay": "slim relay {}",
               "slim_relay_qty": "× {}", "do_needed": "{} PLC outputs", "terminals": "terminals {}",
               "end_plates": "end plates {}", "jumpers": "short links {}", "qty_cu": "{} control units",
               "qty_bop": "{} BOP-2", "qty_latch": "{} latching relays", "qty_slim": "{} slim relays",
               "qty_ct": "{} CTs", "qty_io_terminals": "{} I/O terminals"}


def components() -> list[str]:
    found = [(load_yaml(p).get("order", 99), p.parent.name) for p in COMPONENTS_DIR.glob("*/review.yaml")]
    return [name for _, name in sorted(found)]


def _select(name: str):
    return importlib.import_module(f"components.{name}.select").select


def _fmt(v):
    return f"{v:g}" if isinstance(v, float) else v


def describe_inputs(inp: dict) -> str:
    return ", ".join(INPUT_WORDS.get(k, f"{k} {{}}").format(_fmt(v)) for k, v in inp.items())


def describe(status: str, value: dict, rules: list[str]) -> str:
    text = STATUS_WORDS.get(status, status)
    parts = [VALUE_WORDS[k].format(_fmt(v)) for k, v in value.items() if k in VALUE_WORDS and v is not None]
    if parts:
        text += ": " + ", ".join(parts)
    if rules:
        text += f" [{', '.join(rules)}]"
    return text


def data_files(name: str) -> list[Path]:
    """A component's data tables, as its review page lists them (data_files: data/makers, data/company, projects)."""
    return [ROOT / f for f in load_yaml(COMPONENTS_DIR / name / "review.yaml").get("data_files") or []]


def data_hashes(name: str) -> dict[str, str]:
    files = data_files(name) + [COMPONENTS_DIR / name / "rules.yaml"]
    return {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def run_cases(name: str) -> list[dict]:
    rules = load_yaml(COMPONENTS_DIR / name / "rules.yaml")["rules"]
    out = []
    for case, res, diffs in golden.run(COMPONENTS_DIR / name / "golden" / "cases.yaml", _select(name)):
        exp = case["expect"]
        exp_rules = exp.get("warnings") or ([exp["rule"]] if exp.get("rule") else [])
        got_rules = sorted(set(res.warnings)) or [c.rule for c in res.checks if c.verdict == "fail"][:1]
        exp_value = {k: v for k, v in exp.items() if k in VALUE_WORDS}
        out.append({
            "id": case["id"], "passed": not diffs, "given": describe_inputs(case["in"]),
            "expected": describe(exp["status"], exp_value, exp_rules),
            "got": describe(res.status, {k: res.value.get(k) for k in exp_value} or res.value, got_rules),
            "why": case["oracle"] + (f" — {case['calc']}" if case.get("calc") else ""),
            "differences": diffs,
            "rule_text": {r: rules[r]["text"] for r in set(exp_rules) | set(got_rules) if r in rules},
        })
    return out


def source_pages(name: str) -> list[dict]:
    pages = []
    for f in data_files(name):
        d = load_yaml(f)
        ref = d["source"]["ref"]
        src_file = str(register().get(ref, {}).get("file", ""))
        if src_file.endswith((".csv", ".xls", ".xlsx")):
            # a spreadsheet source has no pages: link the file itself; answers cite its line / row numbers
            item = {"ref": ref, "page": None, "printed_page": None, "image": None, "link": f"/source/{ref}",
                    "file": Path(src_file).name, "about": d["source"].get("note", "")}
            if item not in pages:
                pages.append(item)
            continue
        for p in sorted({int(r["page"]) for r in d["rows"] if r.get("page")}):
            img = f"{ref}_p{p:03d}.png"
            off = register().get(ref, {}).get("printed_page_offset", 0)
            item = {"ref": ref, "page": p, "printed_page": p + off,
                    "image": f"/excerpts/{img}" if (EXCERPTS / img).exists() else None,
                    "about": d["source"].get("section") or d["source"].get("column", "")}
            if item not in pages:
                pages.append(item)
    return pages


def signoff_path(name: str) -> Path:
    return COMPONENTS_DIR / name / "signoff.json"


def review(name: str) -> dict:
    if name not in components():
        raise KeyError(name)
    r = load_yaml(COMPONENTS_DIR / name / "review.yaml")
    cases = run_cases(name)
    record = json.loads(signoff_path(name).read_text()) if signoff_path(name).exists() else None
    if record:
        record["still_valid"] = record.get("data_sha256") == data_hashes(name)
    return {"component": name, **r, "cases": cases, "passed": sum(c["passed"] for c in cases), "total": len(cases),
            "pages": source_pages(name), "signoff": record}


def sign_off(name: str, body: dict) -> dict:
    rv = review(name)
    who = str(body.get("name") or "").strip()
    if not who:
        raise ValueError("Enter your name to sign off.")
    if rv["passed"] != rv["total"]:
        raise ValueError(f"{rv['total'] - rv['passed']} automatic check(s) fail: this component cannot be signed off.")
    if not body.get("compared"):
        raise ValueError("Tick the box to confirm you compared answers with the Siemens pages.")
    chosen = body.get("decisions") or {}
    missing = [d["id"] for d in rv["decisions"] if chosen.get(d["id"]) not in d["options"]]
    if missing:
        raise ValueError(f"Choose an answer for: {', '.join(missing)}.")
    record = {
        "component": name, "signed_by": who, "signed_at": datetime.now().isoformat(timespec="seconds"),
        "decisions": {d["id"]: {"question": d["question"], "answer": d["options"][chosen[d["id"]]],
                                "choice": chosen[d["id"]], "recommended": d["recommended"]} for d in rv["decisions"]},
        # the build implements the recommended answers; any other answer means a change + re-check before release
        "changes_needed": [d["id"] for d in rv["decisions"] if chosen[d["id"]] != d["recommended"]],
        "notes": str(body.get("notes") or "").strip(),
        "automatic_checks": f"{rv['passed']}/{rv['total']} passed",
        "data_sha256": data_hashes(name),
    }
    signoff_path(name).write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record
