# Panel assembly — G3 Rule sheet

Machine-readable: `rules.yaml`. **No data files**: the assembly only chains components
(motor FLC → DOL starter / VFD → cable; drive losses → enclosure). Every value it shows
comes from a component result, which cites its own source page.

| Id | Rule | Authority |
|---|---|---|
| R-PNL-01 | load list format, unique tags, unreadable line → invalid | RULE |
| R-PNL-02 | components in order; a refusal stops the line and becomes an open point; no substitutes | RULE |
| R-PNL-03 | DOL feeder cable checked with In = MPCB setting (FLC) | RULE |
| R-PNL-04 | VFD motor cable: overload protection by the drive (Protective Devices p. 3) | MFR |
| R-PNL-05 | drives derated at the panel internal temperature; the enclosure must hold it at the site ambient | RULE |
| R-PNL-06 | BOM counts installed units; heat counts running units + one Control Unit per installed drive | RULE |
| R-PNL-07 | heat only from sourced losses; others listed and heat marked incomplete | RULE |
| R-PNL-08 | parts from components not built yet are listed as not selected; panel incomplete | RULE |
| R-PNL-09 | every component warning carried to the open points | RULE |

Single-phase lines (`ph=1`) use 230 V unless `v=` is given (decision P-3).
