"""Build the detailed return-audit Polars pipeline."""

# Standard library imports.
from typing import NamedTuple, cast

# Third-party imports.
import polars as pl

# Project imports.
import audit_classification
import audit_schema as schema
import data_source
import real_world_events
import returns_builders


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
    """Return the one-day return impact represented by a dividend/split factor.

    Dividend/split factors are multiplicative, so the return contribution is
    factor - 1.0. For example, a 2-for-1 split factor of 2.0 has a +100%
    event-return impact; a $1 dividend on a $100 prior close has an explicit
    factor of 1.01 and therefore a +1% event-return impact.

    Args:
        column_name:
            Name of the factor column.

    Returns:
        Expression for the factor's return impact.
    """
    return pl.col(column_name) - 1.0


def _event_match_tolerance_expr(event_impact_expr: pl.Expr) -> pl.Expr:
    """Return tolerance for matching a return gap to an event impact.

    Dividend/event impacts can differ slightly across source conventions and
    prior-close denominators. Use the same absolute-plus-relative tolerance
    family as real-world event reconciliation when deciding whether an event
    explains the signed return gap.

    Args:
        event_impact_expr:
            Expression containing the signed or unsigned event return impact.

    Returns:
        Expression containing the larger of the absolute and relative match
        tolerances.
    """
    return pl.max_horizontal(
        pl.lit(schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE),
        event_impact_expr.abs() * schema.REAL_WORLD_EVENT_REL_RETURN_TOLERANCE,
    )


def _factor_diff_expr(
    implied_factor_column: str,
    explicit_factor_column: str,
) -> pl.Expr:
    """Return a material implied-minus-explicit factor difference expression.

    Implied factors come from adjusted/raw return behavior; explicit factors
    come from event records. A non-null result means the source's adjusted-close
    chain does not reconcile to its own dividend/split records under the common
    factor convention. Tiny differences are suppressed so rounding noise does
    not masquerade as a corporate-action issue.

    Args:
        implied_factor_column:
            Column containing the factor implied by adjusted/raw return behavior.

        explicit_factor_column:
            Column containing the factor calculated from event records.

    Returns:
        Expression containing the factor difference, or null when the difference
        is missing or immaterial.
    """
    factor_diff: pl.Expr = pl.col(implied_factor_column) - pl.col(explicit_factor_column)

    return (
        pl.when(pl.col(implied_factor_column).is_null() | pl.col(explicit_factor_column).is_null())
        .then(None)
        .when(factor_diff.abs() < schema.TOLERANCE_6)
        .then(None)
        .otherwise(factor_diff)
    )


def _material_factor_mismatch_expr(
    diff_factor_column: str,
    div_split_column: str,
) -> pl.Expr:
    """Return whether a factor diff is large enough to drive classification.

    Cash-only dividend rows naturally produce tiny differences because the
    explicit cash convention is ``1 + cash / prior_close`` while the
    backward-adjusted close chain implies ``prior_close / (prior_close - cash)``.
    Keep the raw diff visible, but do not let expected convention noise become a
    factor-mismatch reason code.

    Args:
        diff_factor_column:
            Column containing the already-computed factor difference.

        div_split_column:
            Column containing compact dividend/split marker text.

    Returns:
        Boolean expression indicating whether the factor difference is material
        enough to drive classification.
    """
    event_text: pl.Expr = pl.col(div_split_column).fill_null("")
    has_split: pl.Expr = event_text.str.contains("sp:", literal=True)
    has_cash: pl.Expr = (
        event_text.str.contains("ca:", literal=True)
        | event_text.str.contains("cd:", literal=True)
        | event_text.str.contains("sc:", literal=True)
    )
    is_cash_only: pl.Expr = has_cash & ~has_split

    return pl.col(diff_factor_column).is_not_null() & (
        ~is_cash_only
        | (pl.col(diff_factor_column).abs() > schema.CASH_FACTOR_CONVENTION_TOLERANCE)
    )


