# Massive Historical Market Data Audit

A lightweight auditing framework for validating Massive historical market data.

This project downloads:
- Massive OHLCV data
- Massive dividend events
- Massive split events
- yFinance OHLCV data
- yFinance dividends
- yFinance splits

It then:
1. Audits Massive split-adjusted OHLCV data.
2. Reconstructs adjusted closes and returns from raw Massive data.
3. Compares those results against yFinance adjusted returns.
4. Produces CSV audit outputs and heuristic suspicion scores identifying potentially incorrect adjusted returns using anomaly detection, split-ratio patterns, rolling robust statistics, and isolated return spikes.

The system is intentionally designed for:
- transparency,
- reproducibility,
- auditability,
- and debugging of corporate-action-adjusted return series.

The project focuses heavily on:
- splits,
- dividends,
- adjusted prices,
- return continuity,
- and vendor normalization differences.

The code streams data directly to CSV files and uses lazy Polars execution heavily for scalability and reproducibility.

---

# Features

## Massive Downloads

Downloads:
- daily OHLCV aggregate bars,
- dividend events,
- split events.

Supports:
- adjusted prices,
- unadjusted prices,
- streaming CSV export,
- defensive schema handling.

Massive adjusted prices are:
- split-adjusted only,
- NOT dividend-adjusted.

---

## yFinance Downloads

Downloads:
- OHLCV bars,
- adjusted closes,
- dividends,
- splits.

The downloader:
- fixes yFinance end-date exclusivity,
- prevents partially-written files,
- fails clearly on empty downloads.

---

## Adjusted OHLCV Audit

The project independently reconstructs split-adjusted OHLCV values using:
- raw Massive OHLCV data,
- Massive split-event data.

It then compares:
- Massive adjusted OHLCV values
vs
- manually reconstructed expected values.

The audit:
- computes cumulative split adjustment factors,
- reconstructs expected OHLCV values,
- identifies mismatches,
- outputs percentage differences.

Audited fields:
- open
- high
- low
- close
- vwap
- volume
- transactions

---

## Return Reconstruction Audit

The system reconstructs:
- split-adjusted closes,
- dividend-adjusted closes,
- total-return-style adjusted returns.

It then compares:
- locally reconstructed returns
vs
- yFinance adjusted returns.

This is performed using:
- split adjustment factors,
- dividend adjustment factors,
- cumulative backward adjustment methodology.

---

## Corporate Action Normalization

The audit framework normalizes:
- splits,
- dividends,
- and combined dividend/split events.

The system explicitly handles:
- split ratios,
- dividend adjustment factors,
- multiple events on the same date,
- backward-adjusted historical pricing.

---

## Suspicion Scoring Engine

The project assigns heuristic suspicion scores to potentially problematic returns.

The scoring system looks for:
- extremely large returns,
- robust z-score anomalies,
- isolated spikes,
- split-ratio-like price jumps,
- violent reversals,
- neighboring return inconsistencies.

Examples:
- missing split adjustments,
- duplicated corporate actions,
- stale prices,
- bad vendor data,
- incorrect adjustment timing.

Rows with:

    score >= 5

typically deserve manual review.

---

# High-Level Workflow

```python
# Download Massive data.
massive_data.download_dividends()
massive_data.download_prices(adjusted=False)
massive_data.download_prices(adjusted=True)
massive_data.download_splits()

# Download yFinance data.
yfinance_data.download_dividends()
yfinance_data.download_prices()
yfinance_data.download_splits()

# Audit Massive adjusted OHLCV columns.
audit.audit_adjusted_ohlcv()

# Audit Massive dividends, splits and returns.
audited_returns = audit.audit_returns()

print(audited_returns[:200])
```

---

# Main Concepts

## Raw Prices vs Adjusted Prices

The project distinguishes between:
- raw market prices,
- split-adjusted prices,
- dividend-adjusted prices,
- economically continuous return series.

This distinction is critical for:
- total return calculations,
- backtesting,
- attribution,
- auditability,
- and vendor reconciliation.

---

## Backward Adjustment Methodology

Historical prices are adjusted using future corporate actions.

Example:
- 2-for-1 split on 2025-01-01
- prices before the split are multiplied by:

    0.5

Dividend adjustments use:

    (prior_close - dividend) / prior_close

This creates economically continuous adjusted price series.

---

# Example Audit Output Columns

## Adjusted OHLCV Audit

| Column | Description |
|---|---|
| ticker | Ticker symbol |
| date | Trading date |
| field | OHLCV field being audited |
| adj_factor | Cumulative split adjustment factor |
| unadjusted | Raw Massive value |
| adjusted | Massive adjusted value |
| expected | Independently reconstructed value |
| pct_diff | Percentage difference |

---

## Returns Audit

| Column | Description |
|---|---|
| ticker | Ticker symbol |
| date | Trading date |
| adj_factor | Combined split/dividend factor |
| close | Raw close |
| adj_close | Reconstructed adjusted close |
| return | Reconstructed adjusted return |
| yf_close | yFinance raw close |
| yf_adj_close | yFinance adjusted close |
| yf_return | yFinance adjusted return |
| diff_return | Return difference |
| score | Suspicion score |
| divs_splits | Massive corporate action flags |
| yf_divs_splits | yFinance corporate action flags |

---

# Project Structure

```text
project/
├── audit.py
├── massive_data.py
├── yfinance_data.py
├── utilities.py
├── main.py
└── output_csvs/
```

---

# Requirements

Core dependencies:
- polars
- pandas
- yfinance
- python-dotenv
- massive

---

# Massive API Key

Massive downloads require:

    MASSIVE_API_KEY

Example `.env`:

```text
MASSIVE_API_KEY=your_actual_api_key_here
```

---

# Why This Project Exists

Corporate actions are one of the largest causes of:
- return discontinuities,
- broken adjusted prices,
- vendor disagreements,
- attribution drift,
- and historical performance restatements.

This project provides:
- a transparent audit layer,
- independent adjustment reconstruction,
- heuristic anomaly detection,
- and reproducible CSV outputs

for validating market data integrity.
