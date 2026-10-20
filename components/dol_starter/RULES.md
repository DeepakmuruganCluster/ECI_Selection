# DOL starter — G3 Rule sheet

Machine-readable: `rules.yaml`. Data: `data/siemens_type2_400v.yaml` (39 rows, pp. 28–29),
`data/siemens_link_modules.yaml` (Table 2-1, p. 22).

## Decision flow

```
inputs valid? (FLC > 0, fault_ka given, IE class known)            else invalid
3-ph, 400 V, motor? ─────────────────────────────── R-DOL-01        else cannot select
coil 230 V AC? ──────────────────────────────────── R-DOL-07        else cannot select
Ik ≤ 150 kA? ────────────────────────────────────── R-DOL-06        else cannot select
0.11 A ≤ FLC ≤ 100 A? ───────────────────────────── R-DOL-10        else cannot select
rows whose range (IE1/2 or IE3/4 column) holds FLC ─ R-DOL-02
   drop IE3 rows with a start-current limit unless Ia given and ≤ limit ── R-DOL-03
   none left → cannot select
pick largest margin; tie → earlier row ──────────── R-DOL-04
contactor from the same row ─────────────────────── R-DOL-05
link module by size (same size only) ────────────── R-DOL-08        mixed size → warning, none
FLC basis guide / unknown ───────────────────────── R-DOL-09        warning
```

## Rules

| Id | Rule | Authority | Note |
|---|---|---|---|
| R-DOL-01 | 3-ph motor, 400 V AC only | MFR | table title "AC 400 V" |
| R-DOL-02 | FLC within the IE1/IE2 or IE3/IE4 range | MFR | IE3/IE4 maxima are lower because of the higher inrush |
| R-DOL-03 | starting-current limit on two rows | MFR | 3RV2021-4EA10 (≤ 256 A) and 3RV2032-4RA10 (≤ 720 A), IE3/IE4 cell |
| R-DOL-04 | largest margin, tie → table order | RULE | keeps the setting clear of both range ends so a nameplate correction still fits |
| R-DOL-05 | contactor from the same row | MFR | Type 2 is only proven for the tested pair |
| R-DOL-06 | Iq 150 kA ≥ Ik | MFR | table title |
| R-DOL-07 | 230 V AC coil only | MFR | footnote 2; other coils need a coil-code source |
| R-DOL-08 | link module, same size only | MFR | Table 2-1 has no S00 MPCB + S0 contactor row |
| R-DOL-09 | guide / unknown FLC basis → warning | MFR | footnote 1 |
| R-DOL-10 | 0.11 … 100 A | RULE | larger feeders need 3VA + 3RT1 (later component) |
| R-DOL-11 | IE class missing → IE3 limits | RULE | conservative: lower maximum setting |
| R-DOL-15 | surge suppressor asked → the varistor for the contactor's size and coil voltage | MFR | IC 10 · 2026 p.3/96 |
| R-DOL-14 | client MPCB setting range given (RFQ) → that Type 2 row and its contactor; FLC outside → warning; no row → refused | RULE | owner 2026-10-18: the RFQ value wins, flag if unsafe |

## Decisions for the sign-off owner

- **E-1** Is "largest margin" the right tie-break, or should it be "smallest size that covers the FLC" (cheaper, narrower panel)?
- **E-2** For an S00 MPCB + S0 contactor (e.g. 3RV2011-1GA10 + 3RT2024), is wiring without a link module acceptable, or should we source the right link module (IC 10)?
- **E-3** ECI uses 24 V DC coils. Can I download the Siemens IC 10 catalogue (or the 3RT2 data sheets) into `sources/pdf/manufacturer/siemens/` to source the coil codes and the DC link-module versions?
