"""Format the actionable audit CSV for human review."""

from __future__ import annotations

import argparse
import csv
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_INPUT_PATH = Path("outputs/_t_actionable.csv")
NARRATIVE_COLUMNS = {
    "evidence_summary",
    "real_world_event",
    "massive_problem_summary",
    "massive_why_incorrect",
    "massive_fix_action",
}
URL_COLUMNS = {
    "primary_source_url",
    "secondary_source_url",
}
WRAPPED_COLUMNS = NARRATIVE_COLUMNS | URL_COLUMNS
PRIORITY_COLUMN = "review_priority"
STATUS_COLUMNS = {
    "event_detected",
    "likely_correct_source",
    "confidence_level",
}


def main() -> None:
    """Parse command-line arguments and write formatted report files."""
    parser = argparse.ArgumentParser(
        description="Create HTML and XLSX review reports from an actionable audit CSV."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Input CSV path. Defaults to {DEFAULT_INPUT_PATH}.",
    )
    parser.add_argument(
        "--html",
        dest="html_path",
        type=Path,
        help="Optional HTML output path. Defaults to <input>.html.",
    )
    parser.add_argument(
        "--xlsx",
        dest="xlsx_path",
        type=Path,
        help="Optional XLSX output path. Defaults to <input>.xlsx.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Do not write the HTML report.",
    )
    parser.add_argument(
        "--no-xlsx",
        action="store_true",
        help="Do not write the XLSX report.",
    )

    args = parser.parse_args()

    rows, fieldnames = read_csv(args.input_path)
    html_path = args.html_path or args.input_path.with_suffix(".html")
    xlsx_path = args.xlsx_path or args.input_path.with_suffix(".xlsx")

    if not args.no_html:
        write_html_report(rows, fieldnames, html_path)
        print(f"Wrote {html_path}")

    if not args.no_xlsx:
        write_xlsx_report(rows, fieldnames, xlsx_path)
        print(f"Wrote {xlsx_path}")


def read_csv(input_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Read a CSV file into dictionaries.

    Args:
        input_path:
            Path to the actionable audit CSV.

    Returns:
        Tuple containing rows and original field names.

    Raises:
        ValueError:
            Raised if the CSV has no header row.
    """
    with input_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"{input_path} has no header row.")
        return list(reader), list(reader.fieldnames)


def display_header(column_name: str) -> str:
    """Return a display header that wraps more naturally."""
    return column_name.replace("_", " ")


def write_html_report(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    output_path: Path,
) -> None:
    """Write a formatted HTML report.

    Args:
        rows:
            CSV rows to write.

        fieldnames:
            Original CSV field names.

        output_path:
            Path where the HTML report should be written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Actionable Audit Report</title>",
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:24px;color:#1f2937;background:#f8fafc}",
        "h1{font-size:22px;margin:0 0 16px}",
        ".table-wrap{overflow:auto;border:1px solid #cbd5e1;background:white}",
        "table{border-collapse:separate;border-spacing:0;font-size:12px;line-height:1.35}",
        "th,td{border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;padding:6px 8px;vertical-align:top}",
        "th{position:sticky;top:0;background:#e5e7eb;z-index:1;font-weight:650;white-space:normal}",
        "td{white-space:nowrap}",
        ".wrap{white-space:normal;min-width:260px;max-width:460px}",
        ".url{white-space:normal;min-width:220px;max-width:360px;word-break:break-word}",
        ".priority-HIGH{background:#fee2e2}",
        ".priority-MEDIUM{background:#fef3c7}",
        ".priority-LOW{background:#dcfce7}",
        ".status-YES,.status-YFINANCE,.status-MASSIVE{background:#dbeafe}",
        ".status-NO,.status-BOTH{background:#dcfce7}",
        ".status-UNCERTAIN,.status-NEITHER{background:#fef3c7}",
        "a{color:#1d4ed8}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Actionable Audit Report</h1>",
        '<div class="table-wrap">',
        "<table>",
        "<thead><tr>",
    ]

    for fieldname in fieldnames:
        html_parts.append(f"<th>{escape(display_header(fieldname))}</th>")

    html_parts.extend(["</tr></thead>", "<tbody>"])

    for row in rows:
        html_parts.append("<tr>")
        for fieldname in fieldnames:
            value = row.get(fieldname, "")
            classes = cell_classes(fieldname, value)
            class_attr = f' class="{" ".join(classes)}"' if classes else ""
            html_parts.append(f"<td{class_attr}>{html_cell_value(fieldname, value)}</td>")
        html_parts.append("</tr>")

    html_parts.extend(["</tbody>", "</table>", "</div>", "</body>", "</html>"])
    output_path.write_text("\n".join(html_parts), encoding="utf-8")