def _factor_change_expr(current_factor_column: str, prior_factor_column: str) -> pl.Expr:
    """Return current/prior factor change while protecting null and zero priors.

    This measures continuity in an adjusted-close basis rather than investment
    return. A clean corporate-action chain should move in explainable ways around
    known events; a data-source-only basis jump is evidence for an adjustment-factor
    continuity diagnostic.

    Args:
        current_factor_column:
            Current-row adjustment factor column.

        prior_factor_column:
            Prior-row adjustment factor column.

    Returns:
        Expression containing the factor change, or null when the prior factor
        is missing or zero.
    """
    return (
        pl.when(pl.col(prior_factor_column).is_null() | (pl.col(prior_factor_column) == 0.0))
        .then(None)
        .otherwise((pl.col(current_factor_column) / pl.col(prior_factor_column)) - 1.0)
    )


def _source_price_event_return_expr() -> pl.Expr:
    """Return source price event return from source2 raw return over source1 raw return.

    This isolates differences in the data sources' unadjusted price scales. Split-like
    discrepancies can appear as raw price-return gaps even before adjusted-return
    fields are considered. For cash dividends, the raw price-return gap is often
    near zero and the effect appears in total adjusted-return difference instead.
    """
    return (
        pl.when(
            pl.col("source1_return_price").is_null()
            | pl.col("source2_return_price").is_null()
            | ((1.0 + pl.col("source1_return_price")) == 0.0)
        )
        .then(None)
        .otherwise(
            ((1.0 + pl.col("source2_return_price")) / (1.0 + pl.col("source1_return_price")))
            - 1.0
        )
    )


def _close_reversal_expr(neighbor_total_return_diff_column: str) -> pl.Expr:
    """Return whether total-return differences reverse against an adjacent row.

    Equal-and-opposite data source differences on adjacent trading days usually point
    to a close timing/source artifact. Example: source1 is 50 bp higher than
    source2 on Tuesday and 50 bp lower on Wednesday; the pair nets out, so the
    row is less likely to be a persistent adjustment-chain defect.

    Args:
        neighbor_total_return_diff_column:
            Column containing the prior or next row's total return difference.

    Returns:
        Boolean expression indicating whether the adjacent row reverses the
        current return difference within tolerance.
    """
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
    source2_lookup_lf: pl.LazyFrame
    source1_explicit_factor_lf: pl.LazyFrame
    source2_explicit_factor_lf: pl.LazyFrame
    source1_div_split_lf: pl.LazyFrame
    source2_div_split_lf: pl.LazyFrame


def _build_return_source_frames(
    source1_data_source: data_source.DataSourceDataset,
    source2_data_source: data_source.DataSourceDataset,
) -> _ReturnSourceFrames:
    """Build normalized source frames used by the return-audit reconciliation.

    The builders deliberately keep raw prices, reconstructed adjusted returns,
    explicit event factors, and compact event-marker text separate until this
    module joins them. Keeping those ingredients separate makes later diagnostics
    clear about what evidence they are using: source records, adjusted-close
    behavior, raw price behavior, or marker timing.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

        source2_data_source:
            Loaded normalized comparison data source.

    Returns:
        Intermediate LazyFrames used to assemble the return-audit pipeline.
    """
    source2_lookup_lf: pl.LazyFrame = returns_builders.build_source2_lookup_lf(
        source2_data_source
    )
    close_lf: pl.LazyFrame = returns_builders.build_source1_close_lf(source1_data_source)

    close_with_prior_lf: pl.LazyFrame = close_lf.with_columns(
        pl.col("close").shift(1).over("ticker").alias("prior_close")
    )

    source2_close_with_prior_lf: pl.LazyFrame = (
        returns_builders.build_source2_close_with_prior_lf(
            source2_lookup_lf,
        )
    )

    cumulative_factors_lf: pl.LazyFrame = returns_builders.build_cumulative_factors_lf(
        source1_data_source,
        close_lf,
        close_with_prior_lf,
    )

    return _ReturnSourceFrames(
        adjusted_lf=returns_builders.build_source1_adjusted_returns_lf(
            close_lf,
            cumulative_factors_lf,
        ),
        source2_lookup_lf=source2_lookup_lf,
        source1_explicit_factor_lf=returns_builders.build_source1_explicit_factor_lf(
            source1_data_source,
            close_with_prior_lf,
        ),
        source2_explicit_factor_lf=returns_builders.build_source2_explicit_factor_lf(
            source2_data_source,
            source2_close_with_prior_lf,
        ),
        source1_div_split_lf=returns_builders.build_source1_div_split_lf(source1_data_source),
        source2_div_split_lf=returns_builders.build_source2_div_split_lf(
            source2_data_source
        ),
    )


