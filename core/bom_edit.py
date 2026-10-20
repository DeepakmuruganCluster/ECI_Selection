"""Designer edits to a project BOM (rule R-PRJ-17): stored per project, checked by the engine, applied with the original kept.

An edit replaces a line's article, changes its quantity, removes it, or adds a line. It may be typed by the designer
or proposed by the assistant from the designer's prompt (core/assistant.propose_edit); either way the engine checks it
here before it is saved: a replacement article is looked up in the parts catalog (data/catalog/parts.yaml) and keeps
the catalog's sources; one not in the held data is saved but marked "not in the held data — confirm"; quantities must
be whole numbers ≥ 0. Edits live in projects/<name>/overrides.yaml, never in the generated BOM.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from . import project as P
from . import versions

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "parts.yaml"
ACTIONS = ("replace", "qty", "remove", "add")
TEXT_FIELDS = ("article", "description", "make", "group")
MAX_QTY = 10000          # a BOM line quantity above this is a typing error, not a design


def key(article: str) -> str:
    """Same normalisation as the catalog: 'KUT 4' = 'KUT4', '5SL6106-6RC' = '5SL61066RC'."""
    return "".join(ch for ch in str(article).upper() if ch.isalnum())


@lru_cache(maxsize=None)
def catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text()) or {}


def _file(project: str | None) -> Path:
    return P.load(project)["_dir"] / "overrides.yaml"


def load(project: str | None = None) -> list[dict]:
    f = _file(project)
    return (yaml.safe_load(f.read_text()) or {}).get("edits", []) if f.exists() else []


def _save(project: str | None, edits: list[dict]) -> None:
    head = ("# Designer edits to the project BOM (rule R-PRJ-17), written by the web app. Each edit names the line it\n"
            "# changes (group, article, description), what changed, who proposed it and the engine's check.\n")
    data = {"edits": edits}
    old = _all(project) if _file(project).exists() else {}
    data.update({k: v for k, v in old.items() if k != "edits" and v})      # power edits and standby units are kept
    _file(project).write_text(head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=200))
    versions.record(_file(project), old, data)                              # every change is a new version


def line_ref(line: dict) -> dict:
    return {"group": str(line.get("group") or ""), "article": str(line.get("article") or ""),
            "description": str(line.get("description") or "")}


def _usable_line(line) -> str | None:
    """Why a line reference cannot be used, or None."""
    if not isinstance(line, dict):
        return "the line must be an object"
    for k in ("group", "article", "description", "used_by"):
        v = line.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (str, int, float))):
            return f"line {k} must be text (got {type(v).__name__})"
    return None


def check(edit: dict) -> dict:
    """The engine's check of an edit: {ok, verdict, notes, source, make, description}."""
    bad = lambda n: {"ok": False, "verdict": "invalid", "notes": n}
    if not isinstance(edit, dict):
        return bad("an edit must be an object")
    a = edit.get("action")
    if a not in ACTIONS:
        return bad(f"action must be one of {', '.join(ACTIONS)}")
    # every text field is text (or absent): a wrong type would break the panel later (QA 2026-10-16, H3)
    for k in TEXT_FIELDS:
        v = edit.get(k)
        if v is not None and not isinstance(v, (str, int, float)) or isinstance(v, bool):
            return bad(f"{k} must be text (got {type(v).__name__})")
        if v is not None and len(str(v)) > 300:
            return bad(f"{k} is too long (over 300 characters)")
    out = {"ok": True, "verdict": "ok", "notes": "", "source": None}
    if a in ("qty", "add", "replace") and edit.get("qty") not in (None, ""):
        if isinstance(edit["qty"], bool):
            return bad(f"quantity must be a number (got {edit['qty']})")
        try:
            q = float(edit["qty"])
        except (TypeError, ValueError):
            return bad(f"quantity must be a number (got {edit['qty']})")
        if not math.isfinite(q) or q < 0 or q != int(q):
            return bad(f"quantity must be a whole number ≥ 0 (got {edit['qty']})")
        if q > MAX_QTY:
            return bad(f"quantity {q:g} is above {MAX_QTY} — check the number")
    if a == "add" and edit.get("qty") not in (None, "") and float(edit["qty"]) < 1:
        return {"ok": False, "verdict": "invalid", "notes": "an added line needs a quantity of at least 1"}
    if a == "qty" and edit.get("qty") in (None, ""):
        return {"ok": False, "verdict": "invalid", "notes": "give the new quantity"}
    if a in ("replace", "add"):
        art = str(edit.get("article") or "").strip()
        if not art:
            return {"ok": False, "verdict": "invalid", "notes": "give the article"}
        part = catalog().get(key(art))
        if part:
            out.update({"source": "; ".join(f"{s['ref']} {s['where']}".strip() for s in part["sources"][:3]),
                        "make": ", ".join(part["make"]), "description": (part["descriptions"] or [""])[0],
                        "notes": f"in the parts catalog ({len(part['sources'])} source row(s))"})
        else:
            out.update({"verdict": "unsourced", "notes": "not in the held data — saved as a designer choice; confirm the "
                        "article and its data before ordering"})
    return out


