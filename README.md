# Massive Market Data Audit

This project audits Massive.com market data using a combination of data consistency checks, heuristic anomaly detection, and comparison against an independent vendor (currently yFinance).  It focuses on adjusted OHLCV values, dividends, splits, adjusted returns, and real-world event explanations for unusual or discrepant return behavior.

The code is designed for investment-performance audit workflows where a discrepant value should not merely be flagged, but reconciled: what happened in the real world, which vendor treatment is economically correct, and whether Massive appears to need a data or adjustment-method fix.

The optional real-world research workflow is performed by a specialized OpenAI-assisted forensic analyst process.

## Sample Demo Output

- [Actionable Findings](outputs/actionable.2021-05-16.2026-05-16.pdf)
- [Non-actionable Findings](outputs/non_actionable.2021-05-16.2026-05-16.pdf)
- [Data Dictionary](outputs/data_dictionary.pdf)

## Functional Overview

At a high level, the project:

1. Downloads or reuses cached Massive data:
   - adjusted daily OHLCV
   - unadjusted daily OHLCV
   - dividends
   - splits

2. Downloads or reuses cached yFinance data:
   - daily OHLCV, including adjusted close
   - dividends
   - splits

3. Audits Massive split-adjusted OHLCV:
   - rebuilds expected Massive split-adjusted OHLCV values
   - compares these expected values to the actual Massive adjusted OHLCV values
   - emits only mismatched adjusted OHLCV rows

4. Audits adjusted returns:
   - rebuilds Massive adjusted closes using Massive dividends and splits
   - calculates Massive adjusted returns
   - compares Massive returns to yFinance adjusted returns
   - independently scores unusual Massive return behavior with a `heuristic_anomaly_score`
   - compares Massive and yFinance corporate-action event markers
   - flags material return differences and high-score anomalies

5. Optionally joins researched real-world event conclusions:
   - file path: `inputs/real_world_events.<from_date>.<to_date>.csv`
   - identifies the event bucket, expected return impact, likely correct source, research confidence, URLs, and evidence summary
   - updates audit diagnostics so researched conclusions can override pre-research assumptions

6. Writes audit outputs:
   - full audited returns CSV
   - review batch CSVs for external research
   - actionable and non-actionable CSV/HTML/PDF reports
   - data dictionary PDF

## Architectural Overview

The project is organized around a small orchestration class, `Audit`, plus focused modules for data access, return construction, classification, event enrichment, and output formatting.

### Main Entry Point

`audit.py`

Contains the `Audit` class. Instantiating `Audit(...)` loads data, runs the adjusted-OHLCV audit, runs the adjusted-return audit, joins optional real-world event research, and writes the full adjusted-OHLCV and return audit CSV outputs. Actionable/non-actionable reports and the data dictionary are written by explicit report methods.

Typical use:

```python
from audit import Audit
import utilities as util

audit = Audit(
    tickers=util.load_single_column("inputs/tickers"),
    from_date="2021-05-16",
    to_date="2026-05-16",
)

audit.csv_audit_report(
    actionable=True,
    output_path="outputs/actionable_audit.csv",
)
audit.html_audit_report(
    actionable=True,
    output_path="outputs/actionable_audit.html",
)
audit.pdf_audit_report(
    actionable=True,
    summary=True,
    output_path="outputs/actionable_audit.pdf",
)
```

### Data Access

`massive_data.py`

Downloads or reuses cached Massive data, then exposes date-ranged CSV cache files under `inputs/`. `MASSIVE_API_KEY` is loaded from `.env` only when a download is needed.

`yfinance_data.py`

Downloads yFinance price, dividend, and split data and writes date-ranged CSV cache files under `inputs/`.

Both data wrappers expose Polars `LazyFrame` objects for downstream processing.

### Adjusted OHLCV Audit

`adjusted_ohlcv_audit.py`

