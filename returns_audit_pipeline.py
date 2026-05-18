"""Build the detailed return-audit Polars pipeline."""

# Standard library imports.
from typing import cast

# Third-party imports.
import polars as pl

# Project imports.
import audit_classification
import audit_schema as schema
import real_world_events
import returns_builders
from massive_data import MassiveData
from yfinance_data import YFinanceData


def build_returns_audit_lf(
    massive_data: MassiveData,
    yfinance_data: YFinanceData,
) -> pl.LazyFrame:
    """Build the detailed lazy return-audit frame.

    Args:
        massive_data:
            Loaded Massive data wrapper.

        yfinance_data:
            Loaded yFinance data wrapper.

    Returns:
        LazyFrame with raw return diagnostics, source comparisons, event
        comparisons, and deterministic analysis fields.
    """
    # Build each source's return and event components separately first. The
    # pipeline later joins them by ticker/date so every diagnostic can compare
    # Massive and yFinance using the same row-level vocabulary.
    yfinance_lookup_lf: pl.LazyFrame = returns_builders.build_yfinance_lookup_lf(yfinance_data)
    close_lf: pl.LazyFrame = returns_builders.build_close_lf(massive_data)

    close_with_prior_lf: pl.LazyFrame = close_lf.with_columns(
        pl.col("close").shift(1).over("ticker").alias("prior_close")
    )

    yfinance_close_with_prior_lf: pl.LazyFrame = (
        returns_builders.build_yfinance_close_with_prior_lf(
            yfinance_lookup_lf,
        )
    )

    cumulative_factors_lf: pl.LazyFrame = returns_builders.build_cumulative_factors_lf(
        massive_data,
        close_lf,
        close_with_prior_lf,
    )

    ms_actual_return_lf: pl.LazyFrame = returns_builders.build_massive_actual_return_lf(
        massive_data,
        close_with_prior_lf,
    )
    yf_actual_return_lf: pl.LazyFrame = returns_builders.build_yfinance_actual_return_lf(
        yfinance_data,
        yfinance_close_with_prior_lf,
    )

    adjusted_lf: pl.LazyFrame = returns_builders.build_massive_adjusted_returns_lf(
        close_lf,
        cumulative_factors_lf,
    )

    ms_div_split_lf: pl.LazyFrame = returns_builders.build_massive_div_split_lf(massive_data)
    yf_div_split_lf: pl.LazyFrame = returns_builders.build_yfinance_div_split_lf(yfinance_data)

    # Event marker strings are informational but important for classification:
    # they identify which source explicitly reported a dividend/split event on
    # the trading date.
    adjusted_lf = adjusted_lf.join(
        ms_div_split_lf,
        on=["ticker", "date"],
        how="left",
    ).with_columns(pl.col("ms_div_split").fill_null(""))

    adjusted_lf = adjusted_lf.join(
        yf_div_split_lf,
        on=["ticker", "date"],
        how="left",
    ).with_columns(pl.col("yf_div_split").fill_null(""))

    df_lf: pl.LazyFrame = (
        adjusted_lf.select(
            [
                "ticker",
                "date",
                "adj_factor",
                "close",
                "adj_close",
                "ms_return",
                "ms_return_price",
                "ms_return_div_split_implied",
                "heuristic_anomaly_score",
                "ms_div_split",
                "yf_div_split",
                # Heuristic anomaly score inputs
                "abs_return",
                "prior_return",
                "next_return",
                "raw_close_ratio",
                "rolling_median_return",
                "rolling_mad_return",
                "robust_z",
            ]
        )
        .join(
            yfinance_lookup_lf,
            on=["ticker", "date"],
            how="left",
        )
        .join(
            ms_actual_return_lf,
            on=["ticker", "date"],
            how="left",
        )
        .join(
            yf_actual_return_lf,
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(
            pl.col("ms_return_div_split_actual").fill_null(0.0),
            pl.col("yf_return_div_split_actual").fill_null(0.0),
        )
        .with_columns(
            # yFinance does not publish an adjustment factor directly here, so
            # infer it from adjusted close divided by raw close.
            pl.when(pl.col("yf_close").is_null() | (pl.col("yf_close") == 0.0))
            .then(None)
            .otherwise(pl.col("yf_adj_close") / pl.col("yf_close"))
            .alias("yf_adj_factor")
        )
        # Sign convention: diff_return later uses yFinance minus Massive.
        # Positive means yFinance return is higher; negative means yFinance
        # return is lower.
        .with_columns((pl.col("yf_return") - pl.col("ms_return")).alias("total_return_diff"))
        .sort(["ticker", "date"])
        .with_columns(
            pl.col("total_return_diff").shift(1).over("ticker").alias("prior_total_return_diff"),
            pl.col("total_return_diff").shift(-1).over("ticker").alias("next_total_return_diff"),
            pl.col("adj_factor").shift(1).over("ticker").alias("prior_ms_adj_factor"),
            pl.col("yf_adj_factor").shift(1).over("ticker").alias("prior_yf_adj_factor"),
            pl.col("ms_div_split").shift(1).over("ticker").alias("prior_ms_div_split"),
            pl.col("ms_div_split").shift(-1).over("ticker").alias("next_ms_div_split"),
            pl.col("yf_div_split").shift(1).over("ticker").alias("prior_yf_div_split"),
            pl.col("yf_div_split").shift(-1).over("ticker").alias("next_yf_div_split"),
        )
        .with_columns(
            # Adjustment-factor changes expose discontinuities in the adjusted
            # close chain. Comparing factor changes between vendors helps tell
            # apart a real event from a vendor normalization issue.
            pl.when(
                pl.col("prior_ms_adj_factor").is_null() | (pl.col("prior_ms_adj_factor") == 0.0)
            )
            .then(None)
            .otherwise((pl.col("adj_factor") / pl.col("prior_ms_adj_factor")) - 1.0)
            .alias("ms_adj_factor_change"),
            pl.when(
                pl.col("prior_yf_adj_factor").is_null() | (pl.col("prior_yf_adj_factor") == 0.0)
            )
            .then(None)
            .otherwise((pl.col("yf_adj_factor") / pl.col("prior_yf_adj_factor")) - 1.0)
            .alias("yf_adj_factor_change"),
        )
        .with_columns(
            (pl.col("yf_adj_factor_change") - pl.col("ms_adj_factor_change")).alias(
                "adj_factor_change_diff"
            ),
            # Small total-return differences are treated as no material vendor
            # difference; non-null diff_return is the main review trigger.
            pl.when(pl.col("yf_return").is_null() | pl.col("ms_return").is_null())
            .then(None)
            .when(pl.col("total_return_diff").abs() < schema.TOLERANCE_4)
            .then(None)
            .otherwise(pl.col("total_return_diff"))
            .alias("diff_return"),
        )
        .with_columns(
            # Older Massive marker text is normalized before comparing marker
            # strings so historical naming differences do not create false
            # event-source mismatches.
            (
                pl.col("ms_div_split").str.replace_all("CD", "CA").str.replace_all("SC", "CA")
                != pl.col("yf_div_split")
            ).alias("has_div_split_mismatch")
        )
        .with_columns(
            # Compare adjusted-close-implied event return with explicit event
            # records. A non-null diff means the source's adjusted return does
            # not reconcile cleanly to its own event data.
            pl.when(
                pl.col("ms_return_div_split_implied").is_null()
                | pl.col("ms_return_div_split_actual").is_null()
            )
            .then(None)
            .when(
                (
                    pl.col("ms_return_div_split_implied") - pl.col("ms_return_div_split_actual")
                ).abs()
                < schema.TOLERANCE_6
            )
            .then(None)
            .otherwise(
                pl.col("ms_return_div_split_implied") - pl.col("ms_return_div_split_actual")
            )
            .alias("diff_ms_return_div_split"),
            pl.when(
                pl.col("yf_return_div_split_implied").is_null()
                | pl.col("yf_return_div_split_actual").is_null()
            )
            .then(None)
            .when(
                (
                    pl.col("yf_return_div_split_implied") - pl.col("yf_return_div_split_actual")
                ).abs()
                < schema.TOLERANCE_6
            )
            .then(None)
            .otherwise(
                (pl.col("yf_return_div_split_implied") - pl.col("yf_return_div_split_actual"))
            )
            .alias("diff_yf_return_div_split"),
        )
        .with_columns(
            # These flags separate source-event presence, event-return math
            # mismatches, and adjustment-factor discontinuities so the reason
            # code tree can choose the most specific explanation.
            (pl.col("ms_div_split") != "").alias("has_ms_event"),
            (pl.col("yf_div_split") != "").alias("has_yf_event"),
            pl.col("diff_ms_return_div_split")
            .is_not_null()
            .alias("is_ms_div_split_return_mismatch"),
            pl.col("diff_yf_return_div_split")
            .is_not_null()
            .alias("is_yf_div_split_return_mismatch"),
            (pl.col("adj_factor_change_diff").abs() > schema.ADJ_FACTOR_CHANGE_TOLERANCE).alias(
                "is_adj_factor_mismatch"
            ),
        )
        .with_columns(
            # Same event marker, same raw price return, but different event-return
            # percentages means the vendors are applying the event amount to
            # different historical price/adjustment bases. That is a methodology
            # diagnostic, not a Massive adjustment-chain defect.
            (
                ~pl.col("has_div_split_mismatch")
                & pl.col("has_ms_event")
                & pl.col("has_yf_event")
                & pl.col("diff_return").is_not_null()
                & (pl.col("ms_return_div_split_actual").abs() > schema.TOLERANCE_4)
                & (pl.col("yf_return_div_split_actual").abs() > schema.TOLERANCE_4)
                & (
                    (pl.col("ms_return_div_split_actual") - pl.col("yf_return_div_split_actual"))
                    .abs()
                    > schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("ms_return_price") - pl.col("yf_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_event_return_basis_mismatch"),
        )
        .with_columns(
            # Partial Massive events sit between "missing event" and generic
            # factor-continuity defects. Massive has an event marker on the same
            # date, but yFinance's explicit event return is materially larger and
            # the adjusted-return gap reconciles to that missing event-return
            # piece. This captures cases such as base-plus-variable dividends
            # where Massive records only the base component.
            (
                pl.col("has_div_split_mismatch")
                & pl.col("has_ms_event")
                & pl.col("has_yf_event")
                & pl.col("diff_return").is_not_null()
                & pl.col("ms_return_div_split_actual").is_not_null()
                & pl.col("yf_return_div_split_actual").is_not_null()
                & (
                    pl.col("yf_return_div_split_actual").abs()
                    > pl.col("ms_return_div_split_actual").abs()
                    + schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (
                        (
                            pl.col("yf_return_div_split_actual")
                            - pl.col("ms_return_div_split_actual")
                        )
                        - pl.col("diff_return")
                    ).abs()
                    <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("ms_return_price") - pl.col("yf_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_ms_partial_event"),
        )
        .with_columns(
            # Extra Massive events are the mirror image of partial events. Massive
            # has an event marker on the same date, but its explicit event return
            # is materially larger than yFinance's and the negative return gap
            # reconciles to the excess event-return piece. This covers exact
            # duplicates such as ca:0.65 ca:0.65 versus ca:0.65, as well as extra
            # same-day components that are not supported by the comparison source.
            (
                pl.col("has_div_split_mismatch")
                & pl.col("has_ms_event")
                & pl.col("has_yf_event")
                & pl.col("diff_return").is_not_null()
                & pl.col("ms_return_div_split_actual").is_not_null()
                & pl.col("yf_return_div_split_actual").is_not_null()
                & (
                    pl.col("ms_return_div_split_actual").abs()
                    > pl.col("yf_return_div_split_actual").abs()
                    + schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (
                        (
                            pl.col("ms_return_div_split_actual")
                            - pl.col("yf_return_div_split_actual")
                        )
                        + pl.col("diff_return")
                    ).abs()
                    <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("ms_return_price") - pl.col("yf_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_ms_extra_event"),
        )
        .with_columns(
            # Source price event return captures a gap between raw price returns.
            # Split-like events often appear here because the two sources may
            # carry different unadjusted price scales on the event date.
            pl.when(
                pl.col("ms_return_price").is_null()
                | pl.col("yf_return_price").is_null()
                | ((1.0 + pl.col("ms_return_price")) == 0.0)
            )
            .then(None)
            .otherwise(
                ((1.0 + pl.col("yf_return_price")) / (1.0 + pl.col("ms_return_price"))) - 1.0
            )
            .alias("source_price_event_return"),
        )
        .with_columns(
            (
                (
                    # If the same dividend/split marker appears in the two
                    # sources on adjacent dates, treat it as an event-date
                    # mismatch before treating it as a close reversal.
                    pl.col("has_yf_event")
                    & ~pl.col("has_ms_event")
                    & (pl.col("yf_div_split") != "")
                    & (pl.col("yf_div_split") == pl.col("next_ms_div_split"))
                )
                | (
                    pl.col("has_yf_event")
                    & ~pl.col("has_ms_event")
                    & (pl.col("yf_div_split") != "")
                    & (pl.col("yf_div_split") == pl.col("prior_ms_div_split"))
                )
                | (
                    pl.col("has_ms_event")
                    & ~pl.col("has_yf_event")
                    & (pl.col("ms_div_split") != "")
                    & (pl.col("ms_div_split") == pl.col("next_yf_div_split"))
                )
                | (
                    pl.col("has_ms_event")
                    & ~pl.col("has_yf_event")
                    & (pl.col("ms_div_split") != "")
                    & (pl.col("ms_div_split") == pl.col("prior_yf_div_split"))
                )
            ).alias("is_event_date_mismatch")
        )
        .with_columns(
            # Missing Massive event adjustment is intentionally narrow: yFinance
            # must have an event, Massive must not, yFinance's own event-return
            # math must be internally inconsistent with its adjusted return, and
            # the return difference must reconcile to the event effect.
            (
                pl.col("has_yf_event")
                & ~pl.col("has_ms_event")
                & pl.col("is_yf_div_split_return_mismatch")
                & ~pl.col("is_ms_div_split_return_mismatch")
                & (pl.col("yf_return_div_split_actual").abs() > schema.TOLERANCE_4)
                & (
                    (
                        # Split-like source differences can show up as a gap
                        # between the two unadjusted source price returns.
                        (
                            pl.col("source_price_event_return")
                            - pl.col("yf_return_div_split_actual")
                        ).abs()
                        <= schema.TOLERANCE_4
                    )
                    | (
                        # Cash-dividend differences usually do not create a
                        # source price-return gap. They show up directly in
                        # total adjusted-return difference instead. Use the
                        # explicit event-return value when it reconciles.
                        (pl.col("total_return_diff") - pl.col("yf_return_div_split_actual")).abs()
                        <= schema.TOLERANCE_4
                    )
                    | (
                        # Some vendors apply the cash-dividend adjustment in
                        # the adjusted-close chain with a small difference
                        # from the event-return value calculated from the
                        # explicit dividend marker and prior close. When the
                        # full Massive/yFinance return difference matches
                        # yFinance's implied dividend/split return, treat the
                        # issue as a missing Massive event adjustment rather
                        # than as a yFinance event-return mismatch.
                        (pl.col("total_return_diff") - pl.col("yf_return_div_split_implied")).abs()
                        <= schema.TOLERANCE_4
                    )
                )
            ).alias("is_ms_missing_event_adjustment")
        )
        .with_columns(
            # Close reversals are equal-and-opposite adjacent differences. They
            # usually indicate a close timing/source artifact rather than a
            # persistent corporate-action adjustment problem.
            (
                (pl.col("total_return_diff") * pl.col("next_total_return_diff") < 0.0)
                & (
                    (pl.col("total_return_diff") + pl.col("next_total_return_diff")).abs()
                    <= schema.REVERSAL_TOLERANCE
                )
            ).alias("is_next_close_reversal"),
            (
                (pl.col("total_return_diff") * pl.col("prior_total_return_diff") < 0.0)
                & (
                    (pl.col("total_return_diff") + pl.col("prior_total_return_diff")).abs()
                    <= schema.REVERSAL_TOLERANCE
                )
            ).alias("is_prior_close_reversal"),
        )
        .with_columns(
            (pl.col("is_next_close_reversal") | pl.col("is_prior_close_reversal")).alias(
                "is_close_reversal"
            ),
        )
    )

    df_lf = audit_classification.add_analysis_reason_code(df_lf)

    df_lf = audit_classification.add_analysis_labels(df_lf, include_real_world_reason_codes=False)

    df_lf = audit_classification.add_massive_fix_guidance(
        df_lf,
        pl.col("analysis_reason_code").is_in(
            [
                "MS_MISSING_EVENT",
                "MS_EVENT_DATE_MISMATCH",
                "MS_ADJ_FACTOR_CONTINUITY",
                "MS_DIV_SPLIT_RETURN_MISMATCH",
                "MS_RETURN_METHOD_UNRESOLVED",
                "HIGH_SCORE_ANOMALY",
            ]
        ),
    )

    # Add placeholder real-world-event columns before review columns are
    # calculated so downstream expressions can safely reference them.
    df_lf = cast(pl.LazyFrame, real_world_events.add_placeholder_columns(df_lf))  # type: ignore

    df_lf = audit_classification.add_review_columns(df_lf)

    df_lf = df_lf.select(
        [
            "ticker",
            "date",
            pl.col("close").alias("ms_close"),
            "yf_close",
            pl.col("adj_factor").alias("ms_adj_factor"),
            "yf_adj_factor",
            pl.col("adj_close").alias("ms_adj_close"),
            "yf_adj_close",
            # Dividends and splits
            "ms_div_split",
            "yf_div_split",
            "has_div_split_mismatch",
            # Returns due to price change
            "ms_return_price",
            "yf_return_price",
            # Massive returns due to dividends and splits
            "ms_return_div_split_implied",
            "ms_return_div_split_actual",
            "diff_ms_return_div_split",
            # yFinance returns due to dividends and splits
            "yf_return_div_split_implied",
            "yf_return_div_split_actual",
            "diff_yf_return_div_split",
            # Total returns
            "ms_return",
            "yf_return",
            "diff_return",
            "needs_review",
            "review_priority",
            "total_return_diff",
            "prior_total_return_diff",
            "next_total_return_diff",
            # Heuristic anomaly score
            "heuristic_anomaly_score",
            # "diff_score",
            "abs_return",
            "prior_return",
            "next_return",
            "raw_close_ratio",
            "rolling_median_return",
            "rolling_mad_return",
            "robust_z",
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
            # Adjustment-factor diagnostics
            "prior_ms_adj_factor",
            "prior_yf_adj_factor",
            "ms_adj_factor_change",
            "yf_adj_factor_change",
            "adj_factor_change_diff",
            # Event-neighbor diagnostics
            "prior_ms_div_split",
            "next_ms_div_split",
            "prior_yf_div_split",
            "next_yf_div_split",
            # Supporting deterministic flags and values
            "has_ms_event",
            "has_yf_event",
            "is_ms_div_split_return_mismatch",
            "is_yf_div_split_return_mismatch",
            "is_adj_factor_mismatch",
            "is_event_return_basis_mismatch",
            "is_ms_partial_event",
            "is_ms_extra_event",
            "source_price_event_return",
            "is_event_date_mismatch",
            "is_ms_missing_event_adjustment",
            "is_next_close_reversal",
            "is_prior_close_reversal",
            "is_close_reversal",
        ]
    )

    return df_lf
