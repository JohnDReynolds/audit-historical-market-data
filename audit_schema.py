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

DIV_SPLIT_EXAMPLE_INPUTS = (
    "\n\nWorked example: assume prior unadjusted close is 100.00, current "
    "unadjusted close is 51.00, the source records a 2-for-1 split, and the "
    "source records a 1.00 cash dividend on the same date. The raw price factor "
    "is 51.00 / 100.00 = 0.51, which is a -49.0000% raw price return."
)

DIV_SPLIT_EXPLICIT_EXAMPLE = (
    DIV_SPLIT_EXAMPLE_INPUTS
    + " For the explicit factor, use only source event records: split factor 2.0 "
    "times cash factor (1 + 1.00 / 100.00) = 2.02. This 2.02 value is an "
    "adjustment factor, not a standalone investment return. It offsets the "
    "mechanical raw price drop from the split when total return is calculated."
)

DIV_SPLIT_IMPLIED_EXAMPLE = (
    DIV_SPLIT_EXAMPLE_INPUTS
    + " For the implied factor, use the adjusted/raw return relationship rather "
    "than reading event records directly. Under the backward-adjusted close "
    "convention, the prior close is adjusted by (1 / 2.0) * ((100.00 - 1.00) / "
    "100.00) = 0.495, making prior adjusted close 49.50. The adjusted return "
    "factor is 51.00 / 49.50 = 1.030303. The implied dividend/split factor is "
    "then 1.030303 / 0.51 = 2.020202. This is slightly higher than the 2.02 "
    "explicit factor because the cash dividend enters the backward-adjusted close "
    "denominator as prior_close - cash_amount."
)

DIV_SPLIT_CASH_DENOMINATOR_NOTE = (
    "\n\nCash-dividend denominator note: for a cash-dividend-only adjustment, "
    "explicit and implied values may differ slightly because the explicit cash "
    "factor uses 1 + cash_amount / prior_close, while the backward-adjusted close "
    "chain implies prior_close / (prior_close - cash_amount). That convention "
    "difference is not necessarily a data defect."
)


