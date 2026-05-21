"""Build return-audit LazyFrames from normalized data-source inputs."""

# Third-party imports.
import polars as pl

# Project imports.
import data_source


def build_source1_close_lf(source1_data_source: data_source.DataSourceDataset) -> pl.LazyFrame:
    """Build normalized source1 data-source close prices.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

    Returns:
        LazyFrame with normalized ticker, date, and close columns. The output
        still uses ``ticker`` as a compatibility alias for downstream report
        columns.
    """
    return source1_data_source.prices.select(
        pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
        pl.col("date").str.to_date().alias("date"),
        pl.col("close").cast(pl.Float64).alias("close"),
    ).sort(["ticker", "date"])


def build_cumulative_factors_lf(
    source1_data_source: data_source.DataSourceDataset,
    close_lf: pl.LazyFrame,
    close_with_prior_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build backward-looking split/dividend adjustment factors.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

        close_lf:
            Normalized source1 close data by ticker/date.

        close_with_prior_lf:
            Source1 close data with prior close by ticker/date.

    Returns:
        LazyFrame with one cumulative adjustment factor per ticker/date.
    """
    # There are two related but different corporate-action conventions in this
    # file: backward price factors restate old prices onto the current adjusted
    # basis, while dividend/split factors describe the multiplicative one-day
    # adjustment needed to bridge raw and adjusted returns. Keeping those separate
    # prevents inverse split price factors from being compared to forward
    # dividend/split return factors later.
    # Backward-adjusted price history uses the inverse of the split ratio.
    # A 2-for-1 split has a dividend/split factor of 2.0, but prior prices are
    # multiplied by 1/2 so the historical series remains continuous.
    split_events_lf: pl.LazyFrame = source1_data_source.splits.select(
        pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
        pl.col("ex_date").str.to_date().alias("event_date"),
        pl.when(pl.col("amount").cast(pl.Float64) != 0.0)
        .then(1.0 / pl.col("amount").cast(pl.Float64))
        .otherwise(1.0)
        .alias("event_factor"),
    )

    # Cash dividends reduce the backward price factor by cash/prior_close. Sum
    # same-day cash distributions first: multiple cash records on one ex-date
    # are one economic distribution for return-adjustment purposes. Applying
    # separate component factors would introduce an artificial cross-term.
    dividend_events_lf: pl.LazyFrame = (
        source1_data_source.dividends.select(
            pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
            pl.col("ex_date").str.to_date().alias("event_date"),
            pl.col("amount").cast(pl.Float64).alias("cash_amount"),
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


def build_source1_explicit_factor_lf(
    source1_data_source: data_source.DataSourceDataset,
    close_with_prior_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build source1 explicit dividend/split adjustment factors.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

        close_with_prior_lf:
            Source1 close data with prior close attached by ticker.

    Returns:
        LazyFrame with one ``source1_div_split_factor_explicit`` value per
        ticker/date.
    """
    # Explicit dividend/split factors are multiplicative adjustment factors, not
    # standalone investment returns. A 2-for-1 split is represented as 2.0 and a
    # $1 dividend on a $100 prior close is represented as 1.01.
    source1_split_return_events_lf: pl.LazyFrame = source1_data_source.splits.select(
        pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
        pl.col("ex_date").str.to_date().alias("date"),
        pl.col("amount").cast(pl.Float64).alias("event_return_factor"),
    ).filter(pl.col("event_return_factor") != 0.0)

    # Dividend return impact is measured against the previous trading close. Sum
    # same-day cash distributions before computing the return factor; separate
    # component-level dividend factors are not economically equivalent.
    source1_dividend_return_events_lf: pl.LazyFrame = (
        source1_data_source.dividends.select(
            pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
            pl.col("ex_date").str.to_date().alias("date"),
            pl.col("amount").cast(pl.Float64).alias("cash_amount"),
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
        pl.concat([source1_split_return_events_lf, source1_dividend_return_events_lf])
        .group_by(["ticker", "date"])
        # Split and cash factors compound when both occur on a date, but same-day
        # cash distributions have already been combined into one cash factor.
        .agg(pl.col("event_return_factor").product().alias("source1_div_split_factor_explicit"))
    )


def build_source1_adjusted_returns_lf(
    close_lf: pl.LazyFrame,
    cumulative_factors_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build source1 adjusted closes, returns, diagnostics, and anomaly score.

    Args:
        close_lf:
            Normalized source1 close data by ticker/date.

        cumulative_factors_lf:
            Backward-looking split/dividend adjustment factors by ticker/date.

    Returns:
        LazyFrame with source1 adjusted close, return components,
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

    # This adjusted close is reconstructed from source1 raw closes plus source1
    # corporate actions. The legacy ``source1_*`` aliases are kept until the public
    # report schema migrates to source1/source2 naming.
    adjusted_lf = adjusted_lf.with_columns(
        (
            (pl.col("adj_close") - pl.col("adj_close").shift(1).over("ticker"))
            / pl.col("adj_close").shift(1).over("ticker")
        ).alias("source1_return"),
        (
            (pl.col("close") - pl.col("close").shift(1).over("ticker"))
            / pl.col("close").shift(1).over("ticker")
        ).alias("source1_return_price"),
    )

    # The implied factor is multiplicative so it can be compared directly to
    # explicit dividend/split factors.
    adjusted_lf = adjusted_lf.with_columns(
        pl.when(
            pl.col("source1_return").is_null()
            | pl.col("source1_return_price").is_null()
            | ((1.0 + pl.col("source1_return_price")) == 0.0)
        )
        .then(None)
        .otherwise((1.0 + pl.col("source1_return")) / (1.0 + pl.col("source1_return_price")))
        .alias("source1_div_split_factor_implied"),
    )

    # Nearby returns and raw close ratios provide context for classification. An
    # opposite adjacent-day move suggests a close-source artifact, while a raw
    # close ratio near 0.5, 2.0, etc. is split-shaped evidence even before event
    # records are reconciled.
    adjusted_lf = adjusted_lf.with_columns(
        pl.col("source1_return").abs().alias("abs_return"),
        pl.col("source1_return").shift(1).over("ticker").alias("prior_return"),
        pl.col("source1_return").shift(-1).over("ticker").alias("next_return"),
        (pl.col("close") / pl.col("close").shift(1).over("ticker")).alias("raw_close_ratio"),
    )

    # Rolling median/MAD gives the anomaly score a ticker-local baseline. This
    # avoids comparing a naturally volatile security against a quiet one and
    # keeps one-off extreme returns from dominating the baseline the way a mean
    # and standard deviation could.
    adjusted_lf = adjusted_lf.with_columns(
        pl.col("source1_return")
        .rolling_median(window_size=60, min_samples=20)
        .over("ticker")
        .alias("rolling_median_return")
    )

    adjusted_lf = adjusted_lf.with_columns(
        (
            (pl.col("source1_return") - pl.col("rolling_median_return"))
            .abs()
            .rolling_median(window_size=60, min_samples=20)
            .over("ticker")
        ).alias("rolling_mad_return")
    )

    # Robust z-score interprets the current return relative to the recent median
    # absolute deviation. The 1.4826 scale factor makes MAD comparable to standard
    # deviation under a normal distribution, while still being less sensitive to
    # outliers than ordinary standard deviation.
    adjusted_lf = adjusted_lf.with_columns(
        (
            pl.when(pl.col("rolling_mad_return").is_null())
            .then(None)
            .when(pl.col("rolling_mad_return") == 0.0)
            .then(None)
            .otherwise(
                (pl.col("source1_return") - pl.col("rolling_median_return"))
                / (1.4826 * pl.col("rolling_mad_return"))
            )
        ).alias("robust_z")
    )

    # The anomaly score is a triage signal, not a data source verdict. It combines
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
            # Very large absolute returns are suspicious even without data source
            # disagreement, because both sources may be carrying the same real
            # event or the same questionable treatment.
            pl.when(pl.col("abs_return") > 0.80).then(3).otherwise(0)
            + pl.when(pl.col("abs_return") > 0.50).then(2).otherwise(0)
            # Robust outlier points catch returns that are unusual for this
            # ticker, not merely large in universal percentage terms.
            + pl.when(pl.col("robust_z").abs() > 12.0).then(3).otherwise(0)
            + pl.when(pl.col("robust_z").abs() > 8.0).then(2).otherwise(0)
            # Compare against the recent absolute-return baseline so a 12% move
            # in a usually quiet stock ranks differently from a 12% move in a
            # highly volatile stock.
            + pl.when(pl.col("abs_return") > (10.0 * trailing_abs_median_expr))
            .then(3)
            .otherwise(0)
            # A move much larger than both neighboring returns is a local spike;
            # those often deserve review even when no obvious split ratio appears.
            + pl.when(
                (pl.col("abs_return") > 0.10)
                & (pl.col("abs_return") > (5.0 * neighbor_max_expr))
            )
            .then(3)
            .otherwise(0)
            # Raw close ratios near common split/reverse-split ratios are strong
            # corporate-action-shaped evidence. This is intentionally only a
            # triage signal: event records and research decide whether the move
            # is real and which source treated it correctly.
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
            # A large move followed by an opposite large move can indicate close
            # timing, stale-close repair, or another transient source artifact.
            + pl.when(
                (pl.col("source1_return") * pl.col("next_return") < 0.0)
                & (pl.col("abs_return") > 0.20)
                & (pl.col("next_return").abs() > 0.20)
            )
            .then(2)
            .otherwise(0)
        ).alias("heuristic_anomaly_score")
    )

    return adjusted_lf


def build_source1_div_split_lf(
    source1_data_source: data_source.DataSourceDataset,
) -> pl.LazyFrame:
    """Build compact source1 dividend/split event text by ticker/date.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

    Returns:
        LazyFrame with one legacy ``source1_div_split`` string per ticker/date.
    """
    return (
        pl.concat(
            [
                source1_data_source.splits.select(
                    pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
                    pl.col("ex_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.lit("sp:"),
                            pl.col("amount").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
                source1_data_source.dividends.select(
                    pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
                    pl.col("ex_date").str.to_date().alias("date"),
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
                            pl.col("amount").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
            ]
        )
        .group_by(["ticker", "date"])
        # Sorting makes same-day event markers canonical across sources. Without
        # this, equivalent event sets could differ only because input row order
        # happened to be different.
        .agg(pl.col("event_text").sort().str.join(" ").alias("source1_div_split"))
    )


def build_source2_explicit_factor_lf(
    source2_data_source: data_source.DataSourceDataset,
    source2_close_with_prior_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build source2 explicit dividend/split adjustment factors.

    Args:
        source2_data_source:
            Loaded normalized comparison data source.

        source2_close_with_prior_lf:
            Source2 close data with prior close attached by ticker.

    Returns:
        LazyFrame with one ``source2_div_split_factor_explicit`` value per
        ticker/date.
    """
    # The normalized split amount is already in factor form. For example, 2.0
    # means a 2-for-1 split adjustment factor, not a standalone investment return.
    source2_split_return_events_lf: pl.LazyFrame = source2_data_source.splits.select(
        pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
        pl.col("ex_date").str.to_date().alias("date"),
        pl.col("amount").cast(pl.Float64).alias("event_return_factor"),
    ).filter(pl.col("event_return_factor") != 0.0)

    # Build source2 dividend factors the same way as the source1 side so
    # data-source event records are compared using a common factor convention.
    source2_dividend_return_events_lf: pl.LazyFrame = (
        source2_data_source.dividends.select(
            pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
            pl.col("ex_date").str.to_date().alias("date"),
            pl.col("amount").cast(pl.Float64).alias("dividend_amount"),
        )
        .filter(pl.col("dividend_amount") != 0.0)
        .join(
            source2_close_with_prior_lf.select(
                pl.col("ticker"),
                pl.col("date"),
                pl.col("source2_prior_close"),
            ),
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(
            pl.when(
                pl.col("source2_prior_close").is_null()
                | (pl.col("source2_prior_close") == 0.0)
                | pl.col("dividend_amount").is_null()
            )
            .then(1.0)
            .otherwise(1.0 + (pl.col("dividend_amount") / pl.col("source2_prior_close")))
            .alias("event_return_factor")
        )
        .select(
            pl.col("ticker"),
            pl.col("date"),
            pl.col("event_return_factor"),
        )
    )

    return (
        pl.concat([source2_split_return_events_lf, source2_dividend_return_events_lf])
        .group_by(["ticker", "date"])
        # Compound any same-day source2 split/dividend effects into one
        # factor for comparison against adjusted-close behavior.
        .agg(pl.col("event_return_factor").product().alias("source2_div_split_factor_explicit"))
    )


def build_source2_close_with_prior_lf(
    source2_lookup_lf: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build source2 close prices with prior close.

    Args:
        source2_lookup_lf:
            Normalized source2 price and return lookup frame.

    Returns:
        LazyFrame with current and prior source2 close values.
    """
    return source2_lookup_lf.select(
        pl.col("ticker"),
        pl.col("date"),
        pl.col("source2_close"),
    ).with_columns(pl.col("source2_close").shift(1).over("ticker").alias("source2_prior_close"))


def build_source2_div_split_lf(
    source2_data_source: data_source.DataSourceDataset,
) -> pl.LazyFrame:
    """Build compact source2 dividend/split event text by ticker/date.

    Args:
        source2_data_source:
            Loaded normalized comparison data source.

    Returns:
        LazyFrame with one legacy ``source2_div_split`` string per ticker/date.
    """
    return (
        pl.concat(
            [
                source2_data_source.splits.select(
                    pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
                    pl.col("ex_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.lit("sp:"),
                            pl.col("amount").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
                source2_data_source.dividends.select(
                    pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
                    pl.col("ex_date").str.to_date().alias("date"),
                    pl.concat_str(
                        [
                            pl.lit("ca:"),
                            pl.col("amount").cast(pl.Float64).cast(pl.String),
                        ]
                    ).alias("event_text"),
                ),
            ]
        )
        .group_by(["ticker", "date"])
        # Keep source2 marker text canonical; source2 code normalizes
        # equivalent source1 cd/sc cash markers on demand.
        .agg(pl.col("event_text").sort().str.join(" ").alias("source2_div_split"))
    )


def build_source2_lookup_lf(
    source2_data_source: data_source.DataSourceDataset,
) -> pl.LazyFrame:
    """Build normalized source2 price and return lookup data.

    Args:
        source2_data_source:
            Loaded normalized comparison data source.

    Returns:
        LazyFrame with source2 close, adjusted close, price return, adjusted
        return, and implied dividend/split factor columns.
    """
    # Normalize source2 price data and calculate source2 adjusted returns.
    # Source2 adjusted_close is treated as an external source2 series; its
    # implied dividend/split factor is calculated from prices, not from event files.
    # The implied factor uses the same relationship as the source1 side:
    # (1 + adjusted return) / (1 + raw price return). This lets the audit compare
    # adjusted-close behavior with explicit event records using one convention.
    return (
        source2_data_source.prices.select(
            [
                pl.col("identifier").str.strip_chars().str.to_uppercase().alias("ticker"),
                pl.col("date").str.to_date().alias("date"),
                pl.col("close").cast(pl.Float64).alias("source2_close"),
                pl.col("adjusted_close").cast(pl.Float64).alias("source2_adj_close"),
            ]
        )
        .sort(["ticker", "date"])
        .with_columns(
            (
                (pl.col("source2_adj_close") - pl.col("source2_adj_close").shift(1).over("ticker"))
                / pl.col("source2_adj_close").shift(1).over("ticker")
            ).alias("source2_return"),
            (
                (pl.col("source2_close") - pl.col("source2_close").shift(1).over("ticker"))
                / pl.col("source2_close").shift(1).over("ticker")
            ).alias("source2_return_price"),
        )
        .with_columns(
            pl.when(
                pl.col("source2_return").is_null()
                | pl.col("source2_return_price").is_null()
                | ((1.0 + pl.col("source2_return_price")) == 0.0)
            )
            .then(None)
            .otherwise((1.0 + pl.col("source2_return")) / (1.0 + pl.col("source2_return_price")))
            .alias("source2_div_split_factor_implied"),
        )
    )
