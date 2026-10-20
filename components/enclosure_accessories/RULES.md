# Enclosure accessories — G3 Rule sheet

Machine-readable: `rules.yaml` (17 rules: 10 MFR, 5 RULE, 2 CLIENT). Data: one file per Rittal data sheet
(`data/rittal_*.yaml`, every row with `page`; PDF page = printed page) and `rittal_tsc_fan_principle.yaml`
(TSC 3124300 pp. 8, 12).

## Values used (50 Hz / 60 Hz)

| | SK 3239.100 (8 in) | SK 3240.100 (10 in) | Page |
|---|---|---|---|
| frame / cut-out | 204 × 204 / 177 × 177 mm | 255 × 255 / 224 × 224 mm | 3 |
| free airflow, chopped-fibre mat | 100 / 115 m³/h | 175 / 155 m³/h | 2 |
| **with 1 outlet filter** (SK 3239.200 / SK 3240.200) | **74 / 87 m³/h** | **130 / 110 m³/h** | 2 |
| with 2 outlet filters | 84 / 98 m³/h | 159 / 135 m³/h | 2 |
| power | 16.5 / 14 W (p.2) **vs 19 / 18 W (p.5)** | 35 / 34 W | 2, 5 |
| current | 0.12 / 0.09 A (p.2) vs 0.12 / 0.11 A (p.5) | 0.21 / 0.19 A | 2, 5 |
| noise | 46 / 49 dB(A) | 51 / 46 dB(A) | 3 |
| operating range | -15 … 55 °C | -30 … 55 °C | 3 |
| IP | 54 with chopped-fibre / pleated filter | same | 3 |

Plinth side trims TS 8601.060 (100 mm) / TS 8602.060 (200 mm): for W 600 mm, pack of 2, RAL 7022 (p.2/3).
SZ 4127.010: 24 V DC / 6 A, 240 V AC / 6 A, IP 40, without cable (p.2). SZ 4140.820: 24 V DC, 0.08 A, IP 20,
integral on/off/door-operated switch, rows ≤ 2 A (pp. 2–4).

## Decision flow

```
inputs valid? (airflow ≥ 0, doors ≥ 1, V, Hz; depth + suites with a plinth)     else invalid
230 V, 50 or 60 Hz? ───────────────────────────────────── R-ACC-01         else cannot select
outlet filters per fan 1 or 2 ─────────────────────────── R-ACC-05         else cannot select
airflow > 0:
  size given → frame ÷ 25.4 = 8 / 10 inch ─────────────── R-ACC-02         else cannot select
  no size → smaller fan if it fits the doors ──────────── R-ACC-08
  site air within the operating range ─────────────────── R-ACC-09         else cannot select
  matching outlet filter ──────────────────────────────── R-ACC-03
  airflow per fan = printed 'with outlet filter' value ── R-ACC-04 (no other derating)
  n = ceil(required ÷ per fan) ────────────────────────── R-ACC-06
  n ≤ doors × fans per door? ──────────────────────────── R-ACC-07         else warning + shortfall
  load n × W, n × A (higher of two printed values) ────── R-ACC-10; IP 54 R-ACC-11
plinth asked: height 100 / 200 mm? ────────────────────── R-ACC-12         else warning, no article
  depth 600 → 1 pack per suite ────────────────────────── R-ACC-13         else warning, no article
  corner pieces / front-rear trims not held ───────────── R-ACC-14         warning
door switch + light per door, 24 V load ───────────────── R-ACC-15, -16, -17
```

## Where the sources stop

- The data sheets print the airflow with outlet filter as "74/87" without Hz labels; the 50/60 order is the data
  sheet's own convention ("100/115 m³/h … 50/60 Hz", p.4) — checked in VERIFY.md.
- SK 3239.100 prints two different power and current values (features p.2, tender text p.5) — decision A-3.
- No 300 mm plinth: the plinth sheets name only 100 and 200 mm (decision A-5).
- How many doors a 1000 / 1200 mm section has is not in any held source → `doors` is an input.

## Decisions for the sign-off owner

- **A-1** 8 inch = SK 3239.100 (frame 204 mm)?
- **A-2** One outlet filter per fan by default?
- **A-3** SK 3239.100 load: the higher of the two printed powers (19 W)?
- **A-4** One door switch and one light per door (rather than the light's own integral door switch / one light per section)?
- **A-5** ECI's 1 ft stand: Rittal side trims are 100 / 200 mm only — offer 200 mm, or ask ECI / a fabricated stand?
- **A-6** WNS2503: one 8 inch fan per door gives 15 % / 25 % of the airflow needed — confirm cooling units (enclosure H-5)?