DATA_DICTIONARY = {
    "analysis_confidence": (
        "Deterministic confidence label derived from analysis_reason_code. "
        "This is not the same as research_confidence. It reflects the pipeline's "
        "confidence in the current analysis classification.\n\nPossible values, "
        "ordered by confidence:\n"
        "- Blank = no analysis reason code is assigned.\n"
        "- LOW = lower deterministic confidence, usually unresolved or less isolated "
        "diagnostics.\n"
        "- MEDIUM = medium deterministic confidence, including Massive-focused "
        "diagnostics such as missing event adjustment, adjustment-factor continuity, "
        "partial/extra event capture, high-score anomaly, and methodology/source "
        "diagnostics such as event denominator or event source mismatch.\n"
        "- HIGH = high deterministic confidence, such as close reversal, yFinance "
        "dividend/split factor mismatch, or yFinance event-date mismatch."
    ),
    "analysis_reason_code": (
        "Deterministic diagnostic classification assigned by the audit pipeline. It "
        "explains the main reason the row needs review. When real-world research is "
        "available, the code may be adjusted so the diagnostic agrees with "
        "likely_correct_source.\n\nPossible values, alphabetically:\n"
        "- CLOSE_REVERSAL = Massive/yFinance return difference reverses on an "
        "adjacent trading day, suggesting a close-source or timing artifact rather "
        "than a corporate action.\n"
        "  Example: On Tuesday, Massive return is -2.00% and yFinance return is "
        "-3.00%, so diff_return is +1.00%. On Wednesday, Massive return is +1.00% "
        "and yFinance return is +2.00%, so diff_return is -1.00%. The equal and "
        "opposite differences suggest a close timing issue, not a real event.\n"
        "- EVENT_DENOMINATOR_MISMATCH = Massive and yFinance record the same "
        "dividend/split marker, but the event-return percentage differs because "
        "the same cash amount is divided by different prior-close values.\n"
        "  Example: Massive reports cd:0.52, yFinance reports ca:0.52, and both "
        "sources show the same raw price return, but Massive's prior close is "
        "$28.00 while yFinance's prior close is $21.00. The same $0.52 cash "
        "dividend therefore produces different "
        "event-return percentages.\n"
        "- EVENT_SOURCE_MISMATCH = Massive and yFinance report different "
        "dividend/split event markers for the date, especially when both sources "
        "have event markers but use different event formatting, grouping, amounts, "
        "or source-event representation. When both sources have same-day event "
        "markers and the residual return difference is small, this is usually an "
        "event-representation issue; it can also be used as a broader fallback when "
        "event markers differ and pre-research evidence does not determine which "
        "source is economically correct.\n"
        "  Example: On the same ticker/date, Massive reports cd:0.25 while yFinance "
        "reports ca:0.50. With a $50.00 prior close, that is about +0.50% versus "
        "+1.00% expected dividend impact.\n"
        "- HIGH_SCORE_ANOMALY = Massive return has a high heuristic anomaly score "
        "even when the Massive/yFinance return difference is not material.\n"
        "  Example: Massive and yFinance both show +15.00% for the day, so "
        "diff_return is 0.00%. The ticker's recent daily moves are usually near "
        "1.00%, so the +15.00% move still needs review.\n"
        "- MS_ADJ_FACTOR_CONTINUITY = Rare fallback diagnostic for an unexplained "
        "Massive adjustment-chain discontinuity. This situation is expected to be "
        "uncommon and may not appear in ordinary audit runs; it exists as a guardrail "
        "for cases where Massive's cumulative adjustment-factor change does not align "
        "with the adjusted-return difference and the discrepancy is not better "
        "explained by a same-day event-source, event-denominator, missing-event, "
        "partial-event, or extra-event diagnosis.\n"
        "  Example: Both sources show close rising from $100.00 to $101.00, a "
        "+1.00% price return. Both also show a $1.00 dividend, so the adjusted "
        "return should be about +2.00%. Massive's adjusted-return chain shows "
        "+1.20%, and no more specific event or denominator issue explains the "
        "difference.\n"
        "- MS_EVENT_DATE_MISMATCH = Massive appears to have an event on the wrong "
        "trading date.\n"
        "  Example: A $0.50 dividend has confirmed ex-date Tuesday. Massive shows "
        "cd:0.50 on Monday and no event on Tuesday, while yFinance shows ca:0.50 "
        "on Tuesday.\n"
        "- MS_EXTRA_EVENT = Massive records an extra corporate-action event or "
        "extra event amount not supported by the comparison source and "
        "adjusted-return difference.\n"
        "  Example: Research confirms one $0.65 dividend. Massive records "
        "cd:0.65 cd:0.65, yFinance records ca:0.65, and diff_return reconciles "
        "to Massive's extra $0.65 event-return impact.\n"
        "- MS_MISSING_EVENT = Massive appears to be missing a corporate-action event "
        "or related adjustment needed to explain the return difference.\n"
        "  Example: yFinance records sp:1.05 for a confirmed spin-off, implying "
        "about +5.00% adjusted-return impact. Massive has no event marker and "
        "shows a return about 5.00 percentage points lower.\n"
        "- MS_PARTIAL_EVENT = Massive records a same-day corporate-action event, "
        "but the recorded event amount appears incomplete relative to the "
        "comparison source and the adjusted-return difference.\n"
        "  Example: Research confirms a $0.15 dividend made up of a $0.075 base "
        "dividend plus a $0.075 variable dividend. Massive records cd:0.075, "
        "yFinance records ca:0.15, and diff_return reconciles to the missing "
        "$0.075 event-return impact.\n"
        "- MS_RETURN_METHOD_UNRESOLVED = Rare final fallback diagnostic for a "
        "Massive/yFinance return difference that remains unexplained after the "
        "specific event, denominator, date, close-reversal, adjustment-continuity, "
        "and dividend/split reconciliation checks have been applied. This situation "
        "is unexpected in ordinary audit runs; it exists as a guardrail for cases "
        "where the input fields do not isolate a single deterministic cause.\n"
        "  Example: Massive return is +2.00% and yFinance return is +3.20%, so "
        "diff_return is -1.20%. There is no event marker mismatch, denominator "
        "mismatch, factor-continuity mismatch, dividend/split reconciliation break, "
        "or adjacent-day reversal to explain it.\n"
        "- YF_DIV_SPLIT_RETURN_MISMATCH = yFinance implied dividend/split factor "
        "does not reconcile to yFinance explicit dividend/split factor.\n"
        "  Example: yFinance records a $0.40 dividend and prior close is $40.00, "
        "so the explicit dividend impact is about +1.00%. yFinance's adjusted close "
        "implies a +2.50% dividend/split impact instead.\n"
        "- YF_EVENT_DATE_MISMATCH = post-research override indicating yFinance "
        "appears to have the event on the wrong trading date.\n"
        "  Example: Research confirms a $0.60 dividend belongs on Thursday. Massive "
        "shows cd:0.60 on Thursday, but yFinance shows ca:0.60 on Wednesday.\n"
        "- YF_MISSING_EVENT = post-research override indicating yFinance appears "
        "to be missing a corporate-action event or related adjustment.\n"
        "  Example: Research confirms a $0.75 dividend with prior close $75.00, so "
        "the expected impact is about +1.00%. Massive shows cd:0.75, but yFinance "
        "has no dividend marker or adjusted-return impact."
    ),
    "research_confidence": (
        "External research confidence label for the likely_correct_source and event "
        "conclusion. This is separate from analysis_confidence: research_confidence "
        "comes from the analyst/research evidence scoring rules, while "
        "analysis_confidence comes from the deterministic audit classification.\n\n"
        "Possible values, ordered by confidence:\n"
        "- Blank = no external real-world event research was joined.\n"
        "- LOW = weak, ambiguous, or absence-of-event support.\n"
        "- MEDIUM = reasonable but incomplete or partly inferential support.\n"
        "- HIGH = strong source support and clear return/event reconciliation."
    ),
    "date": (
        "Trading date being reconciled. This is the date of the Massive row and the "
        "date used to join yFinance prices, dividend/split event markers, return "
        "calculations, diagnostics, and optional real-world event research."
    ),
    "diff_return": (
        "Material adjusted-return difference between Massive and yFinance, using the "
        "sign convention ms_return - yf_return. Positive means Massive's adjusted "
        "return is higher than yFinance's; negative means Massive's adjusted return "
        "is lower. Differences below the configured 1e-4 tolerance are set to null."
    ),
    "event_bucket": (
        "External research classification for the identified real-world explanation. "
        "\n\nPossible values, alphabetically:\n"
        "- DISTRIBUTION = cash dividend, special dividend, return of capital, or "
        "similar cash/non-split distribution.\n"
        "- MERGER = merger, acquisition, exchange offer, or transaction consideration "
        "affecting the price/return series.\n"
        "- NEWS = material company, industry, macro, earnings, guidance, regulatory, "
        "litigation, or analyst/news event rather than a mechanical corporate "
        "action.\n"
        "- PRICING_METHOD = a non-corporate-action difference caused by different "
        "vendor price, adjustment, or timing methods, after corporate actions and "
        "material news have been investigated.\n"
        "- RIGHTS = rights offering, warrant distribution, subscription right, or "
        "similar shareholder right.\n"
        "- SPINOFF = spin-off, split-off, or separation distribution.\n"
        "- SPLIT = stock split, reverse split, or stock dividend treated as a split "
        "factor.\n"
        "- UNKNOWN = no sufficiently supported real-world explanation was "
        "identified.\n\nThe analyst instructions require event precedence in this "
        "order: SPLIT, SPINOFF, DISTRIBUTION, MERGER, RIGHTS, NEWS, PRICING_METHOD, "
        "UNKNOWN."
    ),
    "event_detected": (
        "External research field indicating whether a real-world event was identified "
        "for the ticker/date.\n\nPossible values, alphabetically:\n"
        "- Blank = no external real-world event research was joined.\n"
        "- NO = research did not identify a relevant real-world event.\n"
        "- UNCERTAIN = research did not support a firm yes/no conclusion.\n"
        "- YES = research identified a relevant real-world event."
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
        "event magnitude reconciles to signed diff_return within tolerance."
    ),
    "has_div_split_mismatch": (
        "Boolean flag indicating whether Massive and yFinance report different "
        "dividend/split marker strings for the ticker/date. The comparison preserves "
        "source marker text in the output, but normalizes equivalent cash-action "
        "prefixes only while comparing: Massive cd and sc markers compare as generic "
        "ca cash-action markers against yFinance.\n\nPossible values, alphabetically:\n"
        "- false = Massive and yFinance dividend/split marker strings match after "
        "normalization.\n"
        "- true = Massive and yFinance dividend/split marker strings differ after "
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
        "- 0 = no independent Massive-side anomaly signals were triggered. The row "
        "may still require review because of a vendor return difference, event-marker "
        "mismatch, or other reconciliation issue.\n"
        "- 1-3 = low anomaly signal. One or more mild conditions may be present, "
        "but the row is usually reviewed only if another diagnostic also requires "
        "attention.\n"
        "- 4-6 = moderate anomaly signal. The Massive return may be unusually large, "
        "inconsistent with nearby price behavior, or close to a corporate-action-style "
        "return pattern. These rows are worth review, especially when paired with "
        "event or adjustment differences.\n"
        "- 7-10 = high anomaly signal. Multiple independent checks suggest the "
        "Massive return is unusual relative to price movement, adjustment mechanics, "
        "nearby returns, or corporate-action expectations.\n"
        "- 11+ = very high anomaly signal. The row has several strong anomaly "
        "indicators and should be reviewed even if Massive and yFinance returns "
        "are identical, because both vendors may be reflecting a real market event "
        "or both may share a questionable treatment.\n\nImportant notes:\n"
        "- The score is additive: multiple smaller signals can produce a high score.\n"
        "- The score is pre-research only. Real-world research and input row math "
        "determine the final classification.\n"
        "- A high score does not imply Massive is wrong. It means the row deserves "
        "investigation.\n"
        "- A score of 0 does not imply the row is correct. It may still be flagged "
        "by return differences, event mismatches, adjustment-factor issues, or "
        "close-reversal diagnostics."
    ),
    "likely_correct_source": (
        "External research conclusion identifying which source appears economically "
        "correct after considering both real-world evidence and input row math. The "
        "analyst instructions require this to follow from ms_return, yf_return, "
        "diff_return, event markers, event-return fields, adjustment factors, and "
        "external evidence.\n\nPossible values, alphabetically:\n"
        "- Blank = no external real-world event research was joined.\n"
        "- BOTH = Massive and yFinance are economically equivalent or both appear "
        "reasonable for the row.\n"
        "- MASSIVE = Massive appears economically correct.\n"
        "- NEITHER = neither Massive nor yFinance appears economically correct.\n"
        "- UNCERTAIN = research cannot determine the likely correct source.\n"
        "- YFINANCE = yFinance appears economically correct."
    ),
    "massive_fix_action": (
        "Suggested Massive review or remediation action, generated from "
        "analysis_reason_code and optional real-world research. When research "
        "concludes likely_correct_source is MASSIVE or BOTH, this is cleared because "
        "no Massive remediation is recommended. Otherwise examples include adding or "
        "correcting missing corporate actions, reviewing adjustment-factor history or "
        "event denominators, rebuilding adjusted close and return chains, or manually "
        "reviewing close/adjusted-close/corporate-action inputs."
    ),
    "massive_fix_priority": (
        "Priority for the suggested Massive remediation. This is research-aware: it "
        "is blank when real-world research concludes likely_correct_source is MASSIVE "
        "or BOTH.\n\nPossible values, ordered by priority:\n"
        "- Blank = no Massive remediation priority is assigned.\n"
        "- LOW = low-priority Massive review, usually lower-score heuristic anomaly.\n"
        "- MEDIUM = more investigative Massive review, such as an unresolved "
        "adjusted-return calculation issue or higher-score anomaly.\n"
        "- HIGH = direct Massive fix candidate, such as missing event adjustment, "
        "event-date mismatch, adjustment-factor continuity, partial event capture, "
        "or extra event capture."
    ),
    "massive_needs_fix": (
        "Boolean flag indicating whether Massive may require correction after "
        "deterministic diagnostics and optional real-world research. If research "
        "concludes likely_correct_source is MASSIVE or BOTH, this is false. If "
        "research concludes likely_correct_source is YFINANCE or NEITHER, this is "
        "true. Without research, it follows Massive-focused reason codes such as "
        "missing event adjustment, event-date mismatch, adjustment-factor continuity "
        "issue, partial event capture, extra event capture, unresolved Massive "
        "adjusted-return calculation issue, or high-score anomaly. Generic "
        "EVENT_SOURCE_MISMATCH "
        "rows require review but do not by themselves imply Massive needs a "
        "fix.\n\nPossible values, alphabetically:\n"
        "- false = Massive does not currently appear to need correction.\n"
        "- true = Massive may require correction or manual remediation review."
    ),
    "massive_problem_and_fix": (
        "Summary-report-only display column that vertically combines "
        "massive_problem_summary, massive_why_incorrect, and massive_fix_action with blank lines "
        "between the three sections."
    ),
    "massive_problem_summary": (
        "Human-readable summary of the audit issue or suspected Massive-side problem, "
        "generated from analysis_reason_code and optional real-world research. Blank "
        "when the pipeline does not identify a review issue or when research concludes "
        "likely_correct_source is MASSIVE or BOTH."
    ),
    "massive_why_incorrect": (
        "Human-readable explanation of why Massive may be incorrect or why the row "
        "needs Massive review/context, generated from analysis_reason_code and "
        "optional real-world research. Blank when the pipeline does not identify a "
        "review issue or when research concludes likely_correct_source is MASSIVE or "
        "BOTH."
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
        "events after the row date so historical closes can be restated on a current "
        "adjusted basis."
    ),
    "ms_close": (
        "Massive unadjusted close price for the ticker/date. This comes from Massive "
        "unadjusted OHLCV data and is used as the raw close input for Massive "
        "adjusted-close and raw price-return calculations."
    ),
    "ms_div_split": (
        "Compact Massive corporate-action marker string for the ticker/date. Split "
        "events are represented as sp:<split_factor>, where split_factor is split_to "
        "/ split_from. Regular cash dividends are represented as cd:<cash_amount>. "
        "Special cash dividends are represented as sc:<cash_amount>. Generic cash "
        "distributions with no Massive regular/special distinction are represented "
        "as ca:<cash_amount>. Multiple same-day events are space-separated."
    ),
    "ms_return": (
        "Final Massive adjusted return for the ticker/date, calculated from the "
        "percentage change in the pipeline's Massive adjusted close series."
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
        "- false = row does not meet review criteria.\n"
        "- true = row meets review criteria."
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
        "research.\n\nPossible values, ordered by priority:\n"
        "- Blank = no review is required.\n"
        "- LOW = heuristic_anomaly_score is at least MIN_SCORE_TO_REVIEW but "
        "higher-priority conditions do not apply.\n"
        "- MEDIUM = heuristic_anomaly_score is at least 8 and the row may be "
        "actionable.\n"
        "- HIGH = diff_return is non-null."
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
        "ca:<cash_amount> because yFinance does not expose the same Massive regular "
        "cash dividend cd versus special cash dividend sc distinction. Multiple "
        "same-day events are space-separated."
    ),
    "yf_return": (
        "Final yFinance adjusted return for the ticker/date, calculated from the "
        "percentage change in yFinance adjusted close."
    ),
    "yf_return_price": (
        "yFinance raw price return from unadjusted closes, calculated as the "
        "percentage change from the prior yFinance unadjusted close to the current "
        "yFinance unadjusted close for the same ticker."
    ),
}

