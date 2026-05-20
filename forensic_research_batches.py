"""Manage forensic analyst batch ordering, validation, and final concatenation."""

# Standard library imports.
import argparse
import csv
import json
from pathlib import Path
from typing import Any

# Project imports.
import audit_schema as schema


def main() -> None:
    """Run the forensic research batch helper command.

    The command is intentionally non-interactive so Codex can call it between
    research passes. It does not perform research; it only enforces the file
    order, schema, and concatenation rules that are easy to get wrong manually.
    """
    parser = argparse.ArgumentParser(
        description="Manage forensic analyst batch files and .researched outputs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Delete stale outputs and list batches.",
    )
    prepare_parser.add_argument("date1")
    prepare_parser.add_argument("date2")

    next_parser = subparsers.add_parser("next", help="Return the next unprocessed batch.")
    next_parser.add_argument("date1")
    next_parser.add_argument("date2")

    validate_parser = subparsers.add_parser("validate-one", help="Validate one .researched file.")
    validate_parser.add_argument("batch_csv")

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Concatenate validated .researched files.",
    )
    finalize_parser.add_argument("date1")
    finalize_parser.add_argument("date2")

    args = parser.parse_args()

    if args.command == "prepare":
        _prepare(args.date1, args.date2)
    elif args.command == "next":
        _next(args.date1, args.date2)
    elif args.command == "validate-one":
        _validate_one(Path(args.batch_csv))
    elif args.command == "finalize":
        _finalize(args.date1, args.date2)


def _prepare(date1: str, date2: str) -> None:
    """Delete stale researched files and print the first batch to process.

    Preparation is the only destructive step in the helper. It removes generated
    ``.researched`` files for this date window so a new research run cannot
    accidentally mix fresh conclusions with stale batch outputs.
    """
    stale_paths = sorted(Path("outputs").glob(f"*_audited_returns.{date1}.{date2}.csv.researched"))
    for stale_path in stale_paths:
        # Stale researched files are generated artifacts; source audit CSVs and
        # instruction files are never deleted by this command.
        stale_path.unlink()

    batch_paths = _batch_paths(date1, date2)
    _require_batches(batch_paths, date1, date2)

    _print_json(
        {
            "status": "prepared",
            "date1": date1,
            "date2": date2,
            "deleted_researched_files": [str(path) for path in stale_paths],
            "batch_count": len(batch_paths),
            "next_batch": str(batch_paths[0]) if batch_paths else None,
            "instructions": _batch_instructions(batch_paths[0]) if batch_paths else None,
        }
    )


def _next(date1: str, date2: str) -> None:
    """Print the next batch whose .researched output is missing.

    Existing researched files are validated before the command skips past them.
    That turns "next" into a guardrail: Codex cannot silently advance over a
    malformed prior batch.
    """
    batch_paths = _batch_paths(date1, date2)
    _require_batches(batch_paths, date1, date2)

    for batch_path in batch_paths:
        # The first missing researched file is the only batch Codex should work
        # on next. Later batches are intentionally not inspected or suggested.
        researched_path = _researched_path(batch_path)
        if not researched_path.exists():
            _print_json(
                {
                    "status": "next_batch",
                    "batch_csv": str(batch_path),
                    "researched_csv": str(researched_path),
                    "instructions": _batch_instructions(batch_path),
                }
            )
            return

        # Validate completed earlier batches before declaring them done. This
        # preserves the one-batch-at-a-time invariant even across resumed runs.
        _validate_researched_file(batch_path)

    _print_json(
        {
            "status": "complete",
            "batch_csv": None,
            "message": "All batch files have validated .researched outputs.",
        }
    )


def _validate_one(batch_path: Path) -> None:
    """Validate one batch's .researched output and print a summary."""
    summary = _validate_researched_file(batch_path)
    _print_json({"status": "validated", **summary})


def _finalize(date1: str, date2: str) -> None:
    """Validate and concatenate all researched files into the real-world events input.

    Finalization is deliberately all-or-nothing: every batch must pass validation
    before the consolidated ``inputs/real_world_events`` file is written. The
    concatenation order is the numeric batch order used by the analyst workflow.
    """
    batch_paths = _batch_paths(date1, date2)
    _require_batches(batch_paths, date1, date2)
    summaries = [_validate_researched_file(batch_path) for batch_path in batch_paths]

    output_path = Path("inputs") / f"real_world_events.{date1}.{date2}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=schema.FORENSIC_ANALYST_OUTPUT_COLUMNS)
        writer.writeheader()

        for batch_path in batch_paths:
            # Each researched file already has the same exact header. The final
            # file writes a single header and then appends rows in batch order.
            with _researched_path(batch_path).open(encoding="utf-8", newline="") as input_file:
                reader = csv.DictReader(input_file)
                for row in reader:
                    writer.writerow({column: row.get(column, "") for column in writer.fieldnames})

    _print_json(
        {
            "status": "finalized",
            "output_csv": str(output_path),
            "batch_count": len(batch_paths),
            "researched_row_count": sum(
                int(summary["researched_row_count"]) for summary in summaries
            ),
        }
    )


def _batch_paths(date1: str, date2: str) -> list[Path]:
    """Return batch CSV paths sorted by ascending numeric prefix.

    Only files with a leading numeric prefix are batch files. This excludes the
    full audit CSV and any ad hoc output while preserving the intended sequence:
    1_, 2_, 3_, and so on.
    """
    paths = [
        path
        for path in Path("outputs").glob(f"*_audited_returns.{date1}.{date2}.csv")
        if _numeric_prefix(path) is not None
    ]
    return sorted(paths, key=lambda path: (_numeric_prefix(path), path.name))


