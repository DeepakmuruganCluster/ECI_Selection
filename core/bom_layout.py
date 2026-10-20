"""How a BOM is organised for people: sections in build order, groups inside them (page and Excel use the same order).

Incoming supply → motor feeders → cables and wiring → control and automation → control circuit → client / project
items → added by the designer → not selected / out of scope. Lines keep their order inside a group.
"""
from __future__ import annotations

SECTIONS = [
    ("Incoming supply and protection", ["Incomer", "Busbar", "Metering", "Auxiliary switchgear"]),
    ("Motor feeders", ["Feeders", "Feeder accessories"]),
    ("Cables and wiring", ["Motor cables", "Cables", "Internal wiring"]),
    ("Control and automation", ["PLC", "Control power", "Control and signalling", "Instruments"]),
    ("Control circuit", ["Control circuit"]),
    ("Other panel items (template)", ["Template items"]),
    ("Client and project items", []),
    ("Added by the designer", ["Added by designer"]),
    ("Not selected / out of scope", ["Not selected", "Out of scope"]),
]
_GROUP = {g: (i, j) for i, (_, gs) in enumerate(SECTIONS) for j, g in enumerate(gs)}
_OTHER = 6          # any other group (client items, plant items …) sits in "Client and project items"


def section_of(group: str) -> str:
    return SECTIONS[_GROUP.get(group, (_OTHER, 0))[0]][0]


def ordered(bom: list[dict]) -> list[dict]:
    """The lines sorted by section, then group (as listed, unknown groups by name), keeping their order inside."""
    first = {}
    for i, b in enumerate(bom):
        first.setdefault(b.get("group", ""), i)
    def k(ib):
        i, b = ib
        g = b.get("group", "")
        s, j = _GROUP.get(g, (_OTHER, 99))
        return (s, j, g if j == 99 else "", first[g], i)
    return [b for _, b in sorted(enumerate(bom), key=k)]
