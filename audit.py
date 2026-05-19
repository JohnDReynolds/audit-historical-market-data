"""Audit Massive adjusted OHLCV values, dividends, splits, and returns."""

# Errors to ignore.
# pylint: disable=import-outside-toplevel
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
import audit_schema as schema
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
        """Return actionable or non-actionable audit results.

        Args:
            actionable:
                Whether to return actionable Massive data problems.

        Returns:
            DataFrame with display column names applied.
        """
        df = (
            audit_outputs.category_actionable(self.audited_returns)
            if actionable
            else audit_outputs.category_non_actionable(self.audited_returns)
        )
        return df.rename(self._display_column_names(df.columns))

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
        yFinance adjusted returns, and assigns a heuristic anomaly score.

        Returns:
            DataFrame with adjusted closes, adjusted returns, yFinance
            comparison columns, event comparison columns, and heuristic anomaly scores.

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
            f"{schema.PATH_AUDITED_RETURNS}.{self.from_date}.{self.to_date}.csv"
        )

        audit_outputs.write_returns_outputs(df, output_path)

        # Return the df with all decimals.
        return df

    def csv_audit_report(
        self,
        actionable: bool,
        output_path: str | None = None,
        verbose: bool = False,
        exclude_columns: Sequence[str] | None = None,
    ) -> str:
        """Create a CSV audit report from audit results.

        Args:
            actionable:
                Whether to report actionable Massive data problems.

            output_path:
                Optional path where the CSV audit report should be written.

            verbose:
                Whether to print the written output path.

            exclude_columns:
                Optional list of output columns to omit if present.

        Returns:
            CSV audit report text.
        """
        # df = self._category_actionable() if actionable else self._category_non_actionable()
        csv_string = io.StringIO()
        df = self._actionable_or_non_actionable(actionable)
        if exclude_columns is not None:
            df = df.drop([column for column in exclude_columns if column in df.columns])
        df.with_columns(pl.col(pl.Float64).round(schema.DISPLAY_DECIMALS)).write_csv(csv_string)
        content = csv_string.getvalue()

        if output_path:
            util.write_text_create_parent(output_path, content)
            if verbose:
                print(f"Wrote {output_path}")

        return content

    @staticmethod
    def _display_column_names(column_names: Sequence[str]) -> dict[str, str]:
        """Build display names for audit report columns.

        Args:
            column_names:
                Internal audit column names.

        Returns:
            Mapping from internal column names to display column names.
        """
        return schema.display_column_names(column_names)

    def html_audit_report(
        self,
        actionable: bool,
        summary: bool = False,
        output_path: str | None = None,
        verbose: bool = False,
    ) -> str:
        """Create an HTML audit report from audit results.

        Args:
            actionable:
                Whether to report actionable Massive data problems.

            summary:
                Whether to omit detail columns and append ``Summary`` to the
                report title.

            output_path:
                Optional path where the HTML audit report should be written.

            verbose:
                Whether to print the written output path.

        Returns:
            HTML audit report text.
        """
        raw_df = (
            audit_outputs.category_actionable(self.audited_returns)
            if actionable
            else audit_outputs.category_non_actionable(self.audited_returns)
        )

        if summary:

            def joined_text_expr(column_names: Sequence[str]) -> pl.Expr:
                """Join nonblank text columns with a blank line for summary reports.

                Args:
                    column_names:
                        Raw column names to combine.

                Returns:
                    Polars expression that joins nonblank column values.
                """
                return pl.struct(
                    [pl.col(col_name).fill_null("").cast(pl.Utf8) for col_name in column_names]
                ).map_elements(
                    lambda values: "\n\n".join(
                        value.strip()
                        for value in values.values()
                        if isinstance(value, str) and value.strip()
                    ),
                    return_dtype=pl.String,
                )

            massive_problem_and_fix_column = "massive_problem_and_fix"
            massive_guidance_columns = [
                "massive_problem_summary",
                "massive_why_incorrect",
                "massive_fix_action",
            ]
            has_massive_problem_and_fix = all(
                column_name in raw_df.columns for column_name in massive_guidance_columns
            )
            if has_massive_problem_and_fix:
                raw_df = raw_df.with_columns(
                    joined_text_expr(massive_guidance_columns).alias(
                        massive_problem_and_fix_column
                    )
                )

            real_world_evidence_column = "real_world_evidence"
            real_world_evidence_columns = [
                "real_world_event",
                "evidence_summary",
            ]
            has_real_world_evidence = all(
                column_name in raw_df.columns for column_name in real_world_evidence_columns
            )
            if has_real_world_evidence:
                raw_df = raw_df.with_columns(
                    joined_text_expr(real_world_evidence_columns).alias(real_world_evidence_column)
                )

            summary_omitted_columns = schema.column_names_in_group("summary_omitted")
            summary_appended_columns = schema.summary_appended_columns()
            kept_columns: list[str] = []
            for column_name in raw_df.columns:
                if (
                    column_name == "expected_return_impact"
                    and "analysis_reason_code" in raw_df.columns
                ):
                    kept_columns.append("analysis_reason_code")
                if column_name == "evidence_summary" and has_real_world_evidence:
                    kept_columns.append(real_world_evidence_column)
                if column_name == "massive_problem_summary":
                    if has_massive_problem_and_fix:
                        kept_columns.append(massive_problem_and_fix_column)
                if column_name not in summary_omitted_columns | {
                    massive_problem_and_fix_column,
                    real_world_evidence_column,
                }:
                    kept_columns.append(column_name)
            kept_columns.extend(
                column_name
                for column_name in summary_appended_columns
                if column_name in raw_df.columns
            )
            raw_df = raw_df.select(kept_columns)

        display_column_names = self._display_column_names(raw_df.columns)
        display_to_raw_column_names = {
            display_column_name: raw_column_name
            for raw_column_name, display_column_name in display_column_names.items()
        }
        df = raw_df.rename(display_column_names)

        narrative_columns = schema.display_names_in_group("narrative")
        priority_column = "review priority"
        status_columns = schema.display_names_in_group("status")
        url_columns = schema.display_names_in_group("url")
        frozen_column_classes = schema.frozen_display_column_classes()

        def escape(value: str) -> str:
            """Escape HTML text without changing slashes.

            Args:
                value:
                    Text value to escape.

            Returns:
                Escaped HTML text.
            """
            return html_escape(value, quote=False)

        def escape_attribute(value: str) -> str:
            """Escape HTML attribute text.

            Args:
                value:
                    Attribute value to escape.

            Returns:
                Escaped HTML attribute text.
            """
            return html_escape(value, quote=True)

        def cell_classes(fieldname: str, value: str) -> list[str]:
            """Return CSS classes for a table cell.

            Args:
                fieldname:
                    Display column name.

                value:
                    Cell value as text.

            Returns:
                CSS class names for the table cell.
            """
            classes: list[str] = []
            if fieldname in frozen_column_classes:
                classes.extend(frozen_column_classes[fieldname].split())

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
            """Return escaped HTML for one cell value.

            Args:
                fieldname:
                    Display column name.

                value:
                    Cell value as text.

            Returns:
                Escaped HTML, including a link for URL columns.
            """
            if fieldname in url_columns and value:
                escaped_value = escape(value)
                return f'<a href="{escaped_value}">{escaped_value}</a>'
            return escape(value)

        def pdf_column_class(fieldname: str) -> str:
            """Return a print-oriented column class for the field.

            Args:
                fieldname:
                    Display column name.

            Returns:
                CSS class name for PDF-oriented column sizing.
            """
            normalized_fieldname = fieldname.lower()

            if fieldname == "ticker":
                return "pdf-col-ticker"
            if fieldname == "date":
                return "pdf-col-date"
            if fieldname in {"evidence summary", "real world evidence"}:
                return "pdf-col-evidence-summary"
            if fieldname == "massive problem and fix":
                return "pdf-col-problem-fix"
            if fieldname == "real world event":
                return "pdf-col-event"
            if fieldname == "massive fix priority":
                return "pdf-col-fix-priority"
            if fieldname == "event bucket":
                return "pdf-col-event-bucket"
            if fieldname in {
                "massive problem summary",
                "massive why incorrect",
                "massive fix action",
            }:
                return "pdf-col-guidance"
            if fieldname in url_columns:
                return "pdf-col-url"
            if fieldname in status_columns or "priority" in normalized_fieldname:
                return "pdf-col-status"
            if fieldname in {
                "expected return impact",
            }:
                return "pdf-col-impact"
            if fieldname in {
                "Massive ms_return",
                "yFinance yf_return",
            }:
                return "pdf-col-summary-return"
            if fieldname == "analysis reason code":
                return "pdf-col-event"
            if normalized_fieldname.endswith("div_split"):
                return "pdf-col-marker"
            if "return" in normalized_fieldname or fieldname == "heuristic anomaly score":
                return "pdf-col-number"

            return "pdf-col-default"

        def build_html(
            rows: list[dict[str, str]],
            fieldnames: list[str],
            header_tooltips: dict[str, str],
        ) -> str:
            """Build the HTML report text.

            Args:
                rows:
                    Display rows to render.

                fieldnames:
                    Display column names in output order.

                header_tooltips:
                    Tooltip text by display column name.

            Returns:
                Complete HTML report text.
            """
            title = f"{'' if actionable else 'Non-'}Actionable Audit Report"
            if summary:
                title = f"{title} Summary"
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
                ".title-main{font-size:22px;font-weight:700;color:#1e3a8a}",
                ".title-path{font-size:13px;color:#64748b}",
                ".table-wrap{max-height:calc(100vh - 96px);overflow:auto;"
                "border:1px solid #cbd5e1;background:white}",
                "table{border-collapse:separate;border-spacing:0;font-size:12px;line-height:1.35}",
                "th,td{border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;"
                "padding:6px 8px;vertical-align:top}",
                "th{position:sticky;top:0;background:#e5e7eb;z-index:2;font-weight:650;"
                "white-space:normal}",
                "td{white-space:nowrap}",
                ".frozen-col{position:sticky;background:white;z-index:1}",
                "th.frozen-col{background:#e5e7eb;z-index:3}",
                ".frozen-ticker{left:0;min-width:72px}",
                ".frozen-date{left:88px;min-width:96px}",
                ".wrap{white-space:pre-wrap;min-width:260px;max-width:460px}",
                ".url{white-space:normal;min-width:220px;max-width:360px;word-break:break-word}",
                ".priority-HIGH{background:#fee2e2}",
                ".priority-MEDIUM{background:#fef3c7}",
                ".priority-LOW{background:#dcfce7}",
                ".status-YES,.status-YFINANCE,.status-MASSIVE{background:#dbeafe}",
                ".status-NO,.status-BOTH{background:#dcfce7}",
                ".status-UNCERTAIN,.status-NEITHER{background:#fef3c7}",
                ".status-HIGH{background:#dcfce7}",
                ".status-MEDIUM{background:#fef3c7}",
                ".status-LOW{background:#fee2e2}",
                "a{color:#1d4ed8}",
                "</style>",
                "</head>",
                "<body>",
                '<h1 class="title">',
                f'<span class="title-main">{title}</span>',
                "</h1>",
                '<div class="table-wrap">',
                "<table>",
                "<colgroup>",
            ]

            for fieldname in fieldnames:
                html_parts.append(f'<col class="{pdf_column_class(fieldname)}">')

            html_parts.extend(
                [
                    "</colgroup>",
                    "<thead><tr>",
                ]
            )

            for fieldname in fieldnames:
                classes = frozen_column_classes.get(fieldname, "")
                class_attr = f' class="{classes}"' if classes else ""
                tooltip = header_tooltips.get(fieldname, "")
                title_attr = f' title="{escape_attribute(tooltip)}"' if tooltip else ""
                html_parts.append(f"<th{class_attr}{title_attr}>{escape(fieldname)}</th>")

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

        df = df.with_columns(pl.col(pl.Float64).round(schema.DISPLAY_DECIMALS))
        fieldnames = df.columns
        header_tooltips = {
            fieldname: schema.column_description(display_to_raw_column_names.get(fieldname, ""))
            for fieldname in fieldnames
        }
        rows = [
            {
                column_name: "" if value is None else str(value)
                for column_name, value in row.items()
            }
            for row in df.to_dicts()
        ]

        content = build_html(rows, fieldnames, header_tooltips)

        if output_path:
            util.write_text_create_parent(output_path, content)
            if verbose:
                print(f"Wrote {output_path}")

        return content

    def pdf_audit_report(
        self,
        output_path: str,
        actionable: bool = True,
        summary: bool = False,
        verbose: bool = False,
    ) -> None:
        """Create a ledger landscape PDF audit report.

        Args:
            output_path:
                Path where the PDF audit report should be written.

            actionable:
                Whether to report actionable Massive data problems.

            summary:
                Whether to omit detail columns and increase the PDF font size.

            verbose:
                Whether to print the written output path.

        Raises:
            RuntimeError:
                Raised if Playwright is not installed or Chromium has not
                been installed for Playwright.
        """
        try:
            # Lazy imports for heavy-handed libraries
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for PDF reports. Install it with "
                "`python -m pip install playwright` and "
                "`python -m playwright install chromium`."
            ) from exc

        pdf_path = Path(output_path)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        pdf_font_size = "14px" if summary else "6.5px"
        pdf_title_font_size = "28px" if summary else "13px"
        pdf_line_height = "1.22" if summary else "1.18"
        if summary:
            pdf_ticker_width = "0.66in"
            pdf_date_width = "1.05in"
            pdf_fix_priority_width = "0.855in"
            pdf_event_bucket_width = "1.195425in"
            pdf_impact_width = "0.77in"
            pdf_summary_return_width = "0.847in"
            pdf_evidence_width = "3.67792285in"
            pdf_problem_fix_width = "2.53765215in"
            pdf_event_width = "2.355in"
            pdf_guidance_width = "1.25in"
            pdf_marker_width = "1.155in"
            pdf_url_width = "0.95in"
        else:
            pdf_ticker_width = "0.36in"
            pdf_date_width = "0.5in"
            pdf_fix_priority_width = "0.45in"
            pdf_event_bucket_width = "0.621in"
            pdf_impact_width = "0.44in"
            pdf_summary_return_width = "0.44in"
            pdf_evidence_width = "2.5in"
            pdf_problem_fix_width = "2.5in"
            pdf_event_width = "0.9126in"
            pdf_guidance_width = "1.2638in"
            pdf_marker_width = "0.605in"
            pdf_url_width = "1.05in"

        print_css = (
            """
            <style>
                @page { size: 17in 11in; margin: 0.25in; }
                @media print {
                    body {
                        margin: 0;
                        background: white;
                        color: #111827;
                    }
                    .title {
                        margin: 0 0 8px;
                    }
                    .title-main {
                        font-size: __PDF_TITLE_FONT_SIZE__;
                    }
                    .table-wrap {
                        max-height: none;
                        overflow: visible;
                        border: 0;
                    }
                    table {
                        width: 100%;
                        table-layout: fixed;
                        font-size: __PDF_FONT_SIZE__;
                        line-height: __PDF_LINE_HEIGHT__;
                    }
                    .pdf-col-ticker { width: __PDF_TICKER_WIDTH__; }
                    .pdf-col-date { width: __PDF_DATE_WIDTH__; }
                    .pdf-col-status { width: 0.45in; }
                    .pdf-col-fix-priority { width: __PDF_FIX_PRIORITY_WIDTH__; }
                    .pdf-col-event-bucket { width: __PDF_EVENT_BUCKET_WIDTH__; }
                    .pdf-col-impact { width: __PDF_IMPACT_WIDTH__; }
                    .pdf-col-summary-return { width: __PDF_SUMMARY_RETURN_WIDTH__; }
                    .pdf-col-evidence-summary { width: __PDF_EVIDENCE_WIDTH__; }
                    .pdf-col-problem-fix { width: __PDF_PROBLEM_FIX_WIDTH__; }
                    .pdf-col-event { width: __PDF_EVENT_WIDTH__; }
                    .pdf-col-guidance { width: __PDF_GUIDANCE_WIDTH__; }
                    .pdf-col-url { width: __PDF_URL_WIDTH__; }
                    .pdf-col-reason { width: 0.65in; }
                    .pdf-col-marker { width: __PDF_MARKER_WIDTH__; }
                    .pdf-col-number { width: 0.45in; }
                    .pdf-col-default { width: 0.55in; }
                    thead {
                        display: table-header-group;
                    }
                    th,
                    td {
                        padding: 1px 2px;
                        white-space: normal;
                        overflow-wrap: anywhere;
                        word-break: break-word;
                    }
                    th {
                        overflow-wrap: normal;
                        word-break: normal;
                    }
                    th,
                    th.frozen-col {
                        position: static;
                        background: #e5e7eb;
                    }
                    .frozen-col {
                        position: static;
                    }
                    .frozen-ticker {
                        width: auto;
                        min-width: 0;
                        max-width: none;
                    }
                    .frozen-date {
                        width: auto;
                        min-width: 0;
                        max-width: none;
                    }
                    .wrap,
                    .url {
                        min-width: 0;
                        max-width: none;
                    }
                    a {
                        color: #1d4ed8;
                        text-decoration: none;
                    }
                }
            </style>
        """.replace("__PDF_FONT_SIZE__", pdf_font_size)
            .replace(
                "__PDF_TITLE_FONT_SIZE__",
                pdf_title_font_size,
            )
            .replace(
                "__PDF_LINE_HEIGHT__",
                pdf_line_height,
            )
            .replace(
                "__PDF_TICKER_WIDTH__",
                pdf_ticker_width,
            )
            .replace(
                "__PDF_DATE_WIDTH__",
                pdf_date_width,
            )
            .replace(
                "__PDF_FIX_PRIORITY_WIDTH__",
                pdf_fix_priority_width,
            )
            .replace(
                "__PDF_EVENT_BUCKET_WIDTH__",
                pdf_event_bucket_width,
            )
            .replace(
                "__PDF_IMPACT_WIDTH__",
                pdf_impact_width,
            )
            .replace(
                "__PDF_SUMMARY_RETURN_WIDTH__",
                pdf_summary_return_width,
            )
            .replace(
                "__PDF_EVIDENCE_WIDTH__",
                pdf_evidence_width,
            )
            .replace(
                "__PDF_PROBLEM_FIX_WIDTH__",
                pdf_problem_fix_width,
            )
            .replace(
                "__PDF_EVENT_WIDTH__",
                pdf_event_width,
            )
            .replace(
                "__PDF_GUIDANCE_WIDTH__",
                pdf_guidance_width,
            )
            .replace(
                "__PDF_URL_WIDTH__",
                pdf_url_width,
            )
            .replace(
                "__PDF_MARKER_WIDTH__",
                pdf_marker_width,
            )
        )
        html = self.html_audit_report(actionable, summary=summary).replace(
            "</head>",
            f"{print_css}</head>",
        )

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page()
                page.emulate_media(media="print")
                page.set_content(html, wait_until="load")
                page.pdf(
                    path=str(pdf_path),
                    width="17in",
                    height="11in",
                    landscape=True,
                    print_background=True,
                    prefer_css_page_size=True,
                )
                browser.close()
            if verbose:
                print(f"Wrote {output_path}")
        except PlaywrightError as exc:
            raise RuntimeError(
                "Failed to create PDF report with Playwright. If Chromium is missing, "
                "run `python -m playwright install chromium`."
            ) from exc

    @staticmethod
    def pdf_data_dictionary(output_path: str) -> None:
        """Create a portrait PDF report for the audit data dictionary.

        Args:
            output_path:
                Path where the PDF data dictionary should be written.

        Raises:
            RuntimeError:
                Raised if Playwright is not installed or Chromium has not
                been installed for Playwright.
        """
        try:
            # Lazy imports for heavy-handed libraries
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for PDF reports. Install it with "
                "`python -m pip install playwright` and "
                "`python -m playwright install chromium`."
            ) from exc

        def escape(value: str) -> str:
            """Escape HTML text without changing slashes.

            Args:
                value:
                    Text value to escape.

            Returns:
                Escaped HTML text.
            """
            return html_escape(value, quote=False)

        def dictionary_description_html(description: str) -> str:
            """Render data dictionary text with styled bullet rows.

            Args:
                description:
                    Plain-text data dictionary description.

            Returns:
                HTML fragment for the description.
            """
            html_lines: list[str] = []
            current_bullet_lines: list[str] = []

            def flush_bullet() -> None:
                """Append any pending bullet block to the rendered lines."""
                if not current_bullet_lines:
                    return

                first_line = current_bullet_lines[0]
                continuation_lines = current_bullet_lines[1:]
                continuation_html = "".join(
                    f'<span class="bullet-continuation">{escape(line)}</span>'
                    for line in continuation_lines
                )
                html_lines.append(
                    f'<span class="bullet-line">{escape(first_line)}{continuation_html}</span>'
                )
                current_bullet_lines.clear()

            for line in description.splitlines():
                if line.startswith("- "):
                    flush_bullet()
                    current_bullet_lines.append(line)
                elif line == "":
                    flush_bullet()
                    html_lines.append('<span class="blank-line"></span>')
                elif current_bullet_lines:
                    current_bullet_lines.append(line)
                else:
                    flush_bullet()
                    html_lines.append(f"<span>{escape(line)}</span>")

            flush_bullet()
            return "".join(html_lines)

        pdf_path = Path(output_path)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        dictionary_items = sorted(schema.DATA_DICTIONARY.items())
        html_parts = [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>Audit Data Dictionary</title>",
            "<style>",
            "@page{size:8.5in 11in;margin:0.65in}",
            "body{margin:0;background:white;color:#111827;"
            "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "font-size:16px;line-height:1.48}",
            "h1{margin:0 0 30px;text-align:center;color:#1e3a8a;"
            "font-size:32px;line-height:1.15;font-weight:750}",
            ".entry{break-inside:avoid;margin:0 0 22px;padding:0 0 18px;"
            "border-bottom:1px solid #dbe3ef}",
            ".entry-breakable{break-inside:auto}",
            ".key{margin:0 0 7px;color:#1e3a8a;font-size:17px;font-weight:720}",
            ".description{margin:0;color:#111827}",
            ".description span{display:block}",
            ".description .blank-line{height:.55em}",
            ".description .bullet-line{margin-top:.18em;padding-left:1.05em;text-indent:-.75em}",
            ".description .bullet-continuation{margin-top:.1em;text-indent:0}",
            "</style>",
            "</head>",
            "<body>",
            "<h1>Audit Data Dictionary</h1>",
        ]

        for key, description in dictionary_items:
            entry_class = "entry entry-breakable" if key == "analysis_reason_code" else "entry"
            html_parts.extend(
                [
                    f'<section class="{entry_class}">',
                    f'<h2 class="key">{escape(key)}</h2>',
                    f'<p class="description">{dictionary_description_html(description)}</p>',
                    "</section>",
                ]
            )

        html_parts.extend(["</body>", "</html>"])
        html = "\n".join(html_parts)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page()
                page.emulate_media(media="print")
                page.set_content(html, wait_until="load")
                page.pdf(
                    path=str(pdf_path),
                    width="8.5in",
                    height="11in",
                    landscape=False,
                    print_background=True,
                    prefer_css_page_size=True,
                )
                browser.close()
        except PlaywrightError as exc:
            raise RuntimeError(
                "Failed to create PDF report with Playwright. If Chromium is missing, "
                "run `python -m playwright install chromium`."
            ) from exc
