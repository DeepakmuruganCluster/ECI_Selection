# DOL starter — G1 Scope

**What it decides:** the motor starter protector (MPCB) and contactor for a
direct-on-line motor feeder, as a Siemens **Type 2** combination, plus the link
module that joins them.

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `flc_a` | A | — | design full-load current, normally from component 1 (motor FLC) |
| `flc_basis` | — | — | `nameplate`, `datasheet`, `guide`, `guide_voltage_scaled`, `calculated`. Missing → warning. |
| `ie_class` | — | IE3 | `IE1` … `IE4`. Missing → IE3 limits (the lower ones) with an info note. |
| `fault_ka` | kA | — | prospective short-circuit current at the starter. **Required.** |
| `starting_current_a` | A | — | motor locked-rotor current. Only needed for the two table rows with a starting-current limit. |
| `phases`, `voltage_v`, `load_type` | | 3, 400, motor | scope checks |
| `coil` | — | 230VAC | contactor coil voltage |

## Outputs

`mpcb` (article no.), `setting_range_a`, `contactor` (article no.), `size`,
`link_module` (article no. or none), `iq_ka`. Every check carries its rule id and
source page.

## In scope (v2.0)

- 3-phase motors at **400 V AC**, CLASS 10, Type 2, Iq 150 kA: SIRIUS manual 09/2017, pp. 28–29
- 3RV2 + 3RT2 combinations, FLC 0.11 … 100 A
- contactor coil **230 V AC 50 Hz** (the coil the table's article numbers carry, footnote 2)
- screw-terminal link modules: Table 2-1, p. 22

## Out of scope (returns `cannot_select`)

- other coil voltages, e.g. **24 V DC (ECI's choice)**: the coil codes are not in a held source → needs Siemens catalogue IC 10 or the contactor data sheets (G2)
- FLC > 100 A (3VA circuit breaker + 3RT1 rows on p. 29): this will be a separate component after the MCCB
- voltages other than 400 V, 1-phase loads, heaters (resistive loads are switched under AC-1, not with the motor table)
- Type 1 coordination (pp. 25–27), spring-loaded / hybrid terminals, soft starters and solid-state contactors
