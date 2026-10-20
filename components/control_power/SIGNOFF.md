# Control power (24 V DC supply) — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-12).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | own switchgear database from v1 (OWN-SWG-*), registered with SHA-256; no manufacturer document behind it | done (authority OWN) |
| G3 Rules | 5 rules (R-CP-01 … 05) in `rules.yaml` | done |
| G4 Golden | 6 cases (C01–C06) written before the code | done |
| G5 Build | `tests/test_control_power.py` | done |
| G6 Verify | SMPS rows equal SMPS.csv; template values equal the .xls cells (scripts/verify_control_power.py) | done |

Decisions for the owner are on the Review tab.
