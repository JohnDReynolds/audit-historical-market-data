"""Shared schema constants for the audit module.

This module intentionally contains only constants and column lists so the
main audit module is easier to scan.
"""

# Constants.
ADJ_FACTOR_CHANGE_TOLERANCE = 0.000001
DISPLAY_DECIMALS = 6
DUMMY_DATE = "1800-01-01"
DUMMY_TICKER = "_d_u_m_m_y_"
MAX_NEEDS_REVIEW_ROWS = 5  # ChatGPT does better research quality if you keep this low
MIN_SCORE_TO_REVIEW = 5  # Setting this lower generates a bunch of false signals
REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE = 0.001
REAL_WORLD_EVENT_REL_RETURN_TOLERANCE = 0.10
REVERSAL_TOLERANCE = 0.0002
TOLERANCE_4 = 0.0001
TOLERANCE_6 = 0.000001


REAL_WORLD_EVENT_BUCKETS: list[str] = [
    "DISTRIBUTION",
    "SPLIT",
    "SPINOFF",
    "MERGER",
    "RIGHTS",
    "NEWS",
    "PRICING_METHOD",
    "UNKNOWN",
]

REAL_WORLD_EVENT_RETURN_BUCKETS: list[str] = [
    "DISTRIBUTION",
    "SPLIT",
    "SPINOFF",
    "MERGER",
    "RIGHTS",
]


