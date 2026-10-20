# Panel assembly — G1 Scope

**What it does:** runs a whole load list through the released-or-reviewed components and
collects the result into feeders, a bill of materials, the panel heat and the cooling,
plus a list of **open points** (everything a component refused or warned about).

It holds **no data of its own**. Every article number, rating and loss comes from a
component, which cites its source. The assembly only chains them, counts quantities and
adds heat.

## Inputs

| Field | Unit | Notes |
|---|---|---|
| `load_list` | text | one load per line: `TAG kW STARTER [cable=m] [flc=A] [qty=n] [standby=n] [ph=1|3] [v=V]`; STARTER = DOL, VFD, SS or HEATER |
| `fault_ka` | kA | prospective short-circuit current at the feeders. Required. |
| `panel_internal_c` | °C | design air temperature inside the panel (drives are derated at it; the enclosure must hold it). Required. |
| `motor_pf` | — | running power factor of the motors, for cable voltage drop. Required; no default. |
| `cable_ambient_c` | °C | air or ground temperature along the cable route. Required. |
| `site_ambient_c` | °C | air outside the panel (enclosure heat balance). Optional; without it the cooling is not assessed. |
| `cable_installation`, `cable_make` | | `air` / `ground` / `duct`; `polycab` / `kei` |
| `voltage_v`, `coil`, `ie_class` | | 400 V, contactor coil, motor efficiency class |
| `vfd_protection`, `line_reactor_up_to_kw` | | fuse / msp / breaker; client line-reactor rule |
| `altitude_m`, `enclosure_area_m2` | | for the enclosure component |

## Chain per load line

`HEATER` lines → motor FLC (calculated) → no starter component yet (open point).
`DOL` → motor FLC → DOL starter → cable (overload device = MPCB set at FLC).
`VFD` → motor FLC → VFD → motor cable (overload protection by the drive, Siemens p. 3).
`SS` → motor FLC → soft starter not built yet (open point).

## Not selected (listed on every result until their components exist)

Incomer and busbar (8), soft starters (5), short-circuit level (7: `fault_ka` is an input),
control power and PLC (10), auxiliary switchgear (11), drive control units (CU240E-2).
