"""Build the detailed return-audit Polars pipeline."""

# Standard library imports.
from typing import NamedTuple, cast

# Third-party imports.
import polars as pl

# Project imports.
import audit_classification
import audit_schema as schema
import real_world_events
import returns_builders
from massive_data import MassiveData
from yfinance_data import YFinanceData


def _normalized_event_marker_expr(column_name: str) -> pl.Expr:
    """Return event marker text normalized only for equality comparisons.

    Args:
        column_name:
            Name of the event-marker column to normalize.

    Returns:
        Polars expression with equivalent cash-action marker prefixes normalized.
    """
    return (
        pl.col(column_name)
        .str.replace_all("cd:", "ca:")
        .str.replace_all("sc:", "ca:")
        .str.replace_all("CD:", "ca:")
        .str.replace_all("SC:", "ca:")
    )


def _factor_impact_expr(column_name: str) -> pl.Expr:
    """Return the one-day impact represented by a dividend/split factor."""
    return pl.col(column_name) - 1.0


def _factor_diff_expr(
    implied_factor_column: str,
    explicit_factor_column: str,
) -> pl.Expr:
    """Return a material implied-minus-explicit factor difference expression."""
    factor_diff: pl.Expr = pl.col(implied_factor_column) - pl.col(explicit_factor_column)

    return (
        pl.when(pl.col(implied_factor_column).is_null() | pl.col(explicit_factor_column).is_null())
        .then(None)
        .when(factor_diff.abs() < schema.TOLERANCE_6)
        .then(None)
        .otherwise(factor_diff)
    )


def _factor_change_expr(current_factor_column: str, prior_factor_column: str) -> pl.Expr:
    """Return current/prior factor change while protecting null and zero priors."""
    return (
        pl.when(pl.col(prior_factor_column).is_null() | (pl.col(prior_factor_column) == 0.0))
        .then(None)
        .otherwise((pl.col(current_factor_column) / pl.col(prior_factor_column)) - 1.0)
    )


def _source_price_event_return_expr() -> pl.Expr:
    """Return source price event return from yFinance raw return over Massive raw return."""
    return (
        pl.when(
            pl.col("ms_return_price").is_null()
            | pl.col("yf_return_price").is_null()
            | ((1.0 + pl.col("ms_return_price")) == 0.0)
        )
        .then(None)
        .otherwise(((1.0 + pl.col("yf_return_price")) / (1.0 + pl.col("ms_return_price"))) - 1.0)
    )


def _close_reversal_expr(neighbor_total_return_diff_column: str) -> pl.Expr:
    """Return whether total-return differences reverse against an adjacent row."""
    return (
        (pl.col("total_return_diff") * pl.col(neighbor_total_return_diff_column) < 0.0)
        & (pl.col("total_return_diff").abs() > schema.TOLERANCE_4)
        & (pl.col(neighbor_total_return_diff_column).abs() > schema.TOLERANCE_4)
        & (
            (pl.col("total_return_diff") + pl.col(neighbor_total_return_diff_column)).abs()
            <= schema.REVERSAL_TOLERANCE
        )
    )


class _ReturnSourceFrames(NamedTuple):
    """Intermediate source frames used to assemble the return-audit pipeline."""

    adjusted_lf: pl.LazyFrame
    yfinance_lookup_lf: pl.LazyFrame
    ms_explicit_factor_lf: pl.LazyFrame
    yf_explicit_factor_lf: pl.LazyFrame
    ms_div_split_lf: pl.LazyFrame
    yf_div_split_lf: pl.LazyFrame


def _build_return_source_frames(
    massive_data: MassiveData,
    yfinance_data: YFinanceData,
) -> _ReturnSourceFrames:
    """Build normalized source frames used by the return-audit reconciliation."""
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

    return _ReturnSourceFrames(
        adjusted_lf=returns_builders.build_massive_adjusted_returns_lf(
            close_lf,
            cumulative_factors_lf,
        ),
        yfinance_lookup_lf=yfinance_lookup_lf,
        ms_explicit_factor_lf=returns_builders.build_massive_explicit_factor_lf(
            massive_data,
            close_with_prior_lf,
        ),
        yf_explicit_factor_lf=returns_builders.build_yfinance_explicit_factor_lf(
            yfinance_data,
            yfinance_close_with_prior_lf,
        ),
        ms_div_split_lf=returns_builders.build_massive_div_split_lf(massive_data),
        yf_div_split_lf=returns_builders.build_yfinance_div_split_lf(yfinance_data),
    )


