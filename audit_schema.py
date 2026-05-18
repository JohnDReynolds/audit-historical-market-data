"""Shared schema constants for the audit module.

This module intentionally contains only constants and column lists so the
main audit module is easier to scan.
"""

# Constants.
# Adjustment-factor changes can differ slightly when vendors encode the same
# cash distribution or split mechanics differently. Five basis points is tight
# enough to catch material chain breaks without routing harmless rounding or
# event-format differences into MS_ADJ_FACTOR_CONTINUITY.
ADJ_FACTOR_CHANGE_TOLERANCE = 0.0005
DISPLAY_DECIMALS = 6
DUMMY_DATE = "1800-01-01"
DUMMY_TICKER = "_d_u_m_m_y_"
MAX_NEEDS_REVIEW_ROWS = 5  # ChatGPT does better research quality if you keep this low
MIN_SCORE_TO_REVIEW = 5  # Setting this lower generates a bunch of false signals
REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE = 0.001
REAL_WORLD_EVENT_REL_RETURN_TOLERANCE = 0.10
REVERSAL_TOLERANCE = 0.0005
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
        "before or apart from external real-world research.\n\nPossible values, "
        "alphabetically:\n"
        "o Blank = no analysis reason code is assigned.\n"
        "o HIGH = high deterministic confidence, such as close reversal, yFinance "
        "dividend/split return mismatch, or yFinance event-date mismatch.\n"
        "o LOW = lower deterministic confidence, usually unresolved or less isolated "
        "diagnostics.\n"
        "o MEDIUM = medium deterministic confidence, usually Massive-focused "
        "diagnostics such as missing event adjustment, adjustment-factor continuity, "
        "partial event capture, or high-score anomaly."
    ),
    "analysis_reason_code": (
        "Deterministic diagnostic classification assigned by the audit pipeline. It "
        "explains the main reason the row needs review. When real-world research is "
        "available, the code may be adjusted so the diagnostic agrees with "
        "likely_correct_source.\n\nPossible values, alphabetically:\n"
        "o CLOSE_REVERSAL = Massive/yFinance return difference reverses on an "
        "adjacent trading day, suggesting a close-source or timing artifact rather "
        "than a corporate action.\n"
        "  Example: On Tuesday, Massive return is -2.00% and yFinance return is "
        "-3.00%, so diff_return is -1.00%. On Wednesday, Massive return is +1.00% "
        "and yFinance return is +2.00%, so diff_return is +1.00%. The equal and "
        "opposite differences suggest a close timing issue, not a real event.\n"
        "o HIGH_SCORE_ANOMALY = Massive return has a high heuristic anomaly score "
        "even when the Massive/yFinance return difference is not material.\n"
        "  Example: Massive and yFinance both show +15.00% for the day, so "
        "diff_return is 0.00%. The ticker's recent daily moves are usually near "
        "1.00%, so the +15.00% move still needs review.\n"
        "o EVENT_SOURCE_MISMATCH = Massive and yFinance report different "
        "dividend/split event markers for the date, especially when both sources "
        "have event markers but use different event formatting, grouping, amounts, "
        "or source-event representation and the residual return difference is "
        "small. Pre-research evidence does not determine which source is "
        "economically correct.\n"
        "  Example: On the same ticker/date, Massive reports ca:0.25 while yFinance "
        "reports ca:0.50. With a $50.00 prior close, that is about +0.50% versus "
        "+1.00% expected dividend impact.\n"
        "o EVENT_RETURN_BASIS_MISMATCH = Massive and yFinance record the same "
        "dividend/split marker, but the event-return percentage differs because "
        "the same event amount is applied to different historical price or "
        "adjustment bases.\n"
        "  Example: Both sources report ca:0.52 and show the same raw price return, "
        "but one source's historical close is $28.00 while the other's is $21.00 "
        "because of a later vendor adjustment methodology. The same $0.52 cash "
        "dividend therefore produces different event-return percentages.\n"
        "o MS_ADJ_FACTOR_CONTINUITY = Massive adjustment-factor continuity does not "
        "align with the adjusted-return difference, and the discrepancy is not "
        "better explained by a same-day event-source or event-return-basis mismatch.\n"
        "  Example: Both sources show close rising from $100.00 to $101.00, a "
        "+1.00% price return. Both also show a $1.00 dividend, so the adjusted "
        "return should be about +2.00%. Massive's adjusted-return chain shows "
        "+1.20%, so the adjustment-factor continuity does not reconcile.\n"
        "o MS_DIV_SPLIT_RETURN_MISMATCH = Massive implied dividend/split return does "
        "not reconcile to Massive explicit event return.\n"
        "  Example: Massive records a $0.50 dividend and prior close is $50.00, so "
        "the explicit dividend impact is about +1.00%. Massive's adjusted close "
        "implies a +2.00% dividend/split impact instead.\n"
        "o MS_EVENT_DATE_MISMATCH = Massive appears to have an event on the wrong "
        "trading date.\n"
        "  Example: A $0.50 dividend has confirmed ex-date Tuesday. Massive shows "
        "ca:0.50 on Monday and no event on Tuesday, while yFinance shows ca:0.50 "
        "on Tuesday.\n"
        "o MS_MISSING_EVENT = Massive appears to be missing a corporate-action event "
        "or related adjustment needed to explain the return difference.\n"
        "  Example: yFinance records sp:1.05 for a confirmed spin-off, implying "
        "about +5.00% adjusted-return impact. Massive has no event marker and "
        "shows a return about 5.00 percentage points lower.\n"
        "o MS_EXTRA_EVENT = Massive records an extra corporate-action event or "
        "extra event amount not supported by the comparison source and "
        "adjusted-return difference.\n"
        "  Example: Research confirms one $0.65 dividend. Massive records "
        "ca:0.65 ca:0.65, yFinance records ca:0.65, and diff_return reconciles "
        "to Massive's extra $0.65 event-return impact.\n"
        "o MS_PARTIAL_EVENT = Massive records a same-day corporate-action event, "
        "but the recorded event amount appears incomplete relative to the "
        "comparison source and the adjusted-return difference.\n"
        "  Example: Research confirms a $0.15 dividend made up of a $0.075 base "
        "dividend plus a $0.075 variable dividend. Massive records ca:0.075, "
        "yFinance records ca:0.15, and diff_return reconciles to the missing "
        "$0.075 event-return impact.\n"
        "o MS_RETURN_METHOD_UNRESOLVED = Massive return differs from yFinance, but "
        "the input fields do not isolate a single deterministic cause.\n"
        "  Example: Massive return is +2.00% and yFinance return is +3.20%, so "
        "diff_return is +1.20%. There is no event marker mismatch, no factor "
        "continuity mismatch, and no adjacent-day reversal to explain it.\n"
        "o YF_DIV_SPLIT_RETURN_MISMATCH = yFinance implied dividend/split return "
        "does not reconcile to yFinance explicit event return.\n"
        "  Example: yFinance records a $0.40 dividend and prior close is $40.00, "
        "so the explicit dividend impact is about +1.00%. yFinance's adjusted close "
        "implies a +2.50% dividend/split impact instead.\n"
        "o YF_EVENT_DATE_MISMATCH = post-research override indicating yFinance "
        "appears to have the event on the wrong trading date.\n"
        "  Example: Research confirms a $0.60 dividend belongs on Thursday. Massive "
        "shows ca:0.60 on Thursday, but yFinance shows ca:0.60 on Wednesday.\n"
        "o YF_MISSING_EVENT = post-research override indicating yFinance appears "
        "to be missing a corporate-action event or related adjustment.\n"
        "  Example: Research confirms a $0.75 dividend with prior close $75.00, so "
        "the expected impact is about +1.00%. Massive shows ca:0.75, but yFinance "
        "has no dividend marker or adjusted-return impact."
    ),
    "analysis_sheet": (
        "Deterministic routing label derived from analysis_reason_code.\n\nPossible "
        "values, alphabetically:\n"
        "o Blank = no analysis reason code is assigned.\n"
        "o Close reversals = rows routed to the close-reversal review group.\n"
        "o Everything else = rows routed to the general review group.\n"
        "o yFinance probably incorrect = rows where deterministic diagnostics point "
        "toward a yFinance-side issue."
    ),
    "confidence_level": (
        "External research confidence label for the likely_correct_source and event "
        "conclusion. This is separate from analysis_confidence: confidence_level comes "
        "from the analyst/research evidence scoring rules, while analysis_confidence "
        "is the deterministic pipeline's pre-research label.\n\nPossible values, "
        "alphabetically:\n"
        "o Blank = no external real-world event research was joined.\n"
        "o HIGH = strong source support and clear return/event reconciliation.\n"
        "o LOW = weak, ambiguous, or absence-of-event support.\n"
        "o MEDIUM = reasonable but incomplete or partly inferential support."
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
        "\n\nPossible values, alphabetically:\n"
        "o DISTRIBUTION = cash dividend, special dividend, return of capital, or "
        "similar cash/non-split distribution.\n"
        "o MERGER = merger, acquisition, exchange offer, or transaction consideration "
        "affecting the price/return series.\n"
        "o NEWS = material company, industry, macro, earnings, guidance, regulatory, "
        "litigation, or analyst/news event rather than a mechanical corporate "
        "action.\n"
        "o PRICING_METHOD = a non-corporate-action difference caused by different "
        "vendor price, adjustment, or timing methods, after corporate actions and "
        "material news have been investigated.\n"
        "o RIGHTS = rights offering, warrant distribution, subscription right, or "
        "similar shareholder right.\n"
        "o SPINOFF = spin-off, split-off, or separation distribution.\n"
        "o SPLIT = stock split, reverse split, or stock dividend treated as a split "
        "factor.\n"
        "o UNKNOWN = no sufficiently supported real-world explanation was "
        "identified.\n\nThe analyst instructions require event precedence in this "
        "order: SPLIT, SPINOFF, DISTRIBUTION, MERGER, RIGHTS, NEWS, PRICING_METHOD, "
        "UNKNOWN."
    ),
    "event_detected": (
        "External research field indicating whether a real-world event was identified "
        "for the ticker/date.\n\nPossible values, alphabetically:\n"
        "o Blank = no external real-world event research was joined.\n"
        "o NO = research did not identify a relevant real-world event.\n"
        "o UNCERTAIN = research did not support a firm yes/no conclusion.\n"
        "o YES = research identified a relevant real-world event."
    ),
    "evidence_summary": (
        "External research narrative summary. Per the analyst instructions, it should "
        "be row-specific, name Massive and yFinance explicitly, summarize sources "
        "reviewed, describe the real-world event or absence of one, explain economic "
        "plausibility, and tie the conclusion back to input row math such as ms_return, "
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
        "older Massive marker text CD and SC to CA before comparing against "
        "yFinance.\n\nPossible values, alphabetically:\n"
        "o false = Massive and yFinance dividend/split marker strings match after "
        "normalization.\n"
        "o true = Massive and yFinance dividend/split marker strings differ after "
        "normalization."
    ),
    "heuristic_anomaly_score": (
        "Deterministic pre-research anomaly score generated from Massive-side "
        "return behavior. The score is not a probability and does not identify "
        "the correct vendor by itself. It is a routing signal that helps identify "
        "rows where Massive's adjusted return looks unusual, even when Massive "
        "and yFinance returns agree.\n\n"
        "Higher scores indicate that more independent anomaly signals were "
        "present.\n\nTypical interpretation:\n"
        "o 0 = no independent Massive-side anomaly signals were triggered. The row "
        "may still require review because of a vendor return difference, event-marker "
        "mismatch, or other reconciliation issue.\n"
        "o 1-3 = low anomaly signal. One or more mild conditions may be present, "
        "but the row is usually reviewed only if another diagnostic also requires "
        "attention.\n"
        "o 4-6 = moderate anomaly signal. The Massive return may be unusually large, "
        "inconsistent with nearby price behavior, or close to a corporate-action-style "
        "return pattern. These rows are worth review, especially when paired with "
        "event or adjustment differences.\n"
        "o 7-10 = high anomaly signal. Multiple independent checks suggest the "
        "Massive return is unusual relative to price movement, adjustment mechanics, "
        "nearby returns, or corporate-action expectations.\n"
        "o 11+ = very high anomaly signal. The row has several strong anomaly "
        "indicators and should be reviewed even if Massive and yFinance returns "
        "are identical, because both vendors may be reflecting a real market event "
        "or both may share a questionable treatment.\n\nImportant notes:\n"
        "o The score is additive: multiple smaller signals can produce a high score.\n"
        "o The score is pre-research only. Real-world research and input row math "
        "determine the final classification.\n"
        "o A high score does not imply Massive is wrong. It means the row deserves "
        "investigation.\n"
        "o A score of 0 does not imply the row is correct. It may still be flagged "
        "by return differences, event mismatches, adjustment-factor issues, or "
        "close-reversal diagnostics."
    ),
    "likely_correct_source": (
        "External research conclusion identifying which source appears economically "
        "correct after considering both real-world evidence and input row math. The "
        "analyst instructions require this to follow from ms_return, yf_return, "
        "diff_return, event markers, event-return fields, adjustment factors, and "
        "external evidence.\n\nPossible values, alphabetically:\n"
        "o Blank = no external real-world event research was joined.\n"
        "o BOTH = Massive and yFinance are economically equivalent or both appear "
        "reasonable for the row.\n"
        "o MASSIVE = Massive appears economically correct.\n"
        "o NEITHER = neither Massive nor yFinance appears economically correct.\n"
        "o UNCERTAIN = research cannot determine the likely correct source.\n"
        "o YFINANCE = yFinance appears economically correct."
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
        "or BOTH.\n\nPossible values, alphabetically:\n"
        "o Blank = no Massive remediation priority is assigned.\n"
        "o HIGH = direct Massive fix candidate, such as missing event adjustment, "
        "event-date mismatch, adjustment-factor continuity, or Massive dividend/split "
        "return mismatch.\n"
        "o LOW = low-priority Massive review, usually lower-score heuristic anomaly.\n"
        "o MEDIUM = more investigative Massive review, such as an unresolved return "
        "method issue or higher-score anomaly."
    ),
    "massive_needs_fix": (
        "Boolean flag indicating whether Massive may require correction after "
        "deterministic diagnostics and optional real-world research. If research "
        "concludes likely_correct_source is MASSIVE or BOTH, this is false. If "
        "research concludes likely_correct_source is YFINANCE or NEITHER, this is "
        "true. Without research, it follows Massive-focused reason codes such as "
        "missing event adjustment, event-date mismatch, adjustment-factor continuity "
        "issue, dividend/split return mismatch, unresolved Massive return method "
        "issue, or high-score anomaly. Generic EVENT_SOURCE_MISMATCH rows require "
        "review but do not by themselves imply Massive needs a fix.\n\nPossible values, "
        "alphabetically:\n"
        "o false = Massive does not currently appear to need correction.\n"
        "o true = Massive may require correction or manual remediation review."
    ),
    "massive_problem_and_fix": (
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
        "ca:<cash_amount>. Multiple same-day events may be space-separated."
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
        "which is currently 5.\n\nPossible values, alphabetically:\n"
        "o false = row does not meet review criteria.\n"
        "o true = row meets review criteria."
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
    "real_world_evidence": (
        "Summary-report-only display column that vertically combines real_world_event "
        "and evidence_summary with a blank line between the two sections. It gives "
        "the event headline followed by the supporting research and input row "
        "reconciliation."
    ),
    "review_priority": (
        "Review priority bucket. This is not the same as massive_fix_priority: "
        "review_priority records why the row merited review, while "
        "massive_fix_priority records whether Massive has a recommended fix after "
        "research.\n\nPossible values, alphabetically:\n"
        "o Blank = no review is required.\n"
        "o HIGH = diff_return is non-null.\n"
        "o LOW = heuristic_anomaly_score is at least MIN_SCORE_TO_REVIEW but "
        "higher-priority conditions do not apply.\n"
        "o MEDIUM = heuristic_anomaly_score is at least 8 and the row may be "
        "actionable."
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
        "ca:<cash_amount>. Multiple same-day events may be space-separated."
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
    "YF_MISSING_EVENT",
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
