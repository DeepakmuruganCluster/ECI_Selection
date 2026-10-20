"""Client-specified items of a project (table and documents from projects/<name>/project.yaml). Rules: rules.yaml (R-CLI-01 … 05)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from core import project as P
from core.provenance import load_sourced_table, load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "client_items"


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


@lru_cache(maxsize=None)
def _spec(project: str | None = None) -> dict:
    """The project's client-items table (project.yaml data: client_items)."""
    return load_sourced_table(P.table("client_items", project), ("panel", "item", "unit", "qty_basis", "spec"))


def _p(page, project: str | None = None) -> str:
    return f"{P.doc('automation', project)} p.{page}"


def select(panel: str = "all", include_plant: bool = True, project: str | None = None) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    try:
        PANELS = P.panels(project)
    except P.ProjectError as e:
        return res.invalid(str(e))
    if panel not in (*PANELS, "all"):
        return res.invalid(f"panel must be one of {', '.join(PANELS)} or all (got {panel})")
    spec = _spec(project)
    panels = PANELS if panel == "all" else (panel,)
    rows = [r for r in spec["rows"] if r["panel"] in panels or (include_plant and r["panel"] == "plant")]
    built = set(_rules()["params"]["built_components"])

    items, missing, interpreted = [], [], []
    for r in rows:
        status = ("bought-out (no engineering check)" if not r.get("verify_by")
                  else "client-specified, check in " + r["verify_by"] + ("" if r["verify_by"] in built else " (not built)"))
        items.append({"panel": r["panel"], "item": r["item"], "make": r.get("make"), "model": r.get("model"),
                      "qty": r.get("qty"), "unit": r["unit"], "qty_basis": r["qty_basis"], "status": status,
                      "source": _p(r["page"], project), "spec": r["spec"], "verify_by": r.get("verify_by")})
        if r.get("qty") is None:
            missing.append(f"{r['panel']}: {r['item']}")
        elif r["qty_basis"] == "interpreted":
            interpreted.append(f"{r['panel']}: {r['item']} = {r['qty']} {r['unit']}")

    res.add("R-CLI-01", "items listed as the client wrote them", f"{len(items)} item(s)", PASS, _p(1, project))
    if missing:
        res.add("R-CLI-01", "every client item has a quantity", f"not stated for {len(missing)}: {'; '.join(missing)}",
                WARN, _p(1, project))
    if interpreted:
        res.add("R-CLI-02", "interpreted quantities confirmed by the client", "; ".join(interpreted), WARN, _p(1, project))
    unverified = sorted({r["verify_by"] for r in rows if r.get("verify_by") and r["verify_by"] not in built})
    res.add("R-CLI-03", "client items checked by an engineering component",
            "waiting for components: " + ", ".join(unverified) if unverified else "all checkable now", INFO)

    # the spec's own arithmetic
    problems = []
    io = [x for x in spec["io"] if x["panel"] in panels]
    for x in io:
        if x["required"] + x["spare"] != x["final"]:
            problems.append(f"{x['panel']} {x['signal']}: {x['required']} + {x['spare']} ≠ {x['final']}")
    if panel == "all":
        tot = spec["io_totals"]
        for sig, val in tot.items():
            if sig == "page":
                continue
            s = sum(x["final"] for x in spec["io"] if x["signal"] == sig)
            if s != val:
                problems.append(f"total {sig}: panels add up to {s}, spec says {val}")
    for r in rows:
        if r.get("sections_mm") and r.get("length_mm"):
            s = sum(r["sections_mm"])
            if s != r["length_mm"]:
                problems.append(f"{r['panel']} sections {' + '.join(map(str, r['sections_mm']))} = {s} mm, "
                                f"spec states length {r['length_mm']} mm")
    if problems:
        res.add("R-CLI-04", "the specification's own numbers add up", "; ".join(problems), WARN, _p(1, project))
    else:
        res.add("R-CLI-04", "the specification's own numbers add up", "yes (I/O sums, section widths)", PASS, _p(1, project))
    spares = "; ".join(f"{x['panel']} {x['signal']} {x['spare'] / x['required']:.0%}" for x in io if x["required"])
    res.add("R-CLI-05", "spare I/O as a share of required I/O", spares, INFO, _p(1, project))

    res.value = {"n_items": len(items), "n_qty_missing": len(missing), "n_interpreted": len(interpreted),
                 "items": items, "spec_problems": problems}
    res.basis = "client specification"
    return res


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
