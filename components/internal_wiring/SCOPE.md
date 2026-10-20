# Internal wiring — G1 Scope

**What it decides:** the minimum cross section of one power or control connection wired
inside the panel (Lapp wire, as the client asks), its current rating Iz after Lapp's
correction factors, the factors used and which check bound the size.

Client requirement: ECI WNS2503 — "LAP Cable Internal Wiring" (`ECI-WNS2503-AUTO` p.1).
Source (held): Lapp Cable Guide "Power Rating" (`LAPP-POWER`), extracts of DIN VDE 0298-4:2003-08.
Page numbers are PDF pages. The PDF has 8 pages, each a spread of two printed pages:
printed = 2·p + 142 (left half) / 2·p + 143 (right half) — no single offset; every data row
carries its `printed` page.

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `ib_a` | A | — | design current of the connection |
| `in_a` | A | — | rated / set current of the protective device (required if `overload_device`) |
| `overload_device` | — | true | false when the device does not protect the wiring against overload (aR fuse, drive output) |
| `ambient_c` | °C | — | air temperature **inside the panel** around the wiring. Required. |
| `insulation` | — | — | rated conductor temperature from the Lapp product page: `60` `70` `80` `85` `90` (Table 12-2) or heat-resistant `heat_90` (H07V2-K / H07Z-K 90 °C), `heat_110`, `heat_145`, `heat_180` (Table 12-4). Required, no default. |
| `conductor_type` | — | single | `single` (Table 12-1 column A) or `multi` (column C) |
| `installation` | — | duct | `duct` (wiring duct / conduit, bunched), `surface` (bunched on the plate), `air_spaced` (single cores ≥ d apart) |
| `circuit` | — | 3ac | `3ac`, `1ac`, `dc` (footnote-3 factor; loaded conductors 3 / 2) |
| `circuits` | — | — | circuits (single cores) or cables (multicore) bunched together, incl. this one. Required for duct / surface. |
| `loaded_cores` | — | 3 / 2 | multicore only; > 3 → Table 12-3 (≤ 10 mm²) |
| `min_size_mm2` | mm² | — | project minimum size (designer / client spec) |

## Outputs

`wire`, `size_mm2`, `iz_a`, `i_table_a`, `k_temp`, `k_bundle`, `k_group`, `k_cores`, `bound_by`
(`ampacity` / `smallest size offered` / `project minimum size`).

## In scope (v1.0)

- Lapp category A single cores (H05V-K, H07V-K, H07V2-K, H07Z-K, LiY, …) and category C multicore (ÖLFLEX) — Table 12-1 at 30 °C
- in a wiring duct or bunched on the plate (Table 12-6 row 1, 1 … 20 circuits; single cores × footnote 3 first); single cores free in air spaced ≥ d
- ambient: Table 12-2 (10 … 85 °C, by rated conductor temperature) or Table 12-4 (heat-resistant, up to 175 °C)
- 3~AC, 1~AC and DC circuits; control wiring (e.g. 24 V DC I/O) with the same tables, sizes from 0.5 mm²

## Out of scope (refused or reported)

- cable trays (Tables 12-7 / 12-8), wires touching free in air (footnote 3 → Table 12-8 = trays), ceilings, one-layer rows; multicore free in air
- category B cords, category D / Table 12-9 rubber, Table 12-10 welding, Table 13 NEC / AWG; spooled cables (Table 12-5)
- parallel conductors; sizes below 0.5 mm² (VDE 0891-1 telecom ratings)
- not checked (no source): voltage drop, short-circuit withstand (incl. unprotected conductors ahead of the device),
  mechanical minimum sizes (IEC 60204-1 / IEC 61439-1), colours, quantity of wire in metres (decision W-5)
