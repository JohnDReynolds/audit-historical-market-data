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
    medium_confidence_reason_codes: list[str] = [
        "MS_MISSING_EVENT",
        "MS_EVENT_DATE_MISMATCH",
        "MS_PARTIAL_EVENT",
        "MS_EXTRA_EVENT",
        "MS_ADJ_FACTOR_CONTINUITY",
        "EVENT_DENOMINATOR_MISMATCH",
        "EVENT_SOURCE_MISMATCH",
        "HIGH_SCORE_ANOMALY",
    ]

    if include_real_world_reason_codes:
        medium_confidence_reason_codes.append("YF_MISSING_EVENT")

    return cast(
        _FrameT,
        frame.with_columns(
            pl.when(pl.col("analysis_reason_code") == "")
            .then(pl.lit(""))
            .when(
                pl.col("analysis_reason_code").is_in(
                    [
                        "CLOSE_REVERSAL",
                        "YF_DIV_SPLIT_RETURN_MISMATCH",
                        "YF_EVENT_DATE_MISMATCH",
                    ]
                )
            )
            .then(pl.lit("HIGH"))
            .when(pl.col("analysis_reason_code").is_in(medium_confidence_reason_codes))
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
        .when(
            pl.col("diff_return").is_null()
            & (pl.col("heuristic_anomaly_score") >= schema.MIN_SCORE_TO_REVIEW)
        )
        .then(pl.lit("HIGH_SCORE_ANOMALY"))
        .when(pl.col("is_event_date_mismatch"))
        .then(pl.lit("MS_EVENT_DATE_MISMATCH"))
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
            pl.when(research_says_massive_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_massive_fix)
            .then(
                pl.lit(
                    "Massive close appears incorrect after an adjacent-day close reversal."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_MISSING_EVENT")
            .then(
                pl.lit(
                    "Massive is missing the event/adjustment needed to explain the return "
                    "difference."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EVENT_DATE_MISMATCH")
            .then(
                pl.lit(
                    "Massive appears to have the correct event amount on the wrong trading "
                    "date."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_PARTIAL_EVENT")
            .then(
                pl.lit(
                    "Massive records a corporate-action event, but the event amount appears "
                    "incomplete."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EXTRA_EVENT")
            .then(
                pl.lit(
                    "Massive records an extra corporate-action event or excessive event amount."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_ADJ_FACTOR_CONTINUITY")
            .then(
                pl.lit(
                    "Massive adjustment-factor continuity does not align with the return "
                    "difference."
                )
            )
            .when(pl.col("analysis_reason_code") == "EVENT_SOURCE_MISMATCH")
            .then(
                pl.lit(
                    "Massive and yFinance report different dividend/split event data for the "
                    "date."
                )
            )
            .when(pl.col("analysis_reason_code") == "EVENT_DENOMINATOR_MISMATCH")
            .then(
                pl.lit(
                    "Massive and yFinance record the same dividend/split event, but calculate "
                    "different event-return percentages because they use different prior-close "
                    "denominators."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_RETURN_METHOD_UNRESOLVED")
            .then(
                pl.lit(
                    "Massive return differs from yFinance, but the available event and factor "
                    "fields do not isolate a single cause."
                )
            )
            .when(pl.col("analysis_reason_code") == "HIGH_SCORE_ANOMALY")
            .then(
                pl.lit(
                    "Massive return has a high heuristic anomaly score even though the "
                    "Massive/yFinance return difference is not material."
                )
            )
            .otherwise(pl.lit(""))
            .alias("massive_problem_summary"),
            pl.when(research_says_massive_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_massive_fix)
            .then(
                pl.lit(
                    "Massive appears incorrect because independent evidence supports the "
                    "comparison source's close, and the return difference reverses across "
                    "adjacent trading days."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_MISSING_EVENT")
            .then(
                pl.lit(
                    "Massive appears incorrect because the comparison source and real-world "
                    "event evidence support an event/adjustment that Massive did not capture."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EVENT_DATE_MISMATCH")
            .then(
                pl.lit(
                    "Massive appears incorrect because the real-world event date and "
                    "return math indicate the event should be recognized on a different "
                    "trading date."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_PARTIAL_EVENT")
            .then(
                pl.lit(
                    "Massive appears incorrect because it captured only part of the "
                    "same-day corporate-action event, and the missing event-return piece "
                    "explains the Massive/yFinance return difference."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EXTRA_EVENT")
            .then(
                pl.lit(
                    "Massive appears incorrect because it captured an extra same-day "
                    "corporate-action event or event amount, and the excess event-return "
                    "piece explains the Massive/yFinance return difference."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_ADJ_FACTOR_CONTINUITY")
            .then(
                pl.lit(
                    "Massive appears incorrect because the adjusted-return difference is "
                    "associated with a change in adjustment-factor continuity rather than "
                    "only a normal price move."
                )
            )
            .when(pl.col("analysis_reason_code") == "EVENT_SOURCE_MISMATCH")
            .then(
                pl.lit(
                    "Massive and yFinance disagree on dividend/split event data, but the "
                    "pre-research fields do not determine which source is economically correct."
                )
            )
            .when(pl.col("analysis_reason_code") == "EVENT_DENOMINATOR_MISMATCH")
            .then(
                pl.lit(
                    "The vendors appear to divide the same cash amount by different prior-close "
                    "values, so the row needs methodology review rather than a presumptive "
                    "Massive correction."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_RETURN_METHOD_UNRESOLVED")
            .then(
                pl.lit(
                    "Massive may be incorrect, but the input fields do not provide enough "
                    "deterministic evidence to assign a more specific defect type."
                )
            )
            .when(pl.col("analysis_reason_code") == "HIGH_SCORE_ANOMALY")
            .then(
                pl.lit(
                    "Massive may need review because its adjusted return is unusual relative "
                    "to the surrounding return pattern, even without a material source "
                    "difference."
                )
            )
            .otherwise(pl.lit(""))
            .alias("massive_why_incorrect"),
            pl.when(research_says_massive_correct)
            .then(pl.lit(""))
            .when(close_reversal_supports_massive_fix)
            .then(
                pl.lit(
                    "Review and correct the Massive close for the affected date, then rebuild "
                    "the adjusted close and adjusted return chain."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_MISSING_EVENT")
            .then(
                pl.lit(
                    "Add or correct the missing Massive dividend/split event, apply the "
                    "appropriate adjustment factor, and rebuild the adjusted close and "
                    "adjusted return chain."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EVENT_DATE_MISMATCH")
            .then(
                pl.lit(
                    "Move the Massive dividend/split event to the externally confirmed "
                    "event date, remove the misstated adjacent-date event if present, and "
                    "rebuild the adjusted close and adjusted return chain."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_PARTIAL_EVENT")
            .then(
                pl.lit(
                    "Correct the Massive event amount to include the full corporate-action "
                    "distribution, then rebuild the adjusted close and adjusted return chain."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EXTRA_EVENT")
            .then(
                pl.lit(
                    "Remove the unsupported Massive event amount or duplicate event, then "
                    "rebuild the adjusted close and adjusted return chain."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_ADJ_FACTOR_CONTINUITY")
            .then(
                pl.lit(
                    "Review Massive corporate-action adjustment factors for this ticker/date, "
                    "correct the factor history if needed, and rebuild the adjusted close and "
                    "adjusted return chain."
                )
            )
            .when(pl.col("analysis_reason_code") == "EVENT_SOURCE_MISMATCH")
            .then(
                pl.lit(
                    "Compare Massive event records against a trusted corporate-action source; "
                    "correct missing, extra, or misstated events and rerun the return "
                    "calculation."
                )
            )
            .when(pl.col("analysis_reason_code") == "EVENT_DENOMINATOR_MISMATCH")
            .then(
                pl.lit(
                    "Review the vendors' prior-close denominators for this event; do not treat "
                    "the row as a Massive event defect unless external evidence shows Massive "
                    "used the wrong prior close."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_RETURN_METHOD_UNRESOLVED")
            .then(
                pl.lit(
                    "Review Massive close, adjusted close, corporate actions, and return "
                    "calculation methodology for this ticker/date; manual investigation is "
                    "required."
                )
            )
            .when(pl.col("analysis_reason_code") == "HIGH_SCORE_ANOMALY")
            .then(
                pl.lit(
                    "Review the Massive close, adjusted close, corporate actions, and nearby "
                    "returns for this ticker/date to confirm whether the high score reflects "
                    "a real event or a data issue."
                )
            )
            .otherwise(pl.lit(""))
            .alias("massive_fix_action"),
            _massive_fix_priority_expr(research_aware_massive_needs_fix_expr).alias(
                "massive_fix_priority"
            ),
        ),
    )


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
            [
                "MS_MISSING_EVENT",
                "MS_EVENT_DATE_MISMATCH",
                "MS_PARTIAL_EVENT",
                "MS_EXTRA_EVENT",
                "MS_ADJ_FACTOR_CONTINUITY",
                "MS_RETURN_METHOD_UNRESOLVED",
                "HIGH_SCORE_ANOMALY",
            ]
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
