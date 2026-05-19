"""Output and compact reporting helpers for audit results."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import polars as pl

# Project imports.
import audit_classification
import audit_schema as schema
import real_world_events


def category_actionable(audited_returns: pl.DataFrame) -> pl.DataFrame:
    """Return actionable Massive data problems using compact report columns.

    Category actionable contains review-required rows where Massive likely needs
    review or correction. These rows are intended for operational
    triage: identify whether Massive has a data problem, what the likely
    problem is, and what should be done to fix it.

    Args:
        audited_returns:
            Full return-audit output.

    Returns:
        DataFrame with the recommended user-facing Category actionable columns.
    """
    review_required_expr: pl.Expr = audit_classification.review_required_expr()

    # Actionable means the row both merits review and currently points to a
    # Massive-side remediation candidate after deterministic diagnostics and
    # optional real-world research have been applied.
    return audited_returns.filter(review_required_expr & pl.col("massive_needs_fix")).select(
        schema.CATEGORY_REPORT_COLUMNS
    )


def category_non_actionable(audited_returns: pl.DataFrame) -> pl.DataFrame:
    """Return informational/non-action rows using compact report columns.

    Category non-actionable contains review-required rows that do not appear to be
    actionable Massive data defects after deterministic diagnostics and optional
    real-world research have been applied.

    Args:
        audited_returns:
            Full return-audit output.

    Returns:
        DataFrame with the recommended user-facing Category non-actionable columns.
    """
    review_required_expr: pl.Expr = audit_classification.review_required_expr()

    # Non-actionable rows are still useful audit evidence: they document
    # reconciled market moves, yFinance-side issues, close reversals, or review
    # triggers that do not currently require a Massive data correction.
    return audited_returns.filter(review_required_expr & ~pl.col("massive_needs_fix")).select(
        schema.CATEGORY_REPORT_COLUMNS
    )


def collect_returns_output(df_lf: pl.LazyFrame) -> pl.DataFrame:
    """Collect the user-facing return-audit columns.

    Args:
        df_lf:
            Detailed lazy return-audit frame.

    Returns:
        DataFrame with the primary return-audit output columns and blank
        real-world event columns ready for optional enrichment.
    """
    df: pl.DataFrame = (
        df_lf.select(
            [
                "ticker",
                "date",
                "ms_close",
                "yf_close",
                "ms_adj_factor",
                "yf_adj_factor",
                "ms_adj_close",
                "yf_adj_close",
                # Dividends and splits
                "ms_div_split",
                "yf_div_split",
                "has_div_split_mismatch",
                # Returns due to price change
                "ms_return_price",
                "yf_return_price",
                # Massive dividend/split factors
                "ms_div_split_factor_implied",
                "ms_div_split_factor_explicit",
                "diff_ms_div_split_factor",
                # yFinance dividend/split factors
                "yf_div_split_factor_implied",
                "yf_div_split_factor_explicit",
                "diff_yf_div_split_factor",
                # Total returns
                "ms_return",
                "yf_return",
                "diff_return",
                "needs_review",
                "review_priority",
                # Heuristic anomaly score
                "heuristic_anomaly_score",
                # "diff_score",
                # Deterministic analysis diagnostics
                "analysis_sheet",
                "analysis_reason_code",
                "analysis_confidence",
                # Massive-focused diagnostics
                "massive_needs_fix",
                "massive_problem_summary",
                "massive_why_incorrect",
                "massive_fix_action",
                "massive_fix_priority",
            ]
        )
        .pipe(real_world_events.add_placeholder_columns)
        .collect()
    )

    return df


def write_returns_outputs(
    df: pl.DataFrame,
    output_path: Path,
) -> None:
    """Write the full return-audit CSV and review batch CSV files.

    Args:
        df:
            Full precision return-audit output.

        output_path:
            Path where the rounded full return-audit CSV should be written.
    """
    # Write display output rounded to the nearest 0.01 basis point. The in-memory
    # DataFrame returned by audit_returns() keeps full precision for downstream
    # calculations.
    rounded_df: pl.DataFrame = df.with_columns(pl.col(pl.Float64).round(schema.DISPLAY_DECIMALS))
    rounded_df.write_csv(output_path)
    _write_needs_review_batches(rounded_df, output_path)


def _write_needs_review_batches(
    df: pl.DataFrame,
    output_path: Path,
    max_needs_review_rows: int = schema.MAX_NEEDS_REVIEW_ROWS,
) -> None:
    """Write ticker-level review batches beside the full return-audit CSV.

    Tickers with no review rows are excluded from the batch files. When a
    ticker has at least one review row, all rows for that ticker are kept
    together in the same batch file. A single ticker is never split across
    files, even when that ticker alone has more than
    ``max_needs_review_rows`` review rows. Stale batch files from prior
    runs are removed before the current batch files are written.

    Args:
        df:
            Full rounded return-audit output that was written to the main
            CSV.

        output_path:
            Path to the full return-audit CSV. Batch files are written next
            to this path using a 1-based ``n_`` filename prefix.

        max_needs_review_rows:
            Maximum number of review rows to include in each batch file
            unless a single ticker exceeds this count by itself.

    Raises:
        ValueError:
            Raised if ``max_needs_review_rows`` is not positive.

        AssertionError:
            Raised if required output columns are missing.
    """
    if max_needs_review_rows <= 0:
        raise ValueError("max_needs_review_rows must be positive.")

    for column_name in ["ticker", "needs_review"]:
        if column_name not in df.columns:
            raise AssertionError(
                f"audit_returns() must persist {column_name} before writing review batches."
            )

    # Remove stale batch files from prior runs so only the current batches remain.
    for existing_batch_path in output_path.parent.glob(f"*_{output_path.name}"):
        batch_prefix: str = existing_batch_path.name.split("_", maxsplit=1)[0]
        if batch_prefix.isdigit():
            existing_batch_path.unlink()

    # Batches are sized by review-row count but grouped by ticker. Keeping all
    # rows for a ticker together preserves surrounding context for analyst
    # research and avoids splitting related event sequences across files.
    review_ticker_counts: pl.DataFrame = (
        df.with_row_index("_audit_original_row")
        .group_by("ticker")
        .agg(
            pl.col("_audit_original_row").min().alias("_first_row"),
            pl.col("needs_review")
            .fill_null(False)
            .cast(pl.Int64)
            .sum()
            .alias("_needs_review_count"),
        )
        .filter(pl.col("_needs_review_count") > 0)
        .sort("_first_row")
    )

    current_tickers: list[str] = []
    current_needs_review_count: int = 0
    batch_number: int = 1

    def write_batch(batch_tickers: list[str], file_number: int) -> None:
        """Write one ticker-preserving batch file.

        Args:
            batch_tickers:
                Tickers to include in the batch file.

            file_number:
                1-based batch file number used in the filename prefix.
        """
        if not batch_tickers:
            return

        batch_path: Path = output_path.with_name(f"{file_number}_{output_path.name}")
        df.filter(pl.col("ticker").is_in(batch_tickers)).write_csv(batch_path)

    for row in review_ticker_counts.iter_rows(named=True):
        ticker: str = str(row["ticker"])
        ticker_needs_review_count: int = int(row["_needs_review_count"])

        if ticker_needs_review_count > max_needs_review_rows:
            if current_tickers:
                write_batch(current_tickers, batch_number)
                batch_number += 1
                current_tickers = []
                current_needs_review_count = 0

            write_batch([ticker], batch_number)
            batch_number += 1
            continue

        if (
            current_tickers
            and current_needs_review_count + ticker_needs_review_count > max_needs_review_rows
        ):
            write_batch(current_tickers, batch_number)
            batch_number += 1
            current_tickers = []
            current_needs_review_count = 0

        current_tickers.append(ticker)
        current_needs_review_count += ticker_needs_review_count

    if current_tickers:
        write_batch(current_tickers, batch_number)
