# Motor FLC — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-10)

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source pack | `data/siemens_guide_400v_4p.yaml`: 31 rows, each with a page number. Source: SIRIUS manual 09/2017 (SHA-256 recorded in `sources/register.yaml`; the loader refuses data if the file is missing or changed). | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 8 rules (2 MFR, 2 PHYS, 4 RULE) | done; RULE items need your decision below |
| G4 Golden cases | `golden/cases.yaml`: 30 cases written before the code (6 PDF, 8 refusals, 3 voltage, 6 nameplate, 3 heater, 2 client, 2 invalid) | done |
| G5 Build | `select.py`, `tests/test_motor_flc.py` | **35/35 tests pass**. The tests also check that every rule in the code is in the rule sheet and that every rule is exercised by a case. |
| G6 Verify | `VERIFY.md` (re-generate: `scripts/verify_motor_flc.py`) | PDF re-extraction 31/31, **0 mismatches**; WNS2503 67 feeders run, see observations |

## G6 observations on WNS2503 (for your review)

1. **15 single-phase dosing pumps (0.25 / 0.75 kW, 230 V) → `cannot_select`.** v1 used an unsourced 1-ph table (2.2 A for 0.25 kW). v2 needs the pump maker's nameplate current, or a sourced 1-ph motor table added through G2.
2. **3.7 kW (K202) and 1.9 kW (P104A/B) → `cannot_select`.** These ratings are not in the Siemens table, and v1 interpolated them. Nameplate needed.
3. **Heater HT401, 15 kW:** the client list says 28.52 A (= 1.9 × kW, a motor rule of thumb). As a resistive load it is **21.65 A**. v2 flags the +32 %.
4. **The client's values are 1.9 × kW throughout.** For small motors that is 20–44 % **below** the guide value (e.g. 0.25 kW: 0.48 A vs 0.85 A). Undersizing MPCB ranges from the client list would cause nuisance trips. v2 never uses the client value.
5. **On the VFD / SS lines v1 kept the client value when it was within ±10 %. v2 uses the guide value.** For 37 kW this gives 66 A (v2) against 70.34 A (client / v1); for 30 kW, 55 A against 57.03 A. Where the client value is higher, v2's design current is lower. See D-5.

## Decisions needed

Tick one per line and the component is released with that setting.

| # | Question | Options | Recommendation |
|---|---|---|---|
| D-1 | Voltage scaling ±5 % (R-FLC-05) | ☐ keep ±5 % ☐ 400 V only | keep. It is always flagged, and WNS2503 is at 400 V anyway. |
| D-2 | Ratings not in the table (3.7, 9.3, 1.9 kW) | ☐ refuse, nameplate needed ☐ allow interpolation as RULE | refuse. Add a motor maker's table (G2) if these are common. |
| D-3 | Can a guide value go into an issued BOM? | ☐ yes ☐ preliminary only, nameplate before issue | preliminary only. The manual itself says the selection depends on the motor's actual data. |
| D-4 | Warning thresholds 15 / 5 / 10 % | ☐ accept ☐ change: ___ | accept |
| D-5 | Without a nameplate, should the design current be the guide value or **max(guide, client)**? | ☐ guide ☐ max(guide, client) | guide value, with the R-FLC-08 warning (client lists are formula-derived, point 4). Revisit when sizing VFDs (component 4). |
| D-6 | Single-phase motors | ☐ nameplate only (now) ☐ source a 1-ph table next | source a table: 15 feeders on WNS2503 depend on it |

## Release

Released by: ____________________  Date: __________  Data editions: SIRIUS manual 09/2017
