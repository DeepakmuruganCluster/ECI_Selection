# Soft starter — G6 Verification

`scripts/verify_soft_starter.py` re-reads every value of the three 3RW52 tables from the PDF with a second
text engine (pypdfium2; the importer uses pdftotext -layout) and checks each one is printed on the page it
cites, on its own type's line:

- ratings: 18 types × (IM Class 10A / 10E / 20E at 40/50/60 °C + inline range + inside-delta range) = 90 values
- ordering: 144 articles, each with its spring-loaded twin, Ie at 40 °C and kW at 400 V on the same line
- coordination: 54 rows (3RV2 / 3VA with Iq; 3NA3 and 3NE1 fuses with the line contactor type)

Result 2026-10-14: **288 values checked, 0 mismatches.** Page 6/60 was also compared with the rendered image.