Independently rebuilds split-adjusted OHLCV values from Massive unadjusted OHLCV and Massive split records. It compares those expected values to Massive adjusted OHLCV and returns mismatches only.

### Return Audit Pipeline

`returns_builders.py`

Builds reusable Polars LazyFrames for:

- Massive close prices
- cumulative split/dividend adjustment factors
- Massive explicit dividend/split adjustment factors
- yFinance explicit dividend/split adjustment factors
- Massive adjusted closes and return components
- compact event-marker strings such as `cd:<amount>`, `sc:<amount>`, `ca:<amount>`, and `sp:<factor>`

`returns_audit_pipeline.py`

Combines the builder outputs into the full return-audit frame. It calculates:

- Massive adjusted close and return
- yFinance adjusted return
- return differences
- adjusted-close-implied dividend/split factors versus explicit dividend/split factors
- adjustment-factor diagnostics
- close-reversal diagnostics
- `heuristic_anomaly_score`, an independent Massive-side signal that can flag unusual Massive returns even when yFinance returns are identical or unavailable
- deterministic pre-research reason codes

### Classification and Review Logic

`audit_classification.py`

Assigns review flags, priorities, analysis labels, and Massive remediation guidance.

Current report split:

- actionable report: rows requiring review where `massive_needs_fix == true`
- non-actionable report: rows for review where `massive_needs_fix == false`

Rows require review when:

- `diff_return` is non-null, or
- `heuristic_anomaly_score >= MIN_SCORE_TO_REVIEW`

The heuristic score is intentionally not just a yFinance comparison. It is calculated from Massive return behavior, including the size of the Massive adjusted return, rolling behavior, robust z-scores, raw close ratios, and adjacent-day reversals. This lets the audit surface suspicious Massive return patterns even when the Massive/yFinance return comparison itself does not trigger review.

Real-world research can make these diagnostics research-aware. For example, if external research concludes `likely_correct_source == MASSIVE` or `BOTH`, Massive remediation fields are cleared.

### Real-World Event Enrichment

`real_world_events.py`

Defines the required real-world event schema and joins optional research into audited return rows.

Expected file:

```text
inputs/real_world_events.<from_date>.<to_date>.csv
```

Required columns:

```text
ticker,date,event_detected,event_bucket,expected_return_impact,likely_correct_source,research_confidence,primary_source_url,secondary_source_url,evidence_summary,real_world_event
```

This module also applies reason-code overrides when external event research supports Massive, yFinance, both, or neither. Split and spin-off research values are normalized into the audit's incremental return-impact convention before reconciliation.

### Output Generation

`audit_outputs.py`

Selects compact report columns, writes the full audited returns CSV, and writes review batches for external forensic research.

`audit.py`

Also contains CSV, HTML, and PDF report rendering methods. PDF generation uses Playwright/Chromium.

`audit_schema.py`

Centralizes constants, column lists, report columns, path prefixes, tolerances, event buckets, and the data dictionary used in report tooltips and the data dictionary PDF.

## Inputs

The main ticker input is an extensionless single-column CSV-style file:

```text
inputs/tickers
```

Cached downloaded data is written using date-ranged filenames, for example:

```text
inputs/massive_adjusted_prices.2021-05-16.2026-05-16.csv
inputs/massive_unadjusted_prices.2021-05-16.2026-05-16.csv
inputs/massive_dividends.2021-05-16.2026-05-16.csv
inputs/massive_splits.2021-05-16.2026-05-16.csv
inputs/yfinance_prices.2021-05-16.2026-05-16.csv
inputs/yfinance_dividends.2021-05-16.2026-05-16.csv
inputs/yfinance_splits.2021-05-16.2026-05-16.csv
```

Optional researched event file:

```text
inputs/real_world_events.2021-05-16.2026-05-16.csv
```

## Outputs

Primary outputs are written to `outputs/`.

Examples:

