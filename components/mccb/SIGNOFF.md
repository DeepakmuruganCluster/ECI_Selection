# Branch MCCB — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-10). The review and sign-off are done in the web app (Review & sign off → 3 · Branch MCCB).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: 3VM10–3VM14 line protection (TM210 / TM220), 3/4-pole, 380–415 V, ≤ 2000 m, −25 … +50 °C | done |
| G2 Source pack | 3 data files from Siemens LV 31 · 2018 (official): 12 frame/class Icu/Ics rows (pp. 10–11), 43 In/Ir/Ii rows (pp. 28, 30), 324 article numbers (pp. 28–35). Column layout checked on the page images. | done (2018 edition, see M-5) |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 12 rules (7 MFR, 5 RULE) | done; decisions M-1 … M-7 |
| G4 Golden cases | `golden/cases.yaml`: 37 cases written before the code | done |
| G5 Build | `select.py`, `tests/test_mccb.py` | **37/37 pass**; every rule exercised; every article joins to its Icu/Ics and In/Ir/Ii rows |
| G6 Verify | `VERIFY.md` (`scripts/verify_mccb.py`) | independent re-extraction by word position: 60 breaking-capacity values, 172 trip-rating values, 324 article numbers (2268 attributes): **0 mismatches** |

## Observations

1. **At ECI's 50 kA only class M (55 kA) works**, so every feeder gets a 3VM11 or larger, even a 16 A feeder. 3VM10 stops at 36 kA.
2. **Ics of class M is 41 kA**, below 50 kA. If ECI requires Ics ≥ fault level (M-2), no 3VM can be used at 50 kA.
3. **No let-through I²t** in this catalogue: the cable component cannot get it from here (M-4).
4. **No derating figures above 50 °C**: hot panels are refused (M-3).
5. The catalogue prints every orderable article number; the tool looks them up, it does not assemble them.

## Decisions (answer in the web app)

M-1 margin · M-2 Icu or Ics · M-3 above 50 °C · M-4 let-through I²t source · M-5 confirm 2018 order numbers · M-6 default trip unit · M-7 choice rule.
