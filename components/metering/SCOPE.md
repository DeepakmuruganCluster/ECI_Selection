# Metering — G1 Scope

**What it decides:** for one panel, the Siemens 7KM energy meter with PROFINET and its three
current transformers (CTs): meter type and article-number pattern, PROFINET module article, CT
make / family / size, ratio, accuracy class, rated burden (VA) against the meter + lead burden,
window fit around the busbar or cable, quantity (1 meter + 3 CTs).

Client requirement (ECI WNS2503, `ECI-WNS2503-AUTO` p.1): "Siemens Energy Meter with Profinet
communication for Each Panel - 7KM series with Profinet Communication"; "Rishabh/Selec Current
Transformer"; main incomer 3VA 630 A 55 kA; busbar 75 × 10 mm Cu; 400 V 3-phase 4-wire.

## Sources (page = PDF page)

| Ref | Document | Used | Printed page |
|---|---|---|---|
| `SIE-PAC3220` | PAC3120/PAC3220 Equipment Manual 10/2019 | pp. 10, 15, 17, 48, 73, 75, 98, 99, 106, 107 | PDF − 2 |
| `SIE-7KM-PN` | 7KM PROFIBUS DP / Switched Ethernet PROFINET module manual 01/2020 | pp. 21, 79 (p.15 context) | PDF − 2 |
| `RISH-LTRP` | Rishabh LTRP data sheet REV 08 | pp. 2–11 | = PDF |
| `RISH-TW` | Rishabh TW data sheet Rev D 07/26 | pp. 2–4 | = PDF |
| `SELEC-MEAS` | Selec Electrical Measurement & Protection Catalog 2026 | pp. 9–10 | = PDF |
| `SELEC-CT` | Selec Analog meters & CTs catalogue 2024 (image-only) | pp. 7, 10 (ambient) | PDF − 1 (p.10 = back page, unnumbered) |
| `RISH-XMER` | Rishabh XMER 3-phase CT | not used (one 3-phase unit, not 3 single CTs; out of scope) | — |

## Inputs

| Field | Unit | Default | Notes |
|---|---|---|---|
| `circuit_a` | A | — | current the CTs must carry, e.g. incomer rating. Required. |
| `ct_make` | — | — | `rishabh` or `selec` (client). Required. |
| `voltage_v` | V | 400 | line voltage |
| `system` | — | 3P4W | only 3P4W in scope |
| `accuracy_class` | — | 0.5 | required CT class (RULE param, decision MT-1) |
| `ct_secondary_a` | A | 5 | 1 or 5 (meter); CT data held for 5 A only |
| `busbar_w_mm`, `busbar_t_mm` | mm | — | one bar per phase through the CT; or |
| `cable_od_mm` | mm | — | one cable per phase through the CT |
| `lead_length_m`, `lead_mm2` | m, mm² | — | one-way CT-to-meter wire; omitted → lead burden not checked (warning) |
| `lead_temp_c` | °C | 70 | wire temperature for ρ (decision MT-2) |
| `communication` | — | profinet | `profinet` (client) or `modbus_tcp` (warning) |
| `ambient_c` | °C | — | omitted → temperature limits not checked (warning) |

## Outputs

`meter` (SENTRON PAC3220), `meter_article_pattern` (7KM3220-xBA01-1xA0), `meter_article_example`
(7KM3220-1BA01-1EA0, p.107), `comm_module` (7KM9300-0AE02-0AA0 or none), `ct_make`, `ct_family`,
`ct_size`, `ct_designation`, `ct_ratio`, `ct_primary_a`, `ct_secondary_a`, `ct_class`, `ct_va`,
`ct_window`, `ct_qty` (3), `meter_burden_va`, `lead_burden_va`, `burden_va`.

## In scope

- PAC3220 + PROFINET module; 3P4W ≤ 690 V (UL-N ≤ 400 V), CT Um ≤ 720 V
- Rishabh LTRP 1–9 (72 printed VA/class options, 50 … 7500 A) and TW-1 … TW-6 (146, 50 … 3200 A)
- Selec SPCT (48, 30 … 4000 A) and TWCT (17, 30 … 1600 A), 5 A secondary
- Lead burden (copper), window fit (one bar or one cable per phase), ambient limits

## Out of scope / not covered (refused or reported)

- **1 A secondary CTs**: Rishabh "1A on request" without ratings, Selec 5 A only → cannot select
- **PAC3200 / PAC4200**: accept the module, manuals not held; PAC3120: no module slot
- **Full meter article number**: supply version not decoded in the manual (decision MT-5)
- **Rishabh order codes**: not printed → description only
- **Selec SCCT (split core) and RCT** tables, Rishabh XMER, Selec analog meters: not transcribed
- **Lower burden limit** of the accuracy class (IEC 61869-2 not held), ISF, Ith/Idyn vs fault level
  (Rishabh LTRP Ith 60 × In max 40 kA — not checked against the 55 kA incomer level; needs
  component 7), terminal contact resistance, several bars / cables per phase, clearance in the window
- 3P3W, 1-phase, voltage transformers; ambient outside the printed ranges
- Industry Mall / maker confirmation of order codes (decision MT-5)