def _add_pre_research_classification_columns(df_lf: pl.LazyFrame) -> pl.LazyFrame:
    """Add deterministic classification, guidance, placeholders, and review columns.

    This is the pre-research view of the audit. It must be conservative because
    it has not yet seen external evidence; generic event-source disagreements
    remain review items, while only mechanically isolated source1-side patterns
    become pre-research fix candidates.

    Args:
        df_lf:
            Detailed return-audit LazyFrame before final classification columns.

    Returns:
        LazyFrame with deterministic reason, guidance, placeholder research,
        and review columns.
    """
    df_lf = audit_classification.add_analysis_reason_code(df_lf)

    df_lf = audit_classification.add_analysis_labels(df_lf, include_real_world_reason_codes=False)

    df_lf = audit_classification.add_source1_fix_guidance(
        df_lf,
        pl.col("analysis_reason_code").is_in(
            schema.reason_codes_in_group("source1_fix_pre_research")
        ),
    )

    # Add placeholder real-world-event columns before review columns are
    # calculated so downstream expressions can safely reference them.
    df_lf = cast(pl.LazyFrame, real_world_events.add_placeholder_columns(df_lf))  # type: ignore

    return audit_classification.add_review_columns(df_lf)


def _select_return_audit_columns(df_lf: pl.LazyFrame) -> pl.LazyFrame:
    """Apply stable public aliases and select the detailed return-audit schema.

    Internal builder names such as ``close`` and ``adj_factor`` are source1-side
    values. The aliases make that source ownership explicit before the frame
    leaves the pipeline and becomes a CSV/report contract.

    Args:
        df_lf:
            Detailed return-audit LazyFrame with internal builder columns.

    Returns:
        LazyFrame selected and ordered according to the public return-audit
        schema.
    """
    return df_lf.with_columns(
        pl.col("close").alias("source1_close"),
        pl.col("adj_factor").alias("source1_adj_factor"),
        pl.col("adj_close").alias("source1_adj_close"),
    ).select(
        schema.RETURN_AUDIT_ALL_COLUMNS,
    )


