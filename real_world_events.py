"""Real-world event helpers for return-audit enrichment."""

# Standard library imports.
from typing import TypeVar, cast

# Third-party imports.
import polars as pl
import audit_schema as schema

# Type aliases.
_FrameT = TypeVar("_FrameT", pl.DataFrame, pl.LazyFrame)

REQUIRED_REAL_WORLD_EVENT_COLUMNS: set[str] = schema.REQUIRED_REAL_WORLD_EVENT_COLUMNS


def add_placeholder_columns(frame: _FrameT) -> _FrameT:
    """Add blank real-world-event columns so the audit schema is stable.

    Args:
        frame:
            Return-audit frame before optional real-world event research has
            been joined.

    Returns:
        Frame with all real-world-event output columns present.
    """
    return cast(
        _FrameT,
        frame.with_columns(
            *[
                (
                    pl.lit(None, dtype=pl.Float64)
                    if column_name == "expected_return_impact"
                    else pl.lit("")
                ).alias(column_name)
                for column_name in schema.REAL_WORLD_EVENT_COLUMNS
            ],
        ),
    )


def apply_reason_overrides(df: pl.DataFrame) -> pl.DataFrame:
    """Use real-world event evidence to update reason codes.

    Args:
        df:
            Return-audit output, optionally enriched with real-world event
            fields.

    Returns:
        DataFrame with real-world event support flags applied to
        ``analysis_reason_code``.
    """
    return apply_real_world_reason_policy(add_real_world_reconciliation_flags(df))


