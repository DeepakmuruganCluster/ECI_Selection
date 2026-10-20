# Motor FLC — G3 Rule sheet

Machine-readable version: `rules.yaml` (same ids). Data: `data/siemens_guide_400v_4p.yaml`.

## Decision flow

```
load_type = heater ──────────────► R-FLC-04  I = P/(√3·U) or P/U          basis: calculated
nameplate_flc_a given ───────────► R-FLC-01  use it                       basis: nameplate | datasheet
                                    └ checks R-FLC-06 (vs guide), R-FLC-07 (vs η·cos φ)
otherwise (guide value):
   phases ≠ 3, poles ≠ 4, f ≠ 50 ─► R-FLC-02  cannot select
   kW not in table ──────────────► R-FLC-03  cannot select
   U = 400 V ────────────────────► R-FLC-02  table value                   basis: guide
   |U − 400| ≤ 5 % ──────────────► R-FLC-05  I_400 × 400/U                 basis: guide_voltage_scaled (warning)
   otherwise ────────────────────► R-FLC-05  cannot select
always: R-FLC-08 client value vs design value (report only)
```

## Rules

| Id | Rule | Authority | Why |
|---|---|---|---|
| R-FLC-01 | nameplate / data sheet > guide value; the client list value is never used | RULE | The guide value is explicitly "not the motor's data" (manual p. 29, footnote 1). Client lists are often formula-derived (e.g. 1.9 × kW). |
| R-FLC-02 | The guide value only for 3-ph, 4-pole, 50 Hz, 400 V | MFR | the conditions stated by the table itself |
| R-FLC-03 | no interpolation / extrapolation | RULE | An interpolated value has no source. 3.7 kW and 9.3 kW motors need their nameplate. |
| R-FLC-04 | P/(√3·U), P/U for heaters | PHYS | definition of power at cos φ = 1 |
| R-FLC-05 | ±5 % voltage scaling | RULE | At constant shaft power, η and cos φ change little within ±5 %, so I ∝ 1/U. This is an approximation and is marked as such. |
| R-FLC-06 | nameplate vs guide > 15 % → warning | RULE | catches typing errors (kW vs A, wrong row) without overruling a real motor |
| R-FLC-07 | nameplate vs η·cos φ formula > 5 % → warning | PHYS + RULE | the three nameplate numbers must agree |
| R-FLC-08 | client vs design > 10 % → warning | RULE | same tolerance v1 Layer 0 used |

## Decisions for the sign-off owner

- **D-1** Is ±5 % voltage scaling (R-FLC-05) acceptable, or 400 V only (`voltage_window_pct: 0`)?
- **D-2** Should IS 325 ratings (3.7 kW, 9.3 kW) stay out of scope until a motor maker's table is sourced?
- **D-3** Is a guide value acceptable for **ordering**, or only for preliminary selection, with the nameplate required before issue?
- **D-4** Are the warning thresholds 15 / 5 / 10 % right?
