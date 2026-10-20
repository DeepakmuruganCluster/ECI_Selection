# Incomer MCCB (3VA1, TM240) — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (built 2026-10-20). Review and sign-off in the web app (Review & sign-off → Incomer MCCB 3VA1).

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source pack | LV 10 · 2026 pp.181, 183, 200, 201 (stored, SHA in sources/register.yaml); data sheet 3VA1563-5EF32-0AA0 (SIE-3VA1563-DS, saved by the owner 2026-10-20) | done; 3VA1463-5EF32-0AA0 data sheet requested |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 8 rules | done; decisions V3A-1 (answered), V3A-2 |
| G4 Golden cases | `golden/cases.yaml`: 15 cases written before the code | done |
| G5 Build | `select.py`, `tests/test_mccb_3va.py` | 15/15 + data-sheet agreement test |
| G6 Verify | `VERIFY.md` | structure and data-sheet agreement checked by test; independent re-extraction pending |
