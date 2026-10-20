# Project BOM — G7 Sign-off

Sign-off owner: **Deepak Murugan** · Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). It can only be released after its components are released.

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source | none of its own (chains components) | done |
| G3 Rules | 8 rules | done |
| G4 Golden | 6 cases written before the code: quantities from the load list and ECI's I/O table | done |
| G5 Build | 10 tests, including every option of every decision runs and the CU option swaps the control unit | done |
| G6 Verify | WNS2503 exports `out/WNS2503_<panel>_BOM.xlsx` (main BOM + Options sheet) | done |

## What the options show for WNS2503 (BIO_UF)

- **No STO:** 22 × CU240E-2 PN become CU230P-2 PN.
- **Slim relays only:** 36 latching relays removed; slim relays 44 → 80 (matches ECI's DO count).
- **Breakers instead of fuses:** Siemens lists no breaker for 4–15 kW drives, so 14 drives can't be protected that way; those lines become open points. Fuses stay the main choice.
- **55 °C inside:** drives and internal wires grow (see the Options sheet).
