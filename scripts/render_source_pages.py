"""Render every source page cited by a component's data to sources/excerpts/<REF>_pNNN.png.

The review page shows these images next to the answers, so a reviewer can compare
the tool with the manufacturer's page by eye. Re-run after adding data.

    .venv/bin/python scripts/render_source_pages.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402

from core.data import tables  # noqa: E402
from core.provenance import SOURCES, check_reference, load_yaml  # noqa: E402

OUT = SOURCES / "excerpts"


def cited_pages() -> dict[str, set[int]]:
    pages: dict[str, set[int]] = {}
    for f in tables():
        d = load_yaml(f)
        ref = (d.get("source") or {}).get("ref")
        for r in d.get("rows") or []:
            if ref and r.get("page"):
                pages.setdefault(ref, set()).add(int(r["page"]))
    return pages


def main():
    OUT.mkdir(exist_ok=True)
    for ref, pages in cited_pages().items():
        info = check_reference(ref)
        pdf = pdfium.PdfDocument(str(SOURCES / info["file"]))
        for p in sorted(pages):
            dest = OUT / f"{ref}_p{p:03d}.png"
            if not dest.exists():
                pdf[p - 1].render(scale=2).to_pil().save(dest)
            print(dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
