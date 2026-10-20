# Panel assembly — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). It can only be released after the components it chains (1, 2, 4, 6, 9) are released.

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md` | done |
| G2 Source pack | none of its own: every value comes from a component (Control Unit loss 40 W: SIE-PM240-2 p.34; drive overload protection: SIE-G120-PROT p.3) | done |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 9 rules (1 MFR, 8 RULE) | done; decisions P-1 … P-3 |
| G4 Golden cases | `golden/cases.yaml`: 16 cases written before the code; each expected answer is another component's golden case or a hand count | done |
| G5 Build | `select.py`, `tests/test_panel.py` | 16/16 pass, plus a test that every BOM article equals what the components returned (e.g. 2 drives × 2 output reactors = 4) |
| G6 Verify | `VERIFY.md` (`scripts/verify_panel.py`): WNS2503 end to end, both panels, two cooling cases | see below |

While running WNS2503 the first time, G6 caught a gap in the assembly itself: there was no phase option, so the 15 single-phase dosing pumps were run as 3-phase motors. Fixed (`ph=1`) with three new golden cases (P14–P16) added before the fix.

## WNS2503 end to end (v2, 2026-10-11)

| Panel | Lines | Fully selected | Main open points |
|---|---|---|---|
| BIO/UF | 35 | 26 | 6 single-phase pumps and 2 motors (3.7 / 1.9 kW) need nameplate currents; 1 soft starter (component 5 not built) |
| RO | 31 | 20 | 9 single-phase pumps need nameplate currents; 1 soft starter; heater HT401 (no heater component yet) |

- **Every selected DOL line warns "confirm with the nameplate"** (motor currents are Siemens guide values). 21 DOL lines have no link module for S00 MPCB + S0 contactor (DOL decision E-2).
- **Panel heat from sourced losses** (drives + control units): BIO/UF 4.1 kW at 35 °C inside, 5.7 kW at 55 °C (the drives grow when derated); RO 2.5 / 3.4 kW. DOL starter losses are not included (no source yet, P-1).
- **Cooling at a 50 °C site:** fans can hold 55 °C but need ≈ 3,500 m³/h (BIO/UF) and ≈ 2,100 m³/h (RO), more than one Rittal fan-and-filter unit. Holding 35 °C needs a cooling unit, and the tool can't size it until the enclosure surface area is known (IEC TR 60890, on the purchase list).

## Decisions (answer in the web app)

P-1 incomplete heat · P-2 Control Unit 40 W per drive · P-3 single-phase voltage.
