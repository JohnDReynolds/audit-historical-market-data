"""Real-world event helpers for return-audit enrichment."""

# Standard library imports.
from typing import TypeVar, cast

# Third-party imports.
import polars as pl

# Project imports.
from audit_schema import (
    REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE,
    REAL_WORLD_EVENT_REL_RETURN_TOLERANCE,
)
import utilities as util

# Type aliases.
_FrameT = TypeVar("_FrameT", pl.DataFrame, pl.LazyFrame)

# Constants.
REQUIRED_REAL_WORLD_EVENT_COLUMNS: set[str] = {
    "ticker",
    "date",
    "event_detected",
    "event_bucket",
    "expected_return_impact",
    "likely_correct_source",
    "confidence_level",
    "evidence_summary",
    "real_world_event",
    "primary_source_url",
    "secondary_source_url",
}


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
            pl.lit("").alias("event_detected"),
            pl.lit("").alias("event_bucket"),
            pl.lit(None, dtype=pl.Float64).alias("expected_return_impact"),
            pl.lit("").alias("likely_correct_source"),
            pl.lit("").alias("confidence_level"),
            pl.lit("").alias("evidence_summary"),
            pl.lit("").alias("real_world_event"),
            pl.lit("").alias("primary_source_url"),
            pl.lit("").alias("secondary_source_url"),
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
    real_world_match_tolerance_expr: pl.Expr = pl.max_horizontal(
        pl.lit(REAL_WORLD_EVENT_MIN_RETURN_TOLERANCE),
        pl.col("expected_return_impact").abs() * REAL_WORLD_EVENT_REL_RETURN_TOLERANCE,
    )

    return (
        df.with_columns(
            (
                pl.col("diff_return").is_not_null()
                & (pl.col("event_detected") == "YES")
                & pl.col("event_bucket").is_in(["DISTRIBUTION", "SPLIT", "MERGER", "RIGHTS"])
                & pl.col("expected_return_impact").is_not_null()
                & (
                    ((pl.col("diff_return").abs() - pl.col("expected_return_impact").abs()).abs())
                    <= real_world_match_tolerance_expr
                )
            ).alias("real_world_event_return_match")
        )
        .with_columns(
            (
                pl.col("real_world_event_return_match")
                & pl.col("likely_correct_source").is_in(["MASSIVE", "BOTH"])
            ).alias("real_world_event_supports_massive"),
            (
                pl.col("real_world_event_return_match")
                & pl.col("likely_correct_source").is_in(["YFINANCE", "BOTH"])
            ).alias("real_world_event_supports_yfinance"),
        )
        .with_columns(
            pl.when(
                pl.col("real_world_event_supports_massive")
                & (pl.col("analysis_reason_code") == "MS_EVENT_DATE_MISMATCH")
            )
            .then(pl.lit("YF_EVENT_DATE_MISMATCH"))
            .when(
                pl.col("real_world_event_supports_massive")
                & pl.col("analysis_reason_code").is_in(
                    [
                        "MS_ADJ_FACTOR_CONTINUITY",
                        "MS_EVENT_SOURCE_MISMATCH",
                        "MS_DIV_SPLIT_RETURN_MISMATCH",
                        "MS_RETURN_METHOD_UNRESOLVED",
                    ]
                )
            )
            .then(pl.lit("YF_MISSING_REAL_WORLD_EVENT"))
            .when(
                pl.col("real_world_event_supports_yfinance")
                & pl.col("analysis_reason_code").is_in(
                    [
                        "MS_ADJ_FACTOR_CONTINUITY",
                        "MS_EVENT_SOURCE_MISMATCH",
                        "MS_RETURN_METHOD_UNRESOLVED",
                    ]
                )
            )
            .then(pl.lit("MS_MISSING_EVENT_ADJUSTMENT"))
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
    for column_name in REQUIRED_REAL_WORLD_EVENT_COLUMNS - {"ticker", "date"}:
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
    return f"{util.INPUT_DIRECTORY}real_world_events.{from_date}.{to_date}.csv"


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
                pl.col("confidence_level")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_uppercase()
                .fill_null("")
                .alias("confidence_level_from_file"),
                pl.col("evidence_summary")
                .cast(pl.Utf8)
                .fill_null("")
                .alias("evidence_summary_from_file"),
                pl.col("real_world_event").fill_null("").alias("real_world_event_from_file"),
                pl.col("primary_source_url")
                .cast(pl.Utf8)
                .fill_null("")
                .alias("primary_source_url_from_file"),
                pl.col("secondary_source_url")
                .cast(pl.Utf8)
                .fill_null("")
                .alias("secondary_source_url_from_file"),
            ]
        )
        .group_by(["ticker", "date_key"])
        .agg(
            pl.col("event_detected_from_file").last(),
            pl.col("event_bucket_from_file").last(),
            pl.col("expected_return_impact_from_file").last(),
            pl.col("likely_correct_source_from_file").last(),
            pl.col("confidence_level_from_file").last(),
            pl.col("evidence_summary_from_file").last(),
            pl.col("primary_source_url_from_file").last(),
            pl.col("secondary_source_url_from_file").last(),
            pl.col("real_world_event_from_file").last(),
        )
    )

    return (
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
            pl.coalesce([pl.col("confidence_level_from_file"), pl.col("confidence_level")]).alias(
                "confidence_level"
            ),
            pl.coalesce([pl.col("evidence_summary_from_file"), pl.col("evidence_summary")]).alias(
                "evidence_summary"
            ),
            pl.coalesce([pl.col("real_world_event_from_file"), pl.col("real_world_event")]).alias(
                "real_world_event"
            ),
            pl.coalesce(
                [pl.col("primary_source_url_from_file"), pl.col("primary_source_url")]
            ).alias("primary_source_url"),
            pl.coalesce(
                [pl.col("secondary_source_url_from_file"), pl.col("secondary_source_url")]
            ).alias("secondary_source_url"),
        )
        .drop(
            [
                "date_key",
                "event_detected_from_file",
                "event_bucket_from_file",
                "expected_return_impact_from_file",
                "likely_correct_source_from_file",
                "confidence_level_from_file",
                "evidence_summary_from_file",
                "primary_source_url_from_file",
                "secondary_source_url_from_file",
                "real_world_event_from_file",
            ]
        )
    )
