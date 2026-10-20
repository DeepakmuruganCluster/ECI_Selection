# Internal wiring — G3 Rule sheet

Machine-readable: `rules.yaml` (R-WIR-01 … 13: 6 MFR, 5 RULE, 1 PHYS, 1 CLIENT). Data (PDF pages, printed in brackets):

| File | Content | Pages |
|---|---|---|
| `lapp_t12_1_ratings.yaml` | Table 12-1 columns A (single core) and C (multicore 2 or 3 loaded), 0.08 … 500 mm², 30 °C | 1 (144, 145) |
| `lapp_t12_factors.yaml` | footnote 3 bundling factors; Table 12-2 temperature (60 … 90 °C conductors); Table 12-4 heat-resistant; Table 12-3 loaded cores; Table 12-6 grouping (all 5 rows; row 1 used) | 2 (146/147), 3 (148/149), 4 (150/151) |

## Decision flow

```
inputs valid? (Ib, ambient, insulation, In / flag, circuits for duct / surface)       else invalid
Lapp category A or C ──────────────────────────────────── R-WIR-01   cords / rubber / welding / AWG → cannot select
installation duct / surface / air_spaced ──────────────── R-WIR-03   tray, touching free air → cannot select
temperature factor T12-2 or T12-4 (next hotter row) ──── R-WIR-08, 09  past the column → cannot select
single cores bundled: 0.67 (3~AC) / 0.76 (1~AC, DC) ──── R-WIR-04, 05
grouping T12-6 'bunched … wireways' (next larger n) ──── R-WIR-06, 09  > 20 → cannot select
multicore > 3 loaded: T12-3 free air, ≤ 10 mm² ───────── R-WIR-07, 09
Ib ≤ In ─────────────────────────────────────────────────── R-WIR-10   else cannot select
smallest size ≥ 0.5 mm² (and ≥ project minimum):
  Iz = I(T12-1) × k_temp × k_bundle × k_group × k_cores ≥ In (or Ib)   R-WIR-02, 11, 12
largest fails → cannot select (no parallel conductors) ── R-WIR-11
not checked: voltage drop, short circuit, mechanical minimum, metres ─ R-WIR-13
```

## What the source says (and does not say)

- Table 12-1 is printed for 30 °C ambient and "nominal voltage up to 1000 V"; it does not print a conductor
  temperature — that enters only via Table 12-2 / 12-4, so the insulation class is a required input.
- Column A's drawing shows single cores spaced ≥ d from each other and from the wall: the basis is **not** a duct.
  Footnote 3 gives the bundling factors (0.76 / 0.67 on surfaces → then Table 12-6; 0.8 / 0.7 free in air → then
  Table 12-8, cable trays). Table 12-6 row 1 explicitly draws and names wireways.
- Lapp's "Attention" note: single cores in conduits in **buildings** (A1 / B1) → DIN VDE 0298-4 Tables 3 / 5
  (not held). Our reading for panel ducts is R-WIR-05 (decision W-1).
- Table 12-6 notice: factors only for similarly loaded cables of a similar installation whose sizes differ by
  one step — reported as a condition for the designer.
- Table 12-4 has no 145 °C row (140 → 150); the next hotter row is used.
- Lapp sends "cables & wires in machines" to DIN EN 60204-1 (not held).

## Decisions for the sign-off owner

- **W-1** single cores in a duct via footnote 3 + Table 12-6 · **W-2** Lapp wire type / insulation class for WNS2503
  · **W-3** mechanical minimum sizes · **W-4** MPCB In = top of the setting range · **W-5** wire quantity (metres)
  · **W-6** Ib ≤ In ≤ Iz as the overload rule.
