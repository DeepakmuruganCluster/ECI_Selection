# Source documents: status

## Fetched and registered 2026-10-13 (Siemens)

Filed in `sources/pdf/manufacturer/siemens/` (one folder), each with SHA-256 in `register.yaml`.

| Ref | Document | Edition | Unlocks |
|---|---|---|---|
| SIE-IC10-2026 | Catalog IC 10 · 2026, SIRIUS | 2026, 1452 pp | DOL 24 V DC coils, aux contacts, coil VA, link modules |
| SIE-3RW52-MAN | 3RW52 soft starter equipment manual | 04/2022 | 5 soft starter |
| SIE-LV10-2026 | Catalog LV 10 · 2026 | 2026, 1352 pp | 5SY MCB kA, 5SV RCCB, 5SD SPD, 3KD, 3VA |
| SIE-LV10-3VA-2021 | LV 10 chapter, 3VA MCCBs | 10/2021 | 3 MCCB / 8 incomer (cross-check with LV 10 · 2026) |
| SIE-3VA-QSG-2023 | 3VA quick selection guide | 2023 | 3VA cross-check |
| SIE-CU240E2-OI | G120 CU240E-2 operating instructions | 02/2026 | 4 VFD control unit |
| SIE-D31-1-2024 | Catalog D 31.1 | 12/2024 upd. 10/2025 | 4 VFD cross-check |
| SIE-KT10-1-2022 | Catalog KT 10.1, SITOP | **2022** (the 2024 edition was not reachable) | SITOP 24 V supplies |
| SIE-ET200SP-SYS | ET 200SP system manual | 11/2025 | Siemens PLC I/O |
| SIE-CPU1513-MAN | CPU 1513-1 PN equipment manual | 03/2026 | Siemens PLC power budget |
| SIE-S7-200SMART-SYS | S7-200 SMART system manual V2.7 | 08/2022 | Siemens machine PLC (ST40 + EM AE04) |

Already held before: SIE-3VM-LV31 (3VM, 2018), SIE-G120-PROT (G120 protective devices), SIE-PM240-2, SIE-PAC3220, SIE-7KM-PN.

## Still open

- Selectivity Tables Low Voltage Protection Devices 04/2024 (inbox item 20): incomer selectivity, decision RQ-8. Covers 3VA / 3WA upstream, **not 3VM**.
- IEC 61869-2:2012 (inbox item 21): CT accuracy limits, decision RQ-10. Paid standard, supplied by the owner.

