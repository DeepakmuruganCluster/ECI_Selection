# Cable — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). The review and sign-off are done in the web app (Review & sign off → 6 · Cable).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: Cu XLPE wire-armoured 2/3/3.5/4-core, ≤ 1100 V, 50 Hz; air / buried / duct; Polycab or KEI | done |
| G2 Source pack | 5 data files: Polycab pp. 9, 10, 11, 27, 43, 55, 67, 87; KEI PDF pp. 33, 36, 38, 40, 42, 49. Column order checked on page images. | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 13 rules (6 MFR, 6 RULE, 1 PHYS) | done; decisions C-1 … C-6 |
| G4 Golden cases | `golden/cases.yaml`: 41 cases with page / hand-calc oracles, written before the code | done |
| G5 Build | `select.py`, `tests/test_cable.py` | **41/41 pass**; every rule exercised; ratings rise and R falls with size; makes never mixed |
| G6 Verify | `VERIFY.md` (`scripts/verify_cable.py`) | independent re-extraction: Polycab 354 values (pdfplumber cells), KEI 394 values (pypdfium2 text): **0 mismatches** |

## G6 observations

1. **Polycab and KEI give the same current ratings** (168 pairs, 0 differences). The choice of make only moves results through the temperature factors (≤ 0.01) and R / X (≤ 6 %).
2. **Neither maker covers cable trays or groups in air.** Real panel-to-motor routes are usually on trays with other cables, so until IEC 60364-5-52 (or IS 3961) is held the tool refuses those routes rather than guess (decision C-3). This is the main gap.
3. **WNS2503 (49 three-phase motor feeders with an FLC, 50 m, in air, single circuit):** every feeder gets 3C×4 mm² except BIOUF-VFD-03 (37 kW, 66 A: 10 mm² at 40 °C, 16 mm² at 50 °C) and RO-VFD-01 (30 kW, 55 A: 10 mm²). 18 feeders were skipped because component 1 refuses them (14 single-phase, 2 non-standard kW, 1 spare).
4. Catalogue slips found (not used by the tool): Polycab p.43 prints "0268" for 0.268 Ω/km; p.65 prints aluminium resistances in a copper table.

## Decisions (answer in the web app)

C-1 running voltage-drop limit · C-2 starting voltage-drop limit · C-3 trays / grouping in air · C-4 default make · C-5 parallel runs and short circuit · C-6 maximum parallel runs.
