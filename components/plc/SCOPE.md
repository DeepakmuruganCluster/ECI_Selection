# PLC and I/O modules — G1 Scope

Picks an Omron CP2E CPU and its CP1W digital expansion modules from the AutoBOM databases
(`OWN-AB-PLC`, `OWN-AB-PLCIO`), following the AutoBOM logic sheet: 40 % spare, smallest CPU, at
most its expansion-module limit, next CPU if it doesn't fit. It also works out the PLC's 24 V
current, which feeds the 24 V supply (control power).

Not in scope yet:
- Analog, temperature and communication modules.
- NX1P CPUs and NX modules (incomplete rows).
- Siemens S7-1500 / ET 200SP (they wait for the Siemens manuals).
- Fieldbus to the drives: the database records none, so the tool refuses.
