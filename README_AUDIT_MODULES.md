# Audit Module Overview

This folder contains the audit pipeline for comparing Massive and yFinance price, corporate-action, and return data.

The main design goal is to keep `audit.py` small and readable while calculation, validation, classification, and output details are in focused helper modules.

## Module responsibilities

### `audit.py`

Public entry point and orchestration layer.

The `Audit` class:

- loads Massive and yFinance input data,
- runs the adjusted-OHLCV audit,
- runs the return audit,
- joins optional real-world event research,
- refreshes final analysis columns,
- writes audit outputs.

This file should stay thin. Avoid adding large Polars pipelines here unless they are only simple orchestration.

### `audit_schema.py`

Shared constants and column lists.

This includes:

- tolerances,
- decimal precision,
- review thresholds,
- category report columns,
- non-actionable reason-code lists.

Use this module when a value is shared across multiple audit modules.

### `audit_validation.py`

Input schema validation.

This module verifies that required columns exist before the audit runs. It should fail early when input CSVs are missing required fields.

### `adjusted_ohlcv_audit.py`

Adjusted OHLCV audit logic.

This module independently applies split adjustment factors to Massive unadjusted OHLCV data and compares the result to Massive adjusted OHLCV data.

### `returns_builders.py`

Lower-level return-building helpers.

This module builds normalized Massive and yFinance price/event frames, including:

- Massive close prices,
- yFinance close and adjusted close returns,
- split/dividend event text,
- explicit dividend/split return components,
- Massive adjusted close and adjusted return calculations.

### `returns_audit_pipeline.py`

Main return-audit Polars pipeline.

This module combines the lower-level return builders and creates the detailed return comparison frame, including:

- Massive/yFinance return differences,
- dividend/split mismatches,
- adjustment-factor diagnostics,
- event-date mismatch flags,
- close-reversal flags,
- final return-audit column selection.

Most remaining return-audit complexity belongs here rather than in `audit.py`.

### `audit_classification.py`

Reason-code, review, confidence, and fix-guidance logic.

This module assigns and refreshes:

- `analysis_reason_code`,
- `analysis_sheet`,
- `analysis_confidence`,
- `needs_review`,
- `review_priority`,
- Massive fix guidance fields.

### `real_world_events.py`

Optional real-world event research handling.

This module manages:

- expected real-world event columns,
- placeholder event columns,
- joining the optional real-world-events CSV,
- real-world-event reason-code overrides,
- final event-column assertions.

### `audit_outputs.py`

Output and reporting helpers.

This module handles:

- writing rounded audit CSV output,
- writing needs-review batch files,
- creating actionable and non-actionable category reports.

## Suggested maintenance rule

When adding new logic, first decide what type of change it is:

- Input requirement → `audit_validation.py`
- Shared constant or report column → `audit_schema.py`
- Data construction → `returns_builders.py`
- Return comparison or diagnostic flag → `returns_audit_pipeline.py`
- Reason code or review priority → `audit_classification.py`
- Real-world research overlay → `real_world_events.py`
- CSV/report output → `audit_outputs.py`
- Public orchestration only → `audit.py`

This keeps `audit.py` easy to understand and reduces the chance that future changes make the module bloated again.
