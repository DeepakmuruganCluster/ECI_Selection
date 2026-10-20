# VFD — G3 Rule sheet

Machine-readable: `rules.yaml`. Data (all from the PM240-2 manual 07/2022; PDF pages):
`pm240_2_400v.yaml` (21 modules, pp. 99–105), `pm240_2_derating.yaml` (pp. 118–119),
`pm240_2_cable_lengths.yaml` (pp. 62–63), `pm240_2_reactors.yaml` (pp. 146, 163, 165).

## Decision flow

```
inputs valid? (kW, FLC, ambient, cable length, fault level)          else invalid
3-ph, 380–480 V, ≤ 1000 m? ─────────────────────── R-VFD-01           else cannot select
Ik ≤ 100 kA? ───────────────────────────────────── R-VFD-06           else cannot select
ambient → next table temperature (≤ 60 °C) ──────── R-VFD-03           else cannot select
duty → LO or HO ───────────────────────────────── R-VFD-02
first module: rated kW ≥ motor kW and derated current ≥ FLC ── R-VFD-04  none → cannot select; upsized → warning
motor kW ≥ 25 % of module kW ───────────────────── R-VFD-05           else cannot select
protection: Siemens-listed fuse / MSP / breaker ── R-VFD-07, 14, 15, 16  none qualifies → cannot select
line reactor (FSA–FSC: client rule or uk < 1 %) ── R-VFD-08           uk unknown → warning
cable length → 0 / 1 / 2 output reactors ───────── R-VFD-09, R-VFD-10  too long → cannot select
notes: cable losses < 5 % (R-VFD-11), CU not selected (R-VFD-12), FLC basis (R-VFD-13)
```

## Things the manual says that v1 had wrong

- **FSA–FSC, shielded cable:** an output reactor does **not** extend the length. It is 150 m either way, and only 100 m with a reactor at 440–480 V. A reactor only helps unshielded cable (225 m).
- **FSD–FSF:** longer cables need **two** output reactors in series, and only on unfiltered drives.
- **FSA–FSC:** the supply impedance must be 1–4 %. Below 1 %, a line reactor is needed.

## Decisions for the sign-off owner

- **V-1** Derating uses the next table temperature, with no interpolation (e.g. 47 °C is taken as 50 °C). Accept?
- **V-2** 3VM is not a Siemens-listed protective device for PM240-2 (Protective Devices 07/2021). Should drive feeders use only listed devices?
- **V-3** The PM240-2 manual we hold is a third-party copy (same edition). Replace it with the official Siemens download?
- **V-4** For ECI, which supply impedance (uk) should the tool assume when it is unknown? Or keep the warning and the client's "line reactor up to 15 kW" rule?
