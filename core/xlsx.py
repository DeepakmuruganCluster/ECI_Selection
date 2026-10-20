"""Minimal .xlsx writer (standard library only): sheets of rows, bold header row, column widths.

Enough for BOM exports; no formulas, no merged cells.
"""
from __future__ import annotations

import io
import math
import re
import zipfile
from xml.sax.saxutils import escape


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _cell_text(v) -> str:
    """Text as XML 1.0 allows it: control characters (other than tab, newline, CR) make Excel reject the file."""
    return _CONTROL.sub("", str(v))


def _cell(ref: str, v, bold: bool) -> str:
    style = ' s="1"' if bold else ""
    if v is None or v == "":
        return f'<c r="{ref}"{style}/>'
    if isinstance(v, bool):
        v = "yes" if v else "no"
    if isinstance(v, float) and not math.isfinite(v):
        v = str(v)                       # NaN / inf are not spreadsheet numbers: shown as text
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{style}><v>{v:g}</v></c>' if isinstance(v, float) else f'<c r="{ref}"{style}><v>{v}</v></c>'
    text = escape(_cell_text(v)).replace("\n", "&#10;")
    return f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet(rows: list[list], widths: list[int] | None) -> str:
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths or [], 1))
    body = []
    for r, row in enumerate(rows, 1):
        cells = "".join(_cell(f"{_col(c)}{r}", v, r == 1) for c, v in enumerate(row, 1))
        body.append(f'<row r="{r}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews>'
            + (f"<cols>{cols}</cols>" if cols else "") + f'<sheetData>{"".join(body)}</sheetData></worksheet>')


def workbook(sheets: list[tuple[str, list[list], list[int] | None]]) -> bytes:
    """sheets: (name ≤ 31 chars, rows with the header first, column widths)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(1, len(sheets) + 1)) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _, _) in enumerate(sheets, 1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
                   '<cellXfs count="2"><xf fontId="0" xfId="0"/><xf fontId="1" xfId="0" applyFont="1"/></cellXfs>'
                   '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i, (_, rows, widths) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet(rows, widths))
    return buf.getvalue()


def read_back(data: bytes) -> dict[str, list[list[str]]]:
    """Parse a workbook written by `workbook` (used by the tests)."""
    import re
    from xml.sax.saxutils import unescape
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = re.findall(r'<sheet name="([^"]+)"', z.read("xl/workbook.xml").decode())
        for i, n in enumerate(names, 1):
            xml = z.read(f"xl/worksheets/sheet{i}.xml").decode()
            rows = []
            for row in re.findall(r"<row [^>]*>(.*?)</row>", xml):
                cells = re.findall(r'<c r="[A-Z]+\d+"[^>]*?(?:/>|>(.*?)</c>)', row)
                rows.append([unescape(re.sub(r"<[^>]+>", "", c)).replace("&#10;", "\n") for c in cells])
            out[unescape(n)] = rows
    return out


def read_any(path) -> dict[str, list[list]]:
    """Read cell values of any simple .xlsx (shared strings, inline strings, numbers); standard library only."""
    import re
    from xml.sax.saxutils import unescape
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            sst = z.read("xl/sharedStrings.xml").decode("utf8")
            for si in re.findall(r"<si>(.*?)</si>", sst, flags=re.S):
                shared.append(unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, flags=re.S))))
        wb = z.read("xl/workbook.xml").decode("utf8")
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
        target = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
        target.update({k: v for v, k in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
        out = {}
        for name, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wb):
            xml = z.read("xl/" + target[rid].lstrip("/").removeprefix("xl/")).decode("utf8")
            rows = []
            for row in re.findall(r"<row [^>]*>(.*?)</row>", xml, flags=re.S):
                cells = []
                for attrs, body in re.findall(r"<c ([^>]*?)(?:/>|>(.*?)</c>)", row, flags=re.S):
                    ref = re.search(r'r="([A-Z]+)\d+"', attrs).group(1)
                    col = 0
                    for ch in ref:
                        col = col * 26 + ord(ch) - 64
                    while len(cells) < col - 1:
                        cells.append(None)
                    v = re.search(r"<v>(.*?)</v>", body or "", flags=re.S)
                    t = re.search(r't="(\w+)"', attrs)
                    if t and t.group(1) == "s" and v:
                        val = shared[int(v.group(1))]
                    elif t and t.group(1) == "inlineStr":
                        val = unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", body, flags=re.S)))
                    elif v:
                        x = v.group(1)
                        val = float(x) if re.fullmatch(r"-?\d+(\.\d+)?(E-?\d+)?", x) else unescape(x)
                    else:
                        val = None
                    cells.append(val)
                rows.append(cells)
            out[unescape(name)] = rows
    return out
