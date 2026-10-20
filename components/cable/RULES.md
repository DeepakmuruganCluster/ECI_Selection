# Cable — G3 Rule sheet

Machine-readable: `rules.yaml` (R-CAB-01 … 13: 6 MFR, 6 RULE, 1 PHYS). Data (PDF pages):

| File | Make | Content | Pages |
|---|---|---|---|
| `polycab_2xwy_ratings.yaml` | Polycab | 61 rating rows (2/3/3.5/4-core × ground/duct/air) + product flag | 27, 43, 55, 67 |
| `polycab_conductor.yaml` | Polycab | R(AC, 90 °C), X(50 Hz, multi-core), 1-s SC rating, 15 sizes each | 11, 10, 9 |
| `polycab_factors.yaml` | Polycab | air / ground / duct temperature factors | 87 |
| `kei_armoured_ratings.yaml` | KEI | 56 rows: ratings + R(AC, 90 °C) + X | 36, 38, 40, 42 |
| `kei_factors.yaml` | KEI | temperature factors, buried group factors (2–6 cables), 1-s SC rating | 33, 49 |

## Decision flow

```
inputs valid? (Ib, length, voltage, cos φ, installation, ambient, In / flag, pairs)   else invalid
Cu, ≤ 1100 V, 50 Hz ─────────────────────────────── R-CAB-01         else cannot select
make → all data from that make ──────────────────── R-CAB-02
air / ground / duct at the maker's basis ────────── R-CAB-03         tray, depth, soil → cannot select
temperature factor (next hotter column) ─────────── R-CAB-04, 05     above table → cannot select
other cables in the group → maker's group factor ── R-CAB-06         none → cannot select
Ib ≤ In ──────────────────────────────────────────── R-CAB-07         else cannot select
for runs = 1 … 4 (each run adds a cable to the group, needs a factor — R-CAB-06):
  for sizes the maker lists as products (R-CAB-13), smallest first:
    Iz = runs × I_tab × k_temp × k_group ≥ In (or Ib)      R-CAB-07
    running ΔU ≤ 5 % (RULE)                                 R-CAB-09, 10
    starting ΔU ≤ 15 % (if start data given)                R-CAB-11
    I²t ≤ Isc1² (if fault data given; ≤ 5 s)                R-CAB-12
first that passes → chosen (R-CAB-08); bound_by = checks the next smaller size fails
```

## What the sources say (and do not say)

- **Both makers print identical current ratings** for every multi-core size and installation (Polycab: "in accordance with IS 3961 (part 6):2016"). They differ in the temperature factors (air 35 °C 1.05 vs 1.04, 50 °C 0.89 vs 0.90, ground 25 °C 1.04 vs 1.03; Polycab goes to 60 °C, KEI to 55 °C), resistance (up to 6 % at 400 mm²) and reactance (up to 4 %).
- **Polycab prints no grouping factors** although its note 1 (p.11) says they must be used. With Polycab, a second cable in a group — including a parallel run — is refused.
- **Neither maker tabulates cable trays** for LV cables. KEI's tray tables (PDF p.20) sit in its HT-cable section; not used (decision C-3).
- Polycab note 5 (p.11): 3.5- and 4-core cables use the 3-core rating; the tables confirm this.
- 3.5-core 16 mm² (Polycab) and 4-core 400 mm² (Polycab) have rating rows but no product code: not offered.
- Voltage drop uses the AC resistance at 90 °C (maximum operating temperature) — conservative at part load.

## Decisions for the sign-off owner

- **C-1** running ΔU limit 5 % · **C-2** starting ΔU limit 15 % · **C-3** keep refusing trays / grouping in air until IEC 60364-5-52 or IS 3961 is held · **C-4** default make Polycab · **C-5** each parallel run withstands the full fault · **C-6** at most 4 parallel runs.
