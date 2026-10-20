# Load-list import (ECI WNS2503) — G1 Scope

**What it does:** reads the client's own load list (ECI *VFD_SS_DOL Panel Specification* Rev02,
a Word file, `ECI-WNS2503-LOADS`) **directly at run time** and turns every motor / heater row into
one line of the panel load-list format (component 12):

`TAG kW STARTER [qty=n] [standby=n] [ph=1 v=V] [cable=m]`

Every value on a line comes from one cell of the Word table, cited as *table T row R* (Word has
no pages; T and R count from 1 as Word shows them, the header row of table 1 is row 1). Nothing is
added from outside the document except two values the user types and the tool labels as theirs:
a cable length (`default_cable_m`) and a standby count per A/B group (`standby_per_group`).

It also checks the document against itself (row arithmetic, panel total rows, Instrument ID vs
Group Marking, client current vs client MPCB range) and against the client's complete equipment
list (`ECI-WNS2503-EQUIP`, PDF, 3 pages), and lists every difference and every repair of a
garbled cell as a warning with the table/row reference.

## Inputs

| Field | Notes |
|---|---|
| `project` | `WNS2503` (the only client load list held) |
| `panel` | `all`, `BIO_UF` or `RO` |
| `default_cable_m` | optional. The client gives no cable lengths. If given, written as `cable=` on every line and flagged as the user's value. |
| `standby_per_group` | optional. The client gives total quantities only. If given, that many units of each A/B… group are written as standby (interpretation, flagged). Default: all running. |
| `tag` | optional. Returns only that row (flat values: kW, starter, qty, phases, client current, line). |

## Outputs

`load_list` (text, ready for the panel tab), `rows` (every field with its table/row), the panel
total checks, and counts (`n_rows`, `n_dol`, `n_vfd`, `n_ss`, `n_heater`, `n_spare`, `n_single_phase`,
`units_*`, `n_duplicate_tags`, `n_tag_mismatch`, `n_repairs`, `n_flc_outside_range`,
`n_pdf_differences`, `n_total_mismatch`).

## Out of scope

- Instruments, PLC I/O and signals (the PDF's other rows): component 10.
- Selecting anything: the load list goes to the panel component (12).
- The client's current (Amps) and MPCB range are **never** written as `flc=`; they are formula
  values from the client, kept for comparison only (R-LL-06).
- Any other client document format: a new client needs its own reader and golden cases.