def cell_classes(fieldname: str, value: str) -> list[str]:
    """Return CSS classes for a table cell."""
    classes: list[str] = []
    if fieldname in NARRATIVE_COLUMNS:
        classes.append("wrap")
    elif fieldname in URL_COLUMNS:
        classes.append("url")

    normalized_value = value.strip().upper()
    if fieldname == PRIORITY_COLUMN and normalized_value:
        classes.append(f"priority-{normalized_value}")
    elif fieldname in STATUS_COLUMNS and normalized_value:
        classes.append(f"status-{normalized_value}")

    return classes


def html_cell_value(fieldname: str, value: str) -> str:
    """Return escaped HTML for one cell value."""
    if fieldname in URL_COLUMNS and value:
        escaped_value = escape(value)
        return f'<a href="{escaped_value}">{escaped_value}</a>'
    return escape(value)


def write_xlsx_report(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    output_path: Path,
) -> None:
    """Write a formatted XLSX report.

    Args:
        rows:
            CSV rows to write.

        fieldnames:
            Original CSV field names.

        output_path:
            Path where the XLSX report should be written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    column_widths = calculate_column_widths(rows, fieldnames)
    hyperlinks = collect_hyperlinks(rows, fieldnames)

    with ZipFile(output_path, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml())
        workbook.writestr("_rels/.rels", package_relationships_xml())
        workbook.writestr("xl/workbook.xml", workbook_xml())
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_relationships_xml())
        workbook.writestr("xl/styles.xml", styles_xml())
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows, fieldnames, column_widths, hyperlinks))
        workbook.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_relationships_xml(hyperlinks))
        workbook.writestr("docProps/core.xml", core_properties_xml())
        workbook.writestr("docProps/app.xml", app_properties_xml())


def calculate_column_widths(rows: list[dict[str, str]], fieldnames: list[str]) -> dict[str, float]:
    """Calculate compact column widths for the XLSX report."""
    widths: dict[str, float] = {}
    for fieldname in fieldnames:
        if fieldname in NARRATIVE_COLUMNS:
            widths[fieldname] = 48.0
        elif fieldname in URL_COLUMNS:
            widths[fieldname] = 36.0
        else:
            max_content_length = max(
                [len(display_header(fieldname)), *(len(row.get(fieldname, "")) for row in rows)]
            )
            widths[fieldname] = float(min(max(max_content_length + 2, 8), 24))
    return widths


def collect_hyperlinks(
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> dict[str, str]:
    """Collect URL cells and relationship targets."""
    hyperlinks: dict[str, str] = {}
    for row_index, row in enumerate(rows, start=2):
        for column_index, fieldname in enumerate(fieldnames, start=1):
            value = row.get(fieldname, "")
            if fieldname in URL_COLUMNS and value:
                hyperlinks[cell_ref(row_index, column_index)] = value
    return hyperlinks


def sheet_xml(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    column_widths: dict[str, float],
    hyperlinks: dict[str, str],
) -> str:
    """Return the XML for the worksheet."""
    last_column = column_letter(len(fieldnames))
    last_row = len(rows) + 1
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" "
        "activePane=\"bottomLeft\" state=\"frozen\"/></sheetView></sheetViews>",
        "<cols>",
    ]

    for column_index, fieldname in enumerate(fieldnames, start=1):
        width = column_widths[fieldname]
        parts.append(
            f'<col min="{column_index}" max="{column_index}" width="{width:.2f}" customWidth="1"/>'
        )

    parts.extend(["</cols>", "<sheetData>"])
    parts.append(f'<row r="1" ht="36" customHeight="1">')
    for column_index, fieldname in enumerate(fieldnames, start=1):
        parts.append(
            xlsx_cell(
                1,
                column_index,
                display_header(fieldname),
                style_id=1,
            )
        )
    parts.append("</row>")

    for row_index, row in enumerate(rows, start=2):
        parts.append(f'<row r="{row_index}">')
        for column_index, fieldname in enumerate(fieldnames, start=1):
            value = row.get(fieldname, "")
            style_id = style_id_for_cell(fieldname, value)
            parts.append(xlsx_cell(row_index, column_index, value, style_id=style_id))
        parts.append("</row>")

    parts.append("</sheetData>")

    if hyperlinks:
        parts.append("<hyperlinks>")
        for relationship_index, cell_reference in enumerate(hyperlinks, start=1):
            parts.append(f'<hyperlink ref="{cell_reference}" r:id="rId{relationship_index}"/>')
        parts.append("</hyperlinks>")

    parts.append(
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
        '<conditionalFormatting sqref="A2:'
        f'{last_column}{last_row}">'
        '<cfRule type="containsText" priority="1" operator="containsText" text="HIGH" dxfId="0">'
        '<formula>NOT(ISERROR(SEARCH("HIGH",A2)))</formula></cfRule>'
        '<cfRule type="containsText" priority="2" operator="containsText" text="MEDIUM" dxfId="1">'
        '<formula>NOT(ISERROR(SEARCH("MEDIUM",A2)))</formula></cfRule>'
        '<cfRule type="containsText" priority="3" operator="containsText" text="LOW" dxfId="2">'
        '<formula>NOT(ISERROR(SEARCH("LOW",A2)))</formula></cfRule>'
        "</conditionalFormatting>"
    )
    parts.append("</worksheet>")
    return "".join(parts)


def style_id_for_cell(fieldname: str, value: str) -> int:
    """Return the XLSX style id for one cell."""
    normalized_value = value.strip().upper()
    if fieldname in URL_COLUMNS:
        return 3
    if fieldname in NARRATIVE_COLUMNS:
        return 2
    if fieldname == PRIORITY_COLUMN:
        if normalized_value == "HIGH":
            return 4
        if normalized_value == "MEDIUM":
            return 5
        if normalized_value == "LOW":
            return 6
    if fieldname in STATUS_COLUMNS and normalized_value:
        return 7
    return 0


def xlsx_cell(row_index: int, column_index: int, value: str, *, style_id: int) -> str:
    """Return the XML for one inline-string worksheet cell."""
    reference = cell_ref(row_index, column_index)
    style = f' s="{style_id}"' if style_id else ""
    return f'<c r="{reference}" t="inlineStr"{style}><is><t>{xml_escape(value)}</t></is></c>'


def cell_ref(row_index: int, column_index: int) -> str:
    """Return an Excel cell reference."""
    return f"{column_letter(column_index)}{row_index}"


def column_letter(column_index: int) -> str:
    """Return the Excel column letter for a 1-based column index."""
    letters = ""
    while column_index:
        column_index, remainder = divmod(column_index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def xml_escape(value: Any) -> str:
    """Escape text for XML text nodes."""
    return escape(str(value), quote=False)


def xml_attribute_escape(value: Any) -> str:
    """Escape text for XML attributes."""
    return escape(str(value), quote=True)


def content_types_xml() -> str:
    """Return XLSX content types XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def package_relationships_xml() -> str:
    """Return package relationships XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def workbook_xml() -> str:
    """Return workbook XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets><sheet name=\"Actionable\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
        "</workbook>"
    )


