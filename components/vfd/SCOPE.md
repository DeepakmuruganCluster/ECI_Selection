# VFD — G1 Scope

**What it decides:** the SINAMICS G120 PM240-2 power module for a motor, derated
for the air temperature around the drive. It also picks the line reactor, any
output reactor(s) for the cable length, and the IEC fuse Siemens specifies.

Source: Siemens PM240-2 Hardware Installation Manual 07/2022 (held). Page numbers
are PDF pages; the printed page number is 2 lower.

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `kw` | kW | — | motor rated power |
| `flc_a` | A | — | motor full-load current (component 1) |
| `flc_basis` | — | — | as for the DOL starter; guide/unknown → warning |
| `duty` | — | normal | `normal` → LO rating, `heavy` → HO rating |
| `ambient_c` | °C | — | **air temperature around the drive** (inside the panel). Required. |
| `altitude_m` | m | 1000 | installation altitude |
| `voltage_v` | V | 400 | line voltage, 3-phase |
| `cable_m` | m | — | motor cable length. Required. |
| `cable_shielded` | — | true | shielded (screened) motor cable |
| `emc_filter` | — | none | `none` (unfiltered drive) or `C2` (integrated C2 filter) |
| `fault_ka` | kA | — | prospective short-circuit current at the drive. Required. |
| `network_uk_pct` | % | — | supply impedance (decides the line reactor for FSA–FSC) |
| `client_line_reactor_up_to_kw` | kW | — | client rule, e.g. ECI: line reactor for drives ≤ 15 kW |
| `protection` | — | fuse | `fuse`, `msp` (motor starter protector) or `breaker` — only devices Siemens lists for the drive |
| `preferred_family` | — | — | e.g. `3VA`, `3RV2`; a family Siemens doesn't list for the drive is refused (e.g. 3VM) |
| `earthing` | — | TN | TN, TT or IT (MSP ratings only valid for TN / TT) |

## Outputs

`power_module` (article no.), `frame`, `rating`, `output_a_derated`, `fuse`,
`line_reactor`, `output_reactor` + `output_reactor_qty`, `protection_device` + ICC, `min_enclosure_m3`, `loss_w`, `cooling_air_ls`.

Second source: Siemens Product Information "Protective Devices for SINAMICS G120 PM240-2" 07/2021 (fuses p. 5, motor starter protectors p. 11, circuit breakers p. 14).

## In scope (v2.0)

- PM240-2 IP20, 380–480 V 3 AC, FSA–FSF (0.55–132 kW LO), unfiltered or with integrated C2 filter
- installation altitude ≤ 1000 m, ambient 20–60 °C around the drive, factory pulse frequency
- line reactors (Table 8-4), output reactors (Tables 8-11, 8-15), IEC fuses (Tables 6-15 … 6-28)

## Out of scope (refused, or reported as not selected)

- Control Unit (CU240E-2) and operator panel: order number and temperature limit not in a held source; reported as "not selected"
- FSG (160–250 kW), 200 V and 690 V drives, push-through (PT) versions, external C1 filters, sine-wave / dU/dt filters
- altitude > 1000 m, non-factory pulse frequencies, single-phase supply
