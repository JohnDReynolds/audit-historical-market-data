"""Input-column validation helpers for audit calculations."""

# Third-party imports.
import polars as pl

# Project imports.
import audit_schema as schema
import data_source
import real_world_events
import utilities as util


def require_audit_returns_columns(
    source1_data_source: data_source.DataSourceDataset,
    source2_data_source: data_source.DataSourceDataset,
    real_world_events_path: str,
    has_real_world_events_file: bool,
) -> None:
    """Validate all columns required by return-audit calculations.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

        source2_data_source:
            Loaded normalized comparison data source.

        real_world_events_path:
            Path to the optional real-world events CSV.

        has_real_world_events_file:
            Whether the optional real-world events CSV exists.

    Raises:
        ValueError:
            Raised if any required input columns are missing.
    """
    if has_real_world_events_file:
        real_world_events_raw_lf: pl.LazyFrame = pl.scan_csv(real_world_events_path)
        real_world_events_required_columns = set(
            real_world_events.REQUIRED_REAL_WORLD_EVENT_COLUMNS
        )

        util.require_lazy_columns(
            real_world_events_raw_lf,
            real_world_events_required_columns,
            "real-world events CSV",
        )

    # Fail early if any normalized data-source file is missing columns required
    # by the generic return audit. Source-specific acquisition modules are
    # responsible for mapping their native files into this contract.
    util.require_lazy_columns(
        source1_data_source.prices,
        set(schema.DATA_SOURCE_PRICE_COLUMNS),
        "source1 prices CSV",
    )
    util.require_lazy_columns(
        source1_data_source.splits,
        set(schema.DATA_SOURCE_SPLIT_COLUMNS),
        "source1 splits CSV",
    )
    util.require_lazy_columns(
        source1_data_source.dividends,
        set(schema.DATA_SOURCE_DIVIDEND_COLUMNS),
        "source1 dividends CSV",
    )
    util.require_lazy_columns(
        source2_data_source.prices,
        set(schema.DATA_SOURCE_PRICE_COLUMNS),
        "source2 prices CSV",
    )
    util.require_lazy_columns(
        source2_data_source.splits,
        set(schema.DATA_SOURCE_SPLIT_COLUMNS),
        "source2 splits CSV",
    )
    util.require_lazy_columns(
        source2_data_source.dividends,
        set(schema.DATA_SOURCE_DIVIDEND_COLUMNS),
        "source2 dividends CSV",
    )
