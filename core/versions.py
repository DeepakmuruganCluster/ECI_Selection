"""Version history of a project's designer changes (owner 2026-10-16): every change saved by the web app — BOM, power,
I/O, standby units, panel settings, undo, restore — makes a new version, kept beside overrides.yaml in versions.yaml.

Each version holds the complete overrides content at that moment, so any version can be looked at or restored (a restore
is itself a new version: nothing is ever lost). Version 1 is the state before the first change made in the web app.
The text of each version is worked out by comparing the two states, so it always says what actually changed.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

LISTS = {"edits": "BOM", "power_edits": "Power", "io_edits": "I/O"}


def _file(path: Path) -> Path:
    """The version file: beside a project's overrides.yaml → versions.yaml; a design panel passes its own *.versions.yaml."""
    return path if path.name.endswith("versions.yaml") else path.with_name("versions.yaml")


def load(overrides: Path) -> list[dict]:
    f = _file(overrides)
    return (yaml.safe_load(f.read_text()) or {}).get("versions", []) if f.exists() else []


def _text(kind: str, e: dict) -> str:
    if kind == "edits":
        what = {"replace": f"replace {e.get('line', {}).get('article') or ''} with {e.get('article')}",
                "qty": f"quantity of {e.get('line', {}).get('article') or e.get('line', {}).get('description')} → {e.get('qty')}",
                "remove": f"remove {e.get('line', {}).get('article') or e.get('line', {}).get('description')}",
                "add": f"add {e.get('article')} × {e.get('qty') or 1}"}.get(e.get("action"), e.get("action"))
    elif kind == "power_edits":
        what = f"{'24 V ' if e.get('dc') else ''}{e.get('action')} {e.get('name') or e.get('item') or e.get('key')}"
    else:
        what = {"rename": f"rename {e.get('name')} → {e.get('to')}"}.get(e.get("action"), f"{e.get('action')} {e.get('name')}")
    return what


def describe(old: dict, new: dict) -> tuple[str, list[str]]:
    """A one-line summary of what changed between two overrides states, and the panels it touched."""
    parts, panels = [], set()
    for k, label in LISTS.items():
        o = {r.get("id"): r for r in old.get(k) or []}
        n = {r.get("id"): r for r in new.get(k) or []}
        for i in n.keys() - o.keys():
            parts.append(f"{label}: {_text(k, n[i])}")
            panels.add(n[i].get("panel"))
        for i in o.keys() - n.keys():
            parts.append(f"{label}: took back '{_text(k, o[i])}'")
            panels.add(o[i].get("panel"))
    for k, label in (("standby", "Standby"), ("settings", "Settings")):
        o, n = old.get(k) or {}, new.get(k) or {}
        for p in set(o) | set(n):
            if o.get(p) != n.get(p):
                changed = {x: (o.get(p) or {}).get(x) for x in set(o.get(p) or {}) | set(n.get(p) or {})
                           if (o.get(p) or {}).get(x) != (n.get(p) or {}).get(x)}
                parts.append(f"{label} {p}: " + ", ".join(f"{x} = {(n.get(p) or {}).get(x, 'default')}" for x in changed))
                panels.add(p)
    return ("; ".join(parts) or "no change"), sorted(x for x in panels if x)


def record(overrides: Path, old: dict, new: dict, prefix: str = "", describe_fn=None) -> dict | None:
    """Add a version for the change old → new (and version 1 = old, when this is the first change). Returns it."""
    describe_ = describe_fn or describe
    vs = load(overrides)
    now = datetime.now().isoformat(timespec="seconds")
    if not vs:
        vs.append({"v": 1, "at": now, "summary": "starting point (before the first change made in the web app)", "panels": [],
                   "data": old})
    summary, panels = describe_(old, new)
    if summary == "no change" and not prefix:
        return None
    rec = {"v": vs[-1]["v"] + 1, "at": now, "summary": (prefix + summary) if prefix else summary, "panels": panels,
           "by": _who(), "state": "draft", "data": new}
    vs.append(rec)
    _dump(overrides, vs)
    return rec


def _who() -> str | None:
    from . import auth
    u = auth.current()
    return u["name"] if u else None


STATES = ("draft", "checked", "approved")


def set_state(path: Path, v: int, state: str) -> dict:
    """Draft → Checked (a checker) → Approved (an approver, after checking). Nobody checks or approves their own version."""
    from . import auth
    if state not in ("checked", "approved"):
        raise ValueError("state must be checked or approved")
    u = auth.require("checker" if state == "checked" else "approver")
    vs = load(path)
    r = next((x for x in vs if x["v"] == int(v)), None)
    if r is None:
        raise ValueError(f"no version {v}")
    if r.get("by") and r["by"] == u["name"]:
        raise PermissionError("four eyes: you made this version — another person checks or approves it")
    cur = r.get("state", "draft")
    if state == "checked" and cur != "draft":
        raise ValueError(f"version {v} is {cur} already")
    if state == "approved":
        if cur != "checked":
            raise ValueError(f"version {v} must be checked before it is approved")
        if r.get("checked_by") == u["name"]:
            raise PermissionError("four eyes: the approver is not the checker")
    r["state"] = state
    r[f"{state}_by"], r[f"{state}_at"] = u["name"], datetime.now().isoformat(timespec="seconds")
    _dump(path, vs)
    return {"v": r["v"], "state": state, "by": u["name"]}


def _dump(path: Path, vs: list[dict]) -> None:
    _file(path).parent.mkdir(parents=True, exist_ok=True)
    _file(path).write_text("# Version history of the designer's changes (written by the web app; one entry per change).\n"
                           + yaml.safe_dump({"versions": vs}, sort_keys=False, allow_unicode=True, width=200))


def label(path: Path, v: int, text: str) -> dict:
    """Name a version (e.g. 'Issued to client, rev A'); an empty text clears the name. The content is not changed."""
    text = str(text or "").strip()[:80]
    vs = load(path)
    r = next((x for x in vs if x["v"] == int(v)), None)
    if r is None:
        raise ValueError(f"no version {v}")
    if text:
        r["label"] = text
    else:
        r.pop("label", None)
    _dump(path, vs)
    return {"v": r["v"], "label": r.get("label")}


def listing(overrides: Path) -> list[dict]:
    """Versions without their content, newest first, with the number of edits of each kind."""
    out = []
    for r in load(overrides):
        d = r.get("data") or {}
        out.append({"v": r["v"], "at": r["at"], "summary": r["summary"], "panels": r.get("panels", []), "label": r.get("label"),
                    "by": r.get("by"), "state": r.get("state", "draft"), "checked_by": r.get("checked_by"), "approved_by": r.get("approved_by"),
                    "checked_at": r.get("checked_at"), "approved_at": r.get("approved_at"),
                    "counts": {label: len(d.get(k) or []) for k, label in LISTS.items()},
                    "standby": sum(len(x) for x in (d.get("standby") or {}).values()),
                    "settings": sum(len(x) for x in (d.get("settings") or {}).values())})
    return out[::-1]


def get(overrides: Path, v: int) -> dict:
    r = next((x for x in load(overrides) if x["v"] == int(v)), None)
    if r is None:
        raise ValueError(f"no version {v}")
    return r
