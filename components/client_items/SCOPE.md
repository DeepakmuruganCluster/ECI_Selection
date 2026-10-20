# Client-specified items — G1 Scope

**What it does:** puts every item ECI's specification names directly (CPU, SITOPs, incomer,
busbar size, energy meter, UPS, switches, tower lamps, enclosure sizes, plinth, …) into the BOM
**exactly as written**, with the page it comes from. Each item names the engineering component
that must check it (e.g. the incomer is checked by component 8). Quantities the spec does not
state, and quantities we had to interpret, are open points for ECI.

It also checks the spec's own arithmetic (I/O sums, section widths vs panel length).

Source: ECI WNS2503 Automation_Rittal Panel Specification Rev02 (pages 1–2), stored as `ECI-WNS2503-AUTO`.

Inputs: `panel` (BIO_UF, RO or all), `include_plant` (plant-wide items such as SCADA PC, UPS, switches).
Out of scope: anything the spec does not name. Those items come from the engineering components.
