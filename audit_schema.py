"""Shared schema constants for the audit module.

This module intentionally contains only constants and column lists so the
main audit module is easier to scan.
"""

# Errors to ignore.
# pylint: disable=too-many-lines

# Standard library imports.
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class _AuditColumn:
    """Metadata for one audit output column.

    The registry keeps stable column facts in one place: the internal name,
    the user-facing description, optional display-name overrides, and group
    membership used by report builders. Calculation logic should stay in the
    audit pipeline; this class is intentionally just schema/display metadata.
    """

    # Internal field name used in Polars frames, CSV files, and joins.
    name: str

    # Data-dictionary text used for report tooltips and the generated PDF.
    description: str = ""

    # Optional explicit display label. Most columns use _default_display_name().
    display_name: str | None = None

    # Behavioral/display groups such as "narrative", "url", or "summary_omitted".
    groups: frozenset[str] = frozenset()

    def to_string(self) -> str:
        """Return the internal column name for compatibility with plain strings."""
        return self.name

    def __str__(self) -> str:
        """Return the internal column name in string contexts."""
        return self.to_string()

    def display_label(self) -> str:
        """Return the user-facing display name for this column."""
        if self.display_name is not None:
            return self.display_name
        return _default_display_name(self.name)


@dataclass(frozen=True)
class ReasonCode:
    """Metadata for one return-audit analysis reason code."""

    code: str
    confidence: str
    groups: frozenset[str] = frozenset()
    source1_problem_summary: str = ""
    source1_why_incorrect: str = ""
    source1_fix_action: str = ""


# Constants.
# Adjustment-factor changes can differ slightly when data sources encode the same
# cash distribution or split mechanics differently. Five basis points is tight
# enough to catch material chain breaks without routing harmless rounding or
# event-format differences into SOURCE1_ADJ_FACTOR_CONTINUITY.
ADJ_FACTOR_CHANGE_TOLERANCE = 0.0005
CASH_FACTOR_CONVENTION_TOLERANCE = 0.0001
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

REAL_WORLD_EVENT_COLUMNS: list[str] = [
    "event_detected",
    "event_bucket",
    "expected_return_impact",
    "likely_correct_source",
    "research_confidence",
    "evidence_summary",
    "real_world_event",
    "primary_url",
    "secondary_url",
]

FORENSIC_ANALYST_OUTPUT_COLUMNS: list[str] = [
    "ticker",
    "date",
    "event_detected",
    "event_bucket",
    "expected_return_impact",
    "likely_correct_source",
    "research_confidence",
    "primary_url",
    "secondary_url",
    "evidence_summary",
    "real_world_event",
]

REAL_WORLD_EVENT_KEY_COLUMNS: list[str] = [
    "ticker",
    "date",
]

REQUIRED_REAL_WORLD_EVENT_COLUMNS: set[str] = set(
    REAL_WORLD_EVENT_KEY_COLUMNS + REAL_WORLD_EVENT_COLUMNS
)

RETURN_AUDIT_PUBLIC_COLUMNS: list[str] = [
    "ticker",
    "date",
    "source1_close",
    "source2_close",
    "source1_adj_factor",
    "source2_adj_factor",
    "source1_adj_close",
    "source2_adj_close",
    "source1_div_split",
    "source2_div_split",
    "has_div_split_mismatch",
    "source1_return_price",
    "source2_return_price",
    "source1_div_split_factor_implied",
    "source1_div_split_factor_explicit",
    "diff_source1_div_split_factor",
    "source2_div_split_factor_implied",
    "source2_div_split_factor_explicit",
    "diff_source2_div_split_factor",
    "source1_return",
    "source2_return",
    "diff_return",
    "needs_review",
    "review_priority",
    "heuristic_anomaly_score",
    "analysis_reason_code",
    "analysis_confidence",
    "source1_needs_fix",
    "source1_problem_summary",
    "source1_why_incorrect",
    "source1_fix_action",
    "source1_fix_priority",
]

RETURN_AUDIT_DIAGNOSTIC_COLUMNS: list[str] = [
    "total_return_diff",
    "prior_total_return_diff",
    "next_total_return_diff",
    "abs_return",
    "prior_return",
    "next_return",
    "raw_close_ratio",
    "rolling_median_return",
    "rolling_mad_return",
    "robust_z",
    "prior_source1_adj_factor",
    "prior_source2_adj_factor",
    "source1_adj_factor_change",
    "source2_adj_factor_change",
    "adj_factor_change_diff",
    "prior_source1_div_split",
    "next_source1_div_split",
    "prior_source2_div_split",
    "next_source2_div_split",
    "has_source1_event",
    "has_source2_event",
    "is_source1_div_split_factor_mismatch",
    "is_source2_div_split_factor_mismatch",
    "is_adj_factor_mismatch",
    "is_event_denominator_mismatch",
    "is_source1_partial_event",
    "is_source1_extra_event",
    "source_price_event_return",
    "is_event_date_mismatch",
    "is_source1_missing_event_adjustment",
    "is_next_close_reversal",
    "is_prior_close_reversal",
    "is_close_reversal",
]

RETURN_AUDIT_ALL_COLUMNS: list[str] = (
    RETURN_AUDIT_PUBLIC_COLUMNS[:24]
    + RETURN_AUDIT_DIAGNOSTIC_COLUMNS[:3]
    + RETURN_AUDIT_PUBLIC_COLUMNS[24:25]
    + RETURN_AUDIT_DIAGNOSTIC_COLUMNS[3:10]
    + RETURN_AUDIT_PUBLIC_COLUMNS[25:]
    + RETURN_AUDIT_DIAGNOSTIC_COLUMNS[10:]
)

_DIV_SPLIT_EXAMPLE_INPUTS = (
    "\n\nWorked example: assume prior unadjusted close is 100.00, current "
    "unadjusted close is 51.00, the source records a 2-for-1 split, and the "
    "source records a 1.00 cash dividend on the same date. The raw price factor "
    "is 51.00 / 100.00 = 0.51, which is a -49.0000% raw price return."
)

_DIV_SPLIT_EXPLICIT_EXAMPLE = (
    _DIV_SPLIT_EXAMPLE_INPUTS
    + " For the explicit factor, use only source event records: split factor 2.0 "
    "times cash factor (1 + 1.00 / 100.00) = 2.02. This 2.02 value is an "
    "adjustment factor, not a standalone investment return. It offsets the "
    "mechanical raw price drop from the split when total return is calculated."
)