```text
outputs/audited_adjusted_ohlcv.<from_date>.<to_date>.csv
outputs/audited_returns.<from_date>.<to_date>.csv
outputs/1_audited_returns.<from_date>.<to_date>.csv
outputs/2_audited_returns.<from_date>.<to_date>.csv
outputs/actionable.<from_date>.<to_date>.csv
outputs/actionable.<from_date>.<to_date>.html
outputs/actionable.<from_date>.<to_date>.pdf
outputs/non_actionable.<from_date>.<to_date>.csv
outputs/non_actionable.<from_date>.<to_date>.html
outputs/non_actionable.<from_date>.<to_date>.pdf
outputs/data_dictionary.pdf
```

The numbered `*_audited_returns...csv` files are research batches for the AI-assisted forensic analyst workflow. They preserve ticker groupings and contain rows that need review, plus surrounding same-ticker context.

## External Research Workflow

The external research step is designed to be automated after a single manual prompt. The user starts the OpenAI-assisted forensic analyst process once, outside this Python process, using the project instructions below; from there, the analyst process automatically researches the generated batches, writes researched batch CSVs, and assembles the real-world-event input file for the next audit run.

The project includes two prompt/instruction files for that process:

- `forensic_ai_analyst_implementation.txt`
- `forensic_ai_analyst_instructions.txt`

The workflow is:

1. Run the audit to generate numbered review batch files under `outputs/`.
2. Prompt the OpenAI-assisted forensic analyst once with the implementation and instruction files.
3. Let the analyst process research each batch independently.
4. Let the analyst process write a corresponding `.researched` CSV for each batch.
5. Let the analyst process concatenate researched batch files into `inputs/real_world_events.<from_date>.<to_date>.csv`.
6. Rerun the audit so researched conclusions are joined into the final reports.

The instructions intentionally require sequential, independent batch processing so conclusions from one batch do not contaminate another.

## Running the Project

The current demo runner is:

```bash
python test.py
```

It:

1. Loads tickers from `inputs/tickers`.
2. Runs the audit for the configured date range in `test.py`.
3. Writes actionable and non-actionable CSV/HTML/PDF reports.
4. Writes `outputs/data_dictionary.pdf`.
5. Writes QA `.test` CSVs and diffs them against `.verified` files.

## Configuration

Massive access requires:

```text
MASSIVE_API_KEY=<your key>
```

The code loads this from `.env`. The key is required only when the run needs to download Massive data; cached input CSVs can be reused without a Massive API key.

## Dependencies

Install Python dependencies with:

```bash
python -m pip install -r requirements.txt
```

The main packages are:

- `polars` for lazy dataframe processing
- `pandas` and `yfinance` for yFinance downloads
- `massive` for Massive.com API access
- `python-dotenv` for loading `MASSIVE_API_KEY` from `.env`
- `playwright` for HTML-to-PDF report generation

PDF generation also requires Playwright's Chromium browser:

```bash
python -m playwright install chromium
```

## Notes on Vendor Semantics

The audit uses two vendor identities:

- Massive: fields prefixed `ms_` or `massive_`
- yFinance: fields prefixed `yf_`

`diff_return` follows this sign convention:

```text
diff_return = yf_return - ms_return
```

So:

- positive `diff_return` means yFinance return is higher
- negative `diff_return` means yFinance return is lower

`expected_return_impact` is an incremental return impact, not a total event factor. For a split example:

```text
sp:1.048 -> expected_return_impact = 0.048
```

## Repository Hygiene

Downloaded input CSVs and generated outputs can be large and date-specific. Treat them as reproducible artifacts unless you intentionally want to preserve a specific audit run.

The source CSV cache behavior is controlled by the `always_download` flag passed to `Audit`.

## License

Copyright (c) 2026 John D Reynolds. All rights reserved.

This project is proprietary. No permission is granted to use, copy, modify,
distribute, sublicense, or create derivative works without prior written
permission.
