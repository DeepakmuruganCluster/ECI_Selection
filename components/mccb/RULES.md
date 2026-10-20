# Branch MCCB — G3 Rule sheet

Machine-readable: `rules.yaml`. Data (all from Siemens LV 31 · 2018; PDF pages):
`3vm_breaking_capacity.yaml` (12 frame/class rows, Icu/Ics at 380–415 V, pp. 10–11; scope
conditions pp. 9, 19), `3vm_trip_ratings.yaml` (43 In/Ir/Ii rows, pp. 28, 30),
`3vm_line_protection_articles.yaml` (324 article numbers, pp. 28–35).

## Decision flow

```
inputs valid? (Ib > 0, fault kA > 0, ambient given, poles, release, neutral, margin ≥ 1)     else invalid
3-phase 380–415 V, ≤ 2000 m, 3/4-pole? ─────────────── R-MCCB-01        else cannot select
ambient −25 … +50 °C? ───────────────────────────────── R-MCCB-04        else cannot select
required = Ib × margin ──────────────────────────────── R-MCCB-02
variant (poles, TM210/TM220, neutral) ───────────────── R-MCCB-08        4-pole, neutral not stated → warning
In ≥ required (≤ 630 A)? ────────────────────────────── R-MCCB-03        else cannot select
Icu (or Ics) ≥ fault? ───────────────────────────────── R-MCCB-05/06     else cannot select
choose smallest In → smallest frame → lowest class ──── R-MCCB-07
Ir setting (TM220 range) / Ii ──────────────────────── R-MCCB-09, R-MCCB-10
notes: I²t not in catalogue (R-MCCB-11); confirm article numbers, 2018 edition (R-MCCB-12)
```

## What the catalogue says that matters

- **At 50 kA only class M works** (Icu 55 kA, 3VM11–3VM14). 3VM10 stops at 36 kA (class S).
  So for ECI (50 kA) the smallest breaker is a 3VM11, even for a 16 A feeder.
- **Ics of class M is 41 kA**, below 50 kA. If the client wants Ics ≥ fault level, no 3VM
  qualifies at 50 kA (decision M-2).
- **No derating up to +50 °C.** Above that the catalogue gives no values.
- **No let-through I²t, cut-off current or tripping curves** in this catalogue.
- The article number is printed in full for every orderable combination, so it is looked up,
  not assembled. Gaps ("--") are real: e.g. 3VM12–3VM14 have no class N, 3VM10 has no TM220
  and no neutral-protected version, 4-pole TM220 3VM12–14 has no class N.

## Decisions for the sign-off owner

- **M-1** Margin on the load current (default 1.0, i.e. In ≥ Ib).
- **M-2** Breaking capacity basis: Icu (default) or Ics.
- **M-3** Above 50 °C: refuse until Siemens derating data is held.
- **M-4** I²t for the cable check: fetch a Siemens source.
- **M-5** Confirm 2018 article numbers against the current Industry Mall.
- **M-6** Default trip unit TM210 (fixed) or TM220 (adjustable).
- **M-7** Choice rule: smallest In / frame / lowest class, or a fixed class for the client.