_DIV_SPLIT_IMPLIED_EXAMPLE = (
    _DIV_SPLIT_EXAMPLE_INPUTS
    + " For the implied factor, use the adjusted/raw return relationship rather "
    "than reading event records directly. Under the backward-adjusted close "
    "convention, the prior close is adjusted by (1 / 2.0) * ((100.00 - 1.00) / "
    "100.00) = 0.495, making prior adjusted close 49.50. The adjusted return "
    "factor is 51.00 / 49.50 = 1.030303. The implied dividend/split factor is "
    "then 1.030303 / 0.51 = 2.020202. This is slightly higher than the 2.02 "
    "explicit factor because the cash dividend enters the backward-adjusted close "
    "denominator as prior_close - cash_amount."
)

_DIV_SPLIT_CASH_DENOMINATOR_NOTE = (
    "\n\nCash-dividend denominator note: for a cash-dividend-only adjustment, "
    "explicit and implied values may differ slightly because the explicit cash "
    "factor uses 1 + cash_amount / prior_close, while the backward-adjusted close "
    "chain implies prior_close / (prior_close - cash_amount). That convention "
    "difference is not necessarily a data defect."
)


REASON_CODES: dict[str, ReasonCode] = {
    "CLOSE_REVERSAL": ReasonCode(
        code="CLOSE_REVERSAL",
        confidence="HIGH",
        source1_problem_summary=(
            "source1 close appears incorrect after an adjacent-day close reversal."
        ),
        source1_why_incorrect=(
            "source1 appears incorrect because independent evidence supports the "
            "source2 close, and the return difference reverses across "
            "adjacent trading days."
        ),
        source1_fix_action=(
            "Review and correct the source1 close for the affected date, then rebuild "
            "the adjusted close and adjusted return chain."
        ),
    ),
    "SOURCE1_MISSING_EVENT": ReasonCode(
        code="SOURCE1_MISSING_EVENT",
        confidence="MEDIUM",
        groups=frozenset({"source1_fix_pre_research", "source1_fix_post_research"}),
        source1_problem_summary=(
            "source1 is missing the event/adjustment needed to explain the return " "difference."
        ),
        source1_why_incorrect=(
            "source1 appears incorrect because source2 and real-world "
            "event evidence support an event/adjustment that source1 did not capture."
        ),
        source1_fix_action=(
            "Add or correct the missing source1 dividend/split event, apply the "
            "appropriate adjustment factor, and rebuild the adjusted close and "
            "adjusted return chain."
        ),
    ),
    "SOURCE1_EVENT_DATE_MISMATCH": ReasonCode(
        code="SOURCE1_EVENT_DATE_MISMATCH",
        confidence="MEDIUM",
        groups=frozenset({"source1_fix_pre_research", "source1_fix_post_research"}),
        source1_problem_summary=(
            "source1 appears to have the correct event amount on the wrong trading " "date."
        ),
        source1_why_incorrect=(
            "source1 appears incorrect because the real-world event date and "
            "return math indicate the event should be recognized on a different "
            "trading date."
        ),
        source1_fix_action=(
            "Move the source1 dividend/split event to the externally confirmed "
            "event date, remove the misstated adjacent-date event if present, and "
            "rebuild the adjusted close and adjusted return chain."
        ),
    ),
    "SOURCE1_PARTIAL_EVENT": ReasonCode(
        code="SOURCE1_PARTIAL_EVENT",
        confidence="MEDIUM",
        groups=frozenset(
            {
                "source1_fix_post_research",
                "source2_missing_override_candidate",
            }
        ),
        source1_problem_summary=(
            "source1 records a corporate-action event, but the event amount appears " "incomplete."
        ),
        source1_why_incorrect=(
            "source1 appears incorrect because it captured only part of the "
            "same-day corporate-action event, and the missing event-return piece "
            "explains the source1/source2 return difference."
        ),
        source1_fix_action=(
            "Correct the source1 event amount to include the full corporate-action "
            "distribution, then rebuild the adjusted close and adjusted return chain."
        ),
    ),
    "SOURCE1_EXTRA_EVENT": ReasonCode(
        code="SOURCE1_EXTRA_EVENT",
        confidence="MEDIUM",
        groups=frozenset(
            {
                "source1_fix_post_research",
                "source2_missing_override_candidate",
            }
        ),
        source1_problem_summary=(
            "source1 records an extra corporate-action event or excessive event amount."
        ),
        source1_why_incorrect=(
            "source1 appears incorrect because it captured an extra same-day "
            "corporate-action event or event amount, and the excess event-return "
            "piece explains the source1/source2 return difference."
        ),
        source1_fix_action=(
            "Remove the unsupported source1 event amount or duplicate event, then "
            "rebuild the adjusted close and adjusted return chain."
        ),
    ),
    "SOURCE1_ADJ_FACTOR_CONTINUITY": ReasonCode(
        code="SOURCE1_ADJ_FACTOR_CONTINUITY",
        confidence="MEDIUM",
        groups=frozenset(
            {
                "source1_fix_pre_research",
                "source1_fix_post_research",
                "source2_missing_override_candidate",
                "source1_missing_override_candidate",
            }
        ),
        source1_problem_summary=(
            "source1 adjustment-factor continuity does not align with the return " "difference."
        ),
        source1_why_incorrect=(
            "source1 appears incorrect because the adjusted-return difference is "
            "associated with a change in adjustment-factor continuity rather than "
            "only a normal price move."
        ),
        source1_fix_action=(
            "Review source1 corporate-action adjustment factors for this ticker/date, "
            "correct the factor history if needed, and rebuild the adjusted close and "
            "adjusted return chain."
        ),
    ),
    "EVENT_DENOMINATOR_MISMATCH": ReasonCode(
        code="EVENT_DENOMINATOR_MISMATCH",
        confidence="MEDIUM",
        source1_problem_summary=(
            "source1 and source2 record the same dividend/split event, but calculate "
            "different event-return percentages because they use different prior-close "
            "denominators."
        ),
        source1_why_incorrect=(
            "The data sources appear to divide the same cash amount by different prior-close "
            "values, so the row needs methodology review rather than a presumptive "
            "source1 correction."
        ),
        source1_fix_action=(
            "Review the data sources' prior-close denominators for this event; do not treat "
            "the row as a source1 event defect unless external evidence shows source1 "
            "used the wrong prior close."
        ),
    ),
    "EVENT_SOURCE_MISMATCH": ReasonCode(
        code="EVENT_SOURCE_MISMATCH",
        confidence="MEDIUM",
        groups=frozenset(
            {
                "source2_missing_override_candidate",
                "source1_missing_override_candidate",
            }
        ),
        source1_problem_summary=(
            "source1 and source2 report different dividend/split event data for the " "date."
        ),
        source1_why_incorrect=(
            "source1 and source2 disagree on dividend/split event data, but the "
            "pre-research fields do not determine which source is economically correct."
        ),
        source1_fix_action=(
            "Compare source1 event records against a trusted corporate-action source; "
            "correct missing, extra, or misstated events and rerun the return "
            "calculation."
        ),
    ),
    "HIGH_SCORE_ANOMALY": ReasonCode(
        code="HIGH_SCORE_ANOMALY",
        confidence="MEDIUM",
        groups=frozenset({"source1_fix_pre_research", "source1_fix_post_research"}),
        source1_problem_summary=(
            "source1 return has a high heuristic anomaly score even though the "
            "source1/source2 return difference is not material."
        ),
        source1_why_incorrect=(
            "source1 may need review because its adjusted return is unusual relative "
            "to the surrounding return pattern, even without a material source "
            "difference."
        ),
        source1_fix_action=(
            "Review the source1 close, adjusted close, corporate actions, and nearby "
            "returns for this ticker/date to confirm whether the high score reflects "
            "a real event or a data issue."
        ),
    ),
    "SOURCE1_RETURN_METHOD_UNRESOLVED": ReasonCode(
        code="SOURCE1_RETURN_METHOD_UNRESOLVED",
        confidence="LOW",
        groups=frozenset(
            {
                "source1_fix_pre_research",
                "source1_fix_post_research",
                "source2_missing_override_candidate",
                "source1_missing_override_candidate",
            }
        ),
        source1_problem_summary=(
            "source1 return differs from source2, but the available event and factor "
            "fields do not isolate a single cause."
        ),
        source1_why_incorrect=(
            "source1 may be incorrect, but the input fields do not provide enough "
            "deterministic evidence to assign a more specific defect type."
        ),
        source1_fix_action=(
            "Review source1 close, adjusted close, corporate actions, and return "
            "calculation methodology for this ticker/date; manual investigation is "
            "required."
        ),
    ),
    "SOURCE2_DIV_SPLIT_RETURN_MISMATCH": ReasonCode(
        code="SOURCE2_DIV_SPLIT_RETURN_MISMATCH",
        confidence="HIGH",
        groups=frozenset({"source1_missing_override_candidate"}),
    ),
    "SOURCE2_EVENT_DATE_MISMATCH": ReasonCode(
        code="SOURCE2_EVENT_DATE_MISMATCH",
        confidence="HIGH",
        groups=frozenset({"real_world_only"}),
    ),
    "SOURCE2_MISSING_EVENT": ReasonCode(
        code="SOURCE2_MISSING_EVENT",
        confidence="MEDIUM",
        groups=frozenset({"real_world_only"}),
    ),
}


