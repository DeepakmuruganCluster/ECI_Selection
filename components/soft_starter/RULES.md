# Soft starter — G3 Rule sheet

Machine-readable: `rules.yaml` (R-SS-01 … 14). Data (imported by `scripts/import_ic10_3rw52.py` from
SIE-IC10-2026): `ic10_3rw52_ratings.yaml` (18 types, pp. 6/59–6/62), `ic10_3rw52_coordination.yaml`
(54 rows, pp. 6/63–6/65), `ic10_3rw52_ordering.yaml` (144 inline articles, pp. 6/67–6/70).

## Decision flow

```
inputs valid? (FLC > 0, fault_ka, ambient_c; class / protection / versions known)   else invalid
3-ph motor, inline, 200 … 600 V, altitude ≤ 1 000 m, ambient ≤ 60 °C ── R-SS-01 / 14 / 03   else cannot select
starting class: given, else duty (SS-1), else 10A ───────────── R-SS-06
protection: given, else by class (SS-2) ─────────────────────── R-SS-10
mpcb with Class 20E, or mpcb with a line contactor ─────────── R-SS-09 / 11   cannot select
for each type, smallest first:
   IM(class, column ≥ ambient: 40 / 50 / 60) ≥ FLC ─────────── R-SS-03
   IM min ≤ FLC ≤ IM max (inline) ────────────────────────── R-SS-04
   starts/h of the class ≥ required (when given) ─────────── R-SS-07
first that passes ──────────────────────────────────────────── R-SS-05   none → cannot select
tested protection for the type and voltage, Iq ≥ fault ─────── R-SS-08   else cannot select
line contactor: given, else Class 20E with fuses (SS-3) ────── R-SS-11   coil version open → warning
article: terminals, function, Us, Ue in the ordering data ──── R-SS-12   else cannot select
FLC basis guide / not stated ───────────────────────────────── R-SS-13   warning
power loss not printed ──────────────────────────────────────── R-SS-14   info
```

The kW printed in the ordering data are shown as `kw_400v_guide` only (R-SS-02).
