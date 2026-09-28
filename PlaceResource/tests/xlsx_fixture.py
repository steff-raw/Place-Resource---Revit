# -*- coding: utf-8 -*-
"""Write minimal .xlsx workbooks with the standard library.

Used by the tests and to generate config/legend_library.xlsx. Not deployed.
Run from PlaceResource to regenerate the sample library:

    python tests/xlsx_fixture.py
"""

import os
import zipfile
from collections import OrderedDict
from xml.sax.saxutils import escape

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_SHEET_TYPE = _REL + "/worksheet"
_STRINGS_TYPE = _REL + "/sharedStrings"
_DOC_TYPE = _REL + "/officeDocument"
_STYLES_TYPE = _REL + "/styles"
_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="{0}">'
           '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
           '<fills count="2"><fill><patternFill patternType="none"/></fill>'
           '<fill><patternFill patternType="gray125"/></fill></fills>'
           '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
           '</styleSheet>').format(_MAIN)


def _column_letters(index):
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def write_workbook(path, sheets, shared_strings=True):
    """Write ``sheets`` (ordered name -> list of rows) to ``path``.

    Text goes to the shared-string table when ``shared_strings`` is true, else inline.
    Numbers (int/float) are written as numeric cells. None and '' leave the cell empty.
    """
    strings = []
    string_index = {}

    def _shared(text):
        if text not in string_index:
            string_index[text] = len(strings)
            strings.append(text)
        return string_index[text]

    sheet_xml = []
    for rows in sheets.values():
        lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                 '<worksheet xmlns="{0}"><sheetData>'.format(_MAIN)]
        for row_number, row in enumerate(rows, 1):
            cells = []
            for column, value in enumerate(row):
                if value is None or value == "":
                    continue
                reference = "{0}{1}".format(_column_letters(column), row_number)
                if isinstance(value, bool):
                    cells.append('<c r="{0}" t="b"><v>{1}</v></c>'.format(reference, 1 if value else 0))
                elif isinstance(value, (int, float)):
                    cells.append('<c r="{0}"><v>{1}</v></c>'.format(reference, value))
                elif shared_strings:
                    cells.append('<c r="{0}" t="s"><v>{1}</v></c>'.format(reference, _shared(str(value))))
                else:
                    cells.append('<c r="{0}" t="inlineStr"><is><t>{1}</t></is></c>'.format(
                        reference, escape(str(value))
                    ))
            if cells:
                lines.append('<row r="{0}">{1}</row>'.format(row_number, "".join(cells)))
        lines.append("</sheetData></worksheet>")
        sheet_xml.append("".join(lines))

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="{0}">'.format(_CT),
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    for index in range(len(sheet_xml)):
        content_types.append(
            '<Override PartName="/xl/worksheets/sheet{0}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(index + 1)
        )
    content_types.append(
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    )
    if strings:
        content_types.append(
            '<Override PartName="/xl/sharedStrings.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        )
    content_types.append("</Types>")

    workbook = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<workbook xmlns="{0}" xmlns:r="{1}"><sheets>'.format(_MAIN, _REL)]
    relationships = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Relationships xmlns="{0}">'.format(_PKG)]
    for index, name in enumerate(sheets.keys(), 1):
        workbook.append('<sheet name="{0}" sheetId="{1}" r:id="rId{1}"/>'.format(escape(name, {'"': "&quot;"}), index))
        relationships.append('<Relationship Id="rId{0}" Type="{1}" Target="worksheets/sheet{0}.xml"/>'.format(
            index, _SHEET_TYPE
        ))
    workbook.append("</sheets></workbook>")
    relationships.append('<Relationship Id="rId{0}" Type="{1}" Target="styles.xml"/>'.format(
        len(sheets) + 1, _STYLES_TYPE
    ))
    if strings:
        relationships.append('<Relationship Id="rId{0}" Type="{1}" Target="sharedStrings.xml"/>'.format(
            len(sheets) + 2, _STRINGS_TYPE
        ))
    relationships.append("</Relationships>")

    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="{0}"><Relationship Id="rId1" Type="{1}" Target="xl/workbook.xml"/>'
                 '</Relationships>').format(_PKG, _DOC_TYPE)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", "".join(workbook))
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(relationships))
        for index, xml in enumerate(sheet_xml, 1):
            archive.writestr("xl/worksheets/sheet{0}.xml".format(index), xml)
        if strings:
            items = "".join('<si><t xml:space="preserve">{0}</t></si>'.format(escape(text)) for text in strings)
            archive.writestr(
                "xl/sharedStrings.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="{0}" count="{1}" uniqueCount="{1}">{2}</sst>'.format(_MAIN, len(strings), items),
            )


HEADER = ["Code", "Title", "Description", "Graphic", "Filled Region Type", "Notes"]
EXAMPLE = "Example row. Replace with office standard."

SAMPLE_LIBRARY = OrderedDict([
    ("Fire Strategy", [
        ["FR-30", "", "30 minute fire resistance", "Region", "Fire - 30 min", EXAMPLE],
        ["FR-60", "", "60 minute fire resistance", "Region", "Fire - 60 min", EXAMPLE],
    ]),
    ("Accessibility", [
        ["ACC-01", "", "Accessible route", "Region", "Access - Route", EXAMPLE],
    ]),
    ("Thermal Envelope", [
        ["TE-01", "", "Thermal envelope line", "Region", "Thermal - Envelope", EXAMPLE],
    ]),
    ("Acoustic", [
        ["AC-45", "", "Rw 45 dB separation", "Region", "Acoustic - Rw45", EXAMPLE],
    ]),
    ("Bollards and Barrier Protection", [
        ["BB-01", "", "Fixed bollard", "Region", "Barrier - Bollard", EXAMPLE],
    ]),
    ("Access and Maintenance", [
        ["AM-01", "", "Maintenance access zone", "Region", "Maintenance - Zone", EXAMPLE],
    ]),
    ("Room Use", [
        ["RU-OFF", "", "Office", "Region", "Room Use - Office", EXAMPLE],
    ]),
    ("Security Zone", [
        ["SZ-1", "", "Public zone", "Region", "Security - Zone 1", EXAMPLE],
    ]),
    ("Walls", [
        ["IWS-105", "", "Internal wall system 105. Metal stud with plasterboard both sides.", "Region",
         "Wall - IWS-105", EXAMPLE],
        ["IWS-110", "", "Internal wall system 110. Shown as a wall legend component.", "Component", "", EXAMPLE],
    ]),
    ("Floors", [
        ["FF-01", "", "Floor finish 01", "Region", "Floor - FF-01", EXAMPLE],
    ]),
    ("Ceilings", [
        ["CL-01", "", "Ceiling type 01", "Region", "Ceiling - CL-01", EXAMPLE],
    ]),
    ("Doors", [
        ["D-01", "", "Door type 01", "Component", "", EXAMPLE],
    ]),
])


def write_sample_library(path):
    """Write the sample legend library with a header row on every sheet."""
    sheets = OrderedDict((name, [HEADER] + rows) for name, rows in SAMPLE_LIBRARY.items())
    write_workbook(path, sheets)


if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "legend_library.xlsx")
    write_sample_library(os.path.abspath(target))
    print("Wrote", os.path.abspath(target))
