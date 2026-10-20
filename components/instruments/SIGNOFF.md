# Field devices — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-13).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | ECI-WNS2503-EQUIP (field-device rows), company costing sheet (fused terminals), own switchgear database (MCBs) | done |
| G3 Rules | 6 rules (R-INS-01 … 06) | done |
| G4 Golden | 4 cases (N01–N04) written before the code | done |
| G5 Build | `tests/test_instruments.py` | done |
| G6 Verify | motor + field-device I/O reproduces the client's required I/O for both panels (tests/test_instruments.py) | done |
