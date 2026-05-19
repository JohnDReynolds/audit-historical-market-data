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
_ENCODING = "utf-8"


def write_text_create_parent(output_path: str | Path, content: str) -> None:
    """Write text to a file, creating the parent directory if needed.

    Args:
        output_path:
            Text file path to write.

        content:
            Text content to write using the project encoding.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=_ENCODING)


def load_single_column(file_path: str | Path) -> tuple[str, ...]:
    """Load a single-column CSV file into a unique sorted tuple of strings.

    Notes:
        Ignores:
            - Empty lines
            - Lines beginning with "#"

    Args:
        file_path:
            Path to the CSV file.

    Returns:
        Alphabetically sorted tuple of unique strings.
    """
    values: list[str] = (
        pl.read_csv(file_path, has_header=False)
        .select(pl.col("column_1").cast(pl.String).str.strip_chars().alias("value"))
        .filter((pl.col("value") != "") & (~pl.col("value").str.starts_with("#")))
        .get_column("value")
        .to_list()
    )

    return tuple(sorted(set(values)))


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
            encoding=_ENCODING,
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