def add_real_world_reconciliation_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Add real-world event reconciliation flags used by reason-code policy.

    Args:
        df:
            Return-audit output enriched with real-world event fields.

    Returns:
        DataFrame with normalized expected return impact and support flags.
    """
    real_world_match_tolerance_expr: pl.Expr = pl.max_horizontal(
        pl.lit(schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE),
        pl.col("expected_return_impact").abs() * schema.REAL_WORLD_EVENT_REL_RETURN_TOLERANCE,
    )

    # Analyst output may provide split/spinoff impact as either an event factor
    # or an event return. Normalize factors such as 1.05 to +0.05 so the value
    # can be compared to diff_return. The sign operation handles reverse-style
    # factors symmetrically: a factor below -1 would be moved toward a return
    # impact rather than treated as a raw factor.
    normalized_expected_return_impact: pl.Expr = (
        pl.when(
            pl.col("event_bucket").is_in(["SPLIT", "SPINOFF"])
            & pl.col("expected_return_impact").is_not_null()
            & (pl.col("expected_return_impact").abs() > 1.0)
        )
        .then(pl.col("expected_return_impact") - pl.col("expected_return_impact").sign())
        .otherwise(pl.col("expected_return_impact"))
    )

    # Only return-bearing corporate actions should change reason codes through
    # event-return reconciliation. NEWS and PRICING_METHOD can explain why a row
    # needs attention, but they should not mechanically convert a data source
    # into a missing dividend/split adjustment.
    return_bearing_event_expr: pl.Expr = (
        (pl.col("event_detected") == "YES")
        & pl.col("event_bucket").is_in(schema.REAL_WORLD_EVENT_RETURN_BUCKETS)
        & pl.col("expected_return_impact").is_not_null()
    )

    # Signed reconciliation matters because diff_return = source1 - source2.
    # If source1 is correct and source2 missed a positive event, diff_return
    # should be positive. If source2 is correct and source1 missed the event,
    # diff_return should be negative. This prevents a real event with the right
    # magnitude but wrong direction from overriding the deterministic diagnosis.
    expected_diff_for_likely_source_expr: pl.Expr = (
        pl.when(pl.col("likely_correct_source") == "SOURCE1")
        .then(pl.col("expected_return_impact"))
        .when(pl.col("likely_correct_source") == "SOURCE2")
        .then(-pl.col("expected_return_impact"))
        .otherwise(None)
    )

    return (
        # Normalize the analyst-provided expected impact before deriving support
        # flags so every later reconciliation test uses the same event-return
        # convention as diff_return and the explicit factor-impact columns.
        df.with_columns(normalized_expected_return_impact.alias("expected_return_impact"))
        .with_columns(
            (
                # real_world_event_return_match is the bridge between external
                # research and input row math. Overrides below are allowed only when
                # the confirmed event magnitude reconciles to the signed return
                # difference within tolerance.
                pl.col("diff_return").is_not_null()
                & return_bearing_event_expr
                & expected_diff_for_likely_source_expr.is_not_null()
                & (
                    (pl.col("diff_return") - expected_diff_for_likely_source_expr).abs()
                    <= real_world_match_tolerance_expr
                )
            ).alias("real_world_event_return_match")
        )
        .with_columns(
            (
                # If research names source1 as the correct source and source1's
                # own explicit event effect explains the signed return gap, a
                # missing numeric expected_return_impact should not block the
                # source-owner override.
                pl.col("diff_return").is_not_null()
                & (pl.col("likely_correct_source") == "SOURCE1")
                & (pl.col("event_detected") == "YES")
                & pl.col("event_bucket").is_in(schema.REAL_WORLD_EVENT_RETURN_BUCKETS)
                & (pl.col("source1_div_split") != "")
                & (pl.col("source2_div_split") == "")
                & pl.col("source1_div_split_factor_explicit").is_not_null()
                & (
                    (
                        pl.col("diff_return")
                        - (pl.col("source1_div_split_factor_explicit") - 1.0)
                    ).abs()
                    <= schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE
                )
            ).alias("source1_event_return_explains_source2_gap")
        )
        .with_columns(
            # These support flags are later used to rewrite generic or
            # pre-research reason codes into source-specific diagnostics.
            (
                (
                    pl.col("real_world_event_return_match")
                    | pl.col("source1_event_return_explains_source2_gap")
                )
                & pl.col("likely_correct_source").is_in(["SOURCE1", "BOTH"])
            ).alias("real_world_event_supports_source1"),
            (
                pl.col("real_world_event_return_match")
                & pl.col("likely_correct_source").is_in(["SOURCE2", "BOTH"])
            ).alias("real_world_event_supports_source2"),
        )
    )


def apply_real_world_reason_policy(df: pl.DataFrame) -> pl.DataFrame:
    """Rewrite reason codes using real-world reconciliation support flags.

    Args:
        df:
            Return-audit output with real-world reconciliation flags.

    Returns:
        DataFrame with research-aware ``analysis_reason_code`` values.
    """
    # These are pre-research diagnostics that can point at source1, but may
    # actually indicate source2 is missing the real-world event once external
    # evidence is joined. They are deliberately eligible for source reversal only
    # after research supplies both a likely source and an event magnitude that
    # reconciles to the signed return gap.
    source2_missing_override_candidates: list[str] = schema.reason_codes_in_group(
        "source2_missing_override_candidate"
    )
    source1_missing_override_candidates: list[str] = schema.reason_codes_in_group(
        "source1_missing_override_candidate"
    )
    source2_event_impact_expr: pl.Expr = pl.col("source2_div_split_factor_explicit") - 1.0
    source2_event_match_tolerance_expr: pl.Expr = pl.max_horizontal(
        pl.lit(schema.REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE),
        source2_event_impact_expr.abs() * schema.REAL_WORLD_EVENT_REL_RETURN_TOLERANCE,
    )
    source2_event_return_explains_source1_gap: pl.Expr = (
        # With diff_return = source1 - source2, a positive event captured by
        # source2 but missed by source1 should make source1 lower by roughly
        # the source2 event impact.
        pl.col("diff_return").is_not_null()
        & pl.col("source2_div_split_factor_explicit").is_not_null()
        & (
            (pl.col("diff_return") + source2_event_impact_expr).abs()
            <= source2_event_match_tolerance_expr
        )
    )

    return (
        df
        .with_columns(
            # Reason-code overrides are deliberately conservative: research must
            # identify the economically correct source and the signed event
            # impact must explain the source1/source2 return difference. The
            # override changes the diagnostic owner; it does not change raw return
            # math or event-marker fields.
            pl.when(
                # Research says source1 is correct and the only deterministic
                # issue was event timing, so ownership flips from a source1 date
                # mismatch to a source2 date mismatch.
                (pl.col("likely_correct_source") == "SOURCE1")
                & (pl.col("analysis_reason_code") == "SOURCE1_EVENT_DATE_MISMATCH")
                & (
                    pl.col("real_world_event_return_match")
                    | pl.col("source1_event_return_explains_source2_gap")
                )
            )
            .then(pl.lit("SOURCE2_EVENT_DATE_MISMATCH"))
            .when(
                # Research says source1 carries the real event and the return
                # math supports that conclusion. Generic or source1-leaning
                # pre-research diagnostics become a source2 missing-event issue.
                (pl.col("likely_correct_source") == "SOURCE1")
                & pl.col("analysis_reason_code").is_in(source2_missing_override_candidates)
                & (
                    pl.col("real_world_event_return_match")
                    | pl.col("source1_event_return_explains_source2_gap")
                )
            )
            .then(pl.lit("SOURCE2_MISSING_EVENT"))
            .when(
                # The support flags are broader than the direct likely-source
                # checks above because they also allow BOTH when the event math
                # confirms source1's treatment is economically valid.
                pl.col("real_world_event_supports_source1")
                & (pl.col("analysis_reason_code") == "SOURCE1_EVENT_DATE_MISMATCH")
            )
            .then(pl.lit("SOURCE2_EVENT_DATE_MISMATCH"))
            .when(
                pl.col("real_world_event_supports_source1")
                & pl.col("analysis_reason_code").is_in(source2_missing_override_candidates)
            )
            .then(pl.lit("SOURCE2_MISSING_EVENT"))
            .when(
                # The mirror case: research and signed return math support
                # source2, so selected pre-research diagnostics become a
                # source1 missing-event issue.
                pl.col("real_world_event_supports_source2")
                & pl.col("analysis_reason_code").is_in(source1_missing_override_candidates)
            )
            .then(pl.lit("SOURCE1_MISSING_EVENT"))
            .when(
                # Some cash distributions reconcile within the broader review
                # tolerance but not the tight deterministic event-return
                # tolerance, so they can initially look like a source2 internal
                # event-return mismatch. If external research says source2 is
                # correct, source2 carries the event marker, and source1 has no
                # same-day event, the operational issue is still a missing
                # source1 event.
                (pl.col("likely_correct_source") == "SOURCE2")
                & (pl.col("event_detected") == "YES")
                & pl.col("event_bucket").is_in(schema.REAL_WORLD_EVENT_RETURN_BUCKETS)
                & (pl.col("source1_div_split") == "")
                & (pl.col("source2_div_split") != "")
                & source2_event_return_explains_source1_gap
                & pl.col("analysis_reason_code").is_in(
                    [
                        "SOURCE2_DIV_SPLIT_RETURN_MISMATCH",
                        "EVENT_SOURCE_MISMATCH",
                        "SOURCE1_RETURN_METHOD_UNRESOLVED",
                    ]
                )
            )
            .then(pl.lit("SOURCE1_MISSING_EVENT"))
            .otherwise(pl.col("analysis_reason_code"))
            .alias("analysis_reason_code")
        )
    )


def assert_output_columns(df: pl.DataFrame) -> None:
    """Fail fast if any real-world event output columns are missing.

    Args:
        df:
            Return-audit output to validate.

    Raises:
        AssertionError:
            Raised if a required real-world event output column is missing.
    """
    for column_name in schema.REAL_WORLD_EVENT_COLUMNS:
        if column_name not in df.columns:
            raise AssertionError(f"audit_returns() must persist {column_name} before writing CSV.")


def get_real_world_events_path(from_date: str, to_date: str) -> str:
    """Return the expected real-world events CSV path.

    Args:
        from_date:
            Inclusive audit start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive audit end date in ``YYYY-MM-DD`` format.

    Returns:
        Path to the optional real-world events CSV for this audit window.
    """
    return f"{schema.INPUT_DIRECTORY}real_world_events.{from_date}.{to_date}.csv"


def join_events(df: pl.DataFrame, real_world_events_path: str) -> pl.DataFrame:
    """Overlay optional real-world event research onto return rows.

    The real-world events CSV is expected to contain the columns in
    ``REQUIRED_REAL_WORLD_EVENT_COLUMNS``.

    Args:
        df:
            Collected return-audit output.

        real_world_events_path:
            Path to the real-world events CSV.

    Returns:
        Return-audit output enriched with real-world event fields.
    """
    # Normalize analyst output before joining so hand-authored CSV variations
    # such as lowercase enums, padded tickers, or datetime-like dates do not
    # prevent a researched row from matching its audit row.
    real_world_events_df: pl.DataFrame = (
        pl.read_csv(real_world_events_path)
        .select(
            [
                pl.col("ticker").str.strip_chars().str.to_uppercase().alias("ticker"),
                pl.col("date").cast(pl.Utf8).str.strip_chars().str.slice(0, 10).alias("date_key"),
                pl.col("event_detected")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .fill_null("")
                .alias("event_detected_from_file"),
                pl.col("event_bucket")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .fill_null("")
                .alias("event_bucket_from_file"),
                pl.col("expected_return_impact")
                .cast(pl.Float64, strict=False)
                .alias("expected_return_impact_from_file"),
                pl.col("likely_correct_source")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .fill_null("")
                .alias("likely_correct_source_from_file"),
                pl.col("research_confidence")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .fill_null("")
                .alias("research_confidence_from_file"),
                pl.col("evidence_summary")
                .cast(pl.Utf8)
                .fill_null("")
                .alias("evidence_summary_from_file"),
                pl.col("real_world_event").fill_null("").alias("real_world_event_from_file"),
                pl.col("primary_url")
                .cast(pl.Utf8)
                .fill_null("")
                .alias("primary_url_from_file"),
                pl.col("secondary_url")
                .cast(pl.Utf8)
                .fill_null("")
                .alias("secondary_url_from_file"),
            ]
        )
        .group_by(["ticker", "date_key"])
        .agg(
            # If duplicate researched rows exist for a ticker/date, keep the last
            # one deterministically. Upstream validation aims to prevent duplicates,
            # but this keeps the join stable if a manually edited file slips through.
            pl.col("event_detected_from_file").last(),
            pl.col("event_bucket_from_file").last(),
            pl.col("expected_return_impact_from_file").last(),
            pl.col("likely_correct_source_from_file").last(),
            pl.col("research_confidence_from_file").last(),
            pl.col("evidence_summary_from_file").last(),
            pl.col("primary_url_from_file").last(),
            pl.col("secondary_url_from_file").last(),
            pl.col("real_world_event_from_file").last(),
        )
    )

    return (
        # Coalesce keeps the pipeline's blank placeholders when no research row
        # exists and overlays analyst research only for matching ticker/date keys.
        df.with_columns(pl.col("date").cast(pl.Utf8).str.slice(0, 10).alias("date_key"))
        .join(real_world_events_df, on=["ticker", "date_key"], how="left")
        .with_columns(
            pl.coalesce([pl.col("event_detected_from_file"), pl.col("event_detected")]).alias(
                "event_detected"
            ),
            pl.coalesce([pl.col("event_bucket_from_file"), pl.col("event_bucket")]).alias(
                "event_bucket"
            ),
            pl.coalesce(
                [pl.col("expected_return_impact_from_file"), pl.col("expected_return_impact")]
            ).alias("expected_return_impact"),
            pl.coalesce(
                [pl.col("likely_correct_source_from_file"), pl.col("likely_correct_source")]
            ).alias("likely_correct_source"),
            pl.coalesce(
                [pl.col("research_confidence_from_file"), pl.col("research_confidence")]
            ).alias("research_confidence"),
            pl.coalesce([pl.col("evidence_summary_from_file"), pl.col("evidence_summary")]).alias(
                "evidence_summary"
            ),
            pl.coalesce([pl.col("real_world_event_from_file"), pl.col("real_world_event")]).alias(
                "real_world_event"
            ),
            pl.coalesce(
                [pl.col("primary_url_from_file"), pl.col("primary_url")]
            ).alias("primary_url"),
            pl.coalesce(
                [pl.col("secondary_url_from_file"), pl.col("secondary_url")]
            ).alias("secondary_url"),
        )
        .drop(
            [
                "date_key",
                "event_detected_from_file",
                "event_bucket_from_file",
                "expected_return_impact_from_file",
                "likely_correct_source_from_file",
                "research_confidence_from_file",
                "evidence_summary_from_file",
                "primary_url_from_file",
                "secondary_url_from_file",
                "real_world_event_from_file",
            ]
        )
    )
