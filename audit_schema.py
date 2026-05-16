"""Shared schema constants for the audit module.

This module intentionally contains only constants and column lists so the
main audit module is easier to scan.
"""

# Constants.
ADJ_FACTOR_CHANGE_TOLERANCE = 0.000001
DISPLAY_DECIMALS = 6
MAX_NEEDS_REVIEW_ROWS = 5  # ChatGPT does better research quality if you keep this low
MIN_SCORE_TO_REVIEW = 5  # Setting this lower generates a bunch of false signals
REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE = 0.001
REAL_WORLD_EVENT_REL_RETURN_TOLERANCE = 0.10
REVERSAL_TOLERANCE = 0.0002
TOLERANCE_4 = 0.0001
TOLERANCE_6 = 0.000001

CATEGORY_REPORT_COLUMNS: list[str] = [
    "ticker",
    "date",
    # # Close
    # "ms_close",
    # "yf_close",
    # "ms_adj_factor",
    # "yf_adj_factor",
    # "ms_adj_close",
    # "yf_adj_close",
    # # Dividends and splits
    "ms_div_split",
    "yf_div_split",
    # # Components of return
    # "ms_return_price",
    # "yf_return_price",
    # "ms_return_div_split_implied",
    # "ms_return_div_split_actual",
    # "diff_ms_return_div_split",
    # "yf_return_div_split_implied",
    # "yf_return_div_split_actual",
    # "diff_yf_return_div_split",
    # Returns
    "ms_return",
    "yf_return",
    "diff_return",
    # "needs_review",
    "review_priority",
    "score",
    # "analysis_sheet",
    "analysis_reason_code",
    "event_detected",
    "event_bucket",
    "expected_return_impact",
    "likely_correct_source",
    "confidence_level",
    "evidence_summary",
    "real_world_event",
    "primary_source_url",
    "secondary_source_url",
    # Massive columns
    # "massive_needs_fix",
    "massive_problem_summary",
    "massive_why_incorrect",
    "massive_fix_action",
    # "massive_fix_priority",
    # "analysis_confidence",
]

CATEGORY_NON_ACTIONABLE: list[str] = [
    "CLOSE_REVERSAL",
    "YF_DIV_SPLIT_RETURN_MISMATCH",
    "YF_EVENT_DATE_MISMATCH",
    "YF_MISSING_REAL_WORLD_EVENT",
]
