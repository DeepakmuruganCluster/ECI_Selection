# Motor FLC — G1 Scope

**What it decides:** the design full-load current (FLC) of one load, and how
trustworthy that number is (`basis`).

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `kw` | kW | — | rated output (motor) or rated power (heater), > 0 |
| `load_type` | — | `motor` | `motor` or `heater` (resistive, cos φ = 1) |
| `phases` | — | 3 | 3 or 1 |
| `voltage_v` | V | 400 | line-line for 3-phase, line-neutral for 1-phase |
| `frequency_hz` | Hz | 50 | |
| `poles` | — | 4 | motor pole count |
| `nameplate_flc_a` | A | — | rated current from the motor nameplate or the maker's data sheet |
| `nameplate_source` | — | `nameplate` | `nameplate` or `datasheet` (what the value was read from) |
| `efficiency_pct`, `power_factor` | %, — | — | optional nameplate data, used only to cross-check `nameplate_flc_a` |
| `client_flc_a` | A | — | the value in the client's load list; **checked, never used** |

## Outputs

`flc_a` (or none), `basis`, `status` (`ok` / `warning` / `cannot_select`), a list of
checks (rule id, requirement, value, verdict, source) and a readable trace.

| basis | Meaning |
|---|---|
| `nameplate` / `datasheet` | the motor's own rated current, entered by the designer |
| `guide` | Siemens guide value, 4-pole, 400 V, 50 Hz |
| `guide_voltage_scaled` | guide value converted to a nearby voltage (rule R-FLC-05) |
| `calculated` | resistive load, P / (√3·U) or P / U |
| `none` | no value can be given with the data held → `cannot_select` |

## In scope (v2.0)

- 3-phase, 4-pole, 50 Hz induction motors, 0.04–250 kW, at 400 V (380–420 V with rule R-FLC-05)
- any motor with a nameplate or data-sheet current
- resistive heaters, 1- and 3-phase, any voltage

## Out of scope (returns `cannot_select` unless a nameplate value is given)

- 2-, 6- and 8-pole motors
- single-phase motors
- 60 Hz; voltages outside 380–420 V (e.g. 690 V, 230 V 3-phase)
- kW ratings not in the Siemens table (e.g. IS 325 ratings 3.7 kW, 9.3 kW): **no interpolation**
- motors above 250 kW, DC motors, slip-ring motors

Each of these comes back into scope only by adding a sourced table (G2) and test
cases (G4) for it.
