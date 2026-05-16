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