def _require_batches(batch_paths: list[Path], date1: str, date2: str) -> None:
    """Fail when no generated batch CSV files are available."""
    if not batch_paths:
        raise FileNotFoundError(
            f"No batch files found matching outputs/*_audited_returns.{date1}.{date2}.csv"
        )


def _numeric_prefix(path: Path) -> int | None:
    """Return a leading numeric batch prefix from a file name."""
    prefix = path.name.split("_", maxsplit=1)[0]
    return int(prefix) if prefix.isdigit() else None


def _researched_path(batch_path: Path) -> Path:
    """Return the required .researched output path for one batch CSV."""
    return batch_path.with_name(f"{batch_path.name}.researched")


def _validate_researched_file(batch_path: Path) -> dict[str, Any]:
    """Validate one researched file against its source batch.

    The researched output is expected to contain exactly one row for each source
    row where ``needs_review`` is true, in the same order. That preserves the
    analyst's row-level contract without requiring the output to repeat all
    source columns.
    """
    if not batch_path.exists():
        raise FileNotFoundError(f"Batch CSV does not exist: {batch_path}")

    researched_path = _researched_path(batch_path)
    if not researched_path.exists():
        raise FileNotFoundError(f"Researched CSV does not exist: {researched_path}")

    source_rows = _read_csv_rows(batch_path)
    researched_rows = _read_csv_rows(researched_path)

    source_review_keys = [
        _row_key(row) for row in source_rows if _is_true(row.get("needs_review", ""))
    ]
    researched_keys = [_row_key(row) for row in researched_rows]

    # Validate schema and enum values before comparing row identity. That gives a
    # clearer error when the file is malformed rather than simply "wrong rows."
    _assert_exact_columns(researched_path, researched_rows)
    _assert_valid_values(researched_path, researched_rows)

    # Row order matters because the final concatenation preserves batch/file
    # order. A set comparison would miss accidental row reordering or duplicates.
    if researched_keys != source_review_keys:
        raise AssertionError(
            f"{researched_path} rows do not match needs_review rows from {batch_path}. "
            f"Expected {source_review_keys}, found {researched_keys}."
        )

    return {
        "batch_csv": str(batch_path),
        "researched_csv": str(researched_path),
        "expected_review_row_count": len(source_review_keys),
        "researched_row_count": len(researched_rows),
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read CSV rows as dictionaries."""
    with path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise AssertionError(f"{path} is missing a CSV header.")
        return list(reader)


def _assert_exact_columns(path: Path, rows: list[dict[str, str]]) -> None:
    """Validate researched output columns exactly match the analyst schema.

    The exact header matters because ``finalize`` concatenates files without
    trying to infer or repair schema drift. Empty researched files still need the
    header, so the empty-file branch reads it directly.
    """
    actual_columns: list[str]
    if rows:
        actual_columns = list(rows[0].keys())
    else:
        with path.open(encoding="utf-8", newline="") as csv_file:
            reader = csv.reader(csv_file)
            try:
                actual_columns = next(reader)
            except StopIteration:
                actual_columns = []

    expected_columns = schema.FORENSIC_ANALYST_OUTPUT_COLUMNS
    if actual_columns != expected_columns:
        raise AssertionError(
            f"{path} columns must exactly be {expected_columns}; found {actual_columns}."
        )


def _assert_valid_values(path: Path, rows: list[dict[str, str]]) -> None:
    """Validate enum-like researched output values.

    Narrative and URL fields are intentionally unconstrained because they depend
    on external research. Enum fields are constrained so downstream reason
    overrides can rely on stable labels such as MASSIVE, YFINANCE, and SPLIT.
    """
    allowed_values = {
        "event_detected": {"YES", "NO", "UNCERTAIN"},
        "event_bucket": set(schema.REAL_WORLD_EVENT_BUCKETS),
        "likely_correct_source": {"MASSIVE", "YFINANCE", "BOTH", "NEITHER", "UNCERTAIN"},
        "research_confidence": {"HIGH", "MEDIUM", "LOW"},
    }

    for row_number, row in enumerate(rows, start=2):
        for column_name, allowed in allowed_values.items():
            # Row numbers start at 2 because line 1 is the CSV header; this makes
            # validation errors point to the human-visible spreadsheet row.
            value = row.get(column_name, "").strip()
            if value not in allowed:
                raise AssertionError(
                    f"{path}:{row_number} has invalid {column_name}={value!r}; "
                    f"expected one of {sorted(allowed)}."
                )


def _row_key(row: dict[str, str]) -> tuple[str, str]:
    """Return the row identity used to preserve reviewed batch order."""
    return (
        row.get("ticker", "").strip().upper(),
        row.get("date", "").strip()[:10],
    )


def _is_true(value: str) -> bool:
    """Return whether a CSV boolean value represents true."""
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}


def _batch_instructions(batch_path: Path) -> str:
    """Return the instruction summary for the current batch."""
    return (
        f"Beginning independent research for {batch_path}. No conclusions from prior files "
        "are being used. Read only this batch CSV, follow forensic_ai_analyst_instructions.txt, "
        f"and write {_researched_path(batch_path)}."
    )


def _print_json(payload: dict[str, Any]) -> None:
    """Print command output as stable JSON for Codex or humans."""
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
