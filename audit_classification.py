"""Classification, review, and guidance helpers for return-audit output."""

# Standard library imports.
from typing import TypeVar, cast

# Third-party imports.
import polars as pl

# Project imports.
from audit_schema import MIN_SCORE_TO_REVIEW

# Type aliases.
_FrameT = TypeVar("_FrameT", pl.DataFrame, pl.LazyFrame)


def add_analysis_labels(
    frame: _FrameT,
    include_real_world_reason_codes: bool,
) -> _FrameT:
    """Add analysis-sheet and confidence labels from reason codes.

    Args:
        frame:
            Return-audit frame with ``analysis_reason_code`` assigned.

        include_real_world_reason_codes:
            Whether labels should include reason codes that can only be
            assigned after real-world event research is joined.

    Returns:
        Frame with ``analysis_sheet`` and ``analysis_confidence`` columns.
    """
    yfinance_reason_codes: list[str] = [
        "YF_DIV_SPLIT_RETURN_MISMATCH",
    ]
    medium_confidence_reason_codes: list[str] = [
        "MS_MISSING_EVENT_ADJUSTMENT",
        "MS_EVENT_DATE_MISMATCH",
        "MS_ADJ_FACTOR_CONTINUITY",
        "MS_DIV_SPLIT_RETURN_MISMATCH",
        "HIGH_SCORE_ANOMALY",
    ]

    if include_real_world_reason_codes:
        yfinance_reason_codes.extend(
            [
                "YF_EVENT_DATE_MISMATCH",
                "YF_MISSING_REAL_WORLD_EVENT",
            ]
        )
        medium_confidence_reason_codes.append("YF_MISSING_REAL_WORLD_EVENT")

    return cast(
        _FrameT,
        frame.with_columns(
            pl.when(pl.col("analysis_reason_code") == "")
            .then(pl.lit(""))
            .when(pl.col("analysis_reason_code") == "CLOSE_REVERSAL")
            .then(pl.lit("Close reversals"))
            .when(pl.col("analysis_reason_code").is_in(yfinance_reason_codes))
            .then(pl.lit("yFinance probably incorrect"))
            .otherwise(pl.lit("Everything else"))
            .alias("analysis_sheet"),
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

    return df_lf.with_columns(
        pl.when(~review_required_expr())
        .then(pl.lit(""))
        .when(pl.col("diff_return").is_null() & (pl.col("score") >= MIN_SCORE_TO_REVIEW))
        .then(pl.lit("HIGH_SCORE_ANOMALY"))
        .when(pl.col("is_event_date_mismatch"))
        .then(pl.lit("MS_EVENT_DATE_MISMATCH"))
        .when(pl.col("is_close_reversal"))
        .then(pl.lit("CLOSE_REVERSAL"))
        .when(pl.col("is_ms_missing_event_adjustment"))
        .then(pl.lit("MS_MISSING_EVENT_ADJUSTMENT"))
        .when(
            pl.col("is_yf_div_split_return_mismatch") & ~pl.col("is_ms_div_split_return_mismatch")
        )
        .then(pl.lit("YF_DIV_SPLIT_RETURN_MISMATCH"))
        .when(pl.col("is_adj_factor_mismatch"))
        .then(pl.lit("MS_ADJ_FACTOR_CONTINUITY"))
        .when(pl.col("is_ms_div_split_return_mismatch"))
        .then(pl.lit("MS_DIV_SPLIT_RETURN_MISMATCH"))
        .when(pl.col("has_div_split_mismatch"))
        .then(pl.lit("MS_EVENT_SOURCE_MISMATCH"))
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
    return cast(
        _FrameT,
        frame.with_columns(
            massive_needs_fix_expr.alias("massive_needs_fix"),
            pl.when(pl.col("analysis_reason_code") == "MS_MISSING_EVENT_ADJUSTMENT")
            .then(
                pl.lit(
                    "Massive is missing the event/adjustment needed to explain the return "
                    "difference."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_ADJ_FACTOR_CONTINUITY")
            .then(
                pl.lit(
                    "Massive adjustment-factor continuity does not align with the return "
                    "difference."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_DIV_SPLIT_RETURN_MISMATCH")
            .then(
                pl.lit(
                    "Massive adjusted return does not reconcile to its explicit "
                    "dividend/split event return."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EVENT_SOURCE_MISMATCH")
            .then(
                pl.lit(
                    "Massive and yFinance report different dividend/split event data for the "
                    "date."
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
            pl.when(pl.col("analysis_reason_code") == "MS_MISSING_EVENT_ADJUSTMENT")
            .then(
                pl.lit(
                    "Massive appears incorrect because the comparison source and real-world "
                    "event evidence support an event/adjustment that Massive did not capture."
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
            .when(pl.col("analysis_reason_code") == "MS_DIV_SPLIT_RETURN_MISMATCH")
            .then(
                pl.lit(
                    "Massive appears incorrect because its implied dividend/split return does "
                    "not match the explicit Massive dividend/split event return."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EVENT_SOURCE_MISMATCH")
            .then(
                pl.lit(
                    "Massive may be incorrect because its dividend/split event data differs "
                    "from the comparison source."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_RETURN_METHOD_UNRESOLVED")
            .then(
                pl.lit(
                    "Massive may be incorrect, but the CSV fields do not provide enough "
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
            pl.when(pl.col("analysis_reason_code") == "MS_MISSING_EVENT_ADJUSTMENT")
            .then(
                pl.lit(
                    "Add or correct the missing Massive dividend/split event, apply the "
                    "appropriate adjustment factor, and rebuild the adjusted close and "
                    "adjusted return chain."
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
            .when(pl.col("analysis_reason_code") == "MS_DIV_SPLIT_RETURN_MISMATCH")
            .then(
                pl.lit(
                    "Review Massive dividend/split event handling for this ticker/date and "
                    "rebuild the adjusted return so the implied event return reconciles to "
                    "the explicit event return."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_EVENT_SOURCE_MISMATCH")
            .then(
                pl.lit(
                    "Compare Massive event records against a trusted corporate-action source; "
                    "correct missing, extra, or misstated events and rerun the return "
                    "calculation."
                )
            )
            .when(pl.col("analysis_reason_code") == "MS_RETURN_METHOD_UNRESOLVED")
            .then(
                pl.lit(
                    "Review Massive close, adjusted close, corporate actions, and return "
                    "methodology for this ticker/date; manual investigation is required."
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
            pl.when(
                pl.col("analysis_reason_code").is_in(
                    [
                        "MS_MISSING_EVENT_ADJUSTMENT",
                        "MS_EVENT_DATE_MISMATCH",
                        "MS_ADJ_FACTOR_CONTINUITY",
                        "MS_DIV_SPLIT_RETURN_MISMATCH",
                    ]
                )
            )
            .then(pl.lit("HIGH"))
            .when(
                pl.col("analysis_reason_code").is_in(
                    [
                        "MS_EVENT_SOURCE_MISMATCH",
                        "MS_RETURN_METHOD_UNRESOLVED",
                        "HIGH_SCORE_ANOMALY",
                    ]
                )
            )
            .then(pl.lit("MEDIUM"))
            .otherwise(pl.lit(""))
            .alias("massive_fix_priority"),
        ),
    )


def add_review_columns(frame: _FrameT) -> _FrameT:
    """Add persisted review workflow columns.

    Args:
        frame:
            Return-audit frame with ``diff_return`` and ``score`` columns.

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
            _review_priority_expr().alias("review_priority"),
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
        pl.col("analysis_reason_code").is_in(
            [
                "MS_MISSING_EVENT_ADJUSTMENT",
                "MS_EVENT_DATE_MISMATCH",
                "MS_ADJ_FACTOR_CONTINUITY",
                "MS_DIV_SPLIT_RETURN_MISMATCH",
                "MS_EVENT_SOURCE_MISMATCH",
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


def _review_priority_expr() -> pl.Expr:
    """Return the expression that assigns review priority.

    Returns:
        Polars expression that assigns the review priority bucket.
    """
    # A score >= 8 is particularly suspicious.
    is_high_score = pl.col("score") >= 8

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
        .when(pl.col("score") >= MIN_SCORE_TO_REVIEW)
        .then(pl.lit("LOW"))
        .otherwise(pl.lit(""))
    )


def review_required_expr() -> pl.Expr:
    """Return the expression that identifies rows requiring review.

    Returns:
        Polars expression that is true when a row has a material return
        difference or a high heuristic audit score.
    """
    return pl.col("diff_return").is_not_null() | (pl.col("score") >= MIN_SCORE_TO_REVIEW)
