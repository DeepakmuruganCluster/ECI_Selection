# Enclosure accessories — G1 Scope

**What it decides:** for one panel (a bayed suite of sections), the Rittal filter fans and outlet filters needed for
the airflow the enclosure component asks for, and whether they fit the doors; the plinth side trim panels for a
requested plinth height; one door-operated switch and one LED light per door. It also hands on the fan load
(W, A at 230 V) for the auxiliary / UPS supply and the light load (A at 24 V DC) for control power.

Sources (all held, registered, PDF page = printed page): Rittal data sheets SK 3239.100 (8 inch filter fan),
SK 3239.200 (its outlet filter), SK 3240.100 (10 inch filter fan), SK 3240.200 (its outlet filter), TS 8601.060 and
TS 8602.060 (side plinth trims 100 / 200 mm), SZ 4127.010 (door-operated switch), SZ 4140.820 (LED light); Rittal TSC
3124300 pp. 8, 12 (fan-and-filter principle). Client: ECI WNS2503 specification p.1 / p.2.

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `required_airflow_m3h` | m³/h | — | from the enclosure component (`fan_airflow_m3h`). Required, ≥ 0 (0: no fans) |
| `doors` | — | — | number of doors (fan positions, lights, switches). Required, ≥ 1 |
| `supply_v`, `frequency_hz` | V, Hz | — | fan supply. Required; only 230 V 50 / 60 Hz held |
| `fans_per_door` | — | 1 | ECI: one fan on each door |
| `fan_size_in` | inch | — | 8 (SK 3239.100) or 10 (SK 3240.100); none → R-ACC-08 picks |
| `outlet_filters_per_fan` | — | 1 | 1 or 2 (the only printed airflows) |
| `site_ambient_c` | °C | — | air drawn in; checked against the fan's operating range |
| `plinth_height_mm`, `enclosure_depth_mm`, `suites` | mm, mm, — | — | plinth request; depth and suites required with a height |
| `section_widths_mm` | mm | — | recorded only (front / rear plinth parts not held) |

## Outputs

`fan`, `fan_size_in`, `outlet_filter`, `airflow_per_fan_m3h`, `fan_qty`, `outlet_filter_qty`, `delivered_airflow_m3h`,
`fan_positions`, `airflow_at_positions_m3h` (only when the doors are not enough), `fan_power_w`, `fan_current_a`,
`fan_noise_dba`, `fan_cutout_mm`, `plinth_side_trim`, `plinth_side_trim_qty`, `door_switch`, `door_switch_qty`,
`door_light`, `door_light_qty`, `light_24vdc_a`.

## In scope (v2.0)

- TopTherm filter fans SK 3239.100 / SK 3240.100, 230 V 1~ 50/60 Hz, with 1 or 2 matching outlet filters, IP 54
- plinth side trim panels 100 / 200 mm for enclosure depth 600 mm
- door-operated switch SZ 4127.010 and LED light SZ 4140.820, one each per door

## Out of scope (refused, or reported as not selected)

- other fan sizes, EC / 24 V / 115 V / 400 V variants, roof-mounted fans, Blue e+ fans above 159 m³/h per unit
- pressure-drop matching against the performance curves (the data sheet's "with outlet filter" figure is used as is)
- IP 55 / 56 (absorber mat, hose-proof hood), EMC versions, pleated filter mats
- plinth heights other than 100 / 200 mm (ECI's 1 ft ≈ 300 mm), plinth corner pieces and front / rear trims
  per section width, baying brackets
- the door switch connection cable, the 24 V power supply for the lights, door count per section width
