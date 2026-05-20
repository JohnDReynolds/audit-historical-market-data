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
            # diagnostic is, not a claim that Massive or yFinance is correct.
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
        # A high Massive-side anomaly with no material vendor disagreement is
        # still review-worthy, but it should not be forced into a vendor-difference
        # category that implies Massive and yFinance disagree economically.
        .when(
            pl.col("diff_return").is_null()
            & (pl.col("heuristic_anomaly_score") >= schema.MIN_SCORE_TO_REVIEW)
        )
        .then(pl.lit("HIGH_SCORE_ANOMALY"))
        .when(pl.col("is_event_date_mismatch"))
        .then(pl.lit("MS_EVENT_DATE_MISMATCH"))
        # Event-date mismatches precede close reversals because a dividend or
        # split placed one trading day off can create the same equal-and-opposite
        # pattern that would otherwise look like a close artifact.
        .when(pl.col("is_close_reversal"))
        .then(pl.lit("CLOSE_REVERSAL"))
        .when(pl.col("is_ms_missing_event_adjustment"))
        .then(pl.lit("MS_MISSING_EVENT"))
        .when(
            # A yFinance internal reconciliation break is assigned only after
            # missing-Massive-event logic has had a chance to claim rows where
            # yFinance's event explains the vendor return gap.
            pl.col("is_yf_div_split_factor_mismatch") & ~pl.col("is_ms_div_split_factor_mismatch")
        )
        .then(pl.lit("YF_DIV_SPLIT_RETURN_MISMATCH"))
        .when(
            pl.col("has_div_split_mismatch")
            & pl.col("has_ms_event")
            & pl.col("has_yf_event")
            # If both vendors carry same-day event markers and the return gap is
            # tiny, the best pre-research explanation is usually event
            # representation, grouping, or marker semantics, not a broken
            # adjustment chain.
            & (pl.col("diff_return").abs() <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE)
        )
        .then(pl.lit("EVENT_SOURCE_MISMATCH"))
        .when(pl.col("is_event_denominator_mismatch"))
        .then(pl.lit("EVENT_DENOMINATOR_MISMATCH"))
        # Partial/extra event categories require same-day markers from both
        # vendors and signed return math that reconciles to the missing or excess
        # event component. They are more specific than generic source mismatch.
        .when(pl.col("is_ms_partial_event"))
        .then(pl.lit("MS_PARTIAL_EVENT"))
        .when(pl.col("is_ms_extra_event"))
        .then(pl.lit("MS_EXTRA_EVENT"))
        .when(pl.col("is_adj_factor_mismatch"))
        .then(pl.lit("MS_ADJ_FACTOR_CONTINUITY"))
        .when(pl.col("has_div_split_mismatch"))
        # Remaining event-marker disagreements are real review items, but without
        # more mechanical evidence or external research the pipeline should not
        # infer which vendor is economically correct.
        .then(pl.lit("EVENT_SOURCE_MISMATCH"))
        .otherwise(pl.lit("MS_RETURN_METHOD_UNRESOLVED"))
        .alias("analysis_reason_code")
    )


