"""Design projects (owner 2026-10-16): a project the designer starts from a description, holding one or more machine
panels. Every selection made in the web app lives in this structure:

    designs/<project>/design.yaml            name, client, location, panels
    designs/<project>/panels/<panel>.yaml     the panel's design: description, answers, BOM / power / I/O edits
    designs/<project>/panels/<panel>.versions.yaml   every saved change of that panel (core/versions.py)

A design holds only what the designer gave (the words and the answers) and the edits; the engine selects everything
again each time it is opened, from the same sources — the saved design is never a frozen copy of a selection.
Client projects (projects/<name>/, with the client's documents) are listed beside these; they keep their own files.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from . import versions

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ROOT / "designs"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,59}$")
FIELDS = ("text", "answers", "edits", "power_edits", "io_edits")


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "-", name.strip()).strip("-")


def _check(name, what: str) -> str:
    if not isinstance(name, str) or not NAME.match(name.strip()) or ".." in name:
        raise ValueError(f"{what} name: letters, digits, space, '_', '-', '.', at most 60 characters (got {name!r})")
    return name.strip()


def _dir(pid: str) -> Path:
    pid = _check(pid, "project")
    d = DESIGNS / _slug(pid)
    if not (d / "design.yaml").exists():
        raise ValueError(f"no design project {pid!r}")
    return d


def _panel_file(pid: str, panel: str) -> Path:
    return _dir(pid) / "panels" / f"{_slug(_check(panel, 'panel'))}.yaml"


def _read(f: Path) -> dict:
    return (yaml.safe_load(f.read_text()) or {}) if f.exists() else {}


def _write(f: Path, data: dict, head: str) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=200))


def listing() -> list[dict]:
    out = []
    for f in sorted(DESIGNS.glob("*/design.yaml")):
        d = _read(f)
        panels = []
        for p in d.get("panels") or []:
            pf = f.parent / "panels" / f"{_slug(p)}.yaml"
            vs = versions.listing(pf.with_name(pf.stem + ".versions.yaml")) if pf.exists() else []
            panels.append({"name": p, "updated": _read(pf).get("updated"), "versions": len(vs),
                           "label": next((v["label"] for v in vs if v.get("label")), None)})
        out.append({"id": f.parent.name, "name": d.get("name"), "client": d.get("client"), "location": d.get("location"),
                    "created": d.get("created"), "panels": panels})
    return out


def create(name: str, client: str = "", location: str = "") -> dict:
    name = _check(name, "project")
    d = DESIGNS / _slug(name)
    if (d / "design.yaml").exists():
        raise ValueError(f"a project {name!r} exists already")
    rec = {"name": name, "client": str(client or "")[:80], "location": str(location or "")[:80],
           "created": datetime.now().isoformat(timespec="seconds"), "panels": []}
    _write(d / "design.yaml", rec, "# Design project (web app): name, client, location and its panels.\n")
    return {"id": d.name, **rec}


def _clean(design: dict) -> dict:
    if not isinstance(design, dict):
        raise ValueError("the design must be an object")
    text = design.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 5000:
        raise ValueError("the design needs its description (at most 5 000 characters)")
    answers = design.get("answers") or {}
    if not isinstance(answers, dict) or not all(isinstance(k, str) and isinstance(v, (str, int, float, bool)) for k, v in answers.items()):
        raise ValueError("answers must be name → value")
    out = {"text": text, "answers": {k: v for k, v in answers.items()}}
    if design.get("template"):                       # an ECI template copy (core/templates.py, R-REQ-29)
        from . import templates
        templates.get(str(design["template"]))
        out["template"] = str(design["template"])
    for k in ("edits", "power_edits", "io_edits"):
        v = design.get(k) or []
        if not isinstance(v, list) or not all(isinstance(e, dict) for e in v) or len(v) > 500:
            raise ValueError(f"{k} must be a list of edits")
        out[k] = v
    return out


def describe(old: dict, new: dict) -> tuple[str, list[str]]:
    """What changed in a machine panel's design (the version text)."""
    parts = []
    if not old:
        return "created", []
    if (old.get("text") or "") != (new.get("text") or ""):
        parts.append("description changed")
    oa, na = old.get("answers") or {}, new.get("answers") or {}
    for k in sorted(set(oa) | set(na)):
        if oa.get(k) != na.get(k):
            parts.append(f"{k}: {oa.get(k, '—')} → {na.get(k, '—')}" if k in na else f"{k}: answer cleared")
    for k, label in (("edits", "BOM"), ("power_edits", "Power"), ("io_edits", "I/O")):
        o, n = old.get(k) or [], new.get(k) or []
        if o != n:
            added = [e for e in n if e not in o]
            gone = [e for e in o if e not in n]
            for e in added:
                parts.append(f"{label}: {versions._text(k, e) if k != 'edits' else versions._text(k, {**e, 'line': e.get('line') or {}})}")
            for e in gone:
                parts.append(f"{label}: took back '{versions._text(k, e) if k != 'edits' else versions._text(k, {**e, 'line': e.get('line') or {}})}'")
    return ("; ".join(parts) or "no change"), []


