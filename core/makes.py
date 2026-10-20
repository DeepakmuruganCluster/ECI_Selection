"""The make (manufacturer) of every BOM line.

The component that chooses a part knows its make and records it on the line (cable make, wiring make, supply brand,
CT make, company-kit item make …). For a line without one, in this order:
  1. the parts catalog (data/catalog/parts.yaml): the makes of the maker tables the article is printed in;
  2. a company-kit line: the kit's own make column, carried in its description "(MAKE, company kit)" / "(MAKE)";
  3. the manufacturer document cited first in the line's source (its publisher in sources/register.yaml);
  4. a Siemens article number (MLFB) — every such article in a BOM comes from a Siemens document;
  5. otherwise none: shown as "—" (make not recorded), never guessed.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .bom_edit import catalog, key
from .provenance import register

SIEMENS = re.compile(r"^(?:3R[TVWAHU]|3V[AM]|3N[AE]|3SU|3SB|3KD|3LD|5S[LYDVTU]|5TT|6SL|6ES|6EP|6AV|7KM|7UG|7KT|3UG|8WA|3TF)\d")


KIT_MAKE = re.compile(r"\(([A-Z][A-Z&./\- ]{1,40}?)(?:, company kit)?\)\s*$")   # "(SCHNEIDER, company kit)", "(REPUTED)", "(A/B/C)"


@lru_cache(maxsize=None)
def _publishers() -> dict:
    """Manufacturer documents only (not client, own or standards): ref → maker."""
    return {k: v["publisher"].replace(" AG", "") for k, v in register().items()
            if str(v.get("kind", "")).startswith("manufacturer") and v.get("publisher")}


def make_of(line: dict) -> str | None:
    if line.get("make"):
        return line["make"]
    art = str(line.get("article") or "")
    if not art:
        return None
    part = catalog().get(key(art))
    if part and part.get("make"):
        return ", ".join(part["make"])
    m = KIT_MAKE.search(str(line.get("description") or ""))
    if m:
        mk = m.group(1).strip()
        if "/" in mk:                     # the costing sheet names several makes: any of them (the owner's choice)
            return "Not fixed (" + " / ".join(x.strip() for x in mk.split("/")) + ")"
        return "Not fixed (any reputed make)" if mk == "REPUTED" else mk if len(mk) <= 3 else mk.title()
    pub = _publishers().get(str(line.get("source") or "").split(" ")[0])
    if pub:
        return pub
    if SIEMENS.match(art.upper().replace(" ", "")):
        return "Siemens"
    return None


def fill(bom: list[dict]) -> list[dict]:
    """Set 'make' on every line that has an article (in place); returns the list."""
    for b in bom:
        if b.get("article"):
            b["make"] = make_of(b)
        else:
            b.setdefault("make", None)
    return bom
