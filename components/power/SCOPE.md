# Power calculation — G1 Scope

Adds up the panel's consumption from the selections; holds no data of its own.

- **AC, 3-phase:** running units × current per phase (drive input current from the PM240-2 data, motor FLC otherwise);
  standby units are not counted.
- **AC, single-phase:** line–neutral loads I = VA / U_LN, line–line loads I = VA / U_LL on both lines (the control
  transformer's 415 V primary), the 24 V supply input 24 V × load / efficiency; placed largest first on the
  least-loaded phase (decision PWR-2). Output: I_L1, I_L2, I_L3, imbalance, neutral current (same power factor assumed),
  S = U_LN × ΣI.
- **DC 24 V:** every load line with its source, × template factor, against the supply.
- **Not in scope:** motor electrical input power in kW (needs efficiency and power factor: rated output listed instead),
  harmonics, inrush and voltage drop, loads without data (listed as not counted).
