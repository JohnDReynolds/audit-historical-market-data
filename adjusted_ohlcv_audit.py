"""Adjusted-OHLCV audit helpers."""

# Third-party imports.
import polars as pl

# Project imports.
from massive_data import MassiveData
import audit_schema as schema
import utilities as util


def audit_adjusted_ohlcv(
    massive_data: MassiveData,
    from_date: str,
    to_date: str,
) -> pl.DataFrame:
    """Audit Massive split-adjusted OHLCV values.

    This function compares Massive unadjusted OHLCV data against Massive
    split-adjusted OHLCV data by independently applying split adjustment
    factors from the Massive split-event file.

    The audit returns one row per mismatched OHLCV field.

    Args:
        massive_data:
            Loaded Massive data wrapper.

        from_date:
            Inclusive audit start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive audit end date in ``YYYY-MM-DD`` format.

    Returns:
        DataFrame containing only mismatched OHLCV values.

    Raises:
        ValueError:
            Raised if any required input columns are missing.
    """
    price_columns: list[str] = [
        "open",
        "high",
        "low",
        "close",
        "vwap",
    ]

    volume_columns: list[str] = [
        "volume",
    ]

    passthrough_columns: list[str] = [
        "transactions",
    ]

    audited_columns: list[str] = price_columns + volume_columns + passthrough_columns

    required_ohlcv_columns: set[str] = {
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "transactions",
    }

    required_splits_columns: set[str] = {
        "ticker",
        "execution_date",
        "split_from",
        "split_to",
    }

    # Fail early if any input file is missing columns required by the audit.
    util.require_lazy_columns(
        massive_data.unadjusted_ohlcv,
        required_ohlcv_columns,
        "unadjusted prices CSV",
    )
    util.require_lazy_columns(
        massive_data.adjusted_ohlcv,
        required_ohlcv_columns,
        "adjusted prices CSV",
    )
    util.require_lazy_columns(
        massive_data.splits,
        required_splits_columns,
        "splits CSV",
    )

    # Convert split rows into price adjustment factors.
    #
    # For a 2-for-1 split:
    # - split_from = 1
    # - split_to = 2
    # - split_price_factor = 1 / 2 = 0.5
    splits_lf: pl.LazyFrame = massive_data.splits.with_columns(
        pl.col("execution_date").str.to_date().alias("execution_date"),
        pl.col("split_from").cast(pl.Float64),
        pl.col("split_to").cast(pl.Float64),
    ).with_columns((pl.col("split_from") / pl.col("split_to")).alias("split_price_factor"))

    # For each ticker/date, find all later split events and multiply their
    # price factors together. The split execution date itself is excluded
    # because backward adjustment applies to dates before the event.
    split_factors_lf: pl.LazyFrame = (
        massive_data.unadjusted_ohlcv.select("ticker", "date")
        .unique()
        .join(
            splits_lf.select(
                "ticker",
                "execution_date",
                "split_price_factor",
            ),
            on="ticker",
            how="left",
        )
        .filter(pl.col("execution_date").is_null() | (pl.col("date") < pl.col("execution_date")))
        .group_by("ticker", "date")
        .agg(pl.col("split_price_factor").product().fill_null(1.0).alias("adj_factor"))
    )

    # Attach the cumulative split factor to each unadjusted OHLCV row.
    manual_lf: pl.LazyFrame = massive_data.unadjusted_ohlcv.join(
        split_factors_lf,
        on=["ticker", "date"],
        how="left",
    ).with_columns(pl.col("adj_factor").fill_null(1.0))

    # Price fields are adjusted by multiplying by the split price factor.
    for column_name in price_columns:
        manual_lf = manual_lf.with_columns(
            (pl.col(column_name).cast(pl.Float64) * pl.col("adj_factor")).alias(
                f"{column_name}_expected"
            )
        )

    # Volume fields move inversely to price adjustment factors.
    for column_name in volume_columns:
        manual_lf = manual_lf.with_columns(
            (pl.col(column_name).cast(pl.Float64) / pl.col("adj_factor")).alias(
                f"{column_name}_expected"
            )
        )

    # Passthrough fields are not split-adjusted by this audit.
    for column_name in passthrough_columns:
        manual_lf = manual_lf.with_columns(
            pl.col(column_name).cast(pl.Float64).alias(f"{column_name}_expected")
        )

    # Rename source columns before joining so manual, adjusted, and expected
    # values can coexist in the same audit frame.
    for column_name in audited_columns:
        manual_lf = manual_lf.rename({column_name: f"{column_name}_unadjusted"})

    adjusted_for_join_lf: pl.LazyFrame = massive_data.adjusted_ohlcv

    for column_name in audited_columns:
        adjusted_for_join_lf = adjusted_for_join_lf.rename(
            {column_name: f"{column_name}_adjusted"}
        )

    audit_lf: pl.LazyFrame = manual_lf.join(
        adjusted_for_join_lf,
        on=["ticker", "date"],
        how="inner",
    )

    # Convert the wide audit row into one row per OHLCV field.
    long_frames: list[pl.LazyFrame] = []

    for column_name in audited_columns:
        long_frames.append(
            audit_lf.select(
                pl.col("ticker"),
                pl.col("date"),
                pl.lit(column_name).alias("field"),
                pl.col("adj_factor"),
                pl.col(f"{column_name}_unadjusted").cast(pl.Float64).alias("unadjusted"),
                pl.col(f"{column_name}_adjusted").cast(pl.Float64).alias("adjusted"),
                pl.col(f"{column_name}_expected").cast(pl.Float64).alias("expected"),
            )
        )

    # Compute percentage difference instead of absolute difference.
    long_audit_lf: pl.LazyFrame = pl.concat(long_frames).with_columns(
        pl.when((pl.col("expected") == 0.0) & (pl.col("adjusted") == 0.0))
        .then(0.0)
        .when(pl.col("expected") == 0.0)
        .then(float("inf"))
        .otherwise((pl.col("adjusted") - pl.col("expected")) / pl.col("expected"))
        .alias("pct_diff")
    )

    df: pl.DataFrame = (
        long_audit_lf.filter(pl.col("pct_diff").abs() > schema.TOLERANCE_4)
        .select(
            [
                "ticker",
                "date",
                "field",
                "adj_factor",
                "unadjusted",
                "adjusted",
                "expected",
                "pct_diff",
            ]
        )
        .collect()
    )

    # Persist audit output to disk.
    df.write_csv(f"{schema.PATH_AUDITED_ADJUSTED_OHLCV}.{from_date}.{to_date}.csv")

    return df
