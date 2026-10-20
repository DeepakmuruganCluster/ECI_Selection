# How the data is organised

There are five places, each with one job. Values live in exactly one of the first four.

| Place | What it holds | Who writes it |
|---|---|---|
| `sources/` | the original documents (`pdf/manufacturer`, `pdf/client`, `pdf/own`, `pdf/guides`, `pdf/standards`), the registry `register.yaml` (ID, edition, file, SHA-256 per document), page pictures (`excerpts/`) and the download `inbox/` | you (downloads) + registry entries |
| `data/makers/<maker>/` | **maker data**, one table per catalogue or manual: `siemens/` (SIRIUS type-2 table, motor guide, link modules, PM240-2, 3VM, PAC3220 …), `rittal/`, `kei/`, `polycab/`, `lapp/`, `finder/`, `connectwell/`, `rishabh/`, `selec/`. Every row cites its page | extracted by hand from the maker PDF, verified in G6 |
| `data/company/<group>/` | **company data** (refs `OWN-*`): `switchgear/` (MCB, RCCB, isolator, SA, PMR, calculation template), `plc/` (PLC and I/O modules), `dc/` (24 V SMPS), `propel/` (DOL and panel kits, drawing conventions), `vfd_logic/` (control unit and memory card logic). Every row cites its sheet row | `scripts/import_*.py` from the spreadsheets, checked by tests |
| `projects/<project>/` | everything **client-specific**: `project.yaml` (documents, panels, design inputs, scope), `data/` (client tables, e.g. ECI items and field devices) and `out/` (that project's exports) | per project |
| `data/catalog/` | **generated index**, never edited: `parts.yaml` (one entry per part: spellings, make, descriptions, SAP code, every source row, which components use it), `prices.yaml` (every price with its source row), `sources.yaml` (documents by kind with the tables that read them), `conflicts.md` (same part with different makes, spellings or prices; zero prices) | `scripts/build_catalog.py` |

Authority of each document (registry `kind`): manufacturer documents are the strongest evidence; client
documents state requirements; own / company data is used but marked "confirm before ordering" and
cross-checked with maker data where possible.

Rules that hold everywhere:
- no source, no data: a table names a registered document, the file's SHA-256 must match, every row cites a page / sheet row (`core/provenance.py`);
- a new project gets its own `projects/<name>/` folder; the generic tables are not copied;
- prices are only indicative company prices (INR) until a dated price list per make is registered.
- components hold rules and code only, never data: each component's `review.yaml` lists the tables it reads (`data_files`), and the code asks for a table by name (`core/data.py: data_file`); table names are unique;
- a shared document is one table, read by every component that needs it (e.g. the SIRIUS table: motor FLC, DOL, the MPCB cross-check);
- `data/MOVED_2026-10-13.json` records where each table came from when they left `components/*/data` (contents byte-identical).

## Adding a client project

Everything project-specific lives in `projects/<name>/` — the code names no project (tests/test_generic.py checks it).
Create `projects/<name>/project.yaml` with:

- `client`, `panels`, optional `aliases` and `export_prefix`;
- `documents`: the client documents by role (`automation`, `equipment`, `load_list`), each registered in `sources/register.yaml`;
- `equipment_panel_headings`: how the equipment PDF names its panels (regex → panel);
- `data`: the project tables (`client_items`, `field_devices`) under `projects/<name>/data/`, every row citing its page;
- `requirements`: the client's own statements that generic checks cite (`relay_terminal_scheme`, `cooling_fans_per_door`,
  `door_switch_light`, `meter_communication`, `internal_wiring`, `io_table`, `supplies_24v`), each `{text, source}`;
- `design_inputs` (stated on every export) and project settings such as `plc` (make, family, CPU / remote I/O per panel).

Project-only helper scripts (e.g. a client-specific importer) go in `projects/<name>/scripts/`. Export with
`scripts/export_project_bom.py --project <name>`; with one project held the name may be left out.