def add_massive_fix_guidance(
    frame: _FrameT,
    massive_needs_fix_expr: pl.Expr,
) -> _FrameT:
    """Add Massive remediation flags and guidance text.

    Args:
        frame:
            Return-audit frame with ``analysis_reason_code`` assigned.

        massive_needs_fix_expr:
            Expression used to assign ``massive_needs_fix`` for the
            current stage of the audit pipeline.

    Returns:
        Frame with Massive remediation flag, summary, explanation, action,
        and priority columns.
    """
    existing_columns: list[str]

    if isinstance(frame, pl.LazyFrame):
        existing_columns = frame.collect_schema().names()
    else:
        existing_columns = frame.columns

    if "likely_correct_source" not in existing_columns:
        frame = cast(_FrameT, frame.with_columns(pl.lit("").alias("likely_correct_source")))

    # Research can clear pre-research Massive suspicion when it concludes Massive
    # is correct or economically equivalent. Conversely, research that names
    # yFinance or neither source as correct should keep the row actionable for
    # Massive review even if the pre-research diagnostic was generic.
    research_says_massive_correct: pl.Expr = pl.col("likely_correct_source").is_in(
        ["MASSIVE", "BOTH"]
    )
    research_says_massive_incorrect: pl.Expr = pl.col("likely_correct_source").is_in(
        ["YFINANCE", "NEITHER"]
    )
    close_reversal_supports_massive_fix: pl.Expr = (
        (pl.col("analysis_reason_code") == "CLOSE_REVERSAL") & research_says_massive_incorrect
    )
    # Real-world research has higher authority than deterministic pre-research
    # suspicion. If research says Massive is correct or economically equivalent,
    # clear Massive remediation; if research says yFinance or neither source is
    # correct, keep/remap the row as a Massive fix candidate.
    research_aware_massive_needs_fix_expr: pl.Expr = (
        pl.when(research_says_massive_correct)
        .then(pl.lit(False))
        .when(research_says_massive_incorrect)
        .then(pl.lit(True))
        .otherwise(massive_needs_fix_expr)
    )

    return cast(
        _FrameT,
        frame.with_columns(
            research_aware_massive_needs_fix_expr.alias("massive_needs_fix"),
            # Close reversals are not pre-research Massive fixes by default. The
            # special branch below emits guidance only when external research says
            # Massive is the incorrect side of the reversal.
            pl.when(research_says_massive_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_massive_fix)
            .then(
                pl.lit(schema.REASON_CODES["CLOSE_REVERSAL"].massive_problem_summary)
            )
            .otherwise(_reason_code_text_expr("massive_problem_summary"))
            .alias("massive_problem_summary"),
            pl.when(research_says_massive_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_massive_fix)
            .then(
                pl.lit(schema.REASON_CODES["CLOSE_REVERSAL"].massive_why_incorrect)
            )
            .otherwise(_reason_code_text_expr("massive_why_incorrect"))
            .alias("massive_why_incorrect"),
            pl.when(research_says_massive_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_massive_fix)
            .then(
                pl.lit(schema.REASON_CODES["CLOSE_REVERSAL"].massive_fix_action)
            )
            .otherwise(_reason_code_text_expr("massive_fix_action"))
            .alias("massive_fix_action"),
            _massive_fix_priority_expr(research_aware_massive_needs_fix_expr).alias(
                "massive_fix_priority"
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
    because it has a special research-aware branch in ``add_massive_fix_guidance``.
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
    """Refresh analysis labels, Massive fix guidance, and review columns.

    Args:
        df:
            Return-audit output after deterministic and real-world event
            reason-code classification.

    Returns:
        DataFrame with analysis-sheet, confidence, Massive remediation, and
        review columns synchronized to the final reason code.
    """
    df = add_analysis_labels(
        df,
        include_real_world_reason_codes=True,
    )

    df = add_massive_fix_guidance(
        df,
        # After research, generic EVENT_SOURCE_MISMATCH is not enough by itself
        # to say Massive needs a fix. It must have been converted to a
        # Massive-focused reason code or supported by likely_correct_source.
        pl.col("analysis_reason_code").is_in(
            schema.reason_codes_in_group("massive_fix_post_research")
        ),
    )

    df = add_review_columns(df)

    return df.drop(
        [
            "real_world_event_return_match",
            "real_world_event_supports_massive",
            "real_world_event_supports_yfinance",
        ]
    )


def _massive_fix_priority_expr(massive_needs_fix_expr: pl.Expr) -> pl.Expr:
    """Return the expression that assigns Massive fix priority.

    Args:
        massive_needs_fix_expr:
            Expression used to decide whether Massive fix guidance applies.

    Returns:
        Polars expression that assigns the Massive fix priority bucket.
    """
    return pl.when(massive_needs_fix_expr).then(_triage_priority_expr()).otherwise(pl.lit(""))


def _triage_priority_expr() -> pl.Expr:
    """Return the expression that assigns audit triage priority.

    Returns:
        Polars expression that assigns a HIGH, MEDIUM, LOW, or blank priority.
    """
    # A material Massive/yFinance return difference is always HIGH. Heuristic
    # anomaly rows are lower priority because they may be real market moves even
    # when both sources agree.
    # A heuristic anomaly score >= 8 is particularly suspicious.
    is_high_score = pl.col("heuristic_anomaly_score") >= 8

    # By definition, HIGH_SCORE_ANOMALY has no diff_return. So if both vendors appear
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
