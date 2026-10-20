# Control and signalling — G1 Scope

**What it decides:** for the PLC digital outputs of a panel, the interface relays (a **latching
relay** for each DOL starter output and a **slim relay** for every other output, as ECI requires),
the number of PLC outputs that this needs, the relay accessories (jumper links, separators,
markers, end clamps); the **screwless terminal blocks** for I/O and power wiring with their end
plates, end clamps, marker cards and **distribution short links** (jumpers); and the **Rittal
door-operated switch and LED panel light** per door.

Client requirement (ECI WNS2503, `ECI-WNS2503-AUTO` p.1): "DOL output need to use Latch Relay and
Other Outputs slim Relay - Phoenix/Finder"; "Phoenix or Connectwell Screw less Connectors and
Phoenix/Connectwell Distribution short link Connectors"; "Rittal Door limit switch and Light".
PLC outputs are 24 V DC (ET 200SP DQ).

## Sources (all held, registered; page = PDF page)

| Ref | Document | Printed page |
|---|---|---|
| FINDER-S38 | Series 38 relay interface modules (I-2026) | PDF − 4 (PDF 18 = printed 14) |
| FINDER-S39 | Series 39 MasterINTERFACE (III-2026) | = PDF |
| FINDER-S13 | Series 13 electronic step relays (IX-2026) | = PDF |
| FINDER-S40 | Series 40 PCB/plug-in relays (VIII-2026) — rejected bistable candidate | = PDF |
| FINDER-S20 | Series 20 modular step relays (IV-2026) — rejected step-relay candidate | = PDF |
| CW-ES-2526 | Connectwell Electronic Solutions Catalogue 25-26 | PDF − 3 (PDF 44 = printed 41) |
| CW-TB-2526 | Connectwell Terminal Blocks Catalogue 25-26 | PDF − 3 (PDF 297 = printed 294) |
| RITTAL-4127010 | SZ 4127.010 door-operated switch data sheet | = PDF |
| RITTAL-4140820 | SZ 4140.820 LED compact system light data sheet | = PDF |

## What the sources say about a 24 V DC latching relay (checked carefully)

- **Finder 13.12.0.024.0000** "Call & Reset relay 12 V or 24 V AC/DC, 2 pole" (S13 pp. 5, 7, 8, 11):
  the output closes on a momentary SET input and opens only on a momentary RESET input. 1 CO + 1 NO,
  8 A, AC15 400 VA, 17.5 mm, DIN rail, −10 … +60 °C. SET/RESET impulse 100 ms … 10 s. **The only
  set/reset latching relay in the held catalogues** → used for DOL outputs. It needs **two PLC
  outputs per DOL** (SET and RESET).
- Finder 13.01 "step relay (bistable)" and the 20 series step relays toggle on every impulse; the PLC
  cannot command a known state, and the 20 series coil is limited to 1 h → rejected.
- Finder 40.xx.6 bistable (single coil): in DC operation the reset reverses the coil current through
  RDC with a two-pole reset switch (S40 p.10) — not drivable from one sourcing PLC output; the full
  code is not printed (assembled from the scheme, p.5) → rejected.
- Finder 38 / 39: no bistable or latching version.
- **Connectwell (CW-ES-2526): no latching relay at all** (only "Long Latch IDC connectors").

## Inputs

| Field | Default | Notes |
|---|---|---|
| `dol_outputs` | 0 | DOL starters driven through a latching relay |
| `other_outputs` | 0 | other digital outputs (one slim relay each) |
| `coil_v_dc` | 24 | only 24 V DC is in scope |
| `relay_make` | finder | finder · connectwell · phoenix (not held → refused) |
| `latch_make` | = relay_make | lets the slim relays be Connectwell while the latching relays are Finder |
| `finder_series` | "38" | "38" (38.61/38.51) or "39" (MasterBASIC 39.01/39.11) |
| `relay_connection` | screwless | screwless (push-in / spring) or screw (box clamp) |
| `relay_groups` | 1 | separate rows of slim relays (separators, jumpers, end clamps per group) |
| `spare_pct` | 0 | spare relays (owner decision C-3) |
| `contact_v`, `contact_a`, `contact_load` | — | load switched by the relay contact: ac1 · ac15 · dc1 · dc13 |
| `panel_internal_c` | — | air inside the panel (relay ambient check) |
| `do_available` | — | the client's DO count, to check the outputs needed |
| `terminal_make` | connectwell | connectwell · phoenix (not held → refused) |
| `io_terminals`, `io_conductor_mm2` | 0, — | I/O terminals and their conductor size |
| `conductor_type` | ferrule | flex · solid · ferrule |
| `jumper_groups` | — | list of commoned I/O terminal group sizes, e.g. [10, 25] |
| `power_terminals` | — | list of {mm2, count, a} (conductor size, number of terminals, circuit current) |
| `terminal_strips` | one per type | number of separate terminal assemblies |
| `doors` | 0 | panel doors (door switch + light each) |

## Outputs

Relays: `latch_relay`, `latch_relay_qty`, `slim_relay`, `slim_relay_qty`, `slim_jumper`(_qty),
`slim_separator`(_qty), `slim_marker`(_qty), `slim_end_clamp`(_qty), `slim_coil_ma`, `do_needed`.
Terminals: `terminals`, `terminal_qty`, `end_plates`, `end_plate_qty`, `end_clamp`, `end_clamp_qty`,
`markers`, `marker_cards`, `jumpers`, `jumper_qty`. Rittal: `door_switch`(_qty), `light`(_qty),
`light_current_a`, `light_rows_min`. `bom`: every line with its source page.

## Out of scope

- **Phoenix Contact** relays, terminals and jumpers: data sheets not held yet (refused). The data
  files are per source, so a `phoenix_*.yaml` can be added with the same row kinds.
- Tower lamp with buzzer (Schneider), contactor coil suppressors (need IC 10 / 3RT accessories),
  distribution blocks, earth (PE) terminals (component 17), CX spring-clamp and CY/CTS screw terminals.
- Relay coil voltages other than 24 V DC; SSR and timer modules; Finder 38 14 mm 16 A / 2 pole.
- Contact-side jumpering of relays (only the coil common A2 is jumpered).
- Rail length, PLC output current, coil inrush of contactors (needs the contactor data).
