"""Create a simple HTML audit report from a CSV file."""

from __future__ import annotations

import csv
from html import escape as html_escape
from pathlib import Path


def format_audit_report(input_path: str | Path) -> str:
    """Create an HTML audit report from a CSV file.

    Args:
        input_path:
            Path to the input CSV file.

    Returns:
        Path to the generated HTML file.

    Raises:
        ValueError:
            Raised if the CSV has no header row.
    """
    narrative_columns = {
        "evidence_summary",
        "real_world_event",
        "massive_problem_summary",
        "massive_why_incorrect",
        "massive_fix_action",
    }
    priority_column = "review_priority"
    status_columns = {"event_detected", "likely_correct_source", "confidence_level"}
    url_columns = {"primary_source_url", "secondary_source_url"}

    def escape(value: str) -> str:
        """Escape HTML text without changing slashes."""
        return html_escape(value, quote=False)

    def display_header(column_name: str) -> str:
        """Return a display header that wraps more naturally."""
        return column_name.replace("_", " ")

    def cell_classes(fieldname: str, value: str) -> list[str]:
        """Return CSS classes for a table cell."""
        classes: list[str] = []
        if fieldname in narrative_columns:
            classes.append("wrap")
        elif fieldname in url_columns:
            classes.append("url")

        normalized_value = value.strip().upper()
        if fieldname == priority_column and normalized_value:
            classes.append(f"priority-{normalized_value}")
        elif fieldname in status_columns and normalized_value:
            classes.append(f"status-{normalized_value}")

        return classes

    def html_cell_value(fieldname: str, value: str) -> str:
        """Return escaped HTML for one cell value."""
        if fieldname in url_columns and value:
            escaped_value = escape(value)
            return f'<a href="{escaped_value}">{escaped_value}</a>'
        return escape(value)

    def build_html(rows: list[dict[str, str]], fieldnames: list[str]) -> str:
        """Build the HTML report text."""
        html_parts: list[str] = [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>Audit Report ({escape(input_path_text)})</title>",
            "<style>",
            "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "margin:24px;color:#1f2937;background:#f8fafc}",
            ".title{display:flex;align-items:baseline;gap:10px;margin:0 0 16px}",
            ".title-main{font-size:22px;font-weight:700}",
            ".title-path{font-size:13px;color:#64748b}",
            ".table-wrap{overflow:auto;border:1px solid #cbd5e1;background:white}",
            "table{border-collapse:separate;border-spacing:0;font-size:12px;line-height:1.35}",
            "th,td{border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;"
            "padding:6px 8px;vertical-align:top}",
            "th{position:sticky;top:0;background:#e5e7eb;z-index:1;font-weight:650;"
            "white-space:normal}",
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
            '<h1 class="title">',
            '<span class="title-main">Audit Report</span>',
            f'<span class="title-path">({escape(input_path_text)})</span>',
            "</h1>",
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
        return "\n".join(html_parts)

    csv_path = Path(input_path)
    input_path_text = str(input_path)
    output_path = csv_path.with_suffix(".html")

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path} has no header row.")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_html(rows, fieldnames),
        encoding="utf-8",
    )

    return str(output_path)
