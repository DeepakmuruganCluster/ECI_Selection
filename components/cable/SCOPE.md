# Cable — G1 Scope

**What it decides:** the smallest copper XLPE armoured 0.6/1 kV cable (IS 7098-1) for a
motor or feeder circuit: size, number of parallel runs, cores, current rating Iz after
the maker's correction factors, voltage drop, and which check bound the choice.

Sources (both held): Polycab LT cable catalogue v9 (`POLYCAB-LT-V9`, primary, default make)
and KEI technical handbook 2023 (`KEI-TH-2023`, second make). Ratings, factors, resistance,
reactance and short-circuit rating all come from the **one make asked for** — never mixed.
Page numbers are PDF pages. Polycab prints the same number. KEI prints two book pages per
PDF page: left half = 2·p − 3, right half = 2·p − 2 (no single `printed_page_offset`).

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `ib_a` | A | — | design current (motor FLC from component 1) |
| `in_a` | A | — | rated / set current of the overload protective device (required if `overload_device`) |
| `overload_device` | — | true | false when the device does not protect the cable against overload (e.g. VFD protects the motor cable) |
| `length_m` | m | — | route length |
| `voltage_v` | V | — | line-line (3-phase) or line-neutral (single-phase) |
| `pf_run` | — | — | running cos φ (no default) |
| `installation` | — | — | `air`, `ground` (buried direct) or `duct` (single-way buried duct) |
| `ambient_c` | °C | — | air temperature (air) or ground temperature (ground / duct) |
| `phases` | — | 3 | 3 → cores `3` / `3.5` / `4`; 1 → cores `2` |
| `cores` | — | 3 (3-ph), 2 (1-ph) | |
| `make` | — | polycab | `polycab` or `kei` |
| `other_cables` | — | 0 | other loaded cables in the same group |
| `group_spacing` | mm | — | `touching` / `150` / `300` / `450` (KEI buried-direct groups only) |
| `depth_mm`, `soil_kmw` | | basis | other than 750 mm / 1.5 K.m/W → refused |
| `vd_limit_pct` | % | 5 (RULE) | project limit, running |
| `start_multiple`, `pf_start` | — | — | optional DOL starting check, both or neither |
| `fault_ka` + `clearing_s`, or `i2t_a2s` | | — | optional short-circuit withstand |

## Outputs

`cable`, `make`, `cores`, `size_mm2`, `runs`, `iz_a`, `k_temp`, `k_group`, `vd_pct`,
`vd_start_pct`, `isc1_ka` (1-s rating of the chosen size), `bound_by`.

## In scope (v2.0)

- Cu XLPE, galvanised-steel round-wire armoured multi-core (Polycab 2XWY; KEI wire armoured), 2 / 3 / 3.5 / 4 core, 4 … 400 mm² as each maker lists them
- system voltage ≤ 1100 V AC, 50 Hz; 3-phase and single-phase
- in air (40 °C basis), buried direct and single-way duct (30 °C ground, 1.5 K.m/W, 750 mm)
- temperature factors as tabulated: Polycab air 25–60 °C, ground/duct 15–50 °C; KEI air 25–55 °C, ground/duct 15–50 °C
- grouping only where the maker tabulates it: KEI multi-core buried direct, 2–6 cables

## Out of scope (refused)

- cable trays, ladders, conduit, trenches; any grouping in air or duct; any grouping with Polycab (no factors printed)
- aluminium conductor; single-core cables; unarmoured and strip-armoured types; 60 Hz; > 1100 V
- laying depth or soil resistivity other than the rating basis (KEI p.33 Table 4 depth factors not used)
- harmonic / VFD-output derating, cable protective-conductor sizing and earth-fault loop (later components)
