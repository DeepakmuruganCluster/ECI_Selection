# Company feeder kits — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-12).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | company DOL BOM, costing sheet and drawing set (OWN-PROPEL-*), registered with SHA-256 | done (authority OWN) |
| G3 Rules | 5 rules (R-KIT-01 … 05) | done |
| G4 Golden | 12 cases (K01–K12) written before the code | done |
| G5 Build | `tests/test_feeder_kit.py` | done |
| G6 Verify | every kit line equals its workbook row; every DOL kit adds up to the sheet total; costing 160 kW contactors = drawing BOM p.14 | done |

Findings for the owner (decisions on the Review tab):
- The 7.5 kW and 22 kW DOL kits' MPCB ranges don't reach a standard motor's current.
- The Pro-wash sheet's "RED PUSH BUTTON" line carries the green-lamp article XB7EV03MPN.
- The costing sheet and the drawing differ for the 160 kW lube motors.
