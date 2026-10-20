# Enclosure heat balance and cooling — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-10). The review and sign-off are done in the web app
(Review & sign off → 9 · Enclosure). The web app has no input tab for this component yet: the "Try it"
buttons need an `enclosure` tab (webapp change, not part of this component).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: sheet-steel enclosure, indoor, 0–1000 m; passive / fans / air-air heat exchanger / cooling unit | done |
| G2 Source pack | 5 data files: Rittal TSC 3124300 EN pp. 7, 8, 12, 13, 24, 26, 30, 52 and Siemens PM240-2 PDF p. 34. Formulas read on the page images as well as the text layer. | done; **IEC TR 60890 not held** (H-1) |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 18 rules (10 MFR, 1 PHYS, 7 RULE) | done; decisions H-1 … H-5 |
| G4 Golden cases | `golden/cases.yaml`: 31 cases written before the code (hand calculations; Rittal prints no worked example for these formulas; Siemens formula as independent oracle) | done |
| G5 Build | `select.py`, `tests/test_enclosure.py` | **31/31 pass**; every rule exercised; data sanity; VFD loss feeds the enclosure |
| G6 Verify | `VERIFY.md` (`scripts/verify_enclosure.py`) | independent re-extraction: 5 f bands, k on 3 pages, 10 formulas / sentences, 6 heat-exchanger ratings, fan range, Siemens coefficient and CU loss: **0 mismatches**; Rittal vs Siemens airflow 0.13 % apart; Rittal printed page = PDF page |

## G6 observations

1. **The surface area is the weak point.** Rittal's catalogue relies on IEC 890 for A but does not print it.
   Every answer that uses A carries a warning until IEC TR 60890 is held and the tool can compute A from the
   section sizes and installation type.
2. **Rittal and Siemens agree** on the airflow formula (3.1 m³·K/Wh = 0.861 l·K/(W·s) vs 0.86) at sea level.
   At 1000 m Rittal asks for 13 % more air; Siemens has no altitude factor, so Rittal governs.
3. **WNS2503 (50 °C site, 1000 m).** The VFD component showed every drive must be upsized at 55 °C inside
   (fans) but none at 35 °C (air-conditioned). This component adds:
   - fans can never bring the inside below the outside air (Rittal p. 7: the ambient must be below the
     required internal temperature). With fans the best is about 55 °C (Ti – Tu = 5 K, Rittal's lowest chart
     line), and then V̇ = 3.5 × Q̇v / 5 = 0.7 m³/h per watt: the running drives alone (≈ 5.3 kW in BIO/UF,
     ≈ 3.0 kW in RO at 55 °C sizing) need ≈ 3,700 and ≈ 2,100 m³/h — more than one Blue e+ fan-and-filter
     unit (max 1160 m³/h) per panel, plus bigger drives;
   - 35 °C inside a 50 °C site **needs a cooling unit**: Q̇E = Q̇v + 82.5 W per m² of effective area
     (heat also comes in through the walls). For the drives alone: 3.7 kW + 82.5 × A (BIO/UF), 2.2 kW + 82.5 × A (RO).
   - Decision H-5 asks the owner to confirm cooling units at 35 °C for WNS2503.

## Decisions (answer in the web app)

H-1 designer-entered surface area · H-2 fan / cooling-unit threshold · H-3 cooling margin · H-4 altitude end points · H-5 WNS2503 cooling choice.
