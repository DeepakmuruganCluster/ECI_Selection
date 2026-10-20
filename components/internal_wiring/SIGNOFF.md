# Internal wiring — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). The review and sign-off are done in the web app (Review & sign off → 19 · Internal wiring).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: Lapp single cores (col A) and multicore (col C); duct / plate / spaced in air; 3~AC, 1~AC, DC | done |
| G2 Source pack | 2 data files: Lapp PDF pp. 1–4 (printed 144–151): Table 12-1 A/C, footnote 3, Tables 12-2, 12-3, 12-4, 12-6 | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 13 rules (6 MFR, 5 RULE, 1 PHYS, 1 CLIENT) | done; decisions W-1 … W-6 |
| G4 Golden cases | `golden/cases.yaml`: 36 cases with page / hand-calc oracles, written before the code | done |
| G5 Build | `select.py`, `tests/test_internal_wiring.py` | **36/36 pass**; every rule exercised; hotter panel / more circuits never give a smaller wire |
| G6 Verify | `VERIFY.md` (`scripts/verify_internal_wiring.py`) | independent re-extraction (pdfplumber word positions): 269 values, **0 mismatches** (7 first-run differences were a checker window error, resolved on the page image) |

## G6 observations

1. **Hot panels cost a lot of copper.** PVC single cores in a duct at 55 °C keep only 0.67 × 0.61 = 41 % of
   Lapp's basic rating: the 37 kW drive's 100 A fuse needs **70 mm²** (35 °C: 50 mm²); the 7.5 kW DOL needs
   **4 mm²** (35 °C: 2.5 mm²). Heat-resistant H07V2-K (Table 12-4: 0.94 at 55 °C) brings the drive back to 50 mm².
2. **The duct is our reading** (W-1): Lapp's basic column is for spaced single wires; footnote 3 + Table 12-6 is
   Lapp's route for bundled wires, but Lapp's own note sends conduits in buildings to DIN VDE 0298-4 Tables 3 / 5,
   which we do not hold. Re-check against IEC 60364-5-52 / IEC 61439-1 when bought.
3. **The circuits sharing a duct matter as much as temperature** (6 circuits: × 0.57) and are not in the client
   documents — the designer must give the number.
4. Not covered: voltage drop, short-circuit withstand, mechanical minimum sizes, wire quantity.

## Decisions (answer in the web app)

W-1 duct method · W-2 Lapp wire type for WNS2503 · W-3 mechanical minimum size · W-4 MPCB In · W-5 wire quantity · W-6 overload rule.