def candidates(line: dict, limit: int = 15) -> list[dict]:
    """Catalog parts that share words with the line (same make first) — the only articles the assistant may suggest."""
    words = {w for w in re.findall(r"[A-Za-z]{3,}|\d+(?:\.\d+)?", f"{line.get('description', '')}") if len(w) > 2}
    words = {w.lower() for w in words} - {"the", "and", "for", "with", "per", "awaiting", "engineered"}
    if not words:
        return []
    art_key = key(line.get("article") or "")
    make, tables = None, set()
    if art_key in catalog():
        make = set(catalog()[art_key]["make"])
        tables = {s["table"] for s in catalog()[art_key]["sources"]}
    scored = []
    for k, p in catalog().items():
        if k == art_key:
            continue
        text = " ".join(p["descriptions"]).lower()
        s = sum(w in text for w in words)
        same_table = bool(tables & {x["table"] for x in p["sources"]})
        if not s and not same_table:
            continue
        cp = next((n for n, (a, b) in enumerate(zip(art_key, k)) if a != b), min(len(art_key), len(k)))
        family = max(cp - 3, 0)          # the longer the shared article stem (3RV20…, 6ES79548L…), the closer the part
        scored.append((-(s + family + (4 if same_table else 0) + (2 if make and set(p["make"]) & make else 0)), k, p))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{"article": p["spellings"][0], "make": ", ".join(p["make"]), "description": (p["descriptions"] or [""])[0][:90]}
            for _, _, p in scored[:limit]]


def search(q: str, limit: int = 20) -> list[dict]:
    """Parts in the catalog for 'Add a component': article numbers starting with the query first, then by how many of
    its words the part's descriptions / makes contain."""
    q = str(q or "").strip()
    if len(q) < 2:
        return []
    qk, words = key(q), [w.lower() for w in re.findall(r"[A-Za-z0-9.]{2,}", q)]
    scored = []
    for k, p in catalog().items():
        text = (" ".join(p["descriptions"]) + " " + " ".join(p["make"]) + " " + " ".join(p["spellings"])).lower()
        s = (10 if k.startswith(qk) else 4 if qk in k else 0) + sum(w in text for w in words)
        if s:
            scored.append((-s, k, p))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{"article": p["spellings"][0], "make": ", ".join(p["make"]), "description": (p["descriptions"] or [""])[0][:90],
             "source": "; ".join(f"{x['ref']} {x['where']}".strip() for x in p["sources"][:2])} for _, _, p in scored[:limit]]


