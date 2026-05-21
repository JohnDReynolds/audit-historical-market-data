"""Classification, review, and guidance helpers for return-audit output."""

# Standard library imports.
from typing import TypeVar, cast

# Third-party imports.
import polars as pl

# Project imports.
import audit_schema as schema

# Type aliases.
_FrameT = TypeVar("_FrameT", pl.DataFrame, pl.LazyFrame)


def add_analysis_labels(
    frame: _FrameT,
    include_real_world_reason_codes: bool,
) -> _FrameT:
    """Add analysis confidence labels from reason codes.

    Args:
        frame:
            Return-audit frame with ``analysis_reason_code`` assigned.

        include_real_world_reason_codes:
            Whether labels should include reason codes that can only be
            assigned after real-world event research is joined.

    Returns:
        Frame with ``analysis_confidence`` column.
    """
    return cast(
        _FrameT,
        frame.with_columns(
            # Blank reason codes represent rows outside the review surface, so
            # they intentionally carry no deterministic confidence label.
            pl.when(pl.col("analysis_reason_code") == "")
            .then(pl.lit(""))
            # Confidence is metadata about how mechanically isolated the current
            # diagnostic is, not a claim that source1 or source2 is correct.
            # Real-world-only reason codes are included only after research has
            # had a chance to rewrite source ownership.
            .when(
                pl.col("analysis_reason_code").is_in(
                    schema.reason_codes_by_confidence(
                        "HIGH",
                        include_real_world_reason_codes,
                    )
                )
            )
            .then(pl.lit("HIGH"))
            .when(
                pl.col("analysis_reason_code").is_in(
                    schema.reason_codes_by_confidence(
                        "MEDIUM",
                        include_real_world_reason_codes,
                    )
                )
            )
            .then(pl.lit("MEDIUM"))
            .otherwise(pl.lit("LOW"))
            .alias("analysis_confidence"),
        ),
    )


def add_analysis_reason_code(df_lf: pl.LazyFrame) -> pl.LazyFrame:
    """Assign deterministic analysis reason codes.

    Args:
        df_lf:
            Detailed lazy return-audit frame with deterministic diagnostic
            flags already calculated.

    Returns:
        LazyFrame with ``analysis_reason_code`` assigned from the existing
        deterministic decision tree.
    """
    # review_required_expr: pl.Expr = review_required_expr()

    # The order is part of the business logic. More specific, mechanically
    # explainable conditions are assigned before broader fallbacks so the output
    # points reviewers toward the most likely reconciliation path. Event-date
    # mismatches beat close reversals because adjacent event placement can create
    # the same equal-and-opposite return pattern that otherwise looks like a close
    # source issue.
    return df_lf.with_columns(
        pl.when(~review_required_expr())
        .then(pl.lit(""))
        # A high source1-side anomaly with no material data source disagreement is
        # still review-worthy, but it should not be forced into a data-source-difference
        # category that implies source1 and source2 disagree economically.
        .when(
            pl.col("diff_return").is_null()
            & (pl.col("heuristic_anomaly_score") >= schema.MIN_SCORE_TO_REVIEW)
        )
        .then(pl.lit("HIGH_SCORE_ANOMALY"))
        .when(pl.col("is_event_date_mismatch"))
        .then(pl.lit("SOURCE1_EVENT_DATE_MISMATCH"))
        # Event-date mismatches precede close reversals because a dividend or
        # split placed one trading day off can create the same equal-and-opposite
        # pattern that would otherwise look like a close artifact.
        .when(pl.col("is_close_reversal"))
        .then(pl.lit("CLOSE_REVERSAL"))
        .when(pl.col("is_source1_missing_event_adjustment"))
        .then(pl.lit("SOURCE1_MISSING_EVENT"))
        .when(
            # A source2 internal reconciliation break is assigned only after
            # missing-source1-event logic has had a chance to claim rows where
            # source2's event explains the data source return gap.
            pl.col("is_source2_div_split_factor_mismatch") & ~pl.col("is_source1_div_split_factor_mismatch")
        )
        .then(pl.lit("SOURCE2_DIV_SPLIT_RETURN_MISMATCH"))
        .when(
            pl.col("has_div_split_mismatch")
            & pl.col("has_source1_event")
            & pl.col("has_source2_event")
            # If both data sources carry same-day event markers and the return gap is
            # tiny, the best pre-research explanation is usually event
            # representation, grouping, or marker semantics, not a broken
            # adjustment chain.
            & (pl.col("diff_return").abs() <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE)
        )
        .then(pl.lit("EVENT_SOURCE_MISMATCH"))
        .when(pl.col("is_event_denominator_mismatch"))
        .then(pl.lit("EVENT_DENOMINATOR_MISMATCH"))
        # Partial/extra event categories require same-day markers from both
        # data sources and signed return math that reconciles to the missing or excess
        # event component. They are more specific than generic source mismatch.
        .when(pl.col("is_source1_partial_event"))
        .then(pl.lit("SOURCE1_PARTIAL_EVENT"))
        .when(pl.col("is_source1_extra_event"))
        .then(pl.lit("SOURCE1_EXTRA_EVENT"))
        .when(pl.col("is_adj_factor_mismatch"))
        .then(pl.lit("SOURCE1_ADJ_FACTOR_CONTINUITY"))
        .when(pl.col("has_div_split_mismatch"))
        # Remaining event-marker disagreements are real review items, but without
        # more mechanical evidence or external research the pipeline should not
        # infer which data source is economically correct.
        .then(pl.lit("EVENT_SOURCE_MISMATCH"))
        .otherwise(pl.lit("SOURCE1_RETURN_METHOD_UNRESOLVED"))
        .alias("analysis_reason_code")
    )


