"""Company standards (owner 2026-10-19): a named, approved set of answers to the RFQ project questions that are company
practice, not per job (PLC family, makes, control circuit, wiring …). An RFQ starts from an approved standard in one
click; every value it gives is shown as coming from that standard (name, version, who approved it, when) and can be
overridden per RFQ or per panel. The site questions (fault level, temperatures, cable length, voltage, other cables
beside the motor cables) are never part of a standard: they are asked for every RFQ.

Four eyes: a standard is written by a designer and approved by an approver who did not write it. Changing an approved
standard makes a new draft version; an RFQ keeps the copy (snapshot) of the version it applied.
Stored in standards/<id>.yaml with every version.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STANDARDS = ROOT / "standards"
SITE = ("fault_ka", "panel_internal_c", "cable_ambient_c", "cable_m", "voltage_v", "cable_other")


def _spec() -> dict:
    from core import rfq_answers as A
    return {k: (kind, opts, A.NUM_LIMITS.get(k), q, grp) for k, q, kind, opts, grp, _ in A.PROJECT if k not in SITE}


def _file(sid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", str(sid or "")):
        raise ValueError(f"no standard {sid!r}")
    return STANDARDS / f"{sid}.yaml"


def _read(sid: str) -> dict:
    f = _file(sid)
    if not f.exists():
        raise ValueError(f"no standard {sid!r}")
    return yaml.safe_load(f.read_text()) or {}


def _write(d: dict) -> None:
    STANDARDS.mkdir(parents=True, exist_ok=True)
    _file(d["id"]).write_text("# Company standard (core/standards.py): answers to the RFQ project questions — written by the web app.\n"
                              + yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=200))


def _clean(values: dict) -> dict:
    """Only company questions, each checked like an RFQ answer; empty values are left out."""
    from core.rfq_answers import _check
    spec, out = _spec(), {}
    for k, v in (values or {}).items():
        if k in SITE:
            raise ValueError(f"{k} is a site question: it is asked for every RFQ, never part of a standard")
        if k not in spec:
            raise ValueError(f"no project question {k!r}")
        kind, opts, lim, _, _ = spec[k]
        x = _check(k, v, kind, opts, lim)
        if x is not None:
            out[k] = x
    return out


def current(d: dict) -> dict:
    return d["versions"][-1]


def approved(d: dict) -> dict | None:
    """The latest approved version (the one an RFQ may apply)."""
    return next((v for v in reversed(d["versions"]) if v.get("state") == "approved"), None)


def summary(d: dict) -> dict:
    c, a = current(d), approved(d)
    return {"id": d["id"], "name": d["name"], "note": d.get("note", ""), "version": c["v"], "state": c["state"],
            "by": c.get("by"), "at": c.get("at"), "values": c["values"], "n_values": len(c["values"]),
            "approved": {"v": a["v"], "by": a["approved_by"], "at": a["approved_at"], "values": a["values"]} if a else None}


def listing() -> list[dict]:
    if not STANDARDS.exists():
        return []
    return [summary(yaml.safe_load(f.read_text())) for f in sorted(STANDARDS.glob("*.yaml"))]


def questions() -> list[dict]:
    """The questions a standard can answer (the company ones), grouped as on the RFQ page."""
    return [{"key": k, "question": q, "kind": kind, "options": opts, "limits": lim, "group": grp}
            for k, (kind, opts, lim, q, grp) in _spec().items()]


def save(name: str, values: dict, note: str = "", sid: str | None = None) -> dict:
    """A new standard, or a new draft version of one (needs the designer role)."""
    from core import auth
    u = auth.require("designer")
    name = str(name or "").strip()
    if not 2 <= len(name) <= 80:
        raise ValueError("a standard needs a name (2 … 80 characters)")
    vals = _clean(values)
    if not vals:
        raise ValueError("a standard answers at least one question")
    now = datetime.now().isoformat(timespec="seconds")
    if sid:
        d = _read(sid)
        d["name"], d["note"] = name, str(note or "")[:400]
        d["versions"].append({"v": current(d)["v"] + 1, "state": "draft", "by": u["name"], "at": now, "values": vals})
    else:
        base = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:40] or "standard"
        sid, n = base, 2
        while (STANDARDS / f"{sid}.yaml").exists():
            sid, n = f"{base}-{n}", n + 1
        d = {"id": sid, "name": name, "note": str(note or "")[:400],
             "versions": [{"v": 1, "state": "draft", "by": u["name"], "at": now, "values": vals}]}
    _write(d)
    return summary(d)


def approve(sid: str, v: int) -> dict:
    """An approver who did not write this version approves it (four eyes)."""
    from core import auth
    u = auth.require("approver")
    d = _read(sid)
    r = next((x for x in d["versions"] if x["v"] == int(v)), None)
    if r is None:
        raise ValueError(f"{sid}: no version {v}")
    if r["state"] == "approved":
        raise ValueError(f"{sid} version {v} is approved already")
    if r is not current(d):
        raise ValueError(f"{sid}: only the latest version ({current(d)['v']}) can be approved")
    if r.get("by") == u["name"]:
        raise PermissionError("four eyes: you wrote this version — another person approves it")
    r.update(state="approved", approved_by=u["name"], approved_at=datetime.now().isoformat(timespec="seconds"))
    _write(d)
    return summary(d)


def snapshot(sid: str) -> dict:
    """What an RFQ keeps when it applies a standard: its latest approved version, with who approved it."""
    d = _read(sid)
    a = approved(d)
    if a is None:
        raise ValueError(f"{d['name']} has no approved version yet: an approver signs it off first")
    return {"id": d["id"], "name": d["name"], "v": a["v"], "approved_by": a["approved_by"], "approved_at": a["approved_at"],
            "values": dict(a["values"])}
