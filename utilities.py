"""Common utility helpers for audit inputs and CSV output."""

# Errors to ignore
# pylint: disable=unsubscriptable-object
# pyright: reportMissingTypeArgument=false

# Standard library imports
from __future__ import annotations  # Enable postponed evaluation of type hints
from collections.abc import Iterator
from contextlib import contextmanager
import csv
from pathlib import Path

# Third-Party imports
import polars as pl

# Constants
DUMMY_DATE = "1800-01-01"
DUMMY_TICKER = "_d_u_m_m_y_"
ENCODING = "utf-8"

# Input file paths
INPUT_DIRECTORY = "inputs/"
PATH_MASSIVE_ADJUSTED_PRICES = f"{INPUT_DIRECTORY}massive_adjusted_prices"
PATH_MASSIVE_DIVIDENDS = f"{INPUT_DIRECTORY}massive_dividends"
PATH_MASSIVE_SPLITS = f"{INPUT_DIRECTORY}massive_splits"
PATH_MASSIVE_UNADJUSTED_PRICES = f"{INPUT_DIRECTORY}massive_unadjusted_prices"
PATH_YFINANCE_DIVIDENDS = f"{INPUT_DIRECTORY}yfinance_dividends"
PATH_YFINANCE_PRICES = f"{INPUT_DIRECTORY}yfinance_prices"
PATH_YFINANCE_SPLITS = f"{INPUT_DIRECTORY}yfinance_splits"

# Output file paths
_OUTPUT_DIRECTORY = "outputs/"
PATH_AUDITED_ADJUSTED_OHLCV = f"{_OUTPUT_DIRECTORY}audited_adjusted_ohlcv"
PATH_AUDITED_RETURNS = f"{_OUTPUT_DIRECTORY}audited_returns"


# def format_audit_report(df: pl.DataFrame) -> str:
#     """Create an HTML audit report from a DataFrame.

#     Args:
#         df:
#             DataFrame containing audit report rows.

#     Returns:
#         HTML audit report text.
#     """
#     narrative_columns = {
#         "evidence_summary",
#         "real_world_event",
#         "massive_problem_summary",
#         "massive_why_incorrect",
#         "massive_fix_action",
#     }
#     priority_column = "review_priority"
#     status_columns = {"event_detected", "likely_correct_source", "confidence_level"}
#     url_columns = {"primary_source_url", "secondary_source_url"}

#     def escape(value: str) -> str:
#         """Escape HTML text without changing slashes."""
#         return html_escape(value, quote=False)

#     def display_header(column_name: str) -> str:
#         """Return a display header that wraps more naturally."""
#         return column_name.replace("_", " ")

#     def cell_classes(fieldname: str, value: str) -> list[str]:
#         """Return CSS classes for a table cell."""
#         classes: list[str] = []
#         if fieldname in narrative_columns:
#             classes.append("wrap")
#         elif fieldname in url_columns:
#             classes.append("url")

#         normalized_value = value.strip().upper()
#         if fieldname == priority_column and normalized_value:
#             classes.append(f"priority-{normalized_value}")
#         elif fieldname in status_columns and normalized_value:
#             classes.append(f"status-{normalized_value}")

#         return classes

#     def html_cell_value(fieldname: str, value: str) -> str:
#         """Return escaped HTML for one cell value."""
#         if fieldname in url_columns and value:
#             escaped_value = escape(value)
#             return f'<a href="{escaped_value}">{escaped_value}</a>'
#         return escape(value)

#     def build_html(rows: list[dict[str, str]], fieldnames: list[str]) -> str:
#         """Build the HTML report text."""
#         html_parts: list[str] = [
#             "<!doctype html>",
#             '<html lang="en">',
#             "<head>",
#             '<meta charset="utf-8">',
#             "<title>Audit Report</title>",
#             "<style>",
#             "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
#             "margin:24px;color:#1f2937;background:#f8fafc}",
#             ".title{display:flex;align-items:baseline;gap:10px;margin:0 0 16px}",
#             ".title-main{font-size:22px;font-weight:700}",
#             ".title-path{font-size:13px;color:#64748b}",
#             ".table-wrap{overflow:auto;border:1px solid #cbd5e1;background:white}",
#             "table{border-collapse:separate;border-spacing:0;font-size:12px;line-height:1.35}",
#             "th,td{border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;"
#             "padding:6px 8px;vertical-align:top}",
#             "th{position:sticky;top:0;background:#e5e7eb;z-index:1;font-weight:650;"
#             "white-space:normal}",
#             "td{white-space:nowrap}",
#             ".wrap{white-space:normal;min-width:260px;max-width:460px}",
#             ".url{white-space:normal;min-width:220px;max-width:360px;word-break:break-word}",
#             ".priority-HIGH{background:#fee2e2}",
#             ".priority-MEDIUM{background:#fef3c7}",
#             ".priority-LOW{background:#dcfce7}",
#             ".status-YES,.status-YFINANCE,.status-MASSIVE{background:#dbeafe}",
#             ".status-NO,.status-BOTH{background:#dcfce7}",
#             ".status-UNCERTAIN,.status-NEITHER{background:#fef3c7}",
#             "a{color:#1d4ed8}",
#             "</style>",
#             "</head>",
#             "<body>",
#             '<h1 class="title">',
#             '<span class="title-main">Audit Report</span>',
#             "</h1>",
#             '<div class="table-wrap">',
#             "<table>",
#             "<thead><tr>",
#         ]

