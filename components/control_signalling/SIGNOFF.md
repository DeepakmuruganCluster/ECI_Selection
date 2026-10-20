# Control and signalling — G7 Sign-off

Sign-off owner: **Deepak Murugan**
Status: **awaiting sign-off** (G1–G6 complete 2026-10-11). The review and sign-off are done in the web app (Review & sign off → 16 · Control and signalling).

## Gate record

| Gate | Evidence | State |
|---|---|---|
| G1 Scope | `SCOPE.md`: latching relay per DOL output, slim relay per other output (24 V DC coils), CP push-in terminals with end plates / end clamps / markers / short links, Rittal door switch + light per door | done |
| G2 Source pack | 9 data files, 71 rows: Finder S38 (pp. 5, 12, 13, 18, 20), S39 (pp. 6, 21, 22, 29, 30, 33), S13 (pp. 5, 7, 8, 11), S40 and S20 (rejected candidates, pp. 3–5, 9, 10), Connectwell CW-ES (pp. 44–45), CW-TB (pp. 10, 12–14, 283, 289, 296, 297), Rittal 4127010 (p.2), 4140820 (pp. 2–4). Multi-column tables checked on the page images. | done (editions of 2026-10-11, see C-9) |
| G3 Rule sheet | `RULES.md`, `rules.yaml`: 19 rules (10 MFR, 8 RULE, 1 CLIENT) | done; decisions C-1 … C-9 |
| G4 Golden cases | `golden/cases.yaml`: 45 cases written before the code | done |
| G5 Build | `select.py`, `tests/test_control_signalling.py` | **45/45 golden pass**; every rule exercised; jumper arithmetic checked for 2 … 119 terminals; module codes agree with relay/socket/coil code |
| G6 Verify | `VERIFY.md` (`scripts/verify_control_signalling.py`) | independent re-extraction (pypdfium2 text + pdfplumber word positions): 305 values, 16 printed statements, 5 absence searches: **0 unexplained mismatches** |

## G6: differences found and resolved

1. **CA103 end clamp width** — the script first read 9 mm (it took the word "CA103" from the paragraph above the table). Page image p.283: CA103 = 6 × 41 mm. **Script was wrong**; fixed to locate the header line. Data unchanged.
2. **13.12 wiring row** — the file held a description, not printed text (the "+ (A1) / − (A2)" labels are drawn, not text). **File corrected** (description moved to `note`); the script checks "Type 13.12", "Set", "Reset", polarity read on the image.
3. **Rittal 4127010 statement** — the file paraphrased the printed sentence. **File corrected** to the printed wording.
4. **MC3.5 marker card** — the script cut the row at one third of the page width and lost the last column. **Script was wrong**; data (120 tags, 3.5 mm) confirmed on the image p.289.

## Observations

1. **The only held relay that latches on a SET and releases on a RESET input is Finder 13.12** (Call & Reset, 24 V AC/DC). It needs **two PLC outputs per DOL** and pulses of 100 ms … 10 s. Finder 13.01 / 20 series step relays toggle; 40.xx.6 bistable relays reset by reversing the coil current (S40 p.10); Finder 38/39 and **Connectwell have no latching relay**.
2. **WNS2503:** BIO_UF 36 DOL + 44 other outputs = **116 DO needed vs 80 in ECI's table**; RO 39 + 57 = **135 vs 96** (reading ECI's count as one DO per DOL). Either ECI means something else by "Latch Relay" (C-1) or the DO count must rise (C-2).
3. **Connectwell CSR slim relays carry no AC-15 / DC-13 rating** → refused for contactor coils (C-5).
4. Finder 38 AC-15 = 300 VA at 230 V (1.30 A); DC-1 0.2 A at 110 V DC; DC-13 needs a diode across the load.
5. **CP1.5 accepts only 1.0 mm² with a ferrule**: 1.5 mm² control wiring with ferrules needs CP2.5.

## Decisions (answer in the web app)

C-1 meaning of "Latch Relay" · C-2 DO count · C-3 spare relays · C-4 Finder series · C-5 Connectwell without AC-15 rating · C-6 conductor / terminal type · C-7 switch + light per door · C-8 strips and end clamp · C-9 confirm article numbers.
