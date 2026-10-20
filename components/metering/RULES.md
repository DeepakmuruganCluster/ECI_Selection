# Metering — G3 Rule sheet

Machine-readable: `rules.yaml` (R-MTR-01 … 14; 6 MFR, 2 PHYS, 5 RULE, 1 CLIENT). Data:
`pac3220.yaml` (15 rows, SIE-PAC3220), `pac_profinet_module.yaml` (4 rows, SIE-7KM-PN),
`rishabh_ltrp.yaml` (72) + `rishabh_ltrp_conditions.yaml` (3), `rishabh_tw.yaml` (146) + `rishabh_tw_conditions.yaml` (3), `selec_ct.yaml` (65, SELEC-MEAS),
`selec_ct_ambient.yaml` (2, SELEC-CT).

## Decision flow

```
inputs valid? (circuit > 0, make rishabh|selec, class, secondary 1|5, comm, conductor, leads)     else invalid
3P4W, ≤ 690 V, UL-N ≤ 400 V, CT Um ≤ 720 V? ─────────────── R-MTR-01   else cannot select
PAC3220 + PROFINET module (client) ──────────────────────── R-MTR-02   modbus_tcp → warning
meter article pattern / example (confirm) ──────────────── R-MTR-03   info
CT secondary 5 A (1 A: no CT data) ──────────────────────── R-MTR-04   else cannot select
ambient within meter + CT limits ────────────────────────── R-MTR-11   not given → warning
burden = meter 0.3 VA + 2·L·I²·ρθ/A ─────────────────────── R-MTR-07/08  leads not given → warning
primary ≥ circuit (printed primaries) ───────────────────── R-MTR-05   none → cannot select
class ≤ required ────────────────────────────────────────── R-MTR-06   none → cannot select
window fit ──────────────────────────────────────────────── R-MTR-10   none → cannot select; not given → warning
rated VA ≥ burden ───────────────────────────────────────── R-MTR-09   none → cannot select
choose: smallest primary → closest class → smallest VA → family → size ─ R-MTR-12
primary above the first printed one ≥ circuit → warning ── R-MTR-05
qty 1 meter + 3 CTs ─────────────────────────────────────── R-MTR-13
CT type code (Selec nomenclature / Rishabh description) ── R-MTR-14
```

## Physics used (PHYS)

- Lead burden P = 2 · L · I² · ρθ / A; ρθ = ρ20 (1 + α20 (θ − 20)), ρ20 = 1/58 Ω·mm²/m,
  α20 = 0.00393 /K (IEC 60028, annealed copper). At 70 °C ρ = 0.020629 Ω·mm²/m:
  5 m of 2.5 mm² at 5 A = 2.063 VA.
- Window: bar w × t fits a rectangle W × H if (w ≤ W ∧ t ≤ H) ∨ (w ≤ H ∧ t ≤ W); a circle Ø D
  if √(w² + t²) ≤ D; a cable Ø d if d ≤ min(W, H) or d ≤ D.

## What the sources say that matters

- The PROFINET module fits PAC3200 / PAC3220 / PAC4200 only; PAC3120 has no module slot.
- PAC3220 burden is tiny (0.3 VA); the leads dominate (2 VA for 5 m of 2.5 mm²).
- **ECI's 75 × 10 busbar does not pass any Rishabh 630 A CT** (LTRP 4 window 65 × 35): the
  tool moves to TW-6 800/5 A. Selec has no 630 A CT at all; at 800 A only SPCT-140/100 and
  TWCT-D110 take the bar.
- **Rishabh CTs are rated for −25 … +40 °C ambient**; Selec 0 … +50 °C; PAC3220 −25 … +55 °C.

## Decisions for the sign-off owner

MT-1 default class 0.5 · MT-2 wire temperature 70 °C · MT-3 next ratio with a caution ·
MT-4 exact window fit · MT-5 confirm order numbers · MT-6 Rishabh above 40 °C.