#         for fieldname in fieldnames:
#             html_parts.append(f"<th>{escape(display_header(fieldname))}</th>")

#         html_parts.extend(["</tr></thead>", "<tbody>"])

#         for row in rows:
#             html_parts.append("<tr>")
#             for fieldname in fieldnames:
#                 value = row.get(fieldname, "")
#                 classes = cell_classes(fieldname, value)
#                 class_attr = f' class="{" ".join(classes)}"' if classes else ""
#                 html_parts.append(f"<td{class_attr}>{html_cell_value(fieldname, value)}</td>")
#             html_parts.append("</tr>")

#         html_parts.extend(["</tbody>", "</table>", "</div>", "</body>", "</html>"])
#         return "\n".join(html_parts)

#     fieldnames = df.columns
#     rows = [
#         {
#             column_name: "" if value is None else str(value)
#             for column_name, value in row.items()
#         }
#         for row in df.to_dicts()
#     ]

#     return build_html(rows, fieldnames)


def load_single_column_csv(file_path: str | Path) -> tuple[str, ...]:
    """Load a single-column CSV file into a sorted tuple of strings.

    Notes:
        Ignores:
            - Empty lines
            - Lines beginning with "#"

    Args:
        file_path:
            Path to the CSV file.

    Returns:
        Alphabetically sorted tuple of strings.
    """
    values: list[str] = (
        pl.read_csv(file_path, has_header=False)
        .select(pl.col("column_1").cast(pl.String).str.strip_chars().alias("value"))
        .filter((pl.col("value") != "") & (~pl.col("value").str.starts_with("#")))
        .get_column("value")
        .to_list()
    )

    return tuple(sorted(values))


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker symbols and fail fast on blanks.

    Args:
        ticker:
            Ticker symbol to normalize.

    Returns:
        Uppercase ticker symbol with surrounding whitespace removed.

    Raises:
        ValueError:
            Raised if the ticker symbol is blank.
    """
    normalized_ticker: str = ticker.strip().upper()

    if not normalized_ticker:
        raise ValueError("Ticker symbols cannot be blank.")

    return normalized_ticker


def require_lazy_columns(
    lazy_frame: pl.LazyFrame,
    required_columns: set[str],
    source_name: str,
) -> None:
    """Fail fast if a LazyFrame is missing required columns.

    Args:
        lazy_frame:
            LazyFrame to validate.

        required_columns:
            Column names that must be present.

        source_name:
            Human-readable source name used in error messages.

    Raises:
        ValueError:
            Raised if any required columns are missing.
    """
    actual_columns: set[str] = set(lazy_frame.collect_schema().names())
    missing_columns: set[str] = required_columns - actual_columns

    if missing_columns:
        raise ValueError(f"{source_name} is missing required columns: {sorted(missing_columns)}")


@contextmanager
def safe_csv_dict_writer(
    output_csv_path: str,
    fieldnames: list[str],
) -> Iterator[csv.DictWriter[str]]:
    """Open a CSV DictWriter and delete the file if writing fails.

    Args:
        output_csv_path:
            CSV file path to write.

        fieldnames:
            CSV column names.

    Yields:
        Configured CSV ``DictWriter`` with header already written.
    """
    try:
        with open(
            output_csv_path,
            mode="w",
            newline="",
            encoding=ENCODING,
        ) as csv_file:
            writer: csv.DictWriter[str] = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames,
            )

            writer.writeheader()

            yield writer

    except Exception:
        Path(output_csv_path).unlink(missing_ok=True)
        raise