def add_source1_fix_guidance(
    frame: _FrameT,
    source1_needs_fix_expr: pl.Expr,
) -> _FrameT:
    """Add source1 remediation flags and guidance text.

    Args:
        frame:
            Return-audit frame with ``analysis_reason_code`` assigned.

        source1_needs_fix_expr:
            Expression used to assign ``source1_needs_fix`` for the
            current stage of the audit pipeline.

    Returns:
        Frame with source1 remediation flag, summary, explanation, action,
        and priority columns.
    """
    existing_columns: list[str]

    if isinstance(frame, pl.LazyFrame):
        existing_columns = frame.collect_schema().names()
    else:
        existing_columns = frame.columns

    if "likely_correct_source" not in existing_columns:
        frame = cast(_FrameT, frame.with_columns(pl.lit("").alias("likely_correct_source")))

    # Research can clear pre-research source1 suspicion when it concludes source1
    # is correct or economically equivalent. Conversely, research that names
    # source2 or neither source as correct should keep the row actionable for
    # source1 review even if the pre-research diagnostic was generic.
    research_says_source1_correct: pl.Expr = pl.col("likely_correct_source").is_in(
        ["SOURCE1", "BOTH"]
    )
    research_says_source1_incorrect: pl.Expr = pl.col("likely_correct_source").is_in(
        ["SOURCE2", "NEITHER"]
    )
    close_reversal_supports_source1_fix: pl.Expr = (
        (pl.col("analysis_reason_code") == "CLOSE_REVERSAL") & research_says_source1_incorrect
    )
    # Real-world research has higher authority than deterministic pre-research
    # suspicion. If research says source1 is correct or economically equivalent,
    # clear source1 remediation; if research says source2 or neither source is
    # correct, keep/remap the row as a source1 fix candidate.
    research_aware_source1_needs_fix_expr: pl.Expr = (
        pl.when(research_says_source1_correct)
        .then(pl.lit(False))
        .when(research_says_source1_incorrect)
        .then(pl.lit(True))
        .otherwise(source1_needs_fix_expr)
    )

    return cast(
        _FrameT,
        frame.with_columns(
            research_aware_source1_needs_fix_expr.alias("source1_needs_fix"),
            # Close reversals are not pre-research source1 fixes by default. The
            # special branch below emits guidance only when external research says
            # source1 is the incorrect side of the reversal.
            pl.when(research_says_source1_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_source1_fix)
            .then(
                pl.lit(schema.REASON_CODES["CLOSE_REVERSAL"].source1_problem_summary)
            )
            .otherwise(_reason_code_text_expr("source1_problem_summary"))
            .alias("source1_problem_summary"),
            pl.when(research_says_source1_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_source1_fix)
            .then(
                pl.lit(schema.REASON_CODES["CLOSE_REVERSAL"].source1_why_incorrect)
            )
            .otherwise(_reason_code_text_expr("source1_why_incorrect"))
            .alias("source1_why_incorrect"),
            pl.when(research_says_source1_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_source1_fix)
            .then(
                pl.lit(schema.REASON_CODES["CLOSE_REVERSAL"].source1_fix_action)
            )
            .otherwise(_reason_code_text_expr("source1_fix_action"))
            .alias("source1_fix_action"),
            _source1_fix_priority_expr(research_aware_source1_needs_fix_expr).alias(
                "source1_fix_priority"
            ),
        ),
    )


def _reason_code_text_expr(
    reason_code_field: str,
    skip_reason_codes: frozenset[str] = frozenset({"CLOSE_REVERSAL"}),
) -> pl.Expr:
    """Return a text expression backed by reason-code metadata.

    The registry holds the text once, while Polars still needs an expression
    tree to assign row-specific strings. ``CLOSE_REVERSAL`` is skipped here
    because it has a special research-aware branch in ``add_source1_fix_guidance``.

    Args:
        reason_code_field:
            Name of the ``ReasonCode`` text field to read.

        skip_reason_codes:
            Reason codes whose text should not be emitted by this generic
            expression.

    Returns:
        Expression that maps ``analysis_reason_code`` to the requested text.
    """
    text_expr: pl.Expr = pl.lit("")

    for reason_code in reversed(list(schema.REASON_CODES.values())):
        # Build the expression in reverse so the final tree preserves registry
        # precedence without needing a separate mutable mapping column.
        text: str = str(getattr(reason_code, reason_code_field))
        if reason_code.code in skip_reason_codes or not text:
            continue

        text_expr = (
            pl.when(pl.col("analysis_reason_code") == reason_code.code)
            .then(pl.lit(text))
            .otherwise(text_expr)
        )

    return text_expr


