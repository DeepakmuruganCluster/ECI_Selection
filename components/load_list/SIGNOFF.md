# Load-list import (ECI WNS2503) — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). Signing off releases the *reader*; the
eight client questions below still go to ECI.

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source pack | no data files of its own: the registered Word file `ECI-WNS2503-LOADS` is read at run time (SHA-256 checked); `ECI-WNS2503-EQUIP` (PDF) for the cross-check | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 15 rules (6 CLIENT, 3 PHYS, 6 RULE) | done; decisions L-1 … L-8 |
| G4 Golden cases | `golden/cases.yaml`: 23 cases written before the code; each oracle quotes the Word cells | done |
| G5 Build | `select.py`, `tests/test_load_list.py` | 23/23 pass, plus: every produced load list parses with the panel component's `parse()`, no line carries `flc=`, every row cites table/row |
| G6 Verify | `VERIFY.md` (`scripts/verify_load_list.py`): v1 Layer 0 row by row, the equipment PDF, and the panel chain | every difference explained |

## What the import finds in ECI's Word file (2026-10-11)

| Panel | Rows | Drives (rows / units) | Soft starters | DOL (rows / units) | Heater | 1-phase rows |
|---|---|---|---|---|---|---|
| BIO/UF | 35 | 10 / 22 | 1 / 1 | 24 / 36 | – | 5 |
| RO | 32 | 8 / 16 | 1 / 2 | 22 / 39 (incl. 4 spare 'Extra DOL') | HT401 | 9 |

- All six 'Panel Total' rows agree with the Req columns. The 'Total Qty' column does not: BIO/UF drives add up to 23 (P103A/B says 3).
- 17 rating cells had to be split (range and MPCB type run together, or one column to the right).
- Tags: S102 used for two machines, P412A/B in both panels, 5 Instrument IDs ≠ Group Marking.
- 23 rows: ECI's own current is outside ECI's own MPCB range (never used for selection).
- Against ECI's equipment PDF: 5 rows differ: K101A/B 18.5 vs 15 kW, P102A/B 3- vs 1-phase, three tags.

## Through the panel component (cable 50 m and one standby per group typed for this run only)

BIO/UF 27 of 35 lines selected (v1 list: 26), RO 21 of 32 (v1 list: 20 of 31). The difference is P102A/B
(3-phase in Word) and the spare P507 starters ECI counts. See `VERIFY.md`.

## Decisions (answer in the web app)

L-1 K101A/B kW · L-2 P102A/B phases · L-3 P103A/B quantity · L-4 standby · L-5 spare starters ·
L-6 tag problems · L-7 heater HT401 · L-8 report currents outside ECI's ranges.
