# Soft starter — G1 Scope

**What it decides:** the Siemens SIRIUS **3RW52** General Performance soft starter for a 3-phase motor, its
setting (rated motor current IM), the short-circuit protective device Siemens tested with it (type of
coordination 1 or 2) and, where Siemens recommends it, the optional line contactor.

## Source

Catalog IC 10 · 2026 (SIE-IC10-2026, stored PDF), chapter 6 "SIRIUS 3RW soft starters":
- p. 6/8 constraints (select on motor current; kW are guide values), p. 6/12 motor feeders with soft starters
  (type of coordination, fuseless only Class 10, line contactor), p. 6/13 ambient −25 … +60 °C, article scheme
- pp. 6/59–6/62 general data → `data/makers/siemens/ic10_3rw52_ratings.yaml`
- pp. 6/63–6/65 motor feeders according to IEC → `ic10_3rw52_coordination.yaml`
- pp. 6/67–6/70 selection and ordering data, standard (inline) circuit → `ic10_3rw52_ordering.yaml`
Importer: `scripts/import_ic10_3rw52.py`. The equipment manual (SIE-3RW52-MAN) refers technical data to SIOS;
the catalogue holds every value used here.

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `flc_a` | A | — | motor full-load current (component 1). **Required.** |
| `flc_basis` | — | — | as DOL; guide value or missing → warning |
| `fault_ka` | kA | — | prospective short-circuit current. **Required.** |
| `ambient_c` | °C | — | temperature around the soft starter (inside the panel). **Required.** |
| `duty` / `starting_class` | — | — | normal → Class 10A, heavy → Class 20E (decision SS-1); `starting_class` 10A / 10E / 20E overrides |
| `voltage_v` | V | 400 | 200 … 480 V (version ..4); 481 … 600 V (version ..5) |
| `protection` | — | auto | `mpcb` (Type 1, 3RV2 / 3VA), `fuse_gg` (Type 1, 3NA3), `fuse_semi` (Type 2, 3NE1); auto = decision SS-2 |
| `line_contactor` | — | auto | auto = decision SS-3 |
| `control_supply` | — | 230VAC | `230VAC` (110 … 250 V AC version) or `24V` (24 V AC/DC version) |
| `thermistor` | — | false | thermistor motor protection version instead of the analog output version |
| `terminals` | — | screw | control terminals: `screw` or `spring` |
| `starts_per_hour`, `start_current_pct`, `start_time_s` | | — | optional starting-frequency check (all three) |
| `circuit`, `phases`, `altitude_m` | | inline, 3, — | scope checks |

## Outputs

`soft_starter` (article), `type`, `ie_a`, `im_rated_a` (IM for the class at the ambient column), `set_im_a`,
`starting_class`, `column_c`, `protection_device`, `protection_qty`, `coordination`, `iq_ka`, `line_contactor`,
`kw_400v_guide`, `bom`. Every check carries its rule and page.

## Out of scope (cannot select)

- inside-delta circuit (ratings imported; ordering and fuse tables for it not yet built), other soft starter
  families (3RW30/40/50/55), 1-phase loads, heaters
- operational voltage below 200 V or above 600 V; ambient above 60 °C; altitude above 1 000 m (derating curve
  p. 6/8 not transcribed)
- aR partial-range fuses (p. 6/66), fuse bases and the line contactor's coil version (not in these tables: open point)
- power loss (not printed in IC 10 for the 3RW52: the panel heat stays incomplete, warning)