DATA_DICTIONARY = {
    "analysis_confidence": (
        "Deterministic confidence label derived from analysis_reason_code. "
        "This is not the same as research_confidence. It reflects the pipeline's "
        "confidence in the current analysis classification.\n\nPossible values, "
        "ordered by confidence:\n"
        "- Blank = no analysis reason code is assigned.\n"
        "- LOW = lower deterministic confidence, usually unresolved or less isolated "
        "diagnostics.\n"
        "- MEDIUM = medium deterministic confidence, including source1-focused "
        "diagnostics such as missing event adjustment, adjustment-factor continuity, "
        "partial/extra event capture, high-score anomaly, and methodology/source "
        "diagnostics such as event denominator or event source mismatch.\n"
        "- HIGH = high deterministic confidence, such as close reversal, source2 "
        "dividend/split factor mismatch, or source2 event-date mismatch."
    ),
    "analysis_reason_code": (
        "Deterministic diagnostic classification assigned by the audit pipeline. It "
        "explains the main reason the row needs review. When real-world research is "
        "available, the code may be adjusted so the diagnostic agrees with "
        "likely_correct_source.\n\nPossible values:\n"
        "- CLOSE_REVERSAL = source1/source2 return difference reverses on an "
        "adjacent trading day, suggesting a close-source or timing artifact rather "
        "than a corporate action.\n"
        "  Example: On Tuesday, source1 return is -2.00% and source2 return is "
        "-3.00%, so diff_return is +1.00%. On Wednesday, source1 return is +1.00% "
        "and source2 return is +2.00%, so diff_return is -1.00%. The equal and "
        "opposite differences suggest a close timing issue, not a real event.\n"
        "- EVENT_DENOMINATOR_MISMATCH = source1 and source2 record the same "
        "dividend/split marker, but the event-return percentage differs because "
        "the same cash amount is divided by different prior-close values.\n"
        "  Example: source1 reports cd:0.52, source2 reports ca:0.52, and both "
        "sources show the same raw price return, but source1's prior close is "
        "$28.00 while source2's prior close is $21.00. The same $0.52 cash "
        "dividend therefore produces different "
        "event-return percentages.\n"
        "- EVENT_SOURCE_MISMATCH = source1 and source2 report different "
        "dividend/split event markers for the date, especially when both sources "
        "have event markers but use different event formatting, grouping, amounts, "
        "or source-event representation. When both sources have same-day event "
        "markers and the residual return difference is small, this is usually an "
        "event-representation issue; it can also be used as a broader fallback when "
        "event markers differ and pre-research evidence does not determine which "
        "source is economically correct.\n"
        "  Example: On the same ticker/date, source1 reports cd:0.25 while source2 "
        "reports ca:0.50. With a $50.00 prior close, that is about +0.50% versus "
        "+1.00% expected dividend impact.\n"
        "- HIGH_SCORE_ANOMALY = source1 return has a high heuristic anomaly score "
        "even when the source1/source2 return difference is not material.\n"
        "  Example: source1 and source2 both show +15.00% for the day, so "
        "diff_return is 0.00%. The ticker's recent daily moves are usually near "
        "1.00%, so the +15.00% move still needs review.\n"
        "- SOURCE1_ADJ_FACTOR_CONTINUITY = Rare fallback diagnostic for an unexplained "
        "source1 adjustment-chain discontinuity. This situation is expected to be "
        "uncommon and may not appear in ordinary audit runs; it exists as a guardrail "
        "for cases where source1's cumulative adjustment-factor change does not align "
        "with the adjusted-return difference and the discrepancy is not better "
        "explained by a same-day event-source, event-denominator, missing-event, "
        "partial-event, or extra-event diagnosis.\n"
        "  Example: Both sources show close rising from $100.00 to $101.00, a "
        "+1.00% price return. Both also show a $1.00 dividend, so the adjusted "
        "return should be about +2.00%. source1's adjusted-return chain shows "
        "+1.20%, and no more specific event or denominator issue explains the "
        "difference.\n"
        "- SOURCE1_EVENT_DATE_MISMATCH = source1 appears to have an event on the wrong "
        "trading date.\n"
        "  Example: A $0.50 dividend has confirmed ex-date Tuesday. source1 shows "
        "cd:0.50 on Monday and no event on Tuesday, while source2 shows ca:0.50 "
        "on Tuesday.\n"
        "- SOURCE1_EXTRA_EVENT = source1 records an extra corporate-action event or "
        "extra event amount not supported by source2 or by the "
        "adjusted-return difference.\n"
        "  Example: Research confirms one $0.65 dividend. source1 records "
        "cd:0.65 cd:0.65, source2 records ca:0.65, and diff_return reconciles "
        "to source1's extra $0.65 event-return impact.\n"
        "- SOURCE1_MISSING_EVENT = source1 appears to be missing a corporate-action event "
        "or related adjustment needed to explain the return difference.\n"
        "  Example: source2 records sp:1.05 for a confirmed spin-off, implying "
        "about +5.00% adjusted-return impact. source1 has no event marker and "
        "shows a return about 5.00 percentage points lower.\n"
        "- SOURCE1_PARTIAL_EVENT = source1 records a same-day corporate-action event, "
        "but the recorded event amount appears incomplete relative to the "
        "source2 event record and the adjusted-return difference.\n"
        "  Example: Research confirms a $0.15 dividend made up of a $0.075 base "
        "dividend plus a $0.075 variable dividend. source1 records cd:0.075, "
        "source2 records ca:0.15, and diff_return reconciles to the missing "
        "$0.075 event-return impact.\n"
        "- SOURCE1_RETURN_METHOD_UNRESOLVED = Rare final fallback diagnostic for a "
        "source1/source2 return difference that remains unexplained after the "
        "specific event, denominator, date, close-reversal, adjustment-continuity, "
        "and dividend/split reconciliation checks have been applied. This situation "
        "is unexpected in ordinary audit runs; it exists as a guardrail for cases "
        "where the input fields do not isolate a single deterministic cause.\n"
        "  Example: source1 return is +2.00% and source2 return is +3.20%, so "
        "diff_return is -1.20%. There is no event marker mismatch, denominator "
        "mismatch, factor-continuity mismatch, dividend/split reconciliation break, "
        "or adjacent-day reversal to explain it.\n"
        "- SOURCE2_DIV_SPLIT_RETURN_MISMATCH = source2 implied dividend/split factor "
        "materially does not reconcile to source2 explicit dividend/split factor "
        "after allowing for ordinary cash-dividend convention differences.\n"
        "  Example: source2 records a $0.40 dividend and prior close is $40.00, "
        "so the explicit dividend impact is about +1.00%. source2's adjusted close "
        "implies a +2.50% dividend/split impact instead.\n"
        "- SOURCE2_EVENT_DATE_MISMATCH = post-research override indicating source2 "
        "appears to have the event on the wrong trading date.\n"
        "  Example: Research confirms a $0.60 dividend belongs on Thursday. source1 "
        "shows cd:0.60 on Thursday, but source2 shows ca:0.60 on Wednesday.\n"
        "- SOURCE2_MISSING_EVENT = post-research override indicating source2 appears "
        "to be missing a corporate-action event or related adjustment.\n"
        "  Example: Research confirms a $0.75 dividend with prior close $75.00, so "
        "the expected impact is about +1.00%. source1 shows cd:0.75, but source2 "
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
        "Trading date being reconciled. This is the date of the source1 row and the "
        "date used to join source2 prices, dividend/split event markers, return "
        "calculations, diagnostics, and optional real-world event research."
    ),
    "diff_return": (
        "Material adjusted-return difference between source1 and source2, using the "
        "sign convention source1_return - source2_return. Positive means source1's adjusted "
        "return is higher than source2's; negative means source1's adjusted return "
        "is lower. Differences below the configured 1e-4 tolerance are set to null."
    ),
    "event_bucket": (
        "External research classification for the identified real-world explanation. "
        "\n\nPossible values:\n"
        "- DISTRIBUTION = cash dividend, special dividend, return of capital, or "
        "similar cash/non-split distribution.\n"
        "- MERGER = merger, acquisition, exchange offer, or transaction consideration "
        "affecting the price/return series.\n"
        "- NEWS = material company, industry, macro, earnings, guidance, regulatory, "
        "litigation, or analyst/news event rather than a mechanical corporate "
        "action.\n"
        "- PRICING_METHOD = a non-corporate-action difference caused by different "
        "data source price, adjustment, or timing methods, after corporate actions and "
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
        "for the ticker/date.\n\nPossible values:\n"
        "- Blank = no external real-world event research was joined.\n"
        "- NO = research did not identify a relevant real-world event.\n"
        "- UNCERTAIN = research did not support a firm yes/no conclusion.\n"
        "- YES = research identified a relevant real-world event."
    ),
    "evidence_summary": (
        "External research narrative summary. Per the analyst instructions, it should "
        "be row-specific, name source1 and source2 explicitly, summarize sources "
        "reviewed, describe the real-world event or absence of one, explain economic "
        "plausibility, and tie the conclusion back to input row math such as source1_return, "
        "source2_return, diff_return, event markers, and expected return impact."
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
        "Boolean flag indicating whether source1 and source2 report different "
        "dividend/split marker strings for the ticker/date. The comparison preserves "
        "source marker text in the output, but normalizes equivalent cash-action "
        "prefixes only while comparing: source1 cd and sc markers compare as generic "
        "ca cash-action markers against source2.\n\nPossible values:\n"
        "- false = source1 and source2 dividend/split marker strings match after "
        "normalization.\n"
        "- true = source1 and source2 dividend/split marker strings differ after "
        "normalization."
    ),
    "heuristic_anomaly_score": (
        "Deterministic pre-research anomaly score generated from source1-side "
        "return behavior. The score is not a probability and does not identify "
        "the correct data source by itself. It is a routing signal that helps identify "
        "rows where source1's adjusted return looks unusual, even when source1 "
        "and source2 returns agree.\n\n"
        "Higher scores indicate that more independent anomaly signals were "
        "present.\n\nTypical interpretation:\n"
        "- 0 = no independent source1-side anomaly signals were triggered. The row "
        "may still require review because of a data source return difference, event-marker "
        "mismatch, or other reconciliation issue.\n"
        "- 1-3 = low anomaly signal. One or more mild conditions may be present, "
        "but the row is usually reviewed only if another diagnostic also requires "
        "attention.\n"
        "- 4-6 = moderate anomaly signal. The source1 return may be unusually large, "
        "inconsistent with nearby price behavior, or close to a corporate-action-style "
        "return pattern. These rows are worth review, especially when paired with "
        "event or adjustment differences.\n"
        "- 7-10 = high anomaly signal. Multiple independent checks suggest the "
        "source1 return is unusual relative to price movement, adjustment mechanics, "
        "nearby returns, or corporate-action expectations.\n"
        "- 11+ = very high anomaly signal. The row has several strong anomaly "
        "indicators and should be reviewed even if source1 and source2 returns "
        "are identical, because both data sources may be reflecting a real market event "
        "or both may share a questionable treatment.\n\nImportant notes:\n"
        "- The score is additive: multiple smaller signals can produce a high score.\n"
        "- The score is pre-research only. Real-world research and input row math "
        "determine the final classification.\n"
        "- A high score does not imply source1 is wrong. It means the row deserves "
        "investigation.\n"
        "- A score of 0 does not imply the row is correct. It may still be flagged "
        "by return differences, event mismatches, adjustment-factor issues, or "
        "close-reversal diagnostics."
    ),
    "likely_correct_source": (
        "External research conclusion identifying which source appears economically "
        "correct after considering both real-world evidence and input row math. The "
        "analyst instructions require this to follow from source1_return, source2_return, "
        "diff_return, event markers, event-return fields, adjustment factors, and "
        "external evidence.\n\nPossible values:\n"
        "- Blank = no external real-world event research was joined.\n"
        "- BOTH = source1 and source2 are economically equivalent or both appear "
        "reasonable for the row.\n"
        "- SOURCE1 = source1 appears economically correct.\n"
        "- NEITHER = neither source1 nor source2 appears economically correct.\n"
        "- UNCERTAIN = research cannot determine the likely correct source.\n"
        "- SOURCE2 = source2 appears economically correct."
    ),
    "source1_fix_action": (
        "Suggested source1 review or remediation action, generated from "
        "analysis_reason_code and optional real-world research. When research "
        "concludes likely_correct_source is SOURCE1 or BOTH, this is cleared because "
        "no source1 remediation is recommended. Otherwise examples include adding or "
        "correcting missing corporate actions, reviewing adjustment-factor history or "
        "event denominators, rebuilding adjusted close and return chains, or manually "
        "reviewing close/adjusted-close/corporate-action inputs."
    ),
    "source1_fix_priority": (
        "Priority for the suggested source1 remediation. This is research-aware: it "
        "is blank when real-world research concludes likely_correct_source is SOURCE1 "
        "or BOTH.\n\nPossible values, ordered by priority:\n"
        "- Blank = no source1 remediation priority is assigned.\n"
        "- LOW = low-priority source1 review, usually lower-score heuristic anomaly.\n"
        "- MEDIUM = more investigative source1 review, such as an unresolved "
        "adjusted-return calculation issue or higher-score anomaly.\n"
        "- HIGH = direct source1 fix candidate, such as missing event adjustment, "
        "event-date mismatch, adjustment-factor continuity, partial event capture, "
        "or extra event capture."
    ),
    "source1_needs_fix": (
        "Boolean flag indicating whether source1 may require correction after "
        "deterministic diagnostics and optional real-world research. If research "
        "concludes likely_correct_source is SOURCE1 or BOTH, this is false. If "
        "research concludes likely_correct_source is SOURCE2 or NEITHER, this is "
        "true. Without research, it follows source1-focused reason codes such as "
        "missing event adjustment, event-date mismatch, adjustment-factor continuity "
        "issue, partial event capture, extra event capture, unresolved source1 "
        "adjusted-return calculation issue, or high-score anomaly. Generic "
        "EVENT_SOURCE_MISMATCH "
        "rows require review but do not by themselves imply source1 needs a "
        "fix.\n\nPossible values:\n"
        "- false = source1 does not currently appear to need correction.\n"
        "- true = source1 may require correction or manual remediation review."
    ),
    "source1_problem_and_fix": (
        "Summary-report-only display column that vertically combines "
        "source1_problem_summary, source1_why_incorrect, and source1_fix_action with blank lines "
        "between the three sections."
    ),
    "source1_problem_summary": (
        "Human-readable summary of the audit issue or suspected source1-side problem, "
        "generated from analysis_reason_code and optional real-world research. Blank "
        "when the pipeline does not identify a review issue or when research concludes "
        "likely_correct_source is SOURCE1 or BOTH."
    ),
    "source1_why_incorrect": (
        "Human-readable explanation of why source1 may be incorrect or why the row "
        "needs source1 review/context, generated from analysis_reason_code and "
        "optional real-world research. Blank when the pipeline does not identify a "
        "review issue or when research concludes likely_correct_source is SOURCE1 or "
        "BOTH."
    ),
    "source1_adj_close": (
        "source1 adjusted close calculated by this audit pipeline as source1_close * "
        "source1_adj_factor. This is the source1-side adjusted close used to calculate "
        "source1_return."
    ),
    "source1_adj_factor": (
        "source1 cumulative backward-looking adjustment factor calculated by this "
        "audit pipeline from source1 split and dividend records. For splits, the "
        "factor uses split_from / split_to. For dividends, the factor uses "
        "(prior_close - cash_amount) / prior_close. The cumulative factor includes "
        "events after the row date so historical closes can be restated on a current "
        "adjusted basis."
    ),
    "source1_close": (
        "source1 unadjusted close price for the ticker/date. This comes from source1 "
        "unadjusted OHLCV data and is used as the raw close input for source1 "
        "adjusted-close and raw price-return calculations."
    ),
    "source1_div_split": (
        "Compact source1 corporate-action marker string for the ticker/date. Split "
        "events are represented as sp:<split_factor>, where split_factor is split_to "
        "/ split_from. Regular cash dividends are represented as cd:<cash_amount>. "
        "Special cash dividends are represented as sc:<cash_amount>. Generic cash "
        "distributions with no source1 regular/special distinction are represented "
        "as ca:<cash_amount>. Multiple same-day events are space-separated."
    ),
    "source1_return": (
        "Final source1 adjusted return for the ticker/date, calculated from the "
        "percentage change in the pipeline's source1 adjusted close series."
    ),
    "source1_return_price": (
        "source1 raw price return from unadjusted closes, calculated as the percentage "
        "change from the prior source1 unadjusted close to the current source1 "
        "unadjusted close for the same ticker."
    ),
    "needs_review": (
        "Boolean review flag. True when diff_return is non-null or when the source1 "
        "heuristic anomaly score is greater than or equal to MIN_SCORE_TO_REVIEW, "
        "which is currently 5.\n\nPossible values:\n"
        "- false = row does not meet review criteria.\n"
        "- true = row meets review criteria."
    ),
    "primary_url": (
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
        "Review priority bucket. This is not the same as source1_fix_priority: "
        "review_priority records why the row merited review, while "
        "source1_fix_priority records whether source1 has a recommended fix after "
        "research.\n\nPossible values, ordered by priority:\n"
        "- Blank = no review is required.\n"
        "- LOW = heuristic_anomaly_score is at least MIN_SCORE_TO_REVIEW but "
        "higher-priority conditions do not apply.\n"
        "- MEDIUM = heuristic_anomaly_score is at least 8 and the row may be "
        "actionable.\n"
        "- HIGH = diff_return is non-null."
    ),
    "secondary_url": (
        "Secondary or confirming URL supporting the real-world event research "
        "conclusion. The instructions allow credible independent sources such as "
        "Reuters, Bloomberg, Yahoo Finance, Nasdaq, MarketWatch, Macrotrends, or "
        "company press releases."
    ),
    "ticker": (
        "Normalized ticker symbol being audited. The pipeline strips surrounding "
        "whitespace and uppercases ticker symbols before joining source1 and source2 "
        "data."
    ),
    "source2_adj_close": (
        "source2 adjusted close for the ticker/date, taken from source2 OHLCV data. "
        "This is the adjusted close used to calculate source2_return."
    ),
    "source2_adj_factor": (
        "Implied source2 adjustment factor for the ticker/date, calculated as "
        "source2_adj_close / source2_close when source2_close is present and nonzero. Unlike "
        "source1_adj_factor, this is inferred from source2's supplied adjusted close "
        "rather than rebuilt directly from source2 event records."
    ),
    "source2_close": (
        "source2 unadjusted close price for the ticker/date. This comes from "
        "source2 OHLCV data and is used for source2 raw price-return calculations "
        "and to infer the source2 adjustment factor."
    ),
    "source2_div_split": (
        "Compact source2 corporate-action marker string for the ticker/date. Split "
        "events are represented as sp:<split_factor>, where split_factor is "
        "source2's split_ratio. Cash dividend/distribution events are represented as "
        "ca:<cash_amount> because source2 does not expose the same source1 regular "
        "cash dividend cd versus special cash dividend sc distinction. Multiple "
        "same-day events are space-separated."
    ),
    "source2_return": (
        "Final source2 adjusted return for the ticker/date, calculated from the "
        "percentage change in source2 adjusted close."
    ),
    "source2_return_price": (
        "source2 raw price return from unadjusted closes, calculated as the "
        "percentage change from the prior source2 unadjusted close to the current "
        "source2 unadjusted close for the same ticker."
    ),
}

