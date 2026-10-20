# Control circuit — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-13).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | company costing sheet (transformers, operator devices), switchgear template (factor 1.5), own switchgear database (MCBs) | done |
| G3 Rules | 5 rules (R-CC-01 … 05) | done |
| G4 Golden | 7 cases (T01–T07) written before the code | done |
| G5 Build | `tests/test_control_circuit.py` | done |
| G6 Verify | transformer factor equals the template cell (scripts/verify_control_power.py); transformer sizes and devices read from the costing sheet rows | done |
