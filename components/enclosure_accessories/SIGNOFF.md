# Enclosure accessories — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). Review and sign-off in the web app
(Review & sign off → 18 · Enclosure accessories).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: 8 / 10 inch TopTherm filter fans + outlet filters, 230 V 50/60 Hz; plinth side trims 100 / 200 mm; door switch + LED light per door | done |
| G2 Source pack | 9 data files, 105 rows: 8 Rittal data sheets + TSC 3124300 pp. 8, 12. Fan pp. 2, 3, 5 and TS 8602.060 p.2 read on the page images | done; front / rear plinth parts not held |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 17 rules (10 MFR, 5 RULE, 2 CLIENT) | done; decisions A-1 … A-6 |
| G4 Golden cases | `golden/cases.yaml`: 27 cases written before the code (data-sheet values and hand calculation) | done |
| G5 Build | `select.py`, `tests/test_enclosure_accessories.py` | **27/27 pass**; every rule exercised; data sanity; enclosure airflow feeds the fan count |
| G6 Verify | `VERIFY.md` (`scripts/verify_enclosure_accessories.py`) | independent re-extraction of all 105 rows: **0 mismatches**; SK 3239.100 power / current contradict themselves inside the data sheet (both recorded, A-3) |

## G6 observations

1. **SK 3239.100 data sheet contradicts itself**: 16.5 / 14 W and 0.12 / 0.09 A (features, p.2) vs 19 / 18 W and
   0.12 / 0.11 A (tender text, p.5). Both are on the page images; the tool uses the higher (A-3).
2. **WNS2503 fans**: one 8 inch fan (+ outlet filter, 74 m³/h) on each of 7 doors = 518 m³/h vs 3515 m³/h (BIO/UF,
   15 %) and 2077 m³/h (RO, 25 %): 48 and 29 fans needed (912 W and 551 W). At the site altitude 1000 m the
   enclosure asks 13 % more (panel ran it at 0 m). A-6 / enclosure H-5: cooling units.
3. **1 ft stand**: no 300 mm Rittal plinth in the held data (100 / 200 mm side trims only) — A-5.
4. The registered "plinth component" data sheets are side trim panels only; corner pieces and front / rear trims per
   section width need their own data sheets before a complete plinth can be listed.

## Decisions (answer in the web app)

A-1 8 inch = SK 3239.100 · A-2 outlet filters per fan · A-3 fan power value · A-4 switch and light per door ·
A-5 1 ft stand · A-6 WNS2503 fans vs cooling units.