def save(project: str | None, panel: str, line: dict, edit: dict, prompt: str = "", proposed_by: str = "designer",
         words: str = "") -> dict:
    chk = check(edit)
    if not chk["ok"]:
        raise ValueError(chk["notes"])
    why = _usable_line(line)
    if why:
        raise ValueError(why)
    if panel not in P.panels(project):
        raise ValueError(f"no panel {panel!r} in this project (panels: {', '.join(P.panels(project))})")
    edits = load(project)
    rec = {"id": max([e["id"] for e in edits], default=0) + 1, "panel": panel, "line": line_ref(line),
           "action": edit["action"], "article": edit.get("article"), "description": edit.get("description"),
           "qty": int(float(edit["qty"])) if edit.get("qty") not in (None, "") else None,
           "make": edit.get("make") or chk.get("make"), "group": edit.get("group"),
           "proposed_by": proposed_by, "prompt": prompt, "words": words,
           "check": {k: chk.get(k) for k in ("verdict", "notes", "source")},
           "at": datetime.now().isoformat(timespec="seconds")}
    edits.append(rec)
    _save(project, edits)
    return rec


# power-calculation edits (component power, R-PWR-11), kept beside the BOM edits in overrides.yaml
def _all(project: str | None) -> dict:
    f = _file(project)
    return (yaml.safe_load(f.read_text()) or {}) if f.exists() else {}


def load_power(project: str | None, panel: str | None = None) -> list[dict]:
    rows = _all(project).get("power_edits", [])
    return [{k: v for k, v in r.items() if k not in ("id", "panel", "at")} for r in rows if panel is None or r["panel"] == panel]


def power_list(project: str | None) -> list[dict]:
    return _all(project).get("power_edits", [])


def _write(project: str | None, data: dict, prefix: str = "") -> None:
    head = ("# Designer edits to the project BOM (rule R-PRJ-17) and to the power calculation (R-PWR-11), written by the web app.\n")
    old = _all(project) if _file(project).exists() else {}
    _file(project).write_text(head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=200))
    versions.record(_file(project), old, data, prefix)                      # every change is a new version


def restore(project: str | None, v: int) -> dict:
    """Make version v the current state again (a new version: nothing is lost)."""
    data = versions.get(_file(project), v)["data"] or {}
    _write(project, dict(data), prefix=f"restored version {int(v)}: ")
    return versions.listing(_file(project))[0]


def power_save(project: str | None, panel: str, edit: dict) -> dict:
    if not isinstance(edit, dict) or edit.get("action") not in ("set", "add", "remove") or not edit.get("key"):
        raise ValueError("a power edit needs an action (set, add or remove) and the key of its load")
    if panel not in P.panels(project):
        raise ValueError(f"no panel {panel!r} in this project (panels: {', '.join(P.panels(project))})")
    keep = {k: edit[k] for k in ("action", "key", "name", "connection", "phase", "i_a", "va", "u_v", "running", "kw", "three_phase", "description", "dc", "item", "qty", "per_unit")
            if k in edit and edit[k] not in (None, "")}
    data = _all(project)
    rows = data.get("power_edits", [])
    rec = {"id": max([r["id"] for r in rows], default=0) + 1, "panel": panel, **keep, "at": datetime.now().isoformat(timespec="seconds")}
    data["power_edits"] = rows + [rec]
    _write(project, data)
    return rec


# duty / standby units per tag group (rule R-LL-08), the designer's reading of the client's totals
def load_standby(project: str | None, panel: str) -> dict:
    return dict((_all(project).get("standby") or {}).get(panel) or {})


def standby_save(project: str | None, panel: str, tag: str, units) -> dict:
    """Set (or clear, units None / "") the standby units of one tag group; returns the panel's standby map."""
    if panel not in P.panels(project):
        raise ValueError(f"no panel {panel!r} in this project")
    if not isinstance(tag, str) or not tag or len(tag) > 60:
        raise ValueError("give the tag group (e.g. P101A/B)")
    data = _all(project)
    sb = data.get("standby") or {}
    cur = dict(sb.get(panel) or {})
    if units in (None, ""):
        cur.pop(tag, None)
    else:
        if isinstance(units, bool) or not isinstance(units, (int, float)) or units != int(units) or units < 0:
            raise ValueError(f"standby units must be a whole number ≥ 0 (got {units!r})")
        cur[tag] = int(units)
    sb[panel] = cur
    data["standby"] = {k: v for k, v in sb.items() if v}
    if not data["standby"]:
        data.pop("standby")
    _write(project, data)
    return cur


