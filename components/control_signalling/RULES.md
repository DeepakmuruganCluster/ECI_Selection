# Control and signalling — G3 Rule sheet

Machine-readable: `rules.yaml` (R-CTL-01 … 19: 10 MFR, 8 RULE, 1 CLIENT). Data (PDF pages):
`finder_s38.yaml` (pp. 5, 12, 13, 18, 20), `finder_s39.yaml` (pp. 6, 21, 22, 29, 30, 33),
`finder_s13.yaml` (pp. 5, 7, 8, 11), `finder_s40.yaml` (pp. 4, 5, 9, 10 — rejected),
`finder_s20.yaml` (pp. 3, 4 — rejected), `connectwell_es.yaml` (pp. 44–45),
`connectwell_tb.yaml` (pp. 10, 12–14, 283, 289, 296, 297), `rittal_door_switch.yaml` (p.2),
`rittal_system_light.yaml` (pp. 2–4).

## Decision flow

```
inputs valid? (counts ≥ 0, something to select, load needs V and A, I/O terminals need a size)  else invalid
coil 24 V DC? ──────────────────────────────────── R-CTL-02   else cannot select
makes held? (Phoenix not held) ───────────────────── R-CTL-03   else cannot select
DOL outputs → latching relay 13.12.0.024.0000 ────── R-CTL-04   Connectwell: none → cannot select
other outputs → slim relay (38 / 39 / CSR) ───────── R-CTL-06
quantities (+ spare %) ───────────────────────────── R-CTL-07
PLC outputs needed = 2 × latching + slim ─────────── R-CTL-05   > client's DO count → warning
contact load within rating ───────────────────────── R-CTL-08   not rated → cannot select; not given → warning
DC-13 on Finder → diode across the load ──────────── R-CTL-09   warning
panel temperature within relay range ─────────────── R-CTL-10   outside → cannot select; not given → warning
accessories: separators, markers (MFR), jumpers ──── R-CTL-11, R-CTL-12
terminals: smallest CP block for size and current ── R-CTL-13   none → cannot select
end plates / end clamps / markers / short links ──── R-CTL-14 … 17
Rittal switch + light per door ────────────────────── R-CTL-18
notes: confirm article numbers; not covered items ── R-CTL-19, R-CTL-01
```

## What the catalogues say that matters

- **Only one held relay latches on a SET and releases on a RESET input: Finder 13.12.** It needs two
  PLC outputs and pulses (100 ms … 10 s), not a held output. For WNS2503 this doubles the DOL outputs:
  BIO_UF 36 DOL → 72 DO, RO 39 DOL → 78 DO (ECI counts 80 and 96 DO in total, incl. spare).
- **Connectwell makes no latching relay**, and its slim relay has **no AC-15 or DC-13 rating** — it
  cannot be checked for a contactor coil load.
- Finder 38/39 slim relays: AC-15 300 VA at 230 V AC = 1.30 A; DC-1 6 A at 24 V, but only 0.2 A at
  110 V DC. A 24 V DC contactor coil (DC-13) needs a diode across the coil.
- CP1.5 takes only 1.0 mm² with a ferrule: a 1.5 mm² control wire with ferrule needs CP2.5.
- End plates: at the end of each group of identical blocks and at every size change; end clamps on
  both sides of each assembly.

## Decisions for the sign-off owner

- **C-1** What ECI means by "Latch Relay": set/reset latching relay (Finder 13.12, two DO per DOL) or
  a normal slim relay with a latching (lockable) test lever. Ask ECI.
- **C-2** DO count: with 13.12, ECI's DO count is short (BIO_UF needs ≥ 72 DO for DOLs alone).
- **C-3** Spare relays: 0 % (default; ECI's DO count already has spare channels) or a percentage.
- **C-4** Finder slim relay: 38 series (default) or 39 MasterBASIC; screwless (default) or box clamp.
- **C-5** Connectwell slim relays for contactor coils: refused (no AC-15/DC-13 rating) until
  Connectwell confirms a rating.
- **C-6** Terminal conductor: flexible with ferrule (default); CP push-in (default) or CX spring clamp.
- **C-7** One door switch and one light per door.
- **C-8** Terminal strips: one per terminal type (default, conservative on end clamps); end clamp CA103.
- **C-9** Confirm all article numbers with the suppliers before ordering.
