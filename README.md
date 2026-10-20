# Panel Selector v2 — accuracy first

Rebuild of `../panel-selector` (v1). Plan: `../panel-selector/docs/rebuild/PLAN.md`.

**Principles:** no source, no data · fail closed · accuracy measured against an
independent oracle · one component released (signed off) before the next starts.

## Reviewing and signing off (no technical skills needed)

1. Double-click **`Start Panel Selector.command`** in this folder. A window opens; leave it open. Your browser shows the **Review & sign off** page.
2. Pick a component. Step 1 shows whether every automatic check gives the right answer.
3. Step 2 shows the Siemens pages. Press a **Try it** button, or type a row from the page yourself, and compare the answer with the page.
4. Step 3: answer the decisions (the recommended answer is pre-selected).
5. Step 4: type your name, tick the box and press **Sign off**. The record (name, date, decisions, and a fingerprint of the data) is saved in `components/<name>/signoff.json`. If the data changes later, the page says the sign-off is out of date.

If macOS says the file can't be opened: right-click it → **Open** → **Open** (only needed the first time).

## Components

| # | Component | Status |
|---|---|---|
| 1 | [Motor FLC](components/motor_flc/) | G1–G6 done, awaiting sign-off |
| 2 | [DOL starter](components/dol_starter/) · [company feeder kits](components/feeder_kit/) (Propel DOL / conveyor / star-delta, indicative prices) | G1–G6 done, awaiting sign-off; 24 V DC coils need IC 10 (inbox) |
| 3 | [Branch MCCB 3VM](components/mccb/) | G1–G6 done, awaiting sign-off; no let-through I²t in the catalogue |
| 4 | [VFD](components/vfd/) incl. Siemens-listed protection, Control Unit, BOP-2, memory card | G1–G6 done, awaiting sign-off; CU / BOP / memory card from the company's ECI-VFD-Selection logic and database (cross-checked: 42 drive articles match the Siemens manual) |
| 5 | Soft starter | **blocked**: 3RW52 manual (inbox #2). Star-delta: built from the company kits (feeder_kit) |
| 6 | [Motor cable](components/cable/) (Polycab / KEI) | G1–G6 done, awaiting sign-off; trays / grouping need IEC 60364-5-52 or IS 3961 |
| 7 | Short-circuit level | **blocked**: IEC 60909-0:2026 + TR 60909-4 (to buy) |
| 8 | Incomer and busbar | **blocked**: 3VA manual (inbox #3) + IEC 61439-1 |
| 9 | [Enclosure heat and cooling](components/enclosure/) | **out of scope** for the BOM (owner, 2026-10-11); kept for reference |
| 10 | [Control power](components/control_power/): 24 V DC supply · [PLC and I/O modules](components/plc/) (Omron CP2E + CP1W) | G1–G6 done, awaiting sign-off; AutoBOM databases (197 supplies in 4 makes, 21 CP2E CPUs, 16 CP1W modules) + template method; the PLC's 24 V current is calculated. Siemens PLC, analog I/O, network and UPS still **blocked** on the Siemens manuals |
| 11 | [Auxiliary switchgear](components/aux_switchgear/) (MCB, RCCB, surge arrester, phase monitoring relay, isolator) | G1–G6 done, awaiting sign-off; own switchgear database from v1 (5 makes); kA and SPD class not in it (warning) |
| 12 | [Panel assembly](components/panel/) | G1–G6 done, awaiting sign-off; chains 1, 2, 4, 6, 9 |
| 13 | [Client-specified items](components/client_items/) | G1–G6 done, awaiting sign-off; RO length 7400 ≠ 7800 mm, 9 quantities not stated |
| 14 | [Load-list import](components/load_list/) (ECI Word list, PDF cross-check) | G1–G6 done, awaiting sign-off |
| 15 | [Metering](components/metering/) (PAC3220 + 7KM PROFINET module, Rishabh / Selec CTs) | G1–G6 done, awaiting sign-off |
| 16 | [Control and signalling](components/control_signalling/) (Finder relays, Connectwell push-in terminals) | G1–G6 done, awaiting sign-off; Phoenix and tower lamp wait for the inbox; door switch / light out of scope with enclosures |
| 17 | Earthing and PE (earth bar, instrument earth bar, PE conductors) | waiting for sources: IEC 60364-5-54 (to buy) or the cable maker's PE tables |
| 18 | [Enclosure accessories](components/enclosure_accessories/) | **out of scope** for the BOM (owner, 2026-10-11); kept for reference |
| 19 | [Internal wiring](components/internal_wiring/) (Lapp) | G1–G6 done, awaiting sign-off |
| 20 | Heater feeder | **out of scope** (owner, 2026-10-11) |
| 21 | [Project BOM with options](components/project/) | G1–G6 done, awaiting sign-off; ECI BIO_UF / RO with an Options sheet |
| 22 | [Requirement](components/requirement/): describe the machine in plain words (ClusterVise step 1) | G1–G6 done, awaiting sign-off; one or more motors; runs every built component (feeders, I/O, relays, terminals, wiring, 3VM incomer, metering) after you confirm; IP / outdoor / budget recorded only (owner, 2026-10-12) |
| 23 | [I/O list](components/io_list/) (PLC signals per motor) | G1–G6 done, awaiting sign-off; our signal standard (decisions IO-1 … IO-3) |
| 24 | [Field devices](components/instruments/) (instruments, switches, valves from the ECI list) | G1–G6 done, awaiting sign-off; 230 V instrument / valve MCBs, fused terminals per analog loop, 24 V load, ECI I/O arithmetic and tag-range checks; instrument and valve currents asked |
| 25 | [Control circuit](components/control_circuit/) (control transformer, MCBs, E-stop, reset, phase lamps) | G1–G6 done, awaiting sign-off; company transformer sizes 150–1500 VA at 1.5 × load; coil and lamp VA asked (Siemens IC 10 / data sheets) |
| — | Prices / budget check | **skipped** (owner, 2026-10-12): no price source held |

**Two levels:** a *fresher* walks step by step (explanations open, cautions to acknowledge, basic changes only); an *experienced* designer can jump to any step, see everything on one page, accept the rest in one go and change the panel defaults (drive protection, cable make / installation, DOL source Siemens or company kit, company accessories).

**Company samples** (`sources/Sample complete`): DOL Motors BOM, standard panel costing sheet and the drawing set AVELCPSDL08WPLC. They give the feeder kits, star-delta, indicative prices (INR) and the document conventions (drawing index, tag names, SAP codes, wire colours). The VFD BOM structure has not arrived yet.

**Assistant (Claude API, optional):** in *Describe the machine* the designer can reply in plain words; the assistant (`core/assistant.py`, Claude Opus 5.5, low effort, server-side refusal fallback on) explains and asks the next questions, and *proposes* answers, each quoting the designer's words. The server drops any proposal whose words are not in the message or whose input the tool doesn't ask for; the designer ticks the ones to use, and the deterministic engine still selects everything. Key: `ANTHROPIC_API_KEY` (+ `ANTHROPIC_WORKSPACE_ID` for a key not scoped to a workspace) in the environment or `~/.config/panel-selector/anthropic.env` (outside the project, mode 600). Without them the page falls back to the strict questions.

**Single line diagram:** the walk's final step draws the SLD from the selection in the company drawing layout (A3 frame, grid, title block, legend tags 1SQ / Q / K / F / U), one drop per feeder; anything not selected is drawn dashed. *Open single line diagram* gives a printable file (save as PDF). Generator: `core/sld.py`.

**Not selected:** one list with a category and a reason for every item: components not built, items not selected for this panel, items the company drawing has that no component selects yet (control-circuit devices) and out of scope. It's on the walk, on the SLD and in the document pack's *Not selected* sheet.

**Guided design:** after you confirm the requirement, the designer walks the selection one component at a time
(motor current → VFD Power Module → Control Unit → Memory Card → Operator Panel / DOL starter → cable, per motor;
then incomer, I/O list, relays and terminals, wiring, 24 V supply, surge arrester / phase monitoring, meter, not-selected
items, BOM). Each step shows what it decides, the facts it uses, the parts, every check with its source, and lets the
designer try a change: the selection re-runs, the parts that changed are listed, and any accepted step whose parts
changed must be accepted again. The document pack unlocks when every step is accepted, and carries a Design log sheet: every step accepted and every change tried, with what it changed.

**ClusterVise flow:** the first tab, *Describe the machine*, goes Requirement → Components → Design logic →
BOM → I/O lists → Documents. *Download document pack* gives one Excel file: requirement (each fact with
the words it came from), BOM, VFD BOM, I/O list, design logic (every check with its rule and source
page), open points and the documents cited.

**Excel BOM:** panel tab → *Download Excel BOM* (or `scripts/export_project_bom.py [--project NAME]` → `projects/<name>/out/`). Every line says
whether it is engineered (awaiting sign-off), client-specified (with the spec page) or not selected yet.

Each component folder holds `SCOPE.md` (G1), `data/` (G2), `RULES.md` + `rules.yaml`
(G3), `golden/` (G4), `select.py` (G5), `VERIFY.md` (G6), `SIGNOFF.md` (G7).

## Layout

```
core/provenance.py   loader: refuses data without register ref, page, or with a changed source file
core/result.py       Result / Check: every answer carries its checks, rule ids and sources
core/golden.py       runs golden cases, reports differences
sources/             register.yaml + pdf/ (standards, manufacturer/<make>, guides, client)
components/<name>/   one folder per component (see above)
scripts/             G6 verification scripts
```

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml pytest pdfplumber
.venv/bin/python -m pytest
.venv/bin/python scripts/verify_motor_flc.py
```

Web app (standard library only, no extra install):

```bash
.venv/bin/python webapp/server.py          # open http://127.0.0.1:8000
```

Inputs can be prefilled from the URL, e.g. `http://127.0.0.1:8000/?kw=7.5&voltage_v=415`.

```python
from components.motor_flc.select import select
print(select(kw=7.5, voltage_v=415).trace())
```
