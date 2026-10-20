"""Build the parts catalog (parts master, price book, source map) from every data table. Generated, never edited.

    .venv/bin/python scripts/build_catalog.py

Reads data/makers, data/company and projects/*/data. Writes data/catalog/:
  parts.yaml     one entry per article: make, descriptions, every source row, the components that use it, SAP code
  prices.yaml    every price with its source row and basis, grouped by price source
  sources.yaml   every registered document by authority, with the tables that read it
  conflicts.md   the same article with different descriptions, makes or prices (for the owner to settle)
No value is changed: the catalog only indexes what the tables already hold (tests/test_catalog.py checks it is current).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.data import tables as tables_on_disk  # noqa: E402
from core.provenance import register  # noqa: E402

OUT = ROOT / "data" / "catalog"
ARTICLE_KEYS = ("article", "order_no", "order_no_c2", "mpcb", "contactor", "link_module", "fuse", "model")
MAKE_BY_PREFIX = (("SIE-", "Siemens"), ("POLYCAB", "Polycab"), ("KEI", "KEI"), ("LAPP", "Lapp"), ("FINDER", "Finder"),
                  ("CW-", "Connectwell"), ("RISH", "Rishabh"), ("SELEC", "Selec"), ("RITTAL", "Rittal"),
                  ("OWN-VFD-DB", "Siemens"), ("OWN-CU", "Siemens"), ("OWN-MC", "Siemens"))


MAKE_ALIASES = {"Elemex": "Elmex", "Polycap": "Polycab", "Lapp/Polycap": "Lapp / Polycab", "Gic": "GIC", "Gic/Selec": "GIC / Selec"}


def key(article: str) -> str:
    """One part, however it is written: 'KUT 4' = 'KUT4', '5SL61066RC' = '5SL6106-6RC' (index only; tables keep theirs)."""
    return "".join(ch for ch in article.upper() if ch.isalnum())


def tables():
    for f in tables_on_disk():
        d = yaml.safe_load(f.read_text())
        if isinstance(d, dict) and isinstance(d.get("rows"), list):
            yield f, d


def owner(f: Path) -> str:
    """The components whose review page lists the table (or the project that holds it)."""
    rel = str(f.relative_to(ROOT))
    users = [c for c, files in _readers().items() if rel in files]
    return ", ".join(users) if users else (f"project {f.parts[-3]}" if f.parts[-4] == "projects" else "unused")


@lru_cache(maxsize=None)
def _readers() -> dict:
    out = {}
    for rv in sorted(ROOT.glob("components/*/review.yaml")):
        out[rv.parent.name] = set((yaml.safe_load(rv.read_text()) or {}).get("data_files") or [])
    return out


def locator(r: dict) -> str:
    if r.get("page") is not None:
        return f"p.{r['page']}"
    if r.get("sheet"):
        return f"sheet '{str(r['sheet']).strip()}' row {r.get('row')}"
    return f"row {r.get('row')}" if r.get("row") is not None else ""


def make_of(ref: str, r: dict) -> str:
    for k in ("make", "brand", "manufacturer"):
        if r.get(k):
            return str(r[k]).strip().title() if str(r[k]).isupper() else str(r[k]).strip()
    return next((m for p, m in MAKE_BY_PREFIX if ref.startswith(p)), "")


def build() -> dict:
    parts = defaultdict(lambda: {"make": set(), "descriptions": set(), "sources": [], "used_by": set(), "sap_code": None,
                                 "spellings": set()})
    prices = defaultdict(list)
    used_refs = defaultdict(set)
    for f, d in tables():
        ref = (d.get("source") or {}).get("ref", "")
        table = str(f.relative_to(ROOT))
        used_refs[ref].add(table)
        for r in d["rows"]:
            if not isinstance(r, dict):
                continue
            if r.get("kind") == "sap":          # company SAP codes from the drawing BOM
                parts[key(str(r["article"]))]["sap_code"] = r["sap_code"]
                parts[key(str(r["article"]))]["spellings"].add(str(r["article"]))
                continue
            # company kits keep their lines one level down (items), with prices
            items = r.get("items") if isinstance(r.get("items"), list) else None
            for it, where in ([(i, f"{locator(r).split(' row ')[0]} row {i.get('row')}") for i in items] if items
                              else [(r, locator(r))]):
                for k in ARTICLE_KEYS:
                    a = it.get(k)
                    if not a or not isinstance(a, str) or k == "model" and len(a) < 3:
                        continue
                    a = a.strip()
                    p = parts[key(a)]
                    p["spellings"].add(a)
                    m = make_of(ref, it)
                    if m:
                        p["make"].add(MAKE_ALIASES.get(m, m))
                    desc = it.get("description") or it.get("model") or it.get("item") or it.get("series") or ""
                    if desc:
                        p["descriptions"].add(str(desc).strip())
                    p["sources"].append({"ref": ref, "where": where, "table": table})
                    p["used_by"].update(owner(f).split(", "))
                    if it.get("unit_price_inr") is not None:
                        prices[ref].append({"article": a, "key": key(a), "inr": it["unit_price_inr"], "where": where,
                                            "table": table})
    reg = register()
    return {
        "parts": {k: {"spellings": sorted(p["spellings"]), "make": sorted(p["make"]), "descriptions": sorted(p["descriptions"]),
                      "sap_code": p["sap_code"], "used_by": sorted(p["used_by"]), "sources": p["sources"]}
                  for k, p in sorted(parts.items()) if p["sources"] or p["sap_code"]},
        "prices": {ref: {"title": reg.get(ref, {}).get("title", ""), "edition": reg.get(ref, {}).get("edition", ""),
                         "currency": "INR", "lines": v} for ref, v in sorted(prices.items())},
        "sources": {kind: {r: {"title": v.get("title", ""), "edition": v.get("edition", ""), "file": v.get("file", ""),
                               "tables": sorted(used_refs.get(r, []))} for r, v in sorted(reg.items())
                           if (v.get("kind") or "other") == kind}
                    for kind in sorted({(v.get("kind") or "other") for v in reg.values()})},
    }


def conflicts(cat: dict) -> str:
    lines = ["# Catalog conflicts (generated)", "",
             "The same article with more than one make or price. Nothing is changed automatically: the owner decides.", ""]
    multi_make = [(a, p["make"]) for a, p in cat["parts"].items() if len(p["make"]) > 1]
    lines += ["## More than one make (after merging spelling variants of makes)", ""] + \
        [f"- `{a}`: {', '.join(m)}" for a, m in multi_make] + ["" if multi_make else "none", ""]
    spell = [(a, p["spellings"]) for a, p in cat["parts"].items() if len(p["spellings"]) > 1]
    lines += ["## One part written several ways", ""] + [f"- {' = '.join(f'`{x}`' for x in sp)}" for a, sp in spell] + \
        ["" if spell else "none", ""]
    zero = sorted({ln["article"] for b in cat["prices"].values() for ln in b["lines"] if float(ln["inr"]) == 0})
    lines += ["## Priced at zero in a company sheet", ""] + [f"- `{a}`" for a in zero] + ["" if zero else "none", ""]
    byart = defaultdict(set)
    for ref, block in cat["prices"].items():
        for ln in block["lines"]:
            byart[ln["key"]].add((round(float(ln["inr"]), 2), ref))
    diff = {a: v for a, v in byart.items() if len({x[0] for x in v}) > 1}
    lines += ["## More than one price", ""]
    for a, v in sorted(diff.items()):
        lines.append(f"- `{a}`: " + "; ".join(f"₹{p:,.2f} ({r})" for p, r in sorted(v)))
    if not diff:
        lines.append("none")
    return "\n".join(lines) + "\n"


def write():
    cat = build()
    OUT.mkdir(parents=True, exist_ok=True)
    head = "# Generated by scripts/build_catalog.py — do not edit by hand. It indexes the data tables; values live there.\n"
    for name in ("parts", "prices", "sources"):
        (OUT / f"{name}.yaml").write_text(head + yaml.safe_dump(cat[name], sort_keys=False, allow_unicode=True, width=200))
    (OUT / "conflicts.md").write_text(conflicts(cat))
    return cat


if __name__ == "__main__":
    c = write()
    print(f"{len(c['parts'])} articles; {sum(len(b['lines']) for b in c['prices'].values())} prices in {len(c['prices'])} price "
          f"source(s); {sum(len(v) for v in c['sources'].values())} documents in {len(c['sources'])} kinds")
