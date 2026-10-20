# Metering — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). Review and sign-off in the web app (Review & sign off → 15 · Metering).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: PAC3220 + PROFINET module, Rishabh LTRP/TW and Selec SPCT/TWCT CTs, 3P4W ≤ 690 V, 5 A secondary | done |
| G2 Source pack | 8 data files, 310 rows: PAC3220 manual (15 values, pp. 10–107), PROFINET module manual (4, pp. 21, 79), Rishabh LTRP (72 + 3, pp. 2–11), TW (146 + 3, pp. 2–4), Selec 2026 (65, pp. 9–10), Selec 2024 ambient (2, pp. 7, 10) | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 14 rules (6 MFR, 2 PHYS, 5 RULE, 1 CLIENT) | done; decisions MT-1 … MT-6 |
| G4 Golden cases | `golden/cases.yaml`: 30 cases written before the code (oracles: page + hand calculation) | done |
| G5 Build | `select.py`, `tests/test_metering.py` | **30/30 pass**; every rule exercised; Selec type codes reproduce the 9 codes printed as table titles |
| G6 Verify | `VERIFY.md` (`scripts/verify_metering.py`) | independent re-extraction (regex on page text, ruled-table cells, word positions): 14 PAC3220 values, 4 module rows, 72 LTRP + 146 TW + 65 Selec rows, 11 Selec window sizes, 6 Rishabh conditions: **0 unexplained mismatches**. The first run showed 16 differences, all on the verifier side (Selec SPCT-140/100 two side-by-side halves and the one-row 'Accuracy (0.5)' header of TWCT-D120 were mis-read); checked against the page images, the data was right and the verifier was fixed. Drawn window sizes (Rishabh) and the image-only Selec 2024 catalogue cannot be re-extracted: read on rendered page images, listed in VERIFY.md §6 |

## Observations

1. **WNS2503 incomers (630 A)**: Rishabh → RISH LTRP 4, 630/5 A, 7.5 VA, class 0.5; Selec → SPCT-100/60-800/5A-VA10-CL0.5-CE (Selec prints no 630 A). Meter SENTRON PAC3220 (7KM3220-xBA01-1xA0) + 7KM9300-0AE02-0AA0; 3 CTs per panel. Cautions: wire length, conductor and panel temperature not given.
2. **ECI's 75 × 10 busbar does not pass the Rishabh 630 A CT** (LTRP 4 hole 65 × 35): on the bar the tool gives TW-6 800/5 A 10 VA (with a ratio caution); Selec gives TWCT-T-D110-800/5A-VA10-CL0.5.
3. **Rishabh CTs: ambient −25 … +40 °C only** — above 40 °C inside the panel they are refused (MT-6). Selec 0 … +50 °C; PAC3220 up to +55 °C.
4. 1 A CTs cannot be selected: no 1 A ratings published by either maker.
5. The meter's full article number and the Rishabh order codes are not in the held documents (MT-5).
6. Not checked: CT short-time current Ith against the 55 kA fault level (LTRP: 60 × In, max 40 kA for 1 s — needs component 7), lower burden limit of the accuracy class (IEC 61869-2 not held).

## Decisions (answer in the web app)

MT-1 default class 0.5 · MT-2 wire temperature 70 °C · MT-3 next ratio with a caution · MT-4 exact window fit · MT-5 confirm order numbers · MT-6 Rishabh above 40 °C.
