# Client-specified items — G3 Rule sheet

Machine-readable: `rules.yaml`. Data: `data/eci_wns2503_items.yaml` (44 lines + the I/O table, ECI spec pages 1–2).

| Id | Rule | Authority |
|---|---|---|
| R-CLI-01 | listed exactly as written; missing quantity → open point | CLIENT |
| R-CLI-02 | interpreted quantity → confirm with the client | RULE |
| R-CLI-03 | each item names the component that must check it | RULE |
| R-CLI-04 | the spec's own arithmetic must hold (I/O sums, section widths) | PHYS |
| R-CLI-05 | spare I/O reported as % (no minimum imposed) | RULE |
