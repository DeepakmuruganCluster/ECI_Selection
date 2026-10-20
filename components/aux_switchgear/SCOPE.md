# Auxiliary switchgear — G1 Scope

Picks the small switchgear from the company's own switchgear database (panel-selector v1,
`data/sources/switchgears`):
- **MCBs** for auxiliary circuits;
- **RCCBs** where a circuit asks for earth-leakage protection;
- **surge arrester**;
- **phase monitoring relay**;
- **isolator**.

Makes held: Schneider, Siemens, Mitsubishi, Legrand and AB (MCB / RCCB); OBO and Phoenix (surge
arresters).

Not in the database, so not checked (warning on every answer): breaking capacity (Icn / Icu) and
the surge arrester's class and protection level. These wait for Siemens LV 10 or the maker's
catalogue.
