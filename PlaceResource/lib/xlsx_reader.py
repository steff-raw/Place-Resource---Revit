# -*- coding: utf-8 -*-
"""Read cell values from an Excel .xlsx workbook with the Python standard library.

An .xlsx file is a zip of XML parts. This reader opens it with ``zipfile`` and
``xml.etree``, so no extra package is installed and nothing leaves the machine.

Limits, stated plainly:
- Values are read as text. Formulas are not evaluated; the value Excel cached
  when the file was last saved is used. Save the workbook in Excel after editing.
- Formatting, merged cells, hidden rows and comments are ignored.
- .xls (old binary format) and .xlsb are not supported.

XML namespaces are matched by local tag name, so the reader does not depend on
(or contain) the namespace URIs.
"""

import posixpath
import zipfile
import xml.etree.ElementTree as ElementTree
from collections import OrderedDict

from errors import ConfigurationError


def read_workbook(path):
    """Return an ordered mapping of sheet name to rows (lists of cell text).

    Rows are padded so each row covers every column that has a value.
    Empty cells are ''. Raises ConfigurationError with an actionable message.
    """
    try:
        archive = zipfile.ZipFile(path, "r")
    except FileNotFoundError:
        raise ConfigurationError(
            "The legend library workbook was not found: {0}. Check library_file in "
            "library_legends.json.".format(path)
        )
    except PermissionError:
        raise ConfigurationError(
            "The legend library workbook could not be opened: {0}. Close it in any program that "
            "has it locked, or make sure OneDrive has downloaded it, then try again.".format(path)
        )
    except zipfile.BadZipFile:
        raise ConfigurationError(
            "{0} is not an Excel .xlsx workbook. Save it from Excel as 'Excel Workbook (*.xlsx)'. "
            "If it is on OneDrive, right-click it and choose 'Always keep on this device'.".format(path)
        )
    try:
        with archive:
            names = set(archive.namelist())
            shared = _shared_strings(archive, names)
            sheets = OrderedDict()
            for sheet_name, part in _sheet_parts(archive, names):
                sheets[sheet_name] = _sheet_rows(archive, part, shared)
            return sheets
    except ConfigurationError:
        raise
    except (KeyError, ValueError, ElementTree.ParseError) as ex:
        raise ConfigurationError(
            "The legend library workbook {0} could not be read ({1}). Open it in Excel, save it as "
            ".xlsx, and try again.".format(path, ex)
        )


def sheet_records(rows):
    """Turn rows into dictionaries keyed by the lower-case header text.

    The first row with any value is the header row. Blank rows are skipped.
    Each record also carries ``__row__``: the 1-based row number in Excel.
    """
    header = None
    header_index = None
    for index, row in enumerate(rows):
        if any(cell.strip() for cell in row):
            header = [cell.strip().lower() for cell in row]
            header_index = index
            break
    if header is None:
        return []
    records = []
    for index in range(header_index + 1, len(rows)):
        row = rows[index]
        if not any(cell.strip() for cell in row):
            continue
        record = {"__row__": index + 1}
        for column, key in enumerate(header):
            if not key:
                continue
            record[key] = row[column].strip() if column < len(row) else ""
        records.append(record)
    return records


def column_index(reference):
    """Return the 0-based column of a cell reference such as 'C12' or 'AA3'."""
    letters = ""
    for character in reference:
        if character.isalpha():
            letters += character.upper()
        else:
            break
    if not letters:
        raise ValueError("Cell reference '{0}' has no column letters.".format(reference))
    number = 0
    for character in letters:
        number = number * 26 + (ord(character) - ord("A") + 1)
    return number - 1


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(element, name):
    return [child for child in list(element) if _local(child.tag) == name]


def _attribute(element, name):
    """Read an attribute by local name, with or without a namespace prefix."""
    if name in element.attrib:
        return element.attrib[name]
    for key, value in element.attrib.items():
        if key.endswith("}" + name):
            return value
    return None


def _text_of(element):
    """Concatenate <t> text from a shared-string or inline-string item, skipping phonetic runs."""
    parts = []
    for child in list(element):
        local = _local(child.tag)
        if local == "t":
            parts.append(child.text or "")
        elif local == "r":
            for run_child in list(child):
                if _local(run_child.tag) == "t":
                    parts.append(run_child.text or "")
    return "".join(parts)


def _shared_strings(archive, names):
    part = "xl/sharedStrings.xml"
    if part not in names:
        return []
    root = ElementTree.fromstring(archive.read(part))
    return [_text_of(item) for item in _children(root, "si")]


def _sheet_parts(archive, names):
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    targets = {}
    rels_part = "xl/_rels/workbook.xml.rels"
    if rels_part in names:
        rels = ElementTree.fromstring(archive.read(rels_part))
        for relationship in list(rels):
            if _local(relationship.tag) != "Relationship":
                continue
            target = relationship.attrib.get("Target", "")
            if target.startswith("/"):
                target = target.lstrip("/")
            else:
                target = posixpath.normpath(posixpath.join("xl", target))
            targets[relationship.attrib.get("Id")] = target
    sheets_nodes = _children(workbook, "sheets")
    result = []
    position = 0
    for sheets in sheets_nodes:
        for sheet in _children(sheets, "sheet"):
            position += 1
            name = sheet.attrib.get("name") or "Sheet{0}".format(position)
            relation_id = _attribute(sheet, "id")
            part = targets.get(relation_id) or "xl/worksheets/sheet{0}.xml".format(position)
            if part not in names:
                raise ConfigurationError(
                    "Worksheet '{0}' is listed in the workbook but its data part is missing.".format(name)
                )
            result.append((name, part))
    return result


def _cell_text(cell, shared):
    cell_type = cell.attrib.get("t", "n")
    if cell_type == "inlineStr":
        for inline in _children(cell, "is"):
            return _text_of(inline)
        return ""
    value_nodes = _children(cell, "v")
    raw = value_nodes[0].text if value_nodes and value_nodes[0].text is not None else ""
    if cell_type == "s":
        if raw == "":
            return ""
        return shared[int(raw)]
    if cell_type == "b":
        return "TRUE" if raw.strip() == "1" else "FALSE"
    if cell_type in ("str", "e"):
        return raw
    return _number_text(raw)


def _number_text(raw):
    text = raw.strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer() and "e" not in text.lower():
        return str(int(number))
    return text


def _sheet_rows(archive, part, shared):
    root = ElementTree.fromstring(archive.read(part))
    rows = []
    for sheet_data in _children(root, "sheetData"):
        next_row = 1
        for row in _children(sheet_data, "row"):
            row_number = int(row.attrib.get("r", next_row))
            while len(rows) < row_number - 1:
                rows.append([])
            values = {}
            next_column = 0
            for cell in _children(row, "c"):
                reference = cell.attrib.get("r")
                column = column_index(reference) if reference else next_column
                values[column] = _cell_text(cell, shared)
                next_column = column + 1
            width = (max(values) + 1) if values else 0
            rows.append([values.get(index, "") for index in range(width)])
            next_row = row_number + 1
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]