def save(pid: str, panel: str, design: dict, prefix: str = "") -> dict:
    """Save a panel's design (adding the panel to the project when new). A changed design is a new version."""
    pf = _panel_file(pid, panel)
    new = _clean(design)
    old = _read(pf).get("design") or {}
    if old == new:
        vs = versions.listing(_vfile(pf))
        return {"saved": False, "version": vs[0] if vs else None}
    _write(pf, {"design": new, "updated": datetime.now().isoformat(timespec="seconds")},
           "# A machine panel's design (web app): the words, the answers and the designer's edits. The engine selects again.\n")
    meta_f = _dir(pid) / "design.yaml"
    meta = _read(meta_f)
    if panel.strip() not in (meta.get("panels") or []):
        meta["panels"] = (meta.get("panels") or []) + [panel.strip()]
        _write(meta_f, meta, "# Design project (web app): name, client, location and its panels.\n")
    vf = _vfile(pf)
    if not versions.load(vf):           # the first version of a new panel is its first save
        versions._dump(vf, [{"v": 1, "at": datetime.now().isoformat(timespec="seconds"), "summary": prefix + "created",
                             "panels": [panel], "by": versions._who(), "state": "draft", "data": new}])
        return {"saved": True, "version": versions.listing(vf)[0]}
    rec = versions.record(vf, old, new, prefix, describe_fn=describe)
    return {"saved": True, "version": versions.listing(vf)[0] if rec else None}


def _vfile(pf: Path) -> Path:
    return pf.with_name(pf.stem + ".versions.yaml")


def load(pid: str, panel: str) -> dict:
    pf = _panel_file(pid, panel)
    if not pf.exists():
        raise ValueError(f"no panel {panel!r} in {pid!r}")
    vs = versions.listing(_vfile(pf))
    return {"design": _read(pf)["design"], "updated": _read(pf).get("updated"), "version": vs[0] if vs else None}


def history(pid: str, panel: str) -> list[dict]:
    return versions.listing(_vfile(_panel_file(pid, panel)))


def get(pid: str, panel: str, v: int) -> dict:
    return versions.get(_vfile(_panel_file(pid, panel)), v)


def restore(pid: str, panel: str, v: int) -> dict:
    data = get(pid, panel, v)["data"]
    return save(pid, panel, data, prefix=f"restored version {int(v)}: ")


def set_state(pid: str, panel: str, v: int, state: str) -> dict:
    return versions.set_state(_vfile(_panel_file(pid, panel)), v, state)


def label(pid: str, panel: str, v: int, text: str) -> dict:
    return versions.label(_vfile(_panel_file(pid, panel)), v, text)


# --- delete (owner 2026-10-17): a deleted project or panel goes to designs/.deleted/, never wiped, and can be restored ---
TRASH = ".deleted"


def _approved(d: Path) -> list[str]:
    """Panels of a project folder holding an approved version (deleting those needs an admin)."""
    return sorted({f.name.removesuffix(".versions.yaml") for f in (d / "panels").glob("*.versions.yaml")
                   if any(v.get("state") == "approved" for v in versions.load(f))})


def _guard(approved: list[str], what: str) -> dict:
    from . import auth
    u = auth.require("designer")
    if approved and "admin" not in u["roles"]:
        raise PermissionError(f"{what} has an approved version ({', '.join(approved)}): only an admin deletes approved work")
    return u


