# Client-specified items — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-11)

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | ECI Automation_Rittal spec Rev02, 44 lines + I/O table, transcribed from pages 1–2 and checked on the page images | done |
| G3 Rules | 5 rules | done; decisions K-1 … K-3 |
| G4 Golden | 5 cases written before the code (hand counts from the spec) | done |
| G5 Build | 8/8 tests | done |
| G6 Verify | the spec's own arithmetic: all I/O sums agree; **RO sections add up to 7400 mm, not the stated 7800 mm** | see K-2 |

## Findings for ECI

1. **RO panel length:** 600 + 4 × 1200 + 2 × 1000 = 7400 mm, but 7800 mm is stated.
2. **No quantity given** for: 7-inch HMI (both panels), 55-inch display, CTs, fans "on each door", door switch and light, interface relays, terminals, internal wiring, internal PROFINET cable.
3. **Spare I/O** ranges from 2 % (RO DI: 6 on 330) to 300 % (0–10 V AI: 3 on 1).
4. **Only one CPU is listed** (BIO_UF). RO has ET 200SP stations only, i.e. remote I/O of the BIO_UF CPU. This should be confirmed.