- 3VA1/3VA2 equipment manual 09/2026 (SIOS 109986581, 79 MB): optional, LV 10 · 2026 covers the selection data.
- Catalog ST 70 · 2026 (optional cross-check).
- PM240-2 hardware manual, official Siemens copy (A5E33294624B).
- KEI / Polycab cable data, Rittal (out of scope), Schneider CT 158 (third-party mirror: owner's call).
- IEC / IS standards (section E below) — owner's decision to buy.
- Inbox second batch (Phoenix data sheets, Harmony XVC, PSU6200, 7KM / 3RT data sheets) and the VFD company BOM structure.

---

# Original list (researched 2026-10-10)

Nothing below has been downloaded. Sizes come from the download pages (Siemens refuses size checks
from scripts). Each file goes into `sources/pdf/…` and `register.yaml` with its SHA-256 once fetched.

## A · Starters and protection: completes 2 (24 V DC coils) and unlocks 3 MCCB and 5 soft starter

| Document | Edition / ID | Size | URL |
|---|---|---|---|
| Siemens Catalog IC 10 · 2026, SIRIUS Industrial Controls | E86060-K1010-A101-B8-7600, SIOS 109747945 | 88 MB | https://support.industry.siemens.com/cs/attachments/109747945/SIRIUS_IC10_complete_English_2026_202601291128292156.pdf |
| Equipment Manual SIRIUS 3RW52 Soft Starter | 04/2022, SIOS 109753751 | 13 MB | https://support.industry.siemens.com/cs/attachments/109753751/manual_softstarter_3RW52_en-US.pdf |
| Equipment Manual 3VA1 / 3VA2 MCCBs (IEC) | 09/2026, SIOS 109986581 | 79 MB | https://support.industry.siemens.com/cs/attachments/109986581/L1V30964415002A_RS-AA_001_en-US.pdf |
| 3VM MCCBs, Catalog LV 31 · 2018 (old; the only official 3VM document) | 2018 | unknown | https://assets.new.siemens.com/siemens/assets/api/uuid:607ac5d3-e5c1-42d3-bd80-a3194aa12551/version:0/disjuntores-3vm-catalogo-lv31-en.pdf |
| Branch protection and short-circuit strength, SINAMICS G120 (UL / IEC) | SIOS 109801083 | not yet checked | https://support.industry.siemens.com/cs/ww/en/view/109801083 |

## B · Drives: completes 4 VFD

| Document | Edition / ID | Size | URL |
|---|---|---|---|
| SINAMICS G120 with CU240E-2, Operating Instructions | 02/2026, SIOS 109818082 | 20 MB | https://support.industry.siemens.com/cs/attachments/109818082/G120_CU240E2_op_instr_0226_en-US.pdf |
| Catalog D 31.1, SINAMICS built-in units | 12/2024 upd. 10/2025, SIOS 109755273 | 53 MB | https://support.industry.siemens.com/cs/attachments/109755273/motion-control-D31-1-complete-english-2024-12_update-10-2025.pdf |
| PM240-2 Hardware Installation Manual, official Siemens copy (replaces our third-party copy) | 07/2022 | not yet checked | support.industry.siemens.com (search A5E33294624B) |

## C · Cables, short circuit, enclosure: unlocks 6, 7, 8 (partly), 9

| Document | Edition / ID | Size | URL |
|---|---|---|---|
| KEI Technical Hand Book (ratings, derating, mV/A/m: contents to confirm) | 2023 | 7.7 MB | https://www.kei-ind.com/wp-content/uploads/2022/06/all-technical-hand-book.pdf |
| Polycab LT cable catalogue v9 (XLPE to IS 7098-1) | v9 | unknown (link may be dead) | https://cms.polycab.com/media/cxibmmjk/final_lt-cable-catalog_v9_ord-10054.pdf |
| Rittal Technical System Catalogue, Climate Control | 3124300 EN | unknown | https://www.rittal.com/imf/none/3_8419/3124300_Technical_system_catalogue_EN/ |
| Schneider Cahier Technique 158 (short-circuit) | **third-party mirror**, June 2000 reprint; se.com was under maintenance | 0.7 MB | https://sti.eduscol.education.fr/sites/eduscol.education.fr.sti/files/ressources/techniques/3357/3357-ect158.pdf |

## D · Control power and auxiliary switchgear: unlocks 10, 11

| Document | Edition / ID | Size | URL |
|---|---|---|---|
| Catalog KT 10.1, SITOP | 2024, SIOS 109745655 | 23 MB | https://support.industry.siemens.com/cs/attachments/109745655/SITOP_KT10_1_complete_English.pdf |
| ET 200SP System Manual | 11/2025, SIOS 58649293 | 16 MB | https://support.industry.siemens.com/cs/attachments/58649293/et200sp_system_manual_en-US_en-US.pdf |
| S7-1500 CPU 1513-1 PN Equipment Manual | 01/2026, SIOS 110000616 | 1.5 MB | https://support.industry.siemens.com/cs/attachments/110000616/s71500_cpu1513_1_pn_dtc_manual_en-US_en-US.pdf |
| Catalog LV 10 · 2026 (5SY MCB, 5SV RCCB, 5SD SPD, 3KD, 3VA) | SIOS 109482234 | 109 MB | https://support.industry.siemens.com/cs/attachments/109482234/LV10_2026_EN_202601160649587174.pdf |
| Catalog ST 70 · 2026, SIMATIC (cross-check only, optional) | SIOS 109744167 | 86 MB | https://support.industry.siemens.com/cs/attachments/109744167/simatic-st70-complete-english-2026.pdf |

## E · Standards to buy (your decision; Claude cannot buy or register)

| Standard | Edition | IEC webstore price |
|---|---|---|
| IEC 60364-5-52 (cables) | 2009+AMD1:2024 | CHF 680 |
| IEC 60909-0 (short circuit) | **2026, Ed. 3.0: new, replaces 2016** | CHF 380 |
| IEC TR 60909-4 (worked examples: the test oracle for 7) | 2021 | CHF 380 |
| IEC 60364-5-54 (earthing / PE) | 2011+AMD1:2021 | CHF 570 |
| IEC 61439-1 (assemblies, busbar) | 2020 | CHF 808 (redline) |
| IEC TR 60890 (enclosure heat) | 2022 | CHF 570 (redline) |
| IEC 60947-4-1 (contactors, starters) | 2023 | CHF 475 |

**BIS alternatives:** IS 732 and IS 3961 (cable current ratings) are **free** after a free registration
at standardsbis.bsbedge.com. The download needs a captcha, so you have to do that step yourself.
IS/IEC adoptions (e.g. IS/IEC 61439-1) need a paid subscription.