def _add_pre_research_classification_columns(df_lf: pl.LazyFrame) -> pl.LazyFrame:
    """Add deterministic classification, guidance, placeholders, and review columns."""
    df_lf = audit_classification.add_analysis_reason_code(df_lf)

    df_lf = audit_classification.add_analysis_labels(df_lf, include_real_world_reason_codes=False)

    df_lf = audit_classification.add_massive_fix_guidance(
        df_lf,
        pl.col("analysis_reason_code").is_in(
            schema.reason_codes_in_group("massive_fix_pre_research")
        ),
    )

    # Add placeholder real-world-event columns before review columns are
    # calculated so downstream expressions can safely reference them.
    df_lf = cast(pl.LazyFrame, real_world_events.add_placeholder_columns(df_lf))  # type: ignore

    return audit_classification.add_review_columns(df_lf)


def _select_return_audit_columns(df_lf: pl.LazyFrame) -> pl.LazyFrame:
    """Apply stable public aliases and select the detailed return-audit schema."""
    return df_lf.with_columns(
        pl.col("close").alias("ms_close"),
        pl.col("adj_factor").alias("ms_adj_factor"),
        pl.col("adj_close").alias("ms_adj_close"),
    ).select(
        schema.RETURN_AUDIT_ALL_COLUMNS,
    )


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
    source_frames: _ReturnSourceFrames = _build_return_source_frames(
        massive_data,
        yfinance_data,
    )

    # Event marker strings are informational but important for classification:
    # they identify which source explicitly reported a dividend/split event on
    # the trading date.
    adjusted_lf: pl.LazyFrame = source_frames.adjusted_lf.join(
        source_frames.ms_div_split_lf,
        on=["ticker", "date"],
        how="left",
    ).with_columns(pl.col("ms_div_split").fill_null(""))

    adjusted_lf = adjusted_lf.join(
        source_frames.yf_div_split_lf,
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
                "ms_div_split_factor_implied",
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
            source_frames.yfinance_lookup_lf,
            on=["ticker", "date"],
            how="left",
        )
        .join(
            source_frames.ms_explicit_factor_lf,
            on=["ticker", "date"],
            how="left",
        )
        .join(
            source_frames.yf_explicit_factor_lf,
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(
            # Missing explicit event rows mean the source reported no dividend/split
            # marker for that ticker/date. Treat that as neutral factor 1.0 so the
            # later reconciliation tests can distinguish "no event" from null math.
            pl.col("ms_div_split_factor_explicit").fill_null(1.0),
            pl.col("yf_div_split_factor_explicit").fill_null(1.0),
        )
        .with_columns(
            # yFinance does not publish an adjustment factor directly here, so
            # infer it from adjusted close divided by raw close.
            pl.when(pl.col("yf_close").is_null() | (pl.col("yf_close") == 0.0))
            .then(None)
            .otherwise(pl.col("yf_adj_close") / pl.col("yf_close"))
            .alias("yf_adj_factor")
        )
        # Sign convention: diff_return uses Massive minus yFinance.
        # Positive means Massive return is higher; negative means Massive return
        # is lower.
        .with_columns((pl.col("ms_return") - pl.col("yf_return")).alias("total_return_diff"))
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
            # Adjustment-factor changes describe how each source's adjusted-close
            # basis moves from yesterday to today. A genuine corporate action should
            # usually appear in both event records or be explainable by a known
            # denominator difference; an unexplained vendor-only factor move is a
            # continuity warning.
            _factor_change_expr("adj_factor", "prior_ms_adj_factor").alias(
                "ms_adj_factor_change"
            ),
            _factor_change_expr("yf_adj_factor", "prior_yf_adj_factor").alias(
                "yf_adj_factor_change"
            ),
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
            # Preserve source marker text in output, but normalize equivalent cash
            # marker prefixes only for this comparison. Massive distinguishes
            # regular cash dividends (cd) from special cash dividends (sc), while
            # yFinance exposes generic cash-action markers (ca).
            (
                _normalized_event_marker_expr("ms_div_split")
                != _normalized_event_marker_expr("yf_div_split")
            ).alias("has_div_split_mismatch")
        )
        .with_columns(
            # Compare adjusted-close-implied dividend/split factor with explicit
            # source-event factor. A non-null diff means the source's adjusted
            # return does not reconcile cleanly to its own event data under the
            # same factor convention.
            _factor_diff_expr(
                "ms_div_split_factor_implied",
                "ms_div_split_factor_explicit",
            ).alias("diff_ms_div_split_factor"),
            _factor_diff_expr(
                "yf_div_split_factor_implied",
                "yf_div_split_factor_explicit",
            ).alias("diff_yf_div_split_factor"),
        )
        .with_columns(
            # These flags separate source-event presence, factor math
            # mismatches, and adjustment-factor discontinuities so the reason
            # code tree can choose the most specific explanation.
            (pl.col("ms_div_split") != "").alias("has_ms_event"),
            (pl.col("yf_div_split") != "").alias("has_yf_event"),
            pl.col("diff_ms_div_split_factor")
            .is_not_null()
            .alias("is_ms_div_split_factor_mismatch"),
            pl.col("diff_yf_div_split_factor")
            .is_not_null()
            .alias("is_yf_div_split_factor_mismatch"),
            (pl.col("adj_factor_change_diff").abs() > schema.ADJ_FACTOR_CHANGE_TOLERANCE).alias(
                "is_adj_factor_mismatch"
            ),
        )
        .with_columns(
            # Same event marker, same raw price return, but different event-impact
            # percentages means the vendors are dividing the event amount by
            # different prior-close denominators. That is a methodology diagnostic,
            # not a Massive adjustment-chain defect.
            (
                ~pl.col("has_div_split_mismatch")
                & pl.col("has_ms_event")
                & pl.col("has_yf_event")
                & pl.col("diff_return").is_not_null()
                & (_factor_impact_expr("ms_div_split_factor_explicit").abs() > schema.TOLERANCE_4)
                & (_factor_impact_expr("yf_div_split_factor_explicit").abs() > schema.TOLERANCE_4)
                & (
                    (
                        pl.col("ms_div_split_factor_explicit")
                        - pl.col("yf_div_split_factor_explicit")
                    ).abs()
                    > schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("ms_return_price") - pl.col("yf_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_event_denominator_mismatch"),
        )
        .with_columns(
            # Partial Massive events sit between "missing event" and generic
            # factor-continuity defects. Massive has an event marker on the same
            # date, but yFinance's explicit event impact is materially larger and
            # the adjusted-return gap reconciles to that missing event-impact
            # piece. This captures cases such as base-plus-variable dividends
            # where Massive records only the base component. The sign check uses
            # diff_return = Massive - yFinance, so a missing positive Massive event
            # should make Massive's return lower by the missing event amount.
            (
                pl.col("has_div_split_mismatch")
                & pl.col("has_ms_event")
                & pl.col("has_yf_event")
                & pl.col("diff_return").is_not_null()
                & pl.col("ms_div_split_factor_explicit").is_not_null()
                & pl.col("yf_div_split_factor_explicit").is_not_null()
                & (
                    _factor_impact_expr("yf_div_split_factor_explicit").abs()
                    > _factor_impact_expr("ms_div_split_factor_explicit").abs()
                    + schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (
                        (
                            _factor_impact_expr("yf_div_split_factor_explicit")
                            - _factor_impact_expr("ms_div_split_factor_explicit")
                        )
                        + pl.col("diff_return")
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
            # has an event marker on the same date, but its explicit event impact
            # is materially larger than yFinance's and the negative return gap
            # reconciles to the excess event-impact piece. This covers exact
            # duplicates such as ca:0.65 ca:0.65 versus ca:0.65, as well as extra
            # same-day components that are not supported by the comparison source.
            # With diff_return = Massive - yFinance, an extra positive Massive
            # event should push diff_return positive by the excess amount.
            (
                pl.col("has_div_split_mismatch")
                & pl.col("has_ms_event")
                & pl.col("has_yf_event")
                & pl.col("diff_return").is_not_null()
                & pl.col("ms_div_split_factor_explicit").is_not_null()
                & pl.col("yf_div_split_factor_explicit").is_not_null()
                & (
                    _factor_impact_expr("ms_div_split_factor_explicit").abs()
                    > _factor_impact_expr("yf_div_split_factor_explicit").abs()
                    + schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (
                        (
                            _factor_impact_expr("ms_div_split_factor_explicit")
                            - _factor_impact_expr("yf_div_split_factor_explicit")
                        )
                        - pl.col("diff_return")
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
            _source_price_event_return_expr().alias("source_price_event_return"),
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
                    & (
                        _normalized_event_marker_expr("yf_div_split")
                        == _normalized_event_marker_expr("next_ms_div_split")
                    )
                )
                | (
                    pl.col("has_yf_event")
                    & ~pl.col("has_ms_event")
                    & (pl.col("yf_div_split") != "")
                    & (
                        _normalized_event_marker_expr("yf_div_split")
                        == _normalized_event_marker_expr("prior_ms_div_split")
                    )
                )
                | (
                    pl.col("has_ms_event")
                    & ~pl.col("has_yf_event")
                    & (pl.col("ms_div_split") != "")
                    & (
                        _normalized_event_marker_expr("ms_div_split")
                        == _normalized_event_marker_expr("next_yf_div_split")
                    )
                )
                | (
                    pl.col("has_ms_event")
                    & ~pl.col("has_yf_event")
                    & (pl.col("ms_div_split") != "")
                    & (
                        _normalized_event_marker_expr("ms_div_split")
                        == _normalized_event_marker_expr("prior_yf_div_split")
                    )
                )
            ).alias("is_event_date_mismatch")
        )
        .with_columns(
            # Missing Massive event adjustment is intentionally narrow: yFinance
            # must have an event, Massive must not, and the return difference must
            # reconcile to the yFinance event effect. yFinance does not need to
            # have an internal event-return mismatch; the cleanest missing-Massive
            # cases usually have yFinance's adjusted return reconciling to its own
            # event records.
            (
                pl.col("has_yf_event")
                & ~pl.col("has_ms_event")
                & ~pl.col("is_ms_div_split_factor_mismatch")
                & (_factor_impact_expr("yf_div_split_factor_explicit").abs() > schema.TOLERANCE_4)
                & (
                    (
                        # Split-like source differences can show up as a gap
                        # between the two unadjusted source price returns.
                        (
                            pl.col("source_price_event_return")
                            - _factor_impact_expr("yf_div_split_factor_explicit")
                        ).abs()
                        <= schema.TOLERANCE_4
                    )
                    | (
                        # Cash-dividend differences usually do not create a
                        # source price-return gap. They show up directly in
                        # total adjusted-return difference instead. Use the
                        # explicit factor impact when it reconciles.
                        (
                            pl.col("total_return_diff")
                            + _factor_impact_expr("yf_div_split_factor_explicit")
                        ).abs()
                        <= schema.TOLERANCE_4
                    )
                    | (
                        # As a final fallback, use yFinance's adjusted-close
                        # chain to estimate the event effect directly. This
                        # catches cases where explicit cash/prior-close event
                        # math differs slightly from the event impact implied
                        # by yFinance's adjusted/raw return relationship.
                        (
                            pl.col("total_return_diff")
                            + _factor_impact_expr("yf_div_split_factor_implied")
                        ).abs()
                        <= schema.TOLERANCE_4
                    )
                )
            ).alias("is_ms_missing_event_adjustment")
        )
        .with_columns(
            # Close reversals are equal-and-opposite adjacent differences. They
            # usually indicate a close timing/source artifact rather than a
            # persistent corporate-action adjustment problem.
            _close_reversal_expr("next_total_return_diff").alias("is_next_close_reversal"),
            _close_reversal_expr("prior_total_return_diff").alias("is_prior_close_reversal"),
        )
        .with_columns(
            (pl.col("is_next_close_reversal") | pl.col("is_prior_close_reversal")).alias(
                "is_close_reversal"
            ),
        )
    )

    df_lf = _add_pre_research_classification_columns(df_lf)

    return _select_return_audit_columns(df_lf)
