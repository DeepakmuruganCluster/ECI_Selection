# Load-list import (ECI WNS2503) — G3 Rule sheet

Machine-readable: `rules.yaml`. **No data files.** The component reads the client's Word file
(`ECI-WNS2503-LOADS`, SHA-256 checked by `core.provenance.check_reference`) at run time with the
standard library (zipfile + XML) and cites every value as *table T row R*. The equipment PDF
(`ECI-WNS2503-EQUIP`) is read with pdfplumber, for the cross-check only.

| Id | Rule | Authority |
|---|---|---|
| R-LL-01 | every row read from the registered Word file, values copied as written, cited table/row; unreadable row left out and listed | CLIENT |
| R-LL-02 | panel = the panel named in the next 'Panel Total' row of the section | RULE |
| R-LL-03 | starter and quantity from the Req column holding the count; must agree with the section header | CLIENT |
| R-LL-04 | 'Heater' → HEATER line; 'Extra' / 'Spare' → spare starters (kept, flagged) | RULE |
| R-LL-05 | phases / voltage from 'Operating Voltage'; 1PH 230V → `ph=1 v=230`; 3PH 400V not written | CLIENT |
| R-LL-06 | client Amps / MPCB range kept for comparison only, never `flc=` | RULE |
| R-LL-07 | no cable length invented; `cable=` only from `default_cable_m`, flagged as the user's | RULE |
| R-LL-08 | standby = 0 unless `standby_per_group` given; tag groups always listed | RULE |
| R-LL-09 | repeated Instrument ID kept as TAG_2, flagged | RULE |
| R-LL-10 | Instrument ID must match Group Marking | CLIENT |
| R-LL-11 | row arithmetic: Total KW = KW × Total Qty; Total Qty = Req count = number of tags | PHYS |
| R-LL-12 | panel total rows = sum of the rows (Req counts; Total Qty compared too) | PHYS |
| R-LL-13 | garbled cells repaired only by splitting text that is there; every repair listed | RULE |
| R-LL-14 | client current inside client MPCB range | PHYS |
| R-LL-15 | cross-check with the equipment PDF (tag, kW, Amps, qty, starter count, supply, totals) | CLIENT |

How the document is laid out (what R-LL-02 / R-LL-03 rely on): one long table split over two Word
tables (page break). Three sections, 'VFD Requirement', 'Soft Starter Requirement', 'DOL Requirement'.
Inside each section the BIO/UF rows come first and end with a 'BIO/UF Panel Total …' row, then the RO
rows end with 'RO Panel Total …'. The equipment PDF confirms the split: there, every row sits under
'BIO/UF Panel Requirements' or 'RO PANEL REQUIREMENTS', and all 67 rows land in the same panel.
