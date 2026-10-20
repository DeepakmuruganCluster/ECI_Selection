# Auxiliary switchgear — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-12).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | own switchgear database from v1 (OWN-SWG-*), registered with SHA-256; no manufacturer document behind it | done (authority OWN) |
| G3 Rules | 7 rules (R-AUX-01 … 07) in `rules.yaml` | done |
| G4 Golden | 10 cases (A01–A10) written before the code | done |
| G5 Build | `tests/test_aux_switchgear.py` | done |
| G6 Verify | data files equal the CSV line by line; MCB trip bands checked; 21 Siemens MPCB rows equal SIE-SIRIUS-CM | done |

Decisions for the owner are on the Review tab.
