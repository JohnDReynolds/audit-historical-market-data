"""Validate forensic analyst instruction files against code-level schema facts."""

# Standard library imports.
import re
from pathlib import Path

# Project imports.
import audit_schema as schema

# Constants.
FORENSIC_ANALYST_INSTRUCTIONS_PATH = Path("forensic_ai_analyst_instructions.txt")
FORENSIC_ANALYST_IMPLEMENTATION_PATH = Path("forensic_ai_analyst_implementation.txt")

_EVENT_DETECTED_VALUES = [
    "YES",
    "NO",
    "UNCERTAIN",
]

_LIKELY_CORRECT_SOURCE_VALUES = [
    "MASSIVE",
    "YFINANCE",
    "BOTH",
    "NEITHER",
    "UNCERTAIN",
]

_RESEARCH_CONFIDENCE_VALUES = [
    "HIGH",
    "MEDIUM",
    "LOW",
]


def validate_forensic_docs() -> None:
    """Fail if forensic analyst docs drift from code-level schema assumptions."""
    instructions_text = FORENSIC_ANALYST_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    implementation_text = FORENSIC_ANALYST_IMPLEMENTATION_PATH.read_text(encoding="utf-8")

    _assert_forensic_output_schema(instructions_text)
    _assert_column_rule_values(
        instructions_text,
        "event_detected",
        _EVENT_DETECTED_VALUES,
    )
    _assert_column_rule_values(
        instructions_text,
        "event_bucket",
        schema._REAL_WORLD_EVENT_BUCKETS,  # pylint: disable=protected-access
    )
    _assert_column_rule_values(
        instructions_text,
        "likely_correct_source",
        _LIKELY_CORRECT_SOURCE_VALUES,
    )
    _assert_column_rule_values(
        instructions_text,
        "research_confidence",
        _RESEARCH_CONFIDENCE_VALUES,
    )
    _assert_reason_codes_documented(instructions_text)
    _assert_implementation_contract(implementation_text)


def _assert_forensic_output_schema(instructions_text: str) -> None:
    """Validate the exact CSV header required from the forensic analyst."""
    expected_header = ",".join(schema.FORENSIC_ANALYST_OUTPUT_COLUMNS)

    if expected_header not in instructions_text:
        raise AssertionError(
            "forensic_ai_analyst_instructions.txt OUTPUT SCHEMA does not match "
            f"schema.FORENSIC_ANALYST_OUTPUT_COLUMNS: {expected_header}"
        )


def _assert_column_rule_values(
    instructions_text: str,
    column_name: str,
    expected_values: list[str],
) -> None:
    """Validate allowed values listed under one COLUMN RULES heading."""
    match = re.search(
        rf"^{re.escape(column_name)}:\n(?P<body>(?:[A-Z_]+\n)+)",
        instructions_text,
        re.MULTILINE,
    )

    if match is None:
        raise AssertionError(
            f"forensic_ai_analyst_instructions.txt is missing COLUMN RULES for {column_name}."
        )

    actual_values = [line.strip() for line in match.group("body").splitlines() if line.strip()]

    if actual_values != expected_values:
        raise AssertionError(
            f"forensic_ai_analyst_instructions.txt {column_name} values differ from schema. "
            f"Expected {expected_values}, found {actual_values}."
        )


def _assert_reason_codes_documented(instructions_text: str) -> None:
    """Validate that data-dictionary reason codes appear in the analyst instructions."""
    missing_reason_codes = [
        reason_code for reason_code in schema.REASON_CODES if reason_code not in instructions_text
    ]

    if missing_reason_codes:
        raise AssertionError(
            "forensic_ai_analyst_instructions.txt is missing analysis_reason_code values: "
            + ", ".join(missing_reason_codes)
        )


def _assert_implementation_contract(implementation_text: str) -> None:
    """Validate core batch workflow phrases that code and docs assume."""
    required_phrases = [
        "outputs/*_audited_returns.<date1>.<date2>.csv",
        "<original_input_path>.researched",
        "needs_review == true",
        "inputs/real_world_events.<date1>.<date2>.csv",
        "preserve batch/file order during concatenation",
    ]
    missing_phrases = [phrase for phrase in required_phrases if phrase not in implementation_text]

    if missing_phrases:
        raise AssertionError(
            "forensic_ai_analyst_implementation.txt is missing required workflow phrases: "
            + ", ".join(missing_phrases)
        )
