"""Audit Massive adjusted OHLCV values, dividends, splits, and returns."""

# Errors to ignore.
# pylint: disable=too-many-lines

# Standard library imports
from collections.abc import Sequence
from html import escape as html_escape
import io
from pathlib import Path

# Third-party imports
import polars as pl

# Project imports
import adjusted_ohlcv_audit
import audit_classification
import audit_outputs
from audit_schema import DISPLAY_DECIMALS
import audit_validation
import real_world_events
import returns_audit_pipeline
from massive_data import MassiveData
import utilities as util
from yfinance_data import YFinanceData


class Audit:
    """Audit Massive prices, corporate actions, and calculated returns.

    This class loads Massive and yFinance market data, then produces audit
    outputs for:

    - Massive adjusted OHLCV values.
    - Split/dividend-adjusted return calculations.
    - Differences between Massive-derived returns and yFinance returns.

    Attributes:
        from_date:
            Inclusive audit start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive audit end date in ``YYYY-MM-DD`` format.

        massive_data:
            Loaded Massive data wrapper.

        yfinance_data:
            Loaded yFinance data wrapper.

        audited_adjusted_ohlcv:
            DataFrame containing adjusted OHLCV audit differences.

        audited_returns:
            DataFrame containing adjusted return audit output.
    """

    def __init__(
        self,
        tickers: Sequence[str],
        from_date: str,
        to_date: str,
        always_download: bool = False,
    ) -> None:
        """Initialize Audit and run audit calculations.

        Args:
            tickers:
                Ticker symbols to audit.

            from_date:
                Inclusive audit start date in ``YYYY-MM-DD`` format.

            to_date:
                Inclusive audit end date in ``YYYY-MM-DD`` format.

            always_download:
                Whether to force source data re-download before auditing.
        """
        self.from_date = from_date
        self.to_date = to_date

        self.massive_data = MassiveData(
            tickers,
            self.from_date,
            self.to_date,
            always_download,
        )
        self.yfinance_data = YFinanceData(
            tickers,
            self.from_date,
            self.to_date,
            always_download,
        )

        self.audited_adjusted_ohlcv = self.audit_adjusted_ohlcv()
        self.audited_returns = self.audit_returns()

    def _actionable_or_non_actionable(self, actionable: bool) -> pl.DataFrame:
        """Return the actionable or nonactionable audit results"""
        return (
            audit_outputs.category_actionable(self.audited_returns)
            if actionable
            else audit_outputs.category_non_actionable(self.audited_returns)
        )

    def audit_adjusted_ohlcv(self) -> pl.DataFrame:
        """Audit Massive split-adjusted OHLCV values.

        This method preserves the original public ``Audit`` API while delegating
        the adjusted-OHLCV implementation to ``adjusted_ohlcv_audit``.

        Returns:
            DataFrame containing only mismatched OHLCV values.

        Raises:
            ValueError:
                Raised if any required input columns are missing.
        """
        return adjusted_ohlcv_audit.audit_adjusted_ohlcv(
            self.massive_data,
            self.from_date,
            self.to_date,
        )

    def audit_returns(self) -> pl.DataFrame:
        """Create split/dividend-adjusted closes and returns.

        This method loads:

        1. Unadjusted Massive OHLCV data.
        2. Massive split events.
        3. Massive dividend events.
        4. yFinance OHLCV data.

        It creates a backward-adjusted close series using both splits and
        dividends, compares the locally calculated adjusted returns against
        yFinance adjusted returns, and assigns a heuristic suspicion score.

        Returns:
            DataFrame with adjusted closes, adjusted returns, yFinance
            comparison columns, event comparison columns, and suspicion scores.

        Raises:
            ValueError:
                Raised if any required input columns are missing.
        """
        real_world_events_path: str = real_world_events.get_real_world_events_path(
            self.from_date,
            self.to_date,
        )
        has_real_world_events_file: bool = Path(real_world_events_path).exists()

        audit_validation.require_audit_returns_columns(
            self.massive_data,
            self.yfinance_data,
            real_world_events_path,
            has_real_world_events_file,
        )

        returns_lf: pl.LazyFrame = returns_audit_pipeline.build_returns_audit_lf(
            self.massive_data,
            self.yfinance_data,
        )
        df: pl.DataFrame = audit_outputs.collect_returns_output(returns_lf)

        if has_real_world_events_file:
            df = real_world_events.join_events(
                df,
                real_world_events_path,
            )

        df = real_world_events.apply_reason_overrides(df)
        df = audit_classification.refresh_return_analysis_columns(df)
        real_world_events.assert_output_columns(df)

        output_path: Path = Path(
            f"{util.PATH_AUDITED_RETURNS}.{self.from_date}.{self.to_date}.csv"
        )

        audit_outputs.write_returns_outputs(df, output_path)

        # Return the df with all decimals.
        return df

    def csv_audit_report(self, actionable: bool) -> str:
        """Create a CSV audit report from a DataFrame."""
        # df = self._category_actionable() if actionable else self._category_non_actionable()
        csv_string = io.StringIO()
        df = self._actionable_or_non_actionable(actionable)
        df.with_columns(pl.col(pl.Float64).round(DISPLAY_DECIMALS)).write_csv(csv_string)
        return csv_string.getvalue()

    def html_audit_report(self, actionable: bool) -> str:
        """Create an HTML audit report from a DataFrame.

        Args:
            df:
                DataFrame containing audit report rows.

        Returns:
            HTML audit report text.
        """
        df = self._actionable_or_non_actionable(actionable)

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
            title = f"{'' if actionable else 'Non-'}Actionable Audit Report"
            html_parts: list[str] = [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '<meta charset="utf-8">',
                f"<title>{title}</title>",
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
                f'<span class="title-main">{title}</span>',
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

        df = df.with_columns(pl.col(pl.Float64).round(DISPLAY_DECIMALS))
        fieldnames = df.columns
        rows = [
            {
                column_name: "" if value is None else str(value)
                for column_name, value in row.items()
            }
            for row in df.to_dicts()
        ]

        return build_html(rows, fieldnames)
