# Enclosure heat balance and cooling — G3 Rule sheet

Machine-readable: `rules.yaml` (18 rules: 10 MFR, 1 PHYS, 7 RULE). Data (Rittal TSC 3124300 EN, PDF page =
printed page): `rittal_altitude_factor.yaml` (p. 12), `rittal_heat_transfer.yaml` (pp. 13, 52),
`rittal_formulas.yaml` (pp. 7, 12, 13, 24, 26, 30, 52), `rittal_products.yaml` (pp. 8, 26);
`siemens_cooling_air.yaml` (PM240-2 PDF p. 34, printed 32).

## Formulas (as printed; symbols p. 13)

| | Formula | Page |
|---|---|---|
| natural rise | (ΔT)max = Q̇v / (k · A) | 13 |
| surface heat | Q̇s = A · k · ΔT, ΔT = Ti – Tu (Q̇s < 0 when Ti < Tu) | 13 |
| fan airflow | V̇ = f · Q̇v / ΔT [m³/h], f = 3.1 / 3.2 / 3.3 / 3.4 / 3.5 m³·K/Wh for 0–100 / –250 / –500 / –750 / –1000 m | 12 |
| heat exchanger | qw = (Q̇v – A · ΔT · k) / ΔT [W/K] | 26 |
| cooling unit | Q̇E = Q̇v – k · A · ΔT [W] | 30 |
| k | 5.5 W/m²K for sheet steel; basis indoor siting, static air | 13, 52 |
| Siemens | airflow [l/s] = loss [W] × 0.86 / ΔT [K] | PM240-2 PDF 34 |

All are in the PDF text layer and were also read on the rendered page images (the dotted Q̇ / V̇ and the
fraction bars are only clear on the image).

## Decision flow

```
inputs valid? (heat loss > 0, Tu, Ti, altitude, siting; material with A)        else invalid
indoor, 0 ≤ altitude ≤ 1000 m? ──────────────────────────── R-ENC-01           else cannot select
A given? ── no, sizes given ───────────────────────────── R-ENC-02           cannot select (IEC 890 table not held)
        └─ yes: designer's A, warning ──────────────────── R-ENC-03
material sheet steel → k = 5.5 ─────────────────────────── R-ENC-04           else cannot select
with A: (ΔT)max, natural temperature, Q̇s ───────────────── R-ENC-05, R-ENC-06
        passive if Tu + (ΔT)max ≤ Ti ─────────────────────── R-ENC-07           without A: not assessed
Tu < Ti? ── yes: fan airflow with f (boundary → higher f) ── R-ENC-08, -09, -10; Siemens cross-check R-ENC-13
         │       heat exchanger qw + smallest model ─────── R-ENC-14 (without A: R-ENC-16)
         └─ no: fans / heat exchangers impossible ───────── R-ENC-08
cooling unit Q̇E = Q̇v – k·A·ΔT ──────────────────────────── R-ENC-15           Ti < Tu without A: cannot select
         without A and Ti ≥ Tu: Q̇E = Q̇v ─────────────────── R-ENC-16; margin R-ENC-17
method: passive → fan (Ti – Tu ≥ 5 K, else warning) → cooling unit ── R-ENC-18, R-ENC-11
fan airflow > 1160 m³/h → warning ───────────────────────── R-ENC-12
```

## Where the source stops

- Rittal reproduces only the *result* of the IEC 890 method ("A = effective … surface area to IEC 890",
  pp. 13, 26, 30, 52; p. 31 asks "What is the installation type to IEC 890?") — not the formulas per
  installation type. Those need IEC TR 60890 (to be bought).
- Rittal's fan formula does not subtract the heat leaving through the walls; the tool follows it (conservative).

## Decisions for the sign-off owner

- **H-1** Accept a designer-entered A with a warning until IEC TR 60890 is held?
- **H-2** Below which Ti – Tu should fans give way to a cooling unit (5 K proposed, Rittal's lowest chart line)?
- **H-3** Margin on the cooling-unit output (0 % proposed: Rittal's formula as printed)?
- **H-4** Altitude exactly on a band end point: higher f?
- **H-5** WNS2503: cooling units at 35 °C inside rather than fans at 55 °C?