DATA_DICTIONARY = {
    "analysis_confidence": (
        "Deterministic pre-research confidence label derived from analysis_reason_code. "
        "This is not the same as confidence_level. It reflects the pipeline's confidence "
        "before or apart from external real-world research. CLOSE_REVERSAL, "
        "YF_DIV_SPLIT_RETURN_MISMATCH, and YF_EVENT_DATE_MISMATCH map to HIGH; several "
        "Massive-side diagnostics map to MEDIUM; other nonblank reason codes generally "
        "map to LOW."
    ),
    "analysis_reason_code": (
        "Deterministic diagnostic classification assigned by the audit pipeline. It "
        "explains the main reason the row needs review. When real-world research is "
        "available, the code may be adjusted so the diagnostic agrees with "
        "likely_correct_source. Known values include CLOSE_REVERSAL, "
        "MS_MISSING_EVENT_ADJUSTMENT, MS_EVENT_DATE_MISMATCH, "
        "MS_ADJ_FACTOR_CONTINUITY, MS_DIV_SPLIT_RETURN_MISMATCH, "
        "MS_EVENT_SOURCE_MISMATCH, YF_DIV_SPLIT_RETURN_MISMATCH, HIGH_SCORE_ANOMALY, "
        "MS_RETURN_METHOD_UNRESOLVED, YF_EVENT_DATE_MISMATCH, or "
        "YF_MISSING_REAL_WORLD_EVENT."
    ),
    "analysis_sheet": (
        "Deterministic routing label derived from analysis_reason_code. Known labels "
        "include Close reversals, yFinance probably incorrect, Everything else, or "
        "blank when no analysis reason code is assigned."
    ),
    "confidence_level": (
        "External research confidence label for the likely_correct_source and event "
        "conclusion. Expected values are HIGH, MEDIUM, or LOW. This is separate from "
        "analysis_confidence: confidence_level comes from the analyst/research evidence "
        "scoring rules, while analysis_confidence is the deterministic pipeline's "
        "pre-research label."
    ),
    "date": (
        "Trading date being reconciled. This is the date of the Massive row and the "
        "date used to join yFinance prices, dividend/split event markers, return "
        "calculations, diagnostics, and optional real-world event research."
    ),
    "diff_ms_return_div_split": (
        "Difference between Massive implied event return and Massive explicit event "
        "return. It is calculated as ms_return_div_split_implied - "
        "ms_return_div_split_actual, but small differences below the configured 1e-6 "
        "tolerance are set to null. A non-null value indicates Massive's "
        "adjusted-return behavior does not reconcile cleanly to Massive's explicit "
        "event records."
    ),
    "diff_return": (
        "Material adjusted-return difference between yFinance and Massive, using the "
        "sign convention yf_return - ms_return. Positive means yFinance's adjusted "
        "return is higher than Massive's; negative means yFinance's adjusted return is "
        "lower. Differences below the configured 1e-4 tolerance are set to null."
    ),
    "diff_yf_return_div_split": (
        "Difference between yFinance implied event return and yFinance explicit event "
        "return. It is calculated as yf_return_div_split_implied - "
        "yf_return_div_split_actual, but small differences below the configured 1e-6 "
        "tolerance are set to null. A non-null value indicates yFinance's "
        "adjusted-return behavior does not reconcile cleanly to yFinance's explicit "
        "event records."
    ),
    "event_bucket": (
        "External research classification for the identified real-world explanation. "
        "Expected values are DISTRIBUTION, SPLIT, SPINOFF, MERGER, RIGHTS, NEWS, "
        "PRICING_METHOD, or UNKNOWN. The analyst instructions require event "
        "precedence in that order, with PRICING_METHOD used only after corporate "
        "actions and material news have been investigated."
    ),
    "event_detected": (
        "External research field indicating whether a real-world event was identified "
        "for the ticker/date. Expected values from the forensic analyst instructions "
        "are YES, NO, or UNCERTAIN. If no real-world events file was joined, this is "
        "initially blank."
    ),
    "evidence_summary": (
        "External research narrative summary. Per the analyst instructions, it should "
        "be row-specific, name Massive and yFinance explicitly, summarize sources "
        "reviewed, describe the real-world event or absence of one, explain economic "
        "plausibility, and tie the conclusion back to CSV math such as ms_return, "
        "yf_return, diff_return, event markers, and expected return impact."
    ),
    "expected_return_impact": (
        "External research estimate of the event's expected return impact using the "
        "audit's event-return convention. For splits, the instructions define this as "
        "split_factor - 1.0. For cash distributions, the approximate convention is "
        "cash_amount / prior_close. This value is used by "
        "real_world_events.apply_reason_overrides() to test whether the real-world "
        "event magnitude reconciles to abs(diff_return) within tolerance."
    ),
    "has_div_split_mismatch": (
        "Boolean flag indicating whether Massive and yFinance report different "
        "dividend/split marker strings for the ticker/date. The comparison normalizes "
        "older Massive marker text CD and SC to CA before comparing against yFinance."
    ),
    "heuristic_anomaly_score": (
        "Massive heuristic anomaly score based on the size and unusualness of the "
        "Massive adjusted return. The score increases for very large absolute returns, "
        "extreme robust z-scores versus rolling behavior, returns much larger than "
        "trailing median absolute returns, split-like raw close ratios, and large "
        "adjacent-day reversals."
    ),
    "likely_correct_source": (
        "External research conclusion identifying which source appears economically "
        "correct after considering both real-world evidence and CSV return math. "
        "Expected values are MASSIVE, YFINANCE, BOTH, NEITHER, or UNCERTAIN. The "
        "analyst instructions require this to follow from ms_return, yf_return, "
        "diff_return, event markers, event-return fields, adjustment factors, and "
        "external evidence."
    ),
    "massive_fix_action": (
        "Suggested remediation action for Massive data or Massive return methodology, "
        "generated from analysis_reason_code and optional real-world research. When "
        "research concludes likely_correct_source is MASSIVE or BOTH, this is cleared "
        "because no Massive remediation is recommended. Otherwise examples include "
        "adding or correcting missing corporate actions, reviewing adjustment-factor "
        "history, rebuilding adjusted close and return chains, or manually reviewing "
        "close/adjusted-close/corporate-action inputs."
    ),
    "massive_fix_priority": (
        "Priority for the suggested Massive remediation. This is research-aware: it "
        "is blank when real-world research concludes likely_correct_source is MASSIVE "
        "or BOTH. HIGH is assigned to certain more direct Massive defect categories "
        "such as missing event adjustment, event-date mismatch, adjustment-factor "
        "continuity, and Massive dividend/split return mismatch. MEDIUM is assigned "
        "to less isolated or more investigative Massive categories such as event "
        "source mismatch, unresolved return method issue, and high-score anomaly. "
        "Blank when no Massive fix priority is assigned."
    ),
    "massive_needs_fix": (
        "Boolean flag indicating whether Massive may require correction after "
        "deterministic diagnostics and optional real-world research. If research "
        "concludes likely_correct_source is MASSIVE or BOTH, this is false. If "
        "research concludes likely_correct_source is YFINANCE or NEITHER, this is "
        "true. Without research, it follows Massive-focused reason codes such as "
        "missing event adjustment, event-date mismatch, adjustment-factor continuity "
        "issue, dividend/split return mismatch, event source mismatch, unresolved "
        "Massive return method issue, or high-score anomaly."
    ),
    "massive problem and fix": (
        "Summary-report-only display column that vertically combines massive problem "
        "summary, massive why incorrect, and massive fix action with blank lines "
        "between the three sections."
    ),
    "massive_problem_summary": (
        "Human-readable summary of the suspected Massive-side problem, generated from "
        "analysis_reason_code and optional real-world research. Blank when the "
        "pipeline does not identify a Massive-focused issue or when research "
        "concludes likely_correct_source is MASSIVE or BOTH."
    ),
    "massive_why_incorrect": (
        "Human-readable explanation of why Massive may be incorrect or may need "
        "review, generated from analysis_reason_code and optional real-world "
        "research. Blank when the pipeline does not identify a Massive-focused issue "
        "or when research concludes likely_correct_source is MASSIVE or BOTH."
    ),
    "ms_adj_close": (
        "Massive adjusted close calculated by this audit pipeline as ms_close * "
        "ms_adj_factor. This is the Massive-side adjusted close used to calculate "
        "ms_return."
    ),
    "ms_adj_factor": (
        "Massive cumulative backward-looking adjustment factor calculated by this "
        "audit pipeline from Massive split and dividend records. For splits, the "
        "factor uses split_from / split_to. For dividends, the factor uses "
        "(prior_close - cash_amount) / prior_close. The cumulative factor includes "
        "events after the row date, because it is used to restate historical closes "
        "on an adjusted basis."
    ),
    "ms_close": (
        "Massive unadjusted close price for the ticker/date. This comes from Massive "
        "unadjusted OHLCV data and is used as the raw close input for Massive "
        "adjusted-close and raw price-return calculations."
    ),
    "ms_div_split": (
        "Compact Massive corporate-action marker string for the ticker/date. Split "
        "events are represented as sp:<split_factor>, where split_factor is split_to "
        "/ split_from. Cash dividend/distribution events are represented as "
        "ca:<cash_amount>. Multiple same-day events may be semicolon-separated."
    ),
    "ms_return": (
        "Final Massive adjusted return for the ticker/date, calculated from the "
        "percentage change in the pipeline's Massive adjusted close series."
    ),
    "ms_return_div_split_actual": (
        "Massive explicit event return derived from Massive corporate-action records "
        "on the ticker/date. Split events use split_to / split_from as the event "
        "return factor. Dividend events use 1 + cash_amount / prior_close. Multiple "
        "event factors are multiplied together, then 1.0 is subtracted."
    ),
    "ms_return_div_split_implied": (
        "Massive implied event return component, calculated as ms_return - "
        "ms_return_price. This captures how much of the Massive adjusted return is "
        "attributable to adjustment mechanics rather than raw unadjusted price "
        "movement."
    ),
    "ms_return_price": (
        "Massive raw price return from unadjusted closes, calculated as the percentage "
        "change from the prior Massive unadjusted close to the current Massive "
        "unadjusted close for the same ticker."
    ),
    "needs_review": (
        "Boolean review flag. True when diff_return is non-null or when the Massive "
        "heuristic anomaly score is greater than or equal to MIN_SCORE_TO_REVIEW, "
        "which is currently 5."
    ),
    "primary_source_url": (
        "Primary URL supporting the real-world event research conclusion. The "
        "instructions prefer authoritative sources such as SEC filings, investor "
        "relations releases, exchange notices, or official corporate-action "
        "announcements where available."
    ),
    "real_world_event": (
        "External research description of the real-world event or explanation "
        "associated with the ticker/date. This may describe a split, distribution, "
        "merger, rights offering, news event, pricing-method explanation, or the "
        "absence/uncertainty of a real event depending on the analyst output."
    ),
    "review_priority": (
        "Review priority bucket. HIGH when diff_return is non-null. "
        "MEDIUM when heuristic_anomaly_score is at least 8 and the row may be "
        "actionable. LOW when heuristic_anomaly_score is at least MIN_SCORE_TO_REVIEW "
        "but the higher-priority conditions do not apply. Blank when no review is "
        "required. This is not the same as massive_fix_priority: review_priority "
        "records why the row merited review, while massive_fix_priority records "
        "whether Massive has a recommended fix after research."
    ),
    "secondary_source_url": (
        "Secondary or confirming URL supporting the real-world event research "
        "conclusion. The instructions allow credible independent sources such as "
        "Reuters, Bloomberg, Yahoo Finance, Nasdaq, MarketWatch, Macrotrends, or "
        "company press releases."
    ),
    "ticker": (
        "Normalized ticker symbol being audited. The pipeline strips surrounding "
        "whitespace and uppercases ticker symbols before joining Massive and yFinance "
        "data."
    ),
    "yf_adj_close": (
        "yFinance adjusted close for the ticker/date, taken from yFinance OHLCV data. "
        "This is the adjusted close used to calculate yf_return."
    ),
    "yf_adj_factor": (
        "Implied yFinance adjustment factor for the ticker/date, calculated as "
        "yf_adj_close / yf_close when yf_close is present and nonzero. Unlike "
        "ms_adj_factor, this is inferred from yFinance's supplied adjusted close "
        "rather than rebuilt directly from yFinance event records."
    ),
    "yf_close": (
        "yFinance unadjusted close price for the ticker/date. This comes from "
        "yFinance OHLCV data and is used for yFinance raw price-return calculations "
        "and to infer the yFinance adjustment factor."
    ),
    "yf_div_split": (
        "Compact yFinance corporate-action marker string for the ticker/date. Split "
        "events are represented as sp:<split_factor>, where split_factor is "
        "yFinance's split_ratio. Cash dividend/distribution events are represented as "
        "ca:<cash_amount>. Multiple same-day events may be semicolon-separated."
    ),
    "yf_return": (
        "Final yFinance adjusted return for the ticker/date, calculated from the "
        "percentage change in yFinance adjusted close."
    ),
    "yf_return_div_split_actual": (
        "yFinance explicit event return derived from yFinance split and dividend "
        "records on the ticker/date. Split events use split_ratio as the event return "
        "factor. Dividend events use 1 + cash_amount / prior yFinance close. Multiple "
        "event factors are multiplied together, then 1.0 is subtracted."
    ),
    "yf_return_div_split_implied": (
        "yFinance implied event return component, calculated as yf_return - "
        "yf_return_price. This captures how much of yFinance's adjusted return is "
        "attributable to adjusted-close mechanics rather than raw unadjusted price "
        "movement."
    ),
    "yf_return_price": (
        "yFinance raw price return from unadjusted closes, calculated as the "
        "percentage change from the prior yFinance unadjusted close to the current "
        "yFinance unadjusted close for the same ticker."
    ),
}

