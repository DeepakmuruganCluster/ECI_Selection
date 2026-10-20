# DOL starter — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-10). It depends on component 1 (motor FLC), which is also awaiting sign-off.

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: 3RV2 + 3RT2, Type 2, 400 V, 230 V AC coil, 0.11–100 A | done |
| G2 Source pack | `data/siemens_type2_400v.yaml` (39 rows, pp. 28–29), `data/siemens_link_modules.yaml` (Table 2-1, p. 22). Transcribed by hand and checked against the rendered page images. | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 11 rules (9 MFR, 2 RULE) | done; decisions E-1 … E-3 below |
| G4 Golden cases | `golden/cases.yaml`: 26 cases written before the code (3 single-row, 5 margin rule, 3 starting-current limit, 1 link module, 3 basis/IE default, 2 fault level, 6 scope, 3 invalid) | done |
| G5 Build | `select.py`, `tests/test_dol_starter.py` | **26/26 cases pass**. Every rule in the code is in the rule sheet, and every rule is exercised. Full suite 64/64. |
| G6 Verify | `VERIFY.md` (`scripts/verify_dol_starter.py`) | cell-level PDF re-extraction: 39/39 rows and 5/5 link modules, **0 mismatches**; WNS2503 47 DOL feeders run |

During G6 the first, text-based re-extraction reported two false differences: starting-current notes attached to the neighbouring rows. The page images and a cell-level re-extraction confirm the data file is right, and the checker now reads table cells.

## G6 observations on WNS2503 (for your review)

1. **The client's MPCB ranges often can't be set to the motor current.**
   - 0.25 kW 3-ph pumps (P702A/B and 5 others): the client range is 1.1–1.6 A, but the FLC is 0.85 A, below the range.
   - 3 kW P204A/B: the client range is 4.5–6.3 A, but the FLC is 6.5 A, above the range, so it would trip.
   - 1.5 kW mixers MX401–MX507: the client range is 1.8–2.5 A, but the FLC is 3.6 A.

   These all come from the client's 1.9 × kW currents (see motor FLC SIGNOFF point 4). Only 4 of 30 match v2's MPCB.
2. **v2 and v1 pick the same MPCB articles where both can select.** The ranges look different only because v2 reports the IE3/IE4 column for IE3 motors.
3. **ECI specifies 24 V DC coils, so every ECI DOL feeder is `cannot_select` today (R-DOL-07).** The table above was run with a 230 V AC coil to check the MPCB and contactor choice. Closing this needs E-3.
4. **20 feeders pair an S00 MPCB with an S0 contactor** (1.5 kW up to 7.5 kW IE2; e.g. 3RV2011-1FA10 + 3RT2024). Table 2-1 has no link module for that pair, so each gets a warning (E-2).
5. **Heater HT401 → `cannot_select`.** It needs a heater-feeder component (AC-1 contactor + protection). v1 put it on an MPCB.
6. **17 feeders have no FLC from component 1:** 15 single-phase pumps, plus the 3.7 kW and 1.9 kW motors.

## Decisions needed

| # | Question | Options | Recommendation |
|---|---|---|---|
| E-1 | Tie-break when several ranges fit | ☐ largest margin (now) ☐ smallest size that fits | largest margin: it stays valid when the nameplate current differs a little from the guide value |
| E-2 | S00 MPCB + S0 contactor | ☐ wire without a link module ☐ source the correct link module (IC 10) | source it: 20 WNS2503 feeders |
| E-3 | Download Siemens catalogue IC 10 (or the 3RT2 data sheets) for 24 V DC coil codes and DC link modules | ☐ yes ☐ no | yes: without it no ECI DOL starter can be completed |

## Release

Released by: ____________________  Date: __________  Data editions: SIRIUS manual 09/2017