# panel settings chosen by the designer (incomer factor, smallest power wire), kept per panel in overrides.yaml
_num = lambda lo, hi: (lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi)
SETTINGS = {"incomer_factor": _num(1, 3),
            "min_power_wire_mm2": lambda v: v in (0.5, 0.75, 1.0, 1.5, 2.5) and not isinstance(v, bool),
            # audit 2026-10-17 (owner: "ask each one"): the panel's design inputs and option choices, asked and saved here
            "fault_ka": _num(1, 200), "panel_internal_c": _num(20, 60), "motor_pf": lambda v: _num(0.01, 1)(v),
            "cable_ambient_c": _num(10, 60), "default_cable_m": _num(1, 2000)}
SETTING_MSG = {"incomer_factor": "the incomer factor must be from 1 to 3",
               "min_power_wire_mm2": "the smallest power wire must be 0.5, 0.75, 1, 1.5 or 2.5 mm²",
               "fault_ka": "the fault level must be from 1 to 200 kA", "panel_internal_c": "the panel temperature must be 20 … 60 °C",
               "motor_pf": "the power factor must be above 0 and at most 1", "cable_ambient_c": "the cable route temperature must be 10 … 60 °C",
               "default_cable_m": "the cable length must be 1 … 2000 m"}


def _decisions() -> dict:
    from components.project.select import DECISIONS
    return {k: [v for v, _ in opts] for k, (_, opts) in DECISIONS.items()}


def load_settings(project: str | None, panel: str) -> dict:
    return dict((_all(project).get("settings") or {}).get(panel) or {})


def settings_save(project: str | None, panel: str, name: str, value) -> dict:
    """Set (or clear, value None / "") one panel setting; returns the panel's settings."""
    if panel not in P.panels(project):
        raise ValueError(f"no panel {panel!r} in this project")
    dec = _decisions()
    if name not in SETTINGS and name not in dec:
        raise ValueError(f"setting must be one of {', '.join([*SETTINGS, *dec])}")
    data = _all(project)
    st = data.get("settings") or {}
    cur = dict(st.get(panel) or {})
    if value in (None, ""):
        cur.pop(name, None)
    elif name in dec:                        # one of the option's values (as the UI sends it: text)
        hit = next((v for v in dec[name] if str(v).lower() == str(value).lower()), None)
        if hit is None:
            raise ValueError(f"{name} must be one of {', '.join(str(v) for v in dec[name])}")
        cur[name] = hit
    else:
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(SETTING_MSG[name])
        if not SETTINGS[name](value):
            raise ValueError(SETTING_MSG[name])
        cur[name] = value
    st[panel] = cur
    data["settings"] = {k: v for k, v in st.items() if v}
    if not data["settings"]:
        data.pop("settings")
    _write(project, data)
    return cur


# I/O list edits (component io_list, R-IO-12), kept beside the other edits in overrides.yaml
def load_io(project: str | None, panel: str | None = None) -> list[dict]:
    rows = _all(project).get("io_edits", [])
    return [{k: v for k, v in r.items() if k not in ("id", "panel", "at")} for r in rows if panel is None or r["panel"] == panel]


def io_list(project: str | None) -> list[dict]:
    return _all(project).get("io_edits", [])


