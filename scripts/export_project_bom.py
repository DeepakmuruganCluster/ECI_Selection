"""Write a project's Excel BOM per panel to projects/<name>/out/: main BOM + Options, I/O, power calculation, design
logic and sources (project component). Everything project-specific comes from projects/<name>/project.yaml: panels,
design inputs (stated on the Summary sheet) and the export name prefix.

    .venv/bin/python scripts/export_project_bom.py [--project NAME]     (no name: the only project held)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import project as P  # noqa: E402
from core.bom_export import build_project  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    name = P.resolve(ap.parse_args().project)
    out = P.load(name)["_dir"] / "out"
    out.mkdir(exist_ok=True)
    prefix = P.setting("export_prefix", name) or name
    for panel in P.panels(name):
        base = {"panel": panel, **(P.setting("design_inputs", name) or {}), "project": name}
        title = f"{prefix}_{panel}"
        data, info = build_project(base, title=title)
        (out / f"{title}_BOM.xlsx").write_bytes(data)
        print(f"{title}_BOM.xlsx: {info['bom_lines']} BOM lines, {info['option_rows']} option rows, "
              f"{info['open_points']} open points")