def add_review_columns(frame: _FrameT) -> _FrameT:
    """Add persisted review workflow columns.

    Args:
        frame:
            Return-audit frame with ``diff_return`` and
            ``heuristic_anomaly_score`` columns.

    Returns:
        Frame with ``needs_review`` and ``review_priority`` columns.
    """
    existing_columns: list[str]

    if isinstance(frame, pl.LazyFrame):
        existing_columns = frame.collect_schema().names()
    else:
        existing_columns = frame.columns

    placeholder_exprs: list[pl.Expr] = []

    if "likely_correct_source" not in existing_columns:
        placeholder_exprs.append(pl.lit("").alias("likely_correct_source"))

    if "analysis_reason_code" not in existing_columns:
        placeholder_exprs.append(pl.lit("").alias("analysis_reason_code"))

    # Some callers add review columns before optional research fields exist. Add
    # neutral placeholders so the priority expression can stay research-aware
    # without forcing every upstream frame to materialize those columns first.
    if placeholder_exprs:
        frame = cast(_FrameT, frame.with_columns(*placeholder_exprs))

    return cast(
        _FrameT,
        frame.with_columns(
            review_required_expr().alias("needs_review"),
            _triage_priority_expr().alias("review_priority"),
        ),
    )


def refresh_return_analysis_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Refresh analysis labels, source1 fix guidance, and review columns.

    Args:
        df:
            Return-audit output after deterministic and real-world event
            reason-code classification.

    Returns:
        DataFrame with analysis-sheet, confidence, source1 remediation, and
        review columns synchronized to the final reason code.
    """
    df = add_analysis_labels(
        df,
        include_real_world_reason_codes=True,
    )

    df = add_source1_fix_guidance(
        df,
        # After research, generic EVENT_SOURCE_MISMATCH is not enough by itself
        # to say source1 needs a fix. It must have been converted to a
        # source1-focused reason code or supported by likely_correct_source.
        pl.col("analysis_reason_code").is_in(
            schema.reason_codes_in_group("source1_fix_post_research")
        ),
    )

    df = add_review_columns(df)

    return df.drop(
        [
            "real_world_event_return_match",
            "real_world_event_supports_source1",
            "real_world_event_supports_source2",
        ]
    )


def _source1_fix_priority_expr(source1_needs_fix_expr: pl.Expr) -> pl.Expr:
    """Return the expression that assigns source1 fix priority.

    Args:
        source1_needs_fix_expr:
            Expression used to decide whether source1 fix guidance applies.

    Returns:
        Polars expression that assigns the source1 fix priority bucket.
    """
    return pl.when(source1_needs_fix_expr).then(_triage_priority_expr()).otherwise(pl.lit(""))


def _triage_priority_expr() -> pl.Expr:
    """Return the expression that assigns audit triage priority.

    Returns:
        Polars expression that assigns a HIGH, MEDIUM, LOW, or blank priority.
    """
    # A material source1/source2 return difference is always HIGH. Heuristic
    # anomaly rows are lower priority because they may be real market moves even
    # when both sources agree.
    # A heuristic anomaly score >= 8 is particularly suspicious.
    is_high_score = pl.col("heuristic_anomaly_score") >= 8

    # By definition, HIGH_SCORE_ANOMALY has no diff_return. So if both data sources appear
    # correct, then the anomaly is considered low-actionable and should not receive
    # MEDIUM priority.
    might_be_actionable = ~(
        (pl.col("likely_correct_source") == "BOTH")
        & (pl.col("analysis_reason_code") == "HIGH_SCORE_ANOMALY")
    )

    return (
        pl.when(pl.col("diff_return").is_not_null())
        .then(pl.lit("HIGH"))
        .when(is_high_score & might_be_actionable)
        .then(pl.lit("MEDIUM"))
        .when(pl.col("heuristic_anomaly_score") >= schema.MIN_SCORE_TO_REVIEW)
        .then(pl.lit("LOW"))
        .otherwise(pl.lit(""))
    )


def review_required_expr() -> pl.Expr:
    """Return the expression that identifies rows requiring review.

    Returns:
        Polars expression that is true when a row has a material return
        difference or a high heuristic anomaly score.
    """
    return pl.col("diff_return").is_not_null() | (
        pl.col("heuristic_anomaly_score") >= schema.MIN_SCORE_TO_REVIEW
    )
