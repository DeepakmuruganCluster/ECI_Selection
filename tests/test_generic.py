"""The engine is generic: no client project is named in code; everything project-specific comes from project.yaml."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# The engine: selection code, core, the web app and the generic scripts. Not included: scripts/verify_*.py — the G6
# verification runs behind each component's VERIFY.md, which use a real project (ECI WNS2503) as their worked sample;
# they are recorded evidence, not used by any selection.
CODE = [*ROOT.glob("components/*/select.py"), *ROOT.glob("core/*.py"),
        *(f for f in ROOT.glob("scripts/*.py") if not f.name.startswith("verify_")),
        ROOT / "webapp" / "server.py", ROOT / "webapp" / "index.html"]


def _project_words() -> set[str]:
    """Names, panels and document references of every held project (read from the project files themselves)."""
    from core import project as P
    words = set()
    for n in P.names():
        d = P.load(n)
        words |= {n, *map(str, d.get("aliases") or []), *P.panels(n), *(d.get("documents") or {}).values()}
    return {w for w in words if len(w) > 2}


def test_no_project_is_named_in_code():
    words = _project_words()
    hits = []
    for f in CODE:
        text = f.read_text()
        for w in words:
            if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", text):
                hits.append(f"{f.relative_to(ROOT)}: {w}")
    assert not hits, hits


def test_project_tables_live_with_their_project():
    from core import project as P
    for n in P.names():
        for key in (P.load(n).get("data") or {}):
            assert P.table(key, n).is_file(), (n, key)
            assert P.table(key, n).is_relative_to(P.load(n)["_dir"]), (n, key)


def test_project_resolution(tmp_path, monkeypatch):
    """With one project held it is the default; with two the caller must name one; aliases resolve; unknown → error."""
    from core import project as P
    for name, alias in (("ALPHA", "A1"), ("BETA", None)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "project.yaml").write_text(
            f"client: {name.title()}\npanels: [P1, P2]\n" + (f"aliases: [{alias}]\n" if alias else "")
            + "documents: {automation: X-AUTO}\nrequirements: {meter_communication: {value: profinet, text: t, source: s}}\n")
    monkeypatch.setattr(P, "PROJECTS_DIR", tmp_path)
    for f in (P._aliases, P.load):
        f.cache_clear()
    try:
        assert P.names() == ["ALPHA", "BETA"]
        with pytest.raises(P.ProjectError):
            P.resolve(None)
        assert P.resolve("A1") == "ALPHA" and P.panels("BETA") == ("P1", "P2") and P.client("BETA") == "Beta"
        assert P.doc("automation", "ALPHA") == "X-AUTO"
        with pytest.raises(P.ProjectError):
            P.doc("load_list", "ALPHA")
        with pytest.raises(P.ProjectError):
            P.resolve("GAMMA")
        assert P.cite(P.setting("requirements", "ALPHA"), "meter_communication") == ("t", "s")
        assert P.cite(None, "meter_communication") == (None, "designer input")
    finally:
        for f in (P._aliases, P.load):
            f.cache_clear()


def test_generic_components_without_a_client_requirement_cite_the_designer():
    from components.metering.select import select as metering
    r = metering(circuit_a=630, ct_make="rishabh", busbar_w_mm=40, busbar_t_mm=10, communication="profinet")
    srcs = [c.source for c in r.checks if c.rule == "R-MTR-02"]
    assert srcs and not any("ECI" in s for s in srcs)
