"""Build return-audit LazyFrames from Massive and yFinance source data."""

# Third-party imports.
import polars as pl

# Project imports.
from massive_data import MassiveData
from yfinance_data import YFinanceData


def build_close_lf(massive_data: MassiveData) -> pl.LazyFrame:
    """Build normalized Massive close prices.

    Args:
        massive_data:
            Loaded Massive data wrapper.

    Returns:
        LazyFrame with normalized ticker, date, and close columns.
    """
    return massive_data.unadjusted_ohlcv.select(
        pl.col("ticker").str.strip_chars().str.to_uppercase(),
        pl.col("date"),
        pl.col("close").cast(pl.Float64).alias("close"),
    ).sort(["ticker", "date"])


def build_cumulative_factors_lf(
    massive_data: MassiveData,
    close_lf: pl.LazyFrame,
    close_with_prior_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build backward-looking split/dividend adjustment factors.

    Args:
        massive_data:
            Loaded Massive data wrapper.

        close_lf:
            Normalized Massive close data by ticker/date.

        close_with_prior_lf:
            Massive close data with prior close by ticker/date.

    Returns:
        LazyFrame with one cumulative adjustment factor per ticker/date.
    """
    # There are two related but different corporate-action conventions in this
    # file: backward price factors restate old prices onto the current adjusted
    # basis, while dividend/split factors describe the multiplicative one-day
    # adjustment needed to bridge raw and adjusted returns. Keeping those separate
    # prevents split_from / split_to price factors from being compared to
    # split_to / split_from dividend/split factors later.
    # Backward-adjusted price history uses the inverse of the split ratio.
    # A 2-for-1 split has a dividend/split factor of 2.0, but prior prices are
    # multiplied by 1/2 so the historical series remains continuous.
    split_events_lf: pl.LazyFrame = massive_data.splits.select(
        pl.col("ticker").str.strip_chars().str.to_uppercase(),
        pl.col("execution_date").str.to_date().alias("event_date"),
        (pl.col("split_from").cast(pl.Float64) / pl.col("split_to").cast(pl.Float64)).alias(
            "event_factor"
        ),
    )

    # Cash dividends reduce the backward price factor by cash/prior_close. Sum
    # same-day cash distributions first: multiple cash records on one ex-date
    # are one economic distribution for return-adjustment purposes. Applying
    # separate component factors would introduce an artificial cross-term.
    dividend_events_lf: pl.LazyFrame = (
        massive_data.dividends.select(
            pl.col("ticker").str.strip_chars().str.to_uppercase(),
            pl.col("ex_dividend_date").str.to_date().alias("event_date"),
            pl.col("cash_amount").cast(pl.Float64).alias("cash_amount"),
        )
        .group_by(["ticker", "event_date"])
        .agg(pl.col("cash_amount").sum().alias("cash_amount"))
        .join(
            close_with_prior_lf.select(
                pl.col("ticker"),
                pl.col("date").alias("event_date"),
                pl.col("prior_close"),
            ),
            on=["ticker", "event_date"],
            how="left",
        )
        .with_columns(
            pl.when(
                pl.col("prior_close").is_null()
                | (pl.col("prior_close") == 0.0)
                | pl.col("cash_amount").is_null()
            )
            .then(1.0)
            .otherwise((pl.col("prior_close") - pl.col("cash_amount")) / pl.col("prior_close"))
            .alias("event_factor")
        )
        .select(
            pl.col("ticker"),
            pl.col("event_date"),
            pl.col("event_factor"),
        )
    )

    events_lf: pl.LazyFrame = pl.concat([split_events_lf, dividend_events_lf])

    # For each price date, multiply every later corporate-action factor.
    # Filtering date < event_date intentionally excludes the action date itself:
    # the event impact appears in the return from prior close into event date.
    cumulative_factors_lf: pl.LazyFrame = (
        close_lf.select("ticker", "date")
        .unique()
        .join(
            events_lf,
            on="ticker",
            how="left",
        )
        .filter(pl.col("event_date").is_null() | (pl.col("date") < pl.col("event_date")))
        .group_by("ticker", "date")
        .agg(pl.col("event_factor").product().fill_null(1.0).alias("adj_factor"))
    )

    return cumulative_factors_lf


def build_massive_explicit_factor_lf(
    massive_data: MassiveData,
    close_with_prior_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build Massive explicit dividend/split adjustment factors.

    Args:
        massive_data:
            Loaded Massive data wrapper.

        close_with_prior_lf:
            Massive close data with prior close attached by ticker.

    Returns:
        LazyFrame with one ``ms_div_split_factor_explicit`` value per
        ticker/date.
    """
    # Explicit dividend/split factors are multiplicative adjustment factors, not
    # standalone investment returns. A 2-for-1 split is represented as 2.0 and a
    # $1 dividend on a $100 prior close is represented as 1.01.
    ms_split_return_events_lf: pl.LazyFrame = massive_data.splits.select(
        pl.col("ticker").str.strip_chars().str.to_uppercase(),
        pl.col("execution_date").str.to_date().alias("date"),
        (pl.col("split_to").cast(pl.Float64) / pl.col("split_from").cast(pl.Float64)).alias(
            "event_return_factor"
        ),
    )

    # Dividend return impact is measured against the previous trading close. Sum
    # same-day cash distributions before computing the return factor; separate
    # component-level dividend factors are not economically equivalent.
    ms_dividend_return_events_lf: pl.LazyFrame = (
        massive_data.dividends.select(
            pl.col("ticker").str.strip_chars().str.to_uppercase(),
            pl.col("ex_dividend_date").str.to_date().alias("date"),
            pl.col("cash_amount").cast(pl.Float64).alias("cash_amount"),
        )
        .group_by(["ticker", "date"])
        .agg(pl.col("cash_amount").sum().alias("cash_amount"))
        .join(
            close_with_prior_lf.select(
                pl.col("ticker"),
                pl.col("date"),
                pl.col("prior_close"),
            ),
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(
            pl.when(
                pl.col("prior_close").is_null()
                | (pl.col("prior_close") == 0.0)
                | pl.col("cash_amount").is_null()
            )
            .then(1.0)
            .otherwise(1.0 + (pl.col("cash_amount") / pl.col("prior_close")))
            .alias("event_return_factor")
        )
        .select(
            pl.col("ticker"),
            pl.col("date"),
            pl.col("event_return_factor"),
        )
    )

    return (
        pl.concat([ms_split_return_events_lf, ms_dividend_return_events_lf])
        .group_by(["ticker", "date"])
        # Split and cash factors compound when both occur on a date, but same-day
        # cash distributions have already been combined into one cash factor.
        .agg(pl.col("event_return_factor").product().alias("ms_div_split_factor_explicit"))
    )


def build_massive_adjusted_returns_lf(
    close_lf: pl.LazyFrame,
    cumulative_factors_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build Massive adjusted closes, returns, diagnostics, and anomaly score.

    Args:
        close_lf:
            Normalized Massive close data by ticker/date.

        cumulative_factors_lf:
            Backward-looking split/dividend adjustment factors by ticker/date.

    Returns:
        LazyFrame with Massive adjusted close, return components,
        rolling diagnostics, and heuristic anomaly score.
    """
    adjusted_lf: pl.LazyFrame = (
        close_lf.join(
            cumulative_factors_lf,
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(pl.col("adj_factor").fill_null(1.0))
        .with_columns((pl.col("close") * pl.col("adj_factor")).alias("adj_close"))
        .sort(["ticker", "date"])
    )

    # This adjusted close is reconstructed from Massive raw closes plus Massive
    # corporate actions. Differences from yFinance therefore test the Massive
    # action chain's total-return behavior, not the split-adjusted aggregate
    # endpoint alone.
    # ms_return is the dividend/split-adjusted return derived from the audit's
    # reconstructed adjusted close. ms_return_price is the raw close-to-close
    # price return before corporate-action effects.
    adjusted_lf = adjusted_lf.with_columns(
        (
            (pl.col("adj_close") - pl.col("adj_close").shift(1).over("ticker"))
            / pl.col("adj_close").shift(1).over("ticker")
        ).alias("ms_return"),
        (
            (pl.col("close") - pl.col("close").shift(1).over("ticker"))
            / pl.col("close").shift(1).over("ticker")
        ).alias("ms_return_price"),
    )

    # The implied factor is multiplicative so it can be compared directly to
    # explicit dividend/split factors.
    adjusted_lf = adjusted_lf.with_columns(
        pl.when(
            pl.col("ms_return").is_null()
            | pl.col("ms_return_price").is_null()
            | ((1.0 + pl.col("ms_return_price")) == 0.0)
        )
        .then(None)
        .otherwise((1.0 + pl.col("ms_return")) / (1.0 + pl.col("ms_return_price")))
        .alias("ms_div_split_factor_implied"),
    )

    # Nearby returns and raw close ratios provide context for classification. An
    # opposite adjacent-day move suggests a close-source artifact, while a raw
    # close ratio near 0.5, 2.0, etc. is split-shaped evidence even before event
    # records are reconciled.
    adjusted_lf = adjusted_lf.with_columns(
        pl.col("ms_return").abs().alias("abs_return"),
        pl.col("ms_return").shift(1).over("ticker").alias("prior_return"),
        pl.col("ms_return").shift(-1).over("ticker").alias("next_return"),
        (pl.col("close") / pl.col("close").shift(1).over("ticker")).alias("raw_close_ratio"),
    )

    adjusted_lf = adjusted_lf.with_columns(
        pl.col("ms_return")
        .rolling_median(window_size=60, min_samples=20)
        .over("ticker")
        .alias("rolling_median_return")
    )

    adjusted_lf = adjusted_lf.with_columns(
        (
            (pl.col("ms_return") - pl.col("rolling_median_return"))
            .abs()
            .rolling_median(window_size=60, min_samples=20)
            .over("ticker")
        ).alias("rolling_mad_return")
    )

    adjusted_lf = adjusted_lf.with_columns(
        (
            pl.when(pl.col("rolling_mad_return").is_null())
            .then(None)
            .when(pl.col("rolling_mad_return") == 0.0)
            .then(None)
            .otherwise(
                (pl.col("ms_return") - pl.col("rolling_median_return"))
                / (1.4826 * pl.col("rolling_mad_return"))
            )
        ).alias("robust_z")
    )

    # The anomaly score is a triage signal, not a vendor verdict. It combines
    # independent clues rather than producing a probability: absolute return
    # size, robust deviation from recent behavior, split-shaped raw close ratios,
    # and adjacent-day reversals. Research and reconciliation decide correctness.
    trailing_abs_median_expr: pl.Expr = (
        pl.col("abs_return").rolling_median(window_size=20, min_samples=10).over("ticker")
    )

    neighbor_max_expr: pl.Expr = pl.max_horizontal(
        pl.col("prior_return").abs(),
        pl.col("next_return").abs(),
    )

    adjusted_lf = adjusted_lf.with_columns(
        (
            pl.when(pl.col("abs_return") > 0.80).then(3).otherwise(0)
            + pl.when(pl.col("abs_return") > 0.50).then(2).otherwise(0)
            + pl.when(pl.col("robust_z").abs() > 12.0).then(3).otherwise(0)
            + pl.when(pl.col("robust_z").abs() > 8.0).then(2).otherwise(0)
            + pl.when(pl.col("abs_return") > (10.0 * trailing_abs_median_expr))
            .then(3)
            .otherwise(0)
            + pl.when(
                (pl.col("abs_return") > 0.10)
                & (pl.col("abs_return") > (5.0 * neighbor_max_expr))
            )
            .then(3)
            .otherwise(0)
            + pl.when(
                ((pl.col("raw_close_ratio") - 0.5).abs() < 0.02)
                | ((pl.col("raw_close_ratio") - 2.0).abs() < 0.04)
                | ((pl.col("raw_close_ratio") - 0.3333333333).abs() < 0.02)
                | ((pl.col("raw_close_ratio") - 3.0).abs() < 0.06)
                | ((pl.col("raw_close_ratio") - 0.25).abs() < 0.02)
                | ((pl.col("raw_close_ratio") - 4.0).abs() < 0.08)
            )
            .then(5)
            .otherwise(0)
            + pl.when(
                (pl.col("ms_return") * pl.col("next_return") < 0.0)
                & (pl.col("abs_return") > 0.20)
                & (pl.col("next_return").abs() > 0.20)
            )
            .then(2)
            .otherwise(0)
        ).alias("heuristic_anomaly_score")
    )

    return adjusted_lf


def build_massive_div_split_lf(massive_data: MassiveData) -> pl.LazyFrame:
    """Build compact Massive dividend/split event text by ticker/date.

    Args:
        massive_data:
            Loaded Massive data wrapper.

    Returns:
        LazyFrame with one ``ms_div_split`` string per ticker/date.
    """
    return (
        pl.concat(
            [
                massive_data.splits.select(
                    pl.col("ticker").str.strip_chars().str.to_uppercase(),
                    pl.col("execution_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.lit("sp:"),
                            (
                                pl.col("split_to").cast(pl.Float64)
                                / pl.col("split_from").cast(pl.Float64)
                            ).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
                massive_data.dividends.select(
                    pl.col("ticker").str.strip_chars().str.to_uppercase(),
                    pl.col("ex_dividend_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.when(
                                pl.col("dividend_type")
                                .cast(pl.Utf8)
                                .str.strip_chars()
                                .str.to_lowercase()
                                .is_in(["cd", "sc"])
                            )
                            .then(
                                pl.col("dividend_type")
                                .cast(pl.Utf8)
                                .str.strip_chars()
                                .str.to_lowercase()
                            )
                            .otherwise(pl.lit("ca")),
                            pl.lit(":"),
                            pl.col("cash_amount").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
            ]
        )
        .group_by(["ticker", "date"])
        # Sorting makes same-day event markers canonical across sources. Without
        # this, equivalent event sets could differ only because input row order
        # happened to be different.
        .agg(pl.col("event_text").sort().str.join(" ").alias("ms_div_split"))
    )


def build_yfinance_explicit_factor_lf(
    yfinance_data: YFinanceData,
    yfinance_close_with_prior_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build yFinance explicit dividend/split adjustment factors.

    Args:
        yfinance_data:
            Loaded yFinance data wrapper.

        yfinance_close_with_prior_lf:
            yFinance close data with prior close attached by ticker.

    Returns:
        LazyFrame with one ``yf_div_split_factor_explicit`` value per
        ticker/date.
    """
    # yFinance split_ratio is already in factor form. For example, 2.0 means a
    # 2-for-1 split adjustment factor, not a standalone investment return.
    yf_split_return_events_lf: pl.LazyFrame = yfinance_data.splits.select(
        pl.col("ticker").str.strip_chars().str.to_uppercase(),
        pl.col("execution_date").str.to_date().alias("date"),
        pl.col("split_ratio").cast(pl.Float64).alias("event_return_factor"),
    ).filter(pl.col("event_return_factor") != 0.0)

    # Build yFinance's explicit dividend factor the same way as Massive's so
    # vendor event records are compared using a common factor convention.
    yf_dividend_return_events_lf: pl.LazyFrame = (
        yfinance_data.dividends.select(
            pl.col("ticker").str.strip_chars().str.to_uppercase(),
            pl.col("ex_dividend_date").str.to_date().alias("date"),
            pl.col("cash_amount").cast(pl.Float64).alias("dividend_amount"),
        )
        .filter(pl.col("dividend_amount") != 0.0)
        .join(
            yfinance_close_with_prior_lf.select(
                pl.col("ticker"),
                pl.col("date"),
                pl.col("yf_prior_close"),
            ),
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(
            pl.when(
                pl.col("yf_prior_close").is_null()
                | (pl.col("yf_prior_close") == 0.0)
                | pl.col("dividend_amount").is_null()
            )
            .then(1.0)
            .otherwise(1.0 + (pl.col("dividend_amount") / pl.col("yf_prior_close")))
            .alias("event_return_factor")
        )
        .select(
            pl.col("ticker"),
            pl.col("date"),
            pl.col("event_return_factor"),
        )
    )

    return (
        pl.concat([yf_split_return_events_lf, yf_dividend_return_events_lf])
        .group_by(["ticker", "date"])
        # Compound any same-day yFinance split/dividend effects into one factor
        # for comparison against yFinance's adjusted-close behavior.
        .agg(pl.col("event_return_factor").product().alias("yf_div_split_factor_explicit"))
    )


def build_yfinance_close_with_prior_lf(
    yfinance_lookup_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build yFinance close prices with prior close.

    Args:
        yfinance_lookup_lf:
            Normalized yFinance price and return lookup frame.

    Returns:
        LazyFrame with current and prior yFinance close values.
    """
    return yfinance_lookup_lf.select(
        pl.col("ticker"),
        pl.col("date"),
        pl.col("yf_close"),
    ).with_columns(pl.col("yf_close").shift(1).over("ticker").alias("yf_prior_close"))


def build_yfinance_div_split_lf(yfinance_data: YFinanceData) -> pl.LazyFrame:
    """Build compact yFinance dividend/split event text by ticker/date.

    Args:
        yfinance_data:
            Loaded yFinance data wrapper.

    Returns:
        LazyFrame with one ``yf_div_split`` string per ticker/date.
    """
    return (
        pl.concat(
            [
                yfinance_data.splits.select(
                    pl.col("ticker").str.strip_chars().str.to_uppercase(),
                    pl.col("execution_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.lit("sp:"),
                            pl.col("split_ratio").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
                yfinance_data.dividends.select(
                    pl.col("ticker").str.strip_chars().str.to_uppercase(),
                    pl.col("ex_dividend_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.lit("ca:"),
                            pl.col("cash_amount").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
            ]
        )
        .group_by(["ticker", "date"])
        # Keep yFinance marker text canonical; comparison code normalizes
        # equivalent Massive cd/sc cash markers on demand.
        .agg(pl.col("event_text").sort().str.join(" ").alias("yf_div_split"))
    )


def build_yfinance_lookup_lf(yfinance_data: YFinanceData) -> pl.LazyFrame:
    """Build normalized yFinance price and return lookup data.

    Args:
        yfinance_data:
            Loaded yFinance data wrapper.

    Returns:
        LazyFrame with yFinance close, adjusted close, price return, adjusted
        return, and implied dividend/split factor columns.
    """
    # Normalize yFinance price data and calculate yFinance adjusted returns.
    # yFinance adjusted_close is treated as an external comparison series; its
    # implied dividend/split factor is calculated from prices, not from event files.
    return (
        yfinance_data.ohlcv.select(
            [
                pl.col("ticker").str.strip_chars().str.to_uppercase(),
                pl.col("date").str.strptime(pl.Date, "%Y-%m-%d").alias("date"),
                pl.col("close").cast(pl.Float64).alias("yf_close"),
                pl.col("adjusted_close").cast(pl.Float64).alias("yf_adj_close"),
            ]
        )
        .sort(["ticker", "date"])
        .with_columns(
            (
                (pl.col("yf_adj_close") - pl.col("yf_adj_close").shift(1).over("ticker"))
                / pl.col("yf_adj_close").shift(1).over("ticker")
            ).alias("yf_return"),
            (
                (pl.col("yf_close") - pl.col("yf_close").shift(1).over("ticker"))
                / pl.col("yf_close").shift(1).over("ticker")
            ).alias("yf_return_price"),
        )
        .with_columns(
            pl.when(
                pl.col("yf_return").is_null()
                | pl.col("yf_return_price").is_null()
                | ((1.0 + pl.col("yf_return_price")) == 0.0)
            )
            .then(None)
            .otherwise((1.0 + pl.col("yf_return")) / (1.0 + pl.col("yf_return_price")))
            .alias("yf_div_split_factor_implied"),
        )
    )