def workbook_relationships_xml() -> str:
    """Return workbook relationships XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def sheet_relationships_xml(hyperlinks: dict[str, str]) -> str:
    """Return worksheet relationships XML for hyperlinks."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for relationship_index, target in enumerate(hyperlinks.values(), start=1):
        escaped_target = xml_attribute_escape(quote(target, safe=":/?#[]@!$&'()*+,;=%"))
        parts.append(
            f'<Relationship Id="rId{relationship_index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{escaped_target}" TargetMode="External"/>'
        )
    parts.append("</Relationships>")
    return "".join(parts)


def styles_xml() -> str:
    """Return workbook styles XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '<font><u/><color rgb="FF1D4ED8"/><sz val="11"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="7">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE5E7EB"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFDBEAFE"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left style="thin"><color rgb="FFE2E8F0"/></left><right style="thin"><color rgb="FFE2E8F0"/></right><top style="thin"><color rgb="FFE2E8F0"/></top><bottom style="thin"><color rgb="FFE2E8F0"/></bottom><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="8">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1"><alignment vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1"><alignment vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFill="1"><alignment vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyFill="1"><alignment vertical="top"/></xf>'
        '</cellXfs>'
        '<dxfs count="3">'
        '<dxf><fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/></patternFill></fill></dxf>'
        '<dxf><fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/></patternFill></fill></dxf>'
        '<dxf><fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/></patternFill></fill></dxf>'
        '</dxfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def core_properties_xml() -> str:
    """Return core document properties XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>Actionable Audit Report</dc:title>"
        "</cp:coreProperties>"
    )


def app_properties_xml() -> str:
    """Return extended document properties XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Python</Application>"
        "</Properties>"
    )


if __name__ == "__main__":
    main()