def _bin(name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DESIGNS / TRASH / f"{_slug(name)}--{stamp}"


def delete_project(pid: str) -> dict:
    d = _dir(pid)
    u = _guard(_approved(d), f"project {pid!r}")
    meta = _read(d / "design.yaml")
    meta.update({"deleted_at": datetime.now().isoformat(timespec="seconds"), "deleted_by": u["name"], "kind": "project"})
    _write(d / "design.yaml", meta, "# Design project (web app): name, client, location and its panels. DELETED (restorable).\n")
    dest = _bin(d.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    d.rename(dest)
    return {"deleted": pid, "panels": len(meta.get("panels") or []), "bin": dest.name}


def delete_panel(pid: str, panel: str) -> dict:
    pf = _panel_file(pid, panel)
    if not pf.exists():
        raise ValueError(f"no panel {panel!r} in {pid!r}")
    vf = _vfile(pf)
    u = _guard([panel] if any(v.get("state") == "approved" for v in versions.load(vf)) else [], f"panel {panel!r}")
    dest = _bin(f"{_dir(pid).name}--{pf.stem}")
    (dest / "panels").mkdir(parents=True)
    _write(dest / "deleted.yaml", {"kind": "panel", "project": _dir(pid).name, "panel": panel.strip(),
                                   "deleted_at": datetime.now().isoformat(timespec="seconds"), "deleted_by": u["name"]},
           "# A deleted panel (web app): restorable into its project.\n")
    for f in (pf, vf):
        if f.exists():
            f.rename(dest / "panels" / f.name)
    meta_f = _dir(pid) / "design.yaml"
    meta = _read(meta_f)
    meta["panels"] = [p for p in meta.get("panels") or [] if p != panel.strip()]
    _write(meta_f, meta, "# Design project (web app): name, client, location and its panels.\n")
    return {"deleted": panel.strip(), "project": pid, "bin": dest.name}


def deleted() -> list[dict]:
    """What is in the bin, newest first: {id, kind, name, project, panels, deleted_at, deleted_by}."""
    out = []
    for d in sorted((DESIGNS / TRASH).glob("*"), reverse=True):
        if (d / "deleted.yaml").exists():
            m = _read(d / "deleted.yaml")
            out.append({"id": d.name, "kind": "panel", "name": m.get("panel"), "project": m.get("project"),
                        "deleted_at": m.get("deleted_at"), "deleted_by": m.get("deleted_by")})
        elif (d / "design.yaml").exists():
            m = _read(d / "design.yaml")
            out.append({"id": d.name, "kind": "project", "name": m.get("name"), "panels": m.get("panels") or [],
                        "deleted_at": m.get("deleted_at"), "deleted_by": m.get("deleted_by")})
    return out


def undelete(bin_id: str) -> dict:
    from . import auth
    auth.require("designer")
    if not isinstance(bin_id, str) or "/" in bin_id or bin_id.startswith(".") or not (DESIGNS / TRASH / bin_id).is_dir():
        raise ValueError(f"nothing deleted under {bin_id!r}")
    src = DESIGNS / TRASH / bin_id
    if (src / "deleted.yaml").exists():                      # a panel: back into its project (which must exist)
        m = _read(src / "deleted.yaml")
        pdir = DESIGNS / m["project"]
        if not (pdir / "design.yaml").exists():
            raise ValueError(f"its project {m['project']!r} is gone: restore the project first")
        target = pdir / "panels"
        for f in (src / "panels").iterdir():
            if (target / f.name).exists():
                raise ValueError(f"a panel {m['panel']!r} exists again in {m['project']!r}: rename or delete it first")
        target.mkdir(parents=True, exist_ok=True)
        for f in (src / "panels").iterdir():
            f.rename(target / f.name)
        meta = _read(pdir / "design.yaml")
        if m["panel"] not in (meta.get("panels") or []):
            meta["panels"] = (meta.get("panels") or []) + [m["panel"]]
            _write(pdir / "design.yaml", meta, "# Design project (web app): name, client, location and its panels.\n")
        (src / "deleted.yaml").unlink()
        (src / "panels").rmdir()
        src.rmdir()
        return {"restored": m["panel"], "kind": "panel", "project": m["project"]}
    meta = _read(src / "design.yaml")
    dest = DESIGNS / _slug(meta["name"])
    if dest.exists():
        raise ValueError(f"a project {meta['name']!r} exists again: rename or delete it first")
    for k in ("deleted_at", "deleted_by", "kind"):
        meta.pop(k, None)
    _write(src / "design.yaml", meta, "# Design project (web app): name, client, location and its panels.\n")
    src.rename(dest)
    return {"restored": meta["name"], "kind": "project"}
