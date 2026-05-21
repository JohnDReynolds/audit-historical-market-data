"""Load and validate normalized source1/source2 data-source files."""

# Standard library imports.
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Third-party imports.
import polars as pl

# Project imports.
import audit_schema as schema

DataSourceRole = Literal["source1", "source2"]


@dataclass(frozen=True)
class DataSourceConfig:
    """Describe one normalized data source for a date-ranged audit run.

    Args:
        name:
            Human-readable data-source name, such as ``Massive`` or
            ``yFinance``.

        role:
            Reconciliation role for the source.  The current generic contract
            supports source1 as the audited data source and source2 as the
            comparison data source.

        prices_path:
            Date-specific normalized OHLCV CSV path.

        dividends_path:
            Date-specific normalized dividend CSV path.

        splits_path:
            Date-specific normalized split CSV path.
    """

    name: str
    role: DataSourceRole
    prices_path: Path
    dividends_path: Path
    splits_path: Path


@dataclass(frozen=True)
class DataSourceDataset:
    """Loaded normalized files for one data source.

    Attributes:
        name:
            Human-readable data-source name.

        role:
            Reconciliation role for the source.

        prices:
            LazyFrame with schema.DATA_SOURCE_PRICE_COLUMNS.

        dividends:
            LazyFrame with schema.DATA_SOURCE_DIVIDEND_COLUMNS.

        splits:
            LazyFrame with schema.DATA_SOURCE_SPLIT_COLUMNS.
    """

    name: str
    role: DataSourceRole
    prices: pl.LazyFrame
    dividends: pl.LazyFrame
    splits: pl.LazyFrame


def date_ranged_path(base_path: str, from_date: str, to_date: str) -> Path:
    """Return a normalized data-source CSV path for one date range.

    Args:
        base_path:
            Path prefix without date suffix or ``.csv`` extension.

        from_date:
            Inclusive start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive end date in ``YYYY-MM-DD`` format.

    Returns:
        Date-specific CSV path.
    """
    return Path(f"{base_path}.{from_date}.{to_date}.csv")


def default_source1_config(from_date: str, to_date: str) -> DataSourceConfig:
    """Return the current source1 config backed by Massive files.

    source1 is the audited data source: the side being evaluated for possible
    remediation when audit evidence identifies a data or adjustment issue.

    Args:
        from_date:
            Inclusive start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive end date in ``YYYY-MM-DD`` format.

    Returns:
        Default source1 data-source config.
    """
    return DataSourceConfig(
        name="Massive",
        role="source1",
        prices_path=date_ranged_path(schema.PATH_SOURCE1_PRICES, from_date, to_date),
        dividends_path=date_ranged_path(
            schema.PATH_SOURCE1_DIVIDENDS,
            from_date,
            to_date,
        ),
        splits_path=date_ranged_path(schema.PATH_SOURCE1_SPLITS, from_date, to_date),
    )


def default_source2_config(from_date: str, to_date: str) -> DataSourceConfig:
    """Return the current source2 config backed by yFinance files.

    source2 is the comparison data source: the side used to identify,
    quantify, and explain differences against source1.

    Args:
        from_date:
            Inclusive start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive end date in ``YYYY-MM-DD`` format.

    Returns:
        Default source2 data-source config.
    """
    return DataSourceConfig(
        name="yFinance",
        role="source2",
        prices_path=date_ranged_path(schema.PATH_SOURCE2_PRICES, from_date, to_date),
        dividends_path=date_ranged_path(
            schema.PATH_SOURCE2_DIVIDENDS,
            from_date,
            to_date,
        ),
        splits_path=date_ranged_path(schema.PATH_SOURCE2_SPLITS, from_date, to_date),
    )


def load_data_source(config: DataSourceConfig) -> DataSourceDataset:
    """Validate and load one normalized data-source dataset.

    The return audit consumes this normalized contract rather than any
    provider-native file schema. Acquisition adapters are responsible for
    writing CSVs that match the contract before this loader runs.

    Args:
        config:
            Data-source config with date-specific normalized file paths.

    Returns:
        Loaded normalized data-source dataset.
    """
    _validate_csv_columns(config.prices_path, schema.DATA_SOURCE_PRICE_COLUMNS)
    _validate_csv_columns(config.dividends_path, schema.DATA_SOURCE_DIVIDEND_COLUMNS)
    _validate_csv_columns(config.splits_path, schema.DATA_SOURCE_SPLIT_COLUMNS)

    return DataSourceDataset(
        name=config.name,
        role=config.role,
        prices=pl.scan_csv(config.prices_path),
        dividends=pl.scan_csv(config.dividends_path),
        splits=pl.scan_csv(config.splits_path),
    )


def load_data_sources(
    source1_config: DataSourceConfig,
    source2_config: DataSourceConfig,
) -> tuple[DataSourceDataset, DataSourceDataset]:
    """Load one audited source and one comparison source.

    Args:
        source1_config:
            Config for source1, the audited data source.

        source2_config:
            Config for source2, the comparison data source.

    Returns:
        Loaded source1 and source2 datasets in audit-role order.

    Raises:
        ValueError:
            Raised if either config has the wrong source role.
    """
    if source1_config.role != "source1":
        raise ValueError(f"source1_config role must be 'source1'; found {source1_config.role}.")
    if source2_config.role != "source2":
        raise ValueError(f"source2_config role must be 'source2'; found {source2_config.role}.")

    return load_data_source(source1_config), load_data_source(source2_config)


def load_default_data_sources(
    from_date: str,
    to_date: str,
) -> tuple[DataSourceDataset, DataSourceDataset]:
    """Load the current source1 and source2 normalized data sources.

    Args:
        from_date:
            Inclusive start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive end date in ``YYYY-MM-DD`` format.

    Returns:
        Loaded source1 and source2 datasets in audit-role order.
    """
    return load_data_sources(
        default_source1_config(from_date, to_date),
        default_source2_config(from_date, to_date),
    )


def _validate_csv_columns(path: Path, expected_columns: list[str]) -> None:
    """Fail if a normalized data-source CSV is missing or has schema drift.

    Args:
        path:
            CSV path to validate.

        expected_columns:
            Exact expected column names in order.

    Raises:
        FileNotFoundError:
            Raised if ``path`` does not exist.

        AssertionError:
            Raised if the CSV columns do not exactly match ``expected_columns``.
    """
    if not path.exists():
        raise FileNotFoundError(f"Normalized data-source file does not exist: {path}")

    actual_columns = pl.scan_csv(path).collect_schema().names()
    if actual_columns != expected_columns:
        raise AssertionError(
            f"{path} columns must exactly be {expected_columns}; found {actual_columns}."
        )
