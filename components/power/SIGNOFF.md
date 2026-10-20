# Power calculation — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G5 2026-10-15).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Sources | none of its own: the loads carry their sources (drive data, IC 10 coil power, supply efficiency, company template) | done |
| G3 Rules | `rules.yaml` R-PWR-01 … 09; decisions PWR-2 … PWR-4 open | done |
| G4 Golden | `golden/cases.yaml` W01 … W10 written before the code (hand calculation) | done |
| G5 Build | `select.py`, `tests/test_power.py`; used by the requirement (R-REQ-23) and the project (R-PRJ-15) | 10/10 cases pass |
