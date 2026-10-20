# Branch MCCB — G1 Scope

**What it decides:** the Siemens SENTRON 3VM molded case circuit breaker (line protection,
thermal-magnetic trip unit) for a branch feeder: the article number, frame, rated current In,
breaking-capacity class with its Icu / Ics at 380–415 V, the overload setting Ir and the
instantaneous trip current Ii.

Source: Siemens catalogue LV 31 · 2018 "SENTRON 3VM Molded Case Circuit Breakers" (held,
`SIE-3VM-LV31`). Page numbers are PDF pages. The catalogue prints section/page numbers
("1/4", "2/5"), not a running number: PDF p.10 = printed 1/4, PDF p.11 = 1/5, PDF p.18 = 1/12,
PDF p.19 = 1/13, PDF pp.26–37 = printed 2/2–2/13 (PDF page − 24). No single offset applies.

Client context: ECI uses 3VM for branch feeders at 415/400 V, fault level typically 50 kA.

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `ib_a` | A | — | load (design) current Ib. Required. |
| `fault_ka` | kA | — | prospective short-circuit current at the breaker. Required. |
| `ambient_c` | °C | — | air temperature around the breaker (inside the panel). Required. |
| `poles` | — | 3 | 3 or 4 |
| `neutral_protection` | — | — | 4-pole only: `none` (without N protection) or `100` (100 % N protection). Not stated on a 4-pole → `none` + warning. |
| `release` | — | TM210 | `TM210` (FTFM, fixed Ir) or `TM220` (ATFM, adjustable Ir) |
| `margin` | — | 1.0 | required In = Ib × margin (RULE parameter, owner decision M-1); must be ≥ 1 |
| `breaking_basis` | — | icu | `icu`: Icu ≥ fault; `ics`: Ics ≥ fault (stricter; owner decision M-2) |
| `voltage_v` | V | 400 | line voltage, 3-phase AC 50/60 Hz |
| `phases` | — | 3 | |
| `altitude_m` | m | 2000 (assumed) | installation altitude |

## Outputs

`article_no`, `frame`, `frame_size_a`, `in_a`, `release`, `poles`, `neutral_protection`,
`breaking_class`, `icu_ka`, `ics_ka`, `ir_range`, `ir_set_a`, `ii_a`, `required_a`,
`let_through_i2t` (always empty: not in the catalogue, see below).

## In scope (v2.0)

- 3VM10 … 3VM14 (16 … 630 A), 3- and 4-pole, line protection TM210 FTFM and TM220 ATFM,
  4-pole with or without 100 % neutral protection, fixed-mounted, lug terminal
  (the only connection the ordering tables list) — 324 article numbers, PDF pp. 28–35
- 3-phase 380 … 415 V AC 50/60 Hz (the catalogue's "380 - 415 V" Icu/Ics row), altitude ≤ 2000 m
- ambient −25 … +50 °C (no derating up to +50 °C)

## Out of scope (refused, or reported as not given)

- **ambient above +50 °C**: the catalogue says the rated current is reduced above +50 °C but
  prints no derating values → cannot select (owner decision M-3)
- **let-through energy I²t and cut-off current**: not printed anywhere in LV 31 (no
  let-through curves or tables) → not given; the cable component must get them from another
  Siemens document (owner decision M-4)
- altitude > 2000 m (p.19 gives factors, but the table's footnotes are inconsistent: "Operating
  current Imax 1)" has no footnote 1) → cannot select
- 1- and 2-pole 3VM11, 220–240 V, 440 V, 500 V and DC ratings (printed, not transcribed)
- starter protection (TM110M / TM120M), switch disconnectors, plug-in / DIN-rail versions,
  RCD add-ons, accessories, other connection technologies
- tripping curves (time-current characteristics): not printed in LV 31
