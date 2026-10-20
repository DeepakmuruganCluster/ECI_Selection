"""Client projects: everything project-specific is read from projects/<name>/project.yaml, never written in code.

A project file names its panels, its client documents by role, its data tables, the client's requirement statements
(with their source) and project settings (e.g. the PLC). Components ask this module; they hold no project names.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .provenance import load_yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"


class ProjectError(ValueError):
    pass


def names() -> list[str]:
    """Every project folder that has a project.yaml."""
    return sorted(p.parent.name for p in PROJECTS_DIR.glob("*/project.yaml"))


@lru_cache(maxsize=None)
def _aliases() -> dict:
    out = {}
    for n in names():
        out[n] = n
        for a in load_yaml(PROJECTS_DIR / n / "project.yaml").get("aliases") or []:
            out[str(a)] = n
    return out


def resolve(name: str | None = None) -> str:
    """The project's folder name. None → the only project held (several held → the caller must name one)."""
    if name is None:
        held = names()
        if len(held) != 1:
            raise ProjectError(f"name the project: {', '.join(held) or 'none held'}")
        return held[0]
    if str(name) not in _aliases():
        raise ProjectError(f"unknown project {name!r} (held: {', '.join(names())})")
    return _aliases()[str(name)]


@lru_cache(maxsize=None)
def load(name: str | None = None) -> dict:
    n = resolve(name)
    d = load_yaml(PROJECTS_DIR / n / "project.yaml")
    d["_name"], d["_dir"] = n, PROJECTS_DIR / n
    return d


def panels(name: str | None = None) -> tuple:
    return tuple(load(name)["panels"])


def client(name: str | None = None) -> str:
    return load(name).get("client") or resolve(name)


def doc(role: str, name: str | None = None) -> str:
    """The registered reference of the client document with this role (automation, equipment, load_list …)."""
    docs = load(name).get("documents") or {}
    if role not in docs:
        raise ProjectError(f"project {resolve(name)} names no '{role}' document")
    return docs[role]


def table(key: str, name: str | None = None) -> Path:
    """A project data table by its key in project.yaml 'data'."""
    data = load(name).get("data") or {}
    if key not in data:
        raise ProjectError(f"project {resolve(name)} has no '{key}' table")
    return load(name)["_dir"] / data[key]


def requirement(key: str, name: str | None = None) -> dict | None:
    """A client requirement statement {text, source, value?} or None when the client states none."""
    return (load(name).get("requirements") or {}).get(key)


def setting(key: str, name: str | None = None, default=None):
    return load(name).get(key, default)


def cite(reqs: dict | None, key: str) -> tuple[str | None, str]:
    """(client's text, source) of a requirement passed to a generic component; (None, 'designer input') without one."""
    r = (reqs or {}).get(key)
    return (r.get("text"), r.get("source") or "client") if r else (None, "designer input")
