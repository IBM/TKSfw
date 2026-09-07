#!/usr/bin/env python3
"""xlsx_lite — write a properly formatted .xlsx workbook with the standard library only.

An .xlsx file is a zip of Office Open XML parts. This module writes the handful the framework needs:
several sheets, a bold filled header row, frozen header, autofilter, column widths, wrapped/top-aligned
memo cells, real datetimes (Excel serials with a number format) and text cells that Excel will not turn
into numbers. No formulas, charts or shared strings (inline strings keep the writer simple).

    wb = Workbook()
    wb.add_sheet("changes", ["EntryID", "Title", "Timestamp"], rows,
                 widths={"Title": 60}, wrap={"Description"}, datetimes={"Timestamp"})
    wb.save("ledgers.xlsx")

Rows are lists aligned with the header. Values: str, int, float, bool, None, datetime.datetime, or a
"YYYY-MM-DD hh:mm:ss" string in a datetimes column (converted). Sheet names are sanitised to Excel's rules
(≤ 31 chars, no []:*?/\\). Python ≥ 3.8, std lib only.
"""
import re
import zipfile
from datetime import datetime, date
from xml.sax.saxutils import escape

_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# style ids (cellXfs order in styles.xml)
S_DEFAULT, S_HEADER, S_WRAP, S_DATETIME, S_TEXT = 0, 1, 2, 3, 4


def col_letter(n):
    """1 → A, 27 → AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def excel_serial(dt):
    """Excel 1900-system serial for a datetime (days since 1899-12-30, fraction = time)."""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    delta = dt - datetime(1899, 12, 30)
    return delta.days + delta.seconds / 86400.0


def parse_ts(v):
    if isinstance(v, datetime):
        return v
    s = str(v).strip().strip('"')
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


class Sheet:
    def __init__(self, name, header, rows, widths=None, wrap=None, datetimes=None, freeze=True, autofilter=True):
        self.name = name
        self.header = list(header)
        self.rows = rows
        self.widths = widths or {}
        self.wrap = set(wrap or ())
        self.datetimes = set(datetimes or ())
        self.freeze = freeze
        self.autofilter = autofilter

    def _cell(self, ref, value, col_name):
        if value is None or value == "":
            return f'<c r="{ref}" s="{S_TEXT}"/>'
        if col_name in self.datetimes:
            dt = parse_ts(value)
            if dt is not None:
                return f'<c r="{ref}" s="{S_DATETIME}"><v>{excel_serial(dt):.10f}</v></c>'
        if isinstance(value, bool):
            return f'<c r="{ref}" s="{S_TEXT}" t="b"><v>{1 if value else 0}</v></c>'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{ref}" s="{S_TEXT}"><v>{value}</v></c>'
        text = _CTRL.sub("", str(value))
        style = S_WRAP if (col_name in self.wrap or "\n" in text) else S_TEXT
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'

    def xml(self):
        ncol = len(self.header)
        last = col_letter(max(ncol, 1))
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">']
        out.append(f'<dimension ref="A1:{last}{len(self.rows) + 1}"/>')
        if self.freeze:
            out.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                       '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>')
        else:
            out.append('<sheetViews><sheetView workbookViewId="0"/></sheetViews>')
        out.append('<sheetFormatPr defaultRowHeight="15"/>')
        out.append("<cols>")
        for i, name in enumerate(self.header, 1):
            w = self.widths.get(name) or (14 if name in self.datetimes else 18)
            out.append(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>')
        out.append("</cols>")
        out.append("<sheetData>")
        out.append('<row r="1">' + "".join(
            f'<c r="{col_letter(i)}1" s="{S_HEADER}" t="inlineStr"><is><t>{escape(str(h))}</t></is></c>'
            for i, h in enumerate(self.header, 1)) + "</row>")
        for r, row in enumerate(self.rows, 2):
            cells = []
            for i, name in enumerate(self.header, 1):
                v = row[i - 1] if i - 1 < len(row) else None
                cells.append(self._cell(f"{col_letter(i)}{r}", v, name))
            out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
        out.append("</sheetData>")
        if self.autofilter and self.rows:
            out.append(f'<autoFilter ref="A1:{last}{len(self.rows) + 1}"/>')
        out.append('<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>')
        out.append("</worksheet>")
        return "\n".join(out)


class Workbook:
    def __init__(self):
        self.sheets = []

    def add_sheet(self, name, header, rows, **kw):
        clean = _BAD_SHEET.sub("_", str(name)).strip("'")[:31] or f"Sheet{len(self.sheets) + 1}"
        base, n = clean, 2
        while any(s.name.lower() == clean.lower() for s in self.sheets):
            suffix = f"_{n}"
            clean = base[:31 - len(suffix)] + suffix
            n += 1
        sh = Sheet(clean, header, rows, **kw)
        self.sheets.append(sh)
        return sh

    # ------------------------------------------------------------------ parts
    @staticmethod
    def _styles():
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd hh:mm:ss"/></numFmts>'
                '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
                '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
                '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills>'
                '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                '<cellXfs count="5">'
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'                                   # 0 default
                '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
                '<alignment vertical="center"/></xf>'                                                              # 1 header
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
                '<alignment vertical="top" wrapText="1"/></xf>'                                                    # 2 wrap
                '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1">'
                '<alignment vertical="top"/></xf>'                                                                 # 3 datetime
                '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1">'
                '<alignment vertical="top"/></xf>'                                                                 # 4 text (@)
                '</cellXfs>'
                '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                '</styleSheet>')

    def save(self, path):
        if not self.sheets:
            raise ValueError("workbook has no sheets")
        n = len(self.sheets)
        content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                         '<Default Extension="xml" ContentType="application/xml"/>',
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
                         '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
                         '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
                         '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>']
        for i in range(1, n + 1):
            content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        content_types.append("</Types>")
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
                '</Relationships>')
        wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
              '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="20000" windowHeight="12000"/></bookViews><sheets>']
        for i, s in enumerate(self.sheets, 1):
            wb.append(f'<sheet name="{escape(s.name)}" sheetId="{i}" r:id="rId{i}"/>')
        wb.append("</sheets>")
        # autofilter needs a defined name per sheet to survive a round trip in Excel
        wb.append("<definedNames>" + "".join(
            f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i - 1}" hidden="1">'
            f"'{escape(s.name)}'!$A$1:${col_letter(max(len(s.header), 1))}${len(s.rows) + 1}</definedName>"
            for i, s in enumerate(self.sheets, 1) if s.autofilter and s.rows) + "</definedNames>")
        wb.append("</workbook>")
        wb_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for i in range(1, n + 1):
            wb_rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        wb_rels.append(f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
        wb_rels.append("</Relationships>")
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                '<dc:creator>TKSfw xlsx_lite</dc:creator>'
                f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
                f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')
        app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
               'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>TKSfw</Application></Properties>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "\n".join(content_types))
            z.writestr("_rels/.rels", rels)
            z.writestr("docProps/core.xml", core)
            z.writestr("docProps/app.xml", app)
            z.writestr("xl/workbook.xml", "\n".join(wb))
            z.writestr("xl/_rels/workbook.xml.rels", "\n".join(wb_rels))
            z.writestr("xl/styles.xml", self._styles())
            for i, s in enumerate(self.sheets, 1):
                z.writestr(f"xl/worksheets/sheet{i}.xml", s.xml())
        return path