def io_save(project: str | None, panel: str, edit: dict) -> dict:
    if panel not in P.panels(project):
        raise ValueError(f"no panel {panel!r} in this project")
    if not isinstance(edit, dict) or edit.get("action") not in ("add", "remove", "rename", "set"):
        raise ValueError("an I/O edit needs an action: add, remove, rename or set")
    keep = {k: edit[k] for k in ("action", "type", "name", "to", "signal", "unit") if edit.get(k) not in (None, "")}
    data = _all(project)
    rows = data.get("io_edits", [])
    rec = {"id": max([r["id"] for r in rows], default=0) + 1, "panel": panel, **keep, "at": datetime.now().isoformat(timespec="seconds")}
    data["io_edits"] = rows + [rec]
    _write(project, data)
    return rec


def io_undo(project: str | None, edit_id: int) -> bool:
    data = _all(project)
    rows = data.get("io_edits", [])
    keep = [r for r in rows if r["id"] != int(edit_id)]
    if len(keep) == len(rows):
        return False
    data["io_edits"] = keep
    _write(project, data)
    return True


def power_undo(project: str | None, edit_id: int) -> bool:
    data = _all(project)
    rows = data.get("power_edits", [])
    keep = [r for r in rows if r["id"] != int(edit_id)]
    if len(keep) == len(rows):
        return False
    data["power_edits"] = keep
    _write(project, data)
    return True


def undo(project: str | None, edit_id: int) -> bool:
    edits = load(project)
    keep = [e for e in edits if e["id"] != int(edit_id)]
    if len(keep) == len(edits):
        return False
    _save(project, keep)
    return True


def apply(bom: list[dict], edits: list[dict], panel: str) -> tuple[list[dict], list[dict]]:
    """The BOM with this panel's edits applied (original kept on each edited line) and the edits that matched no line."""
    out = [dict(l) for l in bom]
    unmatched = []
    for e in (x for x in edits if isinstance(x, dict) and x.get("panel") == panel):
        # a stored edit that cannot be used (hand-edited file, older format) is set aside and listed, never fatal (H3)
        why = (check(e) or {}).get("notes") if not check(e)["ok"] else _usable_line(e.get("line") if e["action"] != "add" else {})
        if why or not isinstance(e.get("id"), int) or not isinstance(e.get("check"), dict):
            unmatched.append({**e, "unusable": why or "edit record incomplete"})
            continue
        by = "AI-assisted" if e["proposed_by"] == "assistant" else "designer"
        if e["action"] == "add":
            out.append({"group": e.get("group") or e["line"].get("group") or "Added by designer", "article": e["article"],
                        "make": e.get("make") or (e.get("check") or {}).get("make"),
                        "description": e.get("description") or e["check"].get("notes", ""), "qty": int(float(e["qty"])) if e.get("qty") not in (None, "") else 1,
                        "unit": "no", "status": f"added — {by} (edit {e['id']}): {e['check']['verdict']}",
                        "source": e["check"].get("source") or "designer edit", "used_by": "", "edit_id": e["id"]})
            continue
        ref = e["line"]
        hit = next((l for l in out if line_ref(l) == ref or (l.get("original") and line_ref(l["original"]) == ref)), None)
        if hit is None:
            unmatched.append(e)
            continue
        hit.setdefault("original", {k: hit.get(k) for k in ("group", "article", "description", "qty", "source")})
        if e["action"] == "remove":
            hit["qty"] = 0
            hit["status"] = f"removed — {by} (edit {e['id']})"
        elif e["action"] == "qty":
            hit["qty"] = int(float(e["qty"]))
            hit["status"] = f"quantity edited — {by} (edit {e['id']})"
        elif e["action"] == "replace":
            hit["article"] = e["article"]
            hit["make"] = e.get("make") or (e.get("check") or {}).get("make")   # None: worked out again from the new article
            if e.get("description"):
                hit["description"] = e["description"]
            if e.get("qty") not in (None, ""):
                hit["qty"] = int(float(e["qty"]))
            hit["source"] = e["check"].get("source") or "designer edit (not in the held data)"
            hit["status"] = f"replaced — {by} (edit {e['id']}): {e['check']['verdict']}"
        hit["edit_id"] = e["id"]
    return out, unmatched