# For columns that are fully used and implemented, but too confusing or irrelevant to present to
# the user.  This way, we can keep their definitions for possible future exposure without
# cluttering the public-facing data dictionary.
_DATA_DICTIONARY_FUTURE_COLUMNS: dict[str, str] = {
    "source1_event_return_explains_source2_gap": (
        "Internal real-world-research support flag. True when research identifies "
        "source1 as the likely correct source, source1 has a same-day "
        "dividend/split marker, source2 has no same-day dividend/split marker, "
        "and source1's explicit dividend/split factor impact reconciles to "
        "diff_return within the configured real-world event return tolerance. This "
        "field is used to support post-research reason-code ownership overrides; "
        "it is not intended as a user-facing report column."
    ),
    "diff_source1_div_split_factor": (
        "Difference between source1 implied dividend/split factor and source1 "
        "explicit dividend/split factor. It is calculated as "
        "source1_div_split_factor_implied - "
        "source1_div_split_factor_explicit, but small differences below the configured 1e-6 "
        "tolerance are set to null. Cash-only convention differences may also be "
        "ignored by reason-code classification when they are below the configured "
        "0.0001 cash-factor tolerance. This field compares two related but not "
        "identical views of the same source1 source records: explicit factor math from the "
        "event records themselves, and factor math implied by the reconstructed "
        "backward-adjusted close chain. For ordinary cash dividends, a small positive "
        "difference can be normal because the explicit cash factor uses "
        "1 + cash_amount / prior_close, while the backward-adjusted close chain "
        "implies prior_close / (prior_close - cash_amount). Larger non-null values "
        "are a guardrail for cases where source1's adjusted-return chain may not "
        "reconcile cleanly to source1's explicit event records." + _DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "diff_source2_div_split_factor": (
        "Difference between source2 implied dividend/split factor and source2 "
        "explicit dividend/split factor. It is calculated as "
        "source2_div_split_factor_implied - "
        "source2_div_split_factor_explicit, but small differences below the configured 1e-6 "
        "tolerance are set to null. Cash-only convention differences may also be "
        "ignored by reason-code classification when they are below the configured "
        "0.0001 cash-factor tolerance. This field compares two related but not "
        "identical views of the same source2 source records: explicit factor math from the "
        "event records themselves, and factor math implied by source2's "
        "adjusted-close chain. For ordinary cash dividends, a small positive "
        "difference can be normal because the explicit cash factor uses "
        "1 + cash_amount / prior source2 close, while the adjusted-close chain "
        "implies prior source2 close / (prior source2 close - cash_amount). "
        "Larger non-null values are a guardrail for cases where source2's "
        "adjusted-return chain may not reconcile cleanly to source2's explicit "
        "event records." + _DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "source1_div_split_factor_explicit": (
        "source1 dividend/split adjustment factor calculated directly from source1's "
        "explicit dividend and split records on the ticker/date, independent of "
        "source1's adjusted-close chain. For cash dividends, same-day cash amounts "
        "are summed first and the factor is 1 + total_cash_amount / prior_close. "
        "For splits, the factor is split_to / split_from. If cash and split events "
        "occur on the same date, their factors are multiplied. This is the "
        "source-record view of the adjustment; it is not a claim that source1 is "
        "economically correct." + _DIV_SPLIT_EXPLICIT_EXAMPLE + _DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "source1_div_split_factor_implied": (
        "source1 dividend/split adjustment factor inferred from the relationship "
        "between the pipeline's reconstructed source1 adjusted return and source1 "
        "raw price return: (1 + source1_return) / (1 + source1_return_price). This is the "
        "adjusted-close-chain view of the adjustment, not a direct read from "
        "source1 event records. It is expected to be close to "
        "source1_div_split_factor_explicit, but it may not be identical. In particular, "
        "cash dividends can differ slightly because the explicit field uses "
        "1 + cash_amount / prior_close, while the backward-adjusted close chain "
        "implies prior_close / (prior_close - cash_amount)."
        + _DIV_SPLIT_IMPLIED_EXAMPLE
        + _DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "source2_div_split_factor_explicit": (
        "source2 dividend/split adjustment factor calculated directly from "
        "source2's explicit dividend and split records on the ticker/date, "
        "independent of source2's adjusted-close chain. For cash dividends, the "
        "factor is 1 + cash_amount / prior source2 close. For splits, the factor "
        "is source2 split_ratio. If multiple event records occur on the same date, "
        "their factors are multiplied. This is the source-record view of the "
        "adjustment; it is not a claim that source2 is economically correct."
        + _DIV_SPLIT_EXPLICIT_EXAMPLE
        + _DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
    "source2_div_split_factor_implied": (
        "source2 dividend/split adjustment factor inferred from the relationship "
        "between source2 adjusted return and source2 raw price return: "
        "(1 + source2_return) / (1 + source2_return_price). This is the adjusted-close-chain "
        "view of the adjustment, not a direct read from source2 event records. It "
        "is expected to be close to source2_div_split_factor_explicit, but it may not be "
        "identical. In particular, cash dividends can differ slightly because the "
        "explicit field uses 1 + cash_amount / prior source2 close, while the "
        "adjusted-close chain implies prior source2 close / "
        "(prior source2 close - cash_amount)."
        + _DIV_SPLIT_IMPLIED_EXAMPLE
        + _DIV_SPLIT_CASH_DENOMINATOR_NOTE
    ),
}

CATEGORY_REPORT_COLUMNS: list[str] = [
    # Key values
    "ticker",
    "date",
    # Priority and Impact
    "source1_fix_priority",
    "likely_correct_source",  # optional
    "research_confidence",  # optional
    "event_bucket",  # optional
    "expected_return_impact",
    # Event Overview
    "evidence_summary",
    "real_world_event",
    # source1 Guidance
    "source1_problem_summary",
    "source1_why_incorrect",
    "source1_fix_action",
    # Event URLs
    "primary_url",
    "secondary_url",
    "analysis_reason_code",  # optional
    # Dividends and splits
    "source1_div_split",
    "source2_div_split",
    # Returns
    "source1_return",
    "source2_return",
    "diff_return",
    # Miscellaneous
    "heuristic_anomaly_score",  # optional
]

_CATEGORY_NON_ACTIONABLE: list[str] = [
    "CLOSE_REVERSAL",
    "SOURCE2_DIV_SPLIT_RETURN_MISMATCH",
    "SOURCE2_EVENT_DATE_MISMATCH",
    "SOURCE2_MISSING_EVENT",
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

# Normalized data-source contract paths. These use explicit source-role names
# because file paths are part of the user-visible project contract.
PATH_SOURCE1_DIVIDENDS = f"{INPUT_DIRECTORY}source1_dividends"
PATH_SOURCE1_PRICES = f"{INPUT_DIRECTORY}source1_prices"
PATH_SOURCE1_SPLITS = f"{INPUT_DIRECTORY}source1_splits"
PATH_SOURCE2_DIVIDENDS = f"{INPUT_DIRECTORY}source2_dividends"
PATH_SOURCE2_PRICES = f"{INPUT_DIRECTORY}source2_prices"
PATH_SOURCE2_SPLITS = f"{INPUT_DIRECTORY}source2_splits"

DATA_SOURCE_PRICE_COLUMNS = [
    "identifier",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjusted_close",
]
DATA_SOURCE_DIVIDEND_COLUMNS = [
    "identifier",
    "ex_date",
    "dividend_type",
    "amount",
]
DATA_SOURCE_SPLIT_COLUMNS = [
    "identifier",
    "ex_date",
    "split_type",
    "amount",
]

# Output file paths
_OUTPUT_DIRECTORY = "outputs/"
PATH_AUDITED_SPLIT_ADJUSTED_OHLCV = f"{_OUTPUT_DIRECTORY}audited_split_adjusted_ohlcv"
PATH_AUDITED_RETURNS = f"{_OUTPUT_DIRECTORY}audited_returns"


# Data-source prefixes are expanded in report display names and the raw prefix
# is removed so public headers read naturally.
_DATA_SOURCE_PREFIX_MAP = {
    "source1_": "source1 ",
    "source2_": "source2 ",
}


def _default_display_name(column_name: str) -> str:
    """Build the default report display name for an internal column name.

    Data-source-prefixed columns replace the raw prefix with a readable source
    label, e.g. ``source1_return`` becomes ``source1 return``.
    Other columns use a simple underscore-to-space conversion.

    Args:
        column_name:
            Internal column name.

    Returns:
        Default report display label.
    """
    for prefix, replacement in _DATA_SOURCE_PREFIX_MAP.items():
        if column_name.startswith(prefix):
            return f"{replacement}{column_name.removeprefix(prefix).replace('_', ' ')}"
    return column_name.replace("_", " ")


def _display_name(column_name: str) -> str:
    """Return the report display name for an internal column name.

    Unknown columns still get a reasonable default label so ad hoc or future
    fields can appear in reports without first being added to the registry.

    Args:
        column_name:
            Internal column name.

    Returns:
        Report display label.
    """
    return _AUDIT_COLUMNS.get(column_name, _AuditColumn(column_name)).display_label()


def display_column_names(column_names: Sequence[str]) -> dict[str, str]:
    """Return display names keyed by internal column name.

    Args:
        column_names:
            Internal column names to convert.

    Returns:
        Mapping from internal column name to display label.
    """
    return {column_name: _display_name(column_name) for column_name in column_names}


def column_description(column_name: str) -> str:
    """Return the data-dictionary description for an internal column name.

    Unknown columns return a blank description, which keeps report tooltips
    optional rather than making every transient field a schema requirement.

    Args:
        column_name:
            Internal column name.

    Returns:
        Data-dictionary description, or a blank string for unknown columns.
    """
    return _AUDIT_COLUMNS.get(column_name, _AuditColumn(column_name)).description


def summary_appended_columns() -> list[str]:
    """Return detail columns appended back to summary reports, in report order."""
    return list(_SUMMARY_APPENDED_COLUMNS)


def column_names_in_group(group: str) -> set[str]:
    """Return internal column names tagged with a registry group.

    Use this when code is still working with raw DataFrame column names.

    Args:
        group:
            Registry group name.

    Returns:
        Internal column names tagged with ``group``.
    """
    return {column.name for column in _AUDIT_COLUMNS.values() if group in column.groups}


def reason_codes_in_group(group: str) -> list[str]:
    """Return reason codes tagged with a registry group, preserving registry order.

    Args:
        group:
            Reason-code registry group name.

    Returns:
        Reason-code strings tagged with ``group``.
    """
    return [
        reason_code.code for reason_code in REASON_CODES.values() if group in reason_code.groups
    ]


def reason_codes_by_confidence(
    confidence: str,
    include_real_world_reason_codes: bool,
) -> list[str]:
    """Return reason codes with a confidence label, preserving registry order.

    Args:
        confidence:
            Confidence label to match.

        include_real_world_reason_codes:
            Whether to include reason codes that are assigned only after
            real-world research is joined.

    Returns:
        Reason-code strings with the requested confidence label.
    """
    return [
        reason_code.code
        for reason_code in REASON_CODES.values()
        if reason_code.confidence == confidence
        and (include_real_world_reason_codes or "real_world_only" not in reason_code.groups)
    ]


def display_names_in_group(group: str) -> set[str]:
    """Return display column names tagged with a registry group.

    Use this after report columns have been renamed for HTML/PDF output.

    Args:
        group:
            Registry group name.

    Returns:
        Display labels for columns tagged with ``group``.
    """
    return {column.display_label() for column in _AUDIT_COLUMNS.values() if group in column.groups}


def frozen_display_column_classes() -> dict[str, str]:
    """Return sticky HTML table classes keyed by display column name.

    Report rendering works with display names at this point, so the registry
    converts raw column names before returning the class map.
    """
    return {
        _display_name(column_name): class_names
        for column_name, class_names in _FROZEN_COLUMN_CLASSES.items()
    }


def _column_groups(column_name: str) -> frozenset[str]:
    """Return registry groups for a column name.

    Groups are derived from the compatibility constants below so the first
    registry phase can centralize metadata without changing existing report
    ordering or public constants.

    Args:
        column_name:
            Internal column name.

    Returns:
        Registry groups assigned to the column.
    """
    groups: set[str] = set()
    for group_name, column_names in _COLUMN_GROUPS.items():
        if column_name in column_names:
            groups.add(group_name)
    return frozenset(groups)


def _build_audit_columns(column_names: Iterable[str]) -> dict[str, _AuditColumn]:
    """Build audit column metadata from existing schema constants.

    The registry is currently derived from ``DATA_DICTIONARY`` and
    ``_DATA_DICTIONARY_FUTURE_COLUMNS``. That keeps the refactor
    behavior-preserving while still giving callers a single metadata lookup.

    Args:
        column_names:
            Internal column names to register.

    Returns:
        Audit-column metadata keyed by internal column name.
    """
    return {
        column_name: _AuditColumn(
            name=column_name,
            description=DATA_DICTIONARY.get(
                column_name,
                _DATA_DICTIONARY_FUTURE_COLUMNS.get(column_name, ""),
            ),
            groups=_column_groups(column_name),
        )
        for column_name in column_names
    }


# Columns whose text should wrap in HTML/PDF reports instead of being treated
# like compact scalar values.
_NARRATIVE_COLUMNS: set[str] = {
    "evidence_summary",
    "real_world_evidence",
    "real_world_event",
    "source1_problem_summary",
    "source1_why_incorrect",
    "source1_fix_action",
    "source1_problem_and_fix",
}

# Columns rendered with status-style CSS classes when they have a value.
_STATUS_COLUMNS: set[str] = {
    "research_confidence",
    "event_detected",
    "likely_correct_source",
}

# Columns rendered as links in HTML and given URL-oriented PDF sizing.
_URL_COLUMNS: set[str] = {
    "primary_url",
    "secondary_url",
}

# Columns kept sticky on the left edge of wide HTML report tables.
_FROZEN_COLUMN_CLASSES: dict[str, str] = {
    "ticker": "frozen-col frozen-ticker",
    "date": "frozen-col frozen-date",
}

# Detail columns removed from summary reports. Some are replaced by synthesized
# summary-only columns such as real_world_evidence or source1_problem_and_fix.
_SUMMARY_OMITTED_COLUMNS: set[str] = {
    "likely_correct_source",
    "research_confidence",
    "primary_url",
    "secondary_url",
    "analysis_reason_code",
    "expected_return_impact",
    "evidence_summary",
    "real_world_event",
    "source1_problem_summary",
    "source1_why_incorrect",
    "source1_fix_action",
    "source1_return",
    "source2_return",
    "diff_return",
    "heuristic_anomaly_score",
}

# Detail columns appended back to summary reports for compact numeric context.
_SUMMARY_APPENDED_COLUMNS: list[str] = [
    "source1_return",
    "source2_return",
]

# Group names provide stable query points for report builders while preserving
# the readable list/set constants above.
_COLUMN_GROUPS: dict[str, set[str]] = {
    "category_report": set(CATEGORY_REPORT_COLUMNS),
    "narrative": _NARRATIVE_COLUMNS,
    "status": _STATUS_COLUMNS,
    "url": _URL_COLUMNS,
    "frozen": set(_FROZEN_COLUMN_CLASSES),
    "summary_omitted": _SUMMARY_OMITTED_COLUMNS,
    "summary_appended": set(_SUMMARY_APPENDED_COLUMNS),
    "future": set(_DATA_DICTIONARY_FUTURE_COLUMNS),
}

# Central metadata registry. This is the preferred source for column
# descriptions, display labels, and group membership.
_AUDIT_COLUMNS: dict[str, _AuditColumn] = _build_audit_columns(
    DATA_DICTIONARY.keys() | _DATA_DICTIONARY_FUTURE_COLUMNS.keys()
)
