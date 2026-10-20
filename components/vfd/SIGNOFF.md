# VFD — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-10). The review and sign-off are done in the web app (Review & sign off → 4 · VFD).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: PM240-2 IP20 400 V FSA–FSF, ≤ 1000 m, unfiltered or C2 | done |
| G2 Source pack | 4 data files from the PM240-2 manual 07/2022 (21 modules, derating, cable lengths, line and output reactors). Merged cells checked on the page images. | done (manual is a third-party copy, see V-3) |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 13 rules (11 MFR, 2 RULE) | done; decisions V-1 … V-4 |
| G4 Golden cases | `golden/cases.yaml`: 32 cases written before the code | done |
| G5 Build | `select.py`, `tests/test_vfd.py` | **44/44 pass** (12 added for protection devices); every rule exercised; every module has its reactor assignments; the fuse in the manual equals the fuse in the protective-devices document for all 21 drives |
| G6 Verify | `VERIFY.md` (`scripts/verify_vfd.py`) | independent re-extraction: 252 module values, 4 derating rows, 32 reactor assignments, 17 cable-length rows, 114 protective-device rows: **0 mismatches** |

## G6 observations on WNS2503 (18 VFD feeders)

1. **Panel temperature decides the drive sizes.** In an air-conditioned panel (35 °C) every drive matches its motor. In a fan-cooled panel on a 50 °C site (55 °C inside), **all 18 drives go up one or two sizes**, e.g. 37 kW → 45 kW and 4 kW → 7.5 kW. The cooling choice (component 9) has to be made before the drives are final.
2. **ECI's "line reactor up to 15 kW" rule** adds a reactor to every FSA–FSC drive. FSD and larger drives need none (Siemens: no line impedance restriction).
3. **v1 had the cable-length logic wrong.** For FSA–FSC with shielded cable, an output reactor does not allow a longer cable. For FSD–FSF the longer length needs **two** output reactors. v2 follows the manual's tables.
4. **3VM breakers are not Siemens-listed protection for any PM240-2.** Siemens lists fuses, 3RV motor starter protectors and 3VA/3VL breakers, and 3VL is being phased out. For 4–15 kW drives no breaker is listed at all. ECI's "3VM for branch feeders" can't be applied to drive feeders without leaving Siemens' tested combinations (decision V-2).
5. **The motor currents are guide values**, so every line carries the "confirm with the nameplate" warning.

## Decisions (answer in the web app)

V-1 temperature steps · V-2 drive protection devices (3VM not listed) · V-3 official manual copy · V-4 line reactor rule.
