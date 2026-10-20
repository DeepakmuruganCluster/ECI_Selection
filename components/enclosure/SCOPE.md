# Enclosure heat balance and cooling — G1 Scope

**What it decides:** for one enclosure (or a bayed suite treated as one), whether the heat loss inside
can leave through the walls on its own, and if not the fan-and-filter airflow (m³/h) or the cooling-unit
output (W) Rittal's method asks for; also the air/air heat exchanger output (W/K) and the smallest listed
Rittal model.

Source: Rittal Technical System Catalogue "Cooling with ambient air" 3124300 EN (held). Page numbers are PDF
pages; the number printed on each page is the same (no offset). Cross-check: Siemens PM240-2 manual,
section 3.3 (PDF p. 34, printed 32).

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `heat_loss_w` | W | — | total heat loss inside (Q̇v). Required. Later fed from component outputs, e.g. VFD `loss_w` + 40 W per Control Unit |
| `ambient_c` | °C | — | maximum ambient temperature around the enclosure (Tu). Required |
| `max_internal_c` | °C | — | maximum permitted internal temperature (Ti). Required |
| `altitude_m` | m | — | site altitude. Required (decides f) |
| `siting` | — | — | `indoor` / `outdoor`. Required; outdoor is refused |
| `area_m2` | m² | — | effective surface area A to IEC TR 60890, calculated by the designer (R-ENC-03) |
| `material` | — | — | required with `area_m2`; only `sheet_steel` has a k value |
| `sections` | — | — | list of {width_mm, height_mm, depth_mm, installation}: recorded; **without `area_m2` refused** (R-ENC-02) |

## Outputs

`method` (passive / fan / cooling_unit), `passive` (yes / no / not assessed), `k_w_m2k`, `area_m2`,
`delta_t_natural_k`, `internal_natural_c`, `surface_w`, `altitude_factor`, `fan_airflow_m3h`, `fan_airflow_ls`,
`siemens_airflow_ls`, `heat_exchanger_w_per_k`, `heat_exchanger`, `cooling_unit_w`.

## In scope (v2.0)

- sheet-steel enclosures, indoor siting, site altitude 0 … 1000 m
- natural convection (p. 13), fan-and-filter airflow (p. 12), air/air heat exchanger (p. 26), cooling unit (p. 30)
- heat-exchanger model selection (6 models with printed W/K, p. 26)

## Out of scope (refused, or reported as not selected)

- **effective surface area from sizes and installation type** (free-standing, wall-mounted, end / middle of a suite …):
  the catalogue names IEC 890 but does not print its formulas; IEC TR 60890 not held → refused
- stainless steel, aluminium, plastic enclosures (no k printed); outdoor siting (sun, wind); altitude > 1000 m
- fan-and-filter and cooling-unit **models**: the catalogue gives ranges only (20 – 1160 m³/h, 0.3 – 5.8 kW), no per-model ratings
- fan pressure-drop matching (performance diagrams pp. 12), heaters (p. 52), condensate (p. 30), air/water heat exchangers
- internal hot spots, air routing, filter clogging