# For columns that are fully used and implemented, but too confusing or irreleveant to present to
# the user.  This way, we can keep their definitions for possible future exposure without
# cluttering the public-facing data dictionary.
DATA_DICTIONARY_FUTURE_COLUMNS: dict[str, str] = {
    "massive_event_return_explains_yf_gap": (
        "Internal real-world-research support flag. True when research identifies "
        "Massive as the likely correct source, Massive has a same-day "
        "dividend/split marker, yFinance has no same-day dividend/split marker, "
        "and Massive's explicit dividend/split factor impact reconciles to "
        "diff_return within the configured real-world event return tolerance. This "
        "field is used to support post-research reason-code ownership overrides; "
        "it is not intended as a user-facing report column."
    ),
    "diff_ms_div_split_factor": (
        "Difference between Massive implied dividend/split factor and Massive "
        "explicit dividend/split factor. It is calculated as "
        "ms_div_split_factor_implied - "
        "ms_div_split_factor_explicit, but small differences below the configured 1e-6 "
        "tolerance are set to null. This field compares two related but not identical "
        "views of the same Massive source records: explicit factor math from the "
        "event records themselves, and factor math implied by the reconstructed "
        "backward-adjusted close chain. For ordinary cash dividends, a small positive "
        "difference can be normal because the explicit cash factor uses "
        "1 + cash_amount / prior_close, while the backward-adjusted close chain "
        "implies prior_close / (prior_close - cash_amount). Larger non-null values "
        "are a guardrail for cases where Massive's adjusted-return chain may not "
        "reconcile cleanly to Massive's explicit event records." + DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "diff_yf_div_split_factor": (
        "Difference between yFinance implied dividend/split factor and yFinance "
        "explicit dividend/split factor. It is calculated as "
        "yf_div_split_factor_implied - "
        "yf_div_split_factor_explicit, but small differences below the configured 1e-6 "
        "tolerance are set to null. This field compares two related but not identical "
        "views of the same yFinance source records: explicit factor math from the "
        "event records themselves, and factor math implied by yFinance's "
        "adjusted-close chain. For ordinary cash dividends, a small positive "
        "difference can be normal because the explicit cash factor uses "
        "1 + cash_amount / prior_yfinance_close, while the backward-adjusted close "
        "chain implies prior_yfinance_close / (prior_yfinance_close - cash_amount). "
        "Larger non-null values are a guardrail for cases where yFinance's "
        "adjusted-return chain may not reconcile cleanly to yFinance's explicit "
        "event records." + DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "ms_div_split_factor_explicit": (
        "Massive dividend/split adjustment factor calculated directly from Massive's "
        "explicit dividend and split records on the ticker/date, independent of "
        "Massive's adjusted-close chain. For cash dividends, same-day cash amounts "
        "are summed first and the factor is 1 + total_cash_amount / prior_close. "
        "For splits, the factor is split_to / split_from. If cash and split events "
        "occur on the same date, their factors are multiplied. This is the "
        "source-record view of the adjustment; it is not a claim that Massive is "
        "economically correct." + DIV_SPLIT_EXPLICIT_EXAMPLE + DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "ms_div_split_factor_implied": (
        "Massive dividend/split adjustment factor inferred from the relationship "
        "between the pipeline's reconstructed Massive adjusted return and Massive "
        "raw price return: (1 + ms_return) / (1 + ms_return_price). This is the "
        "adjusted-close-chain view of the adjustment, not a direct read from "
        "Massive event records. It is expected to be close to "
        "ms_div_split_factor_explicit, but it may not be identical. In particular, "
        "cash dividends can differ slightly because the explicit field uses "
        "1 + cash_amount / prior_close, while the backward-adjusted close chain "
        "implies prior_close / (prior_close - cash_amount)."
        + DIV_SPLIT_IMPLIED_EXAMPLE
        + DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "yf_div_split_factor_explicit": (
        "yFinance dividend/split adjustment factor calculated directly from "
        "yFinance's explicit dividend and split records on the ticker/date, "
        "independent of yFinance's adjusted-close chain. For cash dividends, the "
        "factor is 1 + cash_amount / prior yFinance close. For splits, the factor "
        "is yFinance split_ratio. If multiple event records occur on the same date, "
        "their factors are multiplied. This is the source-record view of the "
        "adjustment; it is not a claim that yFinance is economically correct."
        + DIV_SPLIT_EXPLICIT_EXAMPLE
        + DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "yf_div_split_factor_implied": (
        "yFinance dividend/split adjustment factor inferred from the relationship "
        "between yFinance adjusted return and yFinance raw price return: "
        "(1 + yf_return) / (1 + yf_return_price). This is the adjusted-close-chain "
        "view of the adjustment, not a direct read from yFinance event records. It "
        "is expected to be close to yf_div_split_factor_explicit, but it may not be "
        "identical. In particular, cash dividends can differ slightly because the "
        "explicit field uses 1 + cash_amount / prior yFinance close, while the "
        "backward-adjusted close chain implies prior_yfinance_close / "
        "(prior_yfinance_close - cash_amount)."
        + DIV_SPLIT_IMPLIED_EXAMPLE
        + DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
}

CATEGORY_REPORT_COLUMNS: list[str] = [
    # Key values
    "ticker",
    "date",
    # Priority and Impact
    "massive_fix_priority",
    "likely_correct_source",  # optional
    "research_confidence",  # optional
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