CATEGORY_REPORT_COLUMNS: list[str] = [
    # Key values
    "ticker",
    "date",
    # Priority and Impact
    "massive_fix_priority",
    "likely_correct_source",  # optional
    "confidence_level",  # optional
    "event_bucket",  # optional
    "expected_return_impact",
    # Event Overview
    "evidence_summary",
    "real_world_event",
    # Massive Guidance
    "massive_problem_summary",
    "massive_why_incorrect",
    "massive_fix_action",
    # Event URLs
    "primary_source_url",
    "secondary_source_url",
    "analysis_reason_code",  # optional
    # Dividends and splits
    "ms_div_split",
    "yf_div_split",
    # Returns
    "ms_return",
    "yf_return",
    "diff_return",
    # Miscellaneous
    "heuristic_anomaly_score",  # optional
]

CATEGORY_NON_ACTIONABLE: list[str] = [
    "CLOSE_REVERSAL",
    "YF_DIV_SPLIT_RETURN_MISMATCH",
    "YF_EVENT_DATE_MISMATCH",
    "YF_MISSING_REAL_WORLD_EVENT",
]


# Input file paths
INPUT_DIRECTORY = "inputs/"
PATH_MASSIVE_ADJUSTED_PRICES = f"{INPUT_DIRECTORY}massive_adjusted_prices"
PATH_MASSIVE_DIVIDENDS = f"{INPUT_DIRECTORY}massive_dividends"
PATH_MASSIVE_SPLITS = f"{INPUT_DIRECTORY}massive_splits"
PATH_MASSIVE_UNADJUSTED_PRICES = f"{INPUT_DIRECTORY}massive_unadjusted_prices"
PATH_YFINANCE_DIVIDENDS = f"{INPUT_DIRECTORY}yfinance_dividends"
PATH_YFINANCE_PRICES = f"{INPUT_DIRECTORY}yfinance_prices"
PATH_YFINANCE_SPLITS = f"{INPUT_DIRECTORY}yfinance_splits"

# Output file paths
_OUTPUT_DIRECTORY = "outputs/"
PATH_AUDITED_ADJUSTED_OHLCV = f"{_OUTPUT_DIRECTORY}audited_adjusted_ohlcv"
PATH_AUDITED_RETURNS = f"{_OUTPUT_DIRECTORY}audited_returns"


# Vendor Prefixes
VENDOR_PREFIX_MAP = {
    "ms_": "Massive ",
    "yf_": "yFinance ",
}