def build_returns_audit_lf(
    source1_data_source: data_source.DataSourceDataset,
    source2_data_source: data_source.DataSourceDataset,
) -> pl.LazyFrame:
    """Build the detailed lazy return-audit frame.

    Args:
        source1_data_source:
            Loaded normalized source1 data source.

        source2_data_source:
            Loaded normalized comparison data source.

    Returns:
        LazyFrame with raw return diagnostics, source comparisons, event
        comparisons, and deterministic analysis fields.
    """
    # Build each source's return and event components separately first. The
    # pipeline later joins them by ticker/date so every diagnostic can compare
    # source1 and source2 using the same row-level vocabulary.
    source_frames: _ReturnSourceFrames = _build_return_source_frames(
        source1_data_source,
        source2_data_source,
    )

    # Event marker strings are informational but important for classification:
    # they identify which source explicitly reported a dividend/split event on
    # the trading date.
    adjusted_lf: pl.LazyFrame = source_frames.adjusted_lf.join(
        source_frames.source1_div_split_lf,
        on=["ticker", "date"],
        how="left",
    ).with_columns(pl.col("source1_div_split").fill_null(""))

    adjusted_lf = adjusted_lf.join(
        source_frames.source2_div_split_lf,
        on=["ticker", "date"],
        how="left",
    ).with_columns(pl.col("source2_div_split").fill_null(""))

    df_lf: pl.LazyFrame = (
        adjusted_lf.select(
            [
                "ticker",
                "date",
                "adj_factor",
                "close",
                "adj_close",
                "source1_return",
                "source1_return_price",
                "source1_div_split_factor_implied",
                "heuristic_anomaly_score",
                "source1_div_split",
                "source2_div_split",
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
            source_frames.source2_lookup_lf,
            on=["ticker", "date"],
            how="left",
        )
        .join(
            source_frames.source1_explicit_factor_lf,
            on=["ticker", "date"],
            how="left",
        )
        .join(
            source_frames.source2_explicit_factor_lf,
            on=["ticker", "date"],
            how="left",
        )
        .with_columns(
            # Missing explicit event rows mean the source reported no dividend/split
            # marker for that ticker/date. Treat that as neutral factor 1.0 so the
            # later reconciliation tests can distinguish "no event" from null math.
            pl.col("source1_div_split_factor_explicit").fill_null(1.0),
            pl.col("source2_div_split_factor_explicit").fill_null(1.0),
        )
        .with_columns(
            # source2 does not publish an adjustment factor directly here, so
            # infer it from adjusted close divided by raw close.
            pl.when(pl.col("source2_close").is_null() | (pl.col("source2_close") == 0.0))
            .then(None)
            .otherwise(pl.col("source2_adj_close") / pl.col("source2_close"))
            .alias("source2_adj_factor")
        )
        # Sign convention: diff_return uses source1 minus source2.
        # Positive means source1 return is higher; negative means source1 return
        # is lower.
        .with_columns(
            (pl.col("source1_return") - pl.col("source2_return")).alias("total_return_diff")
        )
        .sort(["ticker", "date"])
        .with_columns(
            pl.col("total_return_diff").shift(1).over("ticker").alias("prior_total_return_diff"),
            pl.col("total_return_diff").shift(-1).over("ticker").alias("next_total_return_diff"),
            pl.col("adj_factor").shift(1).over("ticker").alias("prior_source1_adj_factor"),
            pl.col("source2_adj_factor").shift(1).over("ticker").alias("prior_source2_adj_factor"),
            pl.col("source1_div_split").shift(1).over("ticker").alias("prior_source1_div_split"),
            pl.col("source1_div_split").shift(-1).over("ticker").alias("next_source1_div_split"),
            pl.col("source2_div_split").shift(1).over("ticker").alias("prior_source2_div_split"),
            pl.col("source2_div_split").shift(-1).over("ticker").alias("next_source2_div_split"),
        )
        .with_columns(
            # Adjustment-factor changes describe how each source's adjusted-close
            # basis moves from yesterday to today. A genuine corporate action should
            # usually appear in both event records or be explainable by a known
            # denominator difference; an unexplained data-source-only factor move is a
            # continuity warning.
            _factor_change_expr("adj_factor", "prior_source1_adj_factor").alias(
                "source1_adj_factor_change"
            ),
            _factor_change_expr("source2_adj_factor", "prior_source2_adj_factor").alias(
                "source2_adj_factor_change"
            ),
        )
        .with_columns(
            (pl.col("source2_adj_factor_change") - pl.col("source1_adj_factor_change")).alias(
                "adj_factor_change_diff"
            ),
            # Small total-return differences are treated as no material data source
            # difference; non-null diff_return is the main review trigger.
            pl.when(pl.col("source2_return").is_null() | pl.col("source1_return").is_null())
            .then(None)
            .when(pl.col("total_return_diff").abs() < schema.TOLERANCE_4)
            .then(None)
            .otherwise(pl.col("total_return_diff"))
            .alias("diff_return"),
        )
        .with_columns(
            # Preserve source marker text in output, but normalize equivalent cash
            # marker prefixes only for this source2. source1 distinguishes
            # regular cash dividends (cd) from special cash dividends (sc), while
            # source2 exposes generic cash-action markers (ca).
            (
                _normalized_event_marker_expr("source1_div_split")
                != _normalized_event_marker_expr("source2_div_split")
            ).alias("has_div_split_mismatch")
        )
        .with_columns(
            # Compare adjusted-close-implied dividend/split factor with explicit
            # source-event factor. A non-null diff means the source's adjusted
            # return does not reconcile cleanly to its own event data under the
            # same factor convention.
            _factor_diff_expr(
                "source1_div_split_factor_implied",
                "source1_div_split_factor_explicit",
            ).alias("diff_source1_div_split_factor"),
            _factor_diff_expr(
                "source2_div_split_factor_implied",
                "source2_div_split_factor_explicit",
            ).alias("diff_source2_div_split_factor"),
        )
        .with_columns(
            # These flags separate source-event presence, factor math
            # mismatches, and adjustment-factor discontinuities so the reason
            # code tree can choose the most specific explanation.
            (pl.col("source1_div_split") != "").alias("has_source1_event"),
            (pl.col("source2_div_split") != "").alias("has_source2_event"),
            _material_factor_mismatch_expr(
                "diff_source1_div_split_factor",
                "source1_div_split",
            ).alias("is_source1_div_split_factor_mismatch"),
            _material_factor_mismatch_expr(
                "diff_source2_div_split_factor",
                "source2_div_split",
            ).alias("is_source2_div_split_factor_mismatch"),
            (pl.col("adj_factor_change_diff").abs() > schema.ADJ_FACTOR_CHANGE_TOLERANCE).alias(
                "is_adj_factor_mismatch"
            ),
        )
        .with_columns(
            # Same event marker, same raw price return, but different event-impact
            # percentages means the data sources are dividing the event amount by
            # different prior-close denominators. That is a methodology diagnostic,
            # not a source1 adjustment-chain defect.
            (
                ~pl.col("has_div_split_mismatch")
                & pl.col("has_source1_event")
                & pl.col("has_source2_event")
                & pl.col("diff_return").is_not_null()
                & (
                    _factor_impact_expr("source1_div_split_factor_explicit").abs()
                    > schema.TOLERANCE_4
                )
                & (
                    _factor_impact_expr("source2_div_split_factor_explicit").abs()
                    > schema.TOLERANCE_4
                )
                & (
                    (
                        pl.col("source1_div_split_factor_explicit")
                        - pl.col("source2_div_split_factor_explicit")
                    ).abs()
                    > schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("source1_return_price") - pl.col("source2_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_event_denominator_mismatch"),
        )
        .with_columns(
            # Partial source1 events sit between "missing event" and generic
            # factor-continuity defects. source1 has an event marker on the same
            # date, but source2's explicit event impact is materially larger and
            # the adjusted-return gap reconciles to that missing event-impact
            # piece. This captures cases such as base-plus-variable dividends
            # where source1 records only the base component. The sign check uses
            # diff_return = source1 - source2, so a missing positive source1 event
            # should make source1's return lower by the missing event amount.
            (
                pl.col("has_div_split_mismatch")
                & pl.col("has_source1_event")
                & pl.col("has_source2_event")
                & pl.col("diff_return").is_not_null()
                & pl.col("source1_div_split_factor_explicit").is_not_null()
                & pl.col("source2_div_split_factor_explicit").is_not_null()
                & (
                    _factor_impact_expr("source2_div_split_factor_explicit").abs()
                    > _factor_impact_expr("source1_div_split_factor_explicit").abs()
                    + schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (
                        (
                            _factor_impact_expr("source2_div_split_factor_explicit")
                            - _factor_impact_expr("source1_div_split_factor_explicit")
                        )
                        + pl.col("diff_return")
                    ).abs()
                    <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("source1_return_price") - pl.col("source2_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_source1_partial_event"),
        )
        .with_columns(
            # Extra source1 events are the mirror image of partial events. source1
            # has an event marker on the same date, but its explicit event impact
            # is materially larger than source2's and the negative return gap
            # reconciles to the excess event-impact piece. This covers exact
            # duplicates such as ca:0.65 ca:0.65 versus ca:0.65, as well as extra
            # same-day components that are not supported by the source2.
            # With diff_return = source1 - source2, an extra positive source1
            # event should push diff_return positive by the excess amount.
            (
                pl.col("has_div_split_mismatch")
                & pl.col("has_source1_event")
                & pl.col("has_source2_event")
                & pl.col("diff_return").is_not_null()
                & pl.col("source1_div_split_factor_explicit").is_not_null()
                & pl.col("source2_div_split_factor_explicit").is_not_null()
                & (
                    _factor_impact_expr("source1_div_split_factor_explicit").abs()
                    > _factor_impact_expr("source2_div_split_factor_explicit").abs()
                    + schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (
                        (
                            _factor_impact_expr("source1_div_split_factor_explicit")
                            - _factor_impact_expr("source2_div_split_factor_explicit")
                        )
                        - pl.col("diff_return")
                    ).abs()
                    <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
                & (
                    (pl.col("source1_return_price") - pl.col("source2_return_price")).abs()
                    <= schema.TOLERANCE_4
                )
            ).alias("is_source1_extra_event"),
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
                    pl.col("has_source2_event")
                    & ~pl.col("has_source1_event")
                    & (pl.col("source2_div_split") != "")
                    & (
                        _normalized_event_marker_expr("source2_div_split")
                        == _normalized_event_marker_expr("next_source1_div_split")
                    )
                )
                | (
                    pl.col("has_source2_event")
                    & ~pl.col("has_source1_event")
                    & (pl.col("source2_div_split") != "")
                    & (
                        _normalized_event_marker_expr("source2_div_split")
                        == _normalized_event_marker_expr("prior_source1_div_split")
                    )
                )
                | (
                    pl.col("has_source1_event")
                    & ~pl.col("has_source2_event")
                    & (pl.col("source1_div_split") != "")
                    & (
                        _normalized_event_marker_expr("source1_div_split")
                        == _normalized_event_marker_expr("next_source2_div_split")
                    )
                )
                | (
                    pl.col("has_source1_event")
                    & ~pl.col("has_source2_event")
                    & (pl.col("source1_div_split") != "")
                    & (
                        _normalized_event_marker_expr("source1_div_split")
                        == _normalized_event_marker_expr("prior_source2_div_split")
                    )
                )
            ).alias("is_event_date_mismatch")
        )
        .with_columns(
            # Missing source1 event adjustment is intentionally narrow: source2
            # must have an event, source1 must not, and the return difference must
            # reconcile to the source2 event effect. source2 does not need to
            # have an internal event-return mismatch; the cleanest missing-source1
            # cases usually have source2's adjusted return reconciling to its own
            # event records.
            (
                pl.col("has_source2_event")
                & ~pl.col("has_source1_event")
                & ~pl.col("is_source1_div_split_factor_mismatch")
                & (
                    _factor_impact_expr("source2_div_split_factor_explicit").abs()
                    > schema.TOLERANCE_4
                )
                & (
                    (
                        # Split-like source differences can show up as a gap
                        # between the two unadjusted source price returns.
                        (
                            pl.col("source_price_event_return")
                            - _factor_impact_expr("source2_div_split_factor_explicit")
                        ).abs()
                        <= _event_match_tolerance_expr(
                            _factor_impact_expr("source2_div_split_factor_explicit")
                        )
                    )
                    | (
                        # Cash-dividend differences usually do not create a
                        # source price-return gap. They show up directly in
                        # total adjusted-return difference instead. Use the
                        # explicit factor impact when it reconciles.
                        (
                            pl.col("total_return_diff")
                            + _factor_impact_expr("source2_div_split_factor_explicit")
                        ).abs()
                        <= _event_match_tolerance_expr(
                            _factor_impact_expr("source2_div_split_factor_explicit")
                        )
                    )
                    | (
                        # As a final fallback, use source2's adjusted-close
                        # chain to estimate the event effect directly. This
                        # catches cases where explicit cash/prior-close event
                        # math differs slightly from the event impact implied
                        # by source2's adjusted/raw return relationship.
                        (
                            pl.col("total_return_diff")
                            + _factor_impact_expr("source2_div_split_factor_implied")
                        ).abs()
                        <= _event_match_tolerance_expr(
                            _factor_impact_expr("source2_div_split_factor_implied")
                        )
                    )
                )
            ).alias("is_source1_missing_event_adjustment")
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
