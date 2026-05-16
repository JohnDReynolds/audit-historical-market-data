"""Input-column validation helpers for audit calculations."""

# Third-party imports.
import polars as pl

# Project imports.
import real_world_events
from massive_data import MassiveData
import utilities as util
from yfinance_data import YFinanceData


def require_audit_returns_columns(
    massive_data: MassiveData,
    yfinance_data: YFinanceData,
    real_world_events_path: str,
    has_real_world_events_file: bool,
) -> None:
    """Validate all columns required by return-audit calculations.

    Args:
        massive_data:
            Loaded Massive data wrapper.

        yfinance_data:
            Loaded yFinance data wrapper.

        real_world_events_path:
            Path to the optional real-world events CSV.

        has_real_world_events_file:
            Whether the optional real-world events CSV exists.

    Raises:
        ValueError:
            Raised if any required input columns are missing.
    """
    required_ohlcv_columns: set[str] = {
        "ticker",
        "date",
        "close",
    }
    required_splits_columns: set[str] = {
        "ticker",
        "execution_date",
        "split_from",
        "split_to",
    }
    required_dividends_columns: set[str] = {
        "ticker",
        "ex_dividend_date",
        "cash_amount",
    }
    required_yfinance_columns: set[str] = {
        "ticker",
        "date",
        "close",
        "adjusted_close",
    }
    required_yfinance_splits_columns: set[str] = {
        "ticker",
        "execution_date",
        "split_ratio",
    }
    required_yfinance_dividends_columns: set[str] = {
        "ticker",
        "ex_dividend_date",
        "cash_amount",
    }

    if has_real_world_events_file:
        real_world_events_raw_lf: pl.LazyFrame = pl.scan_csv(real_world_events_path)

        util.require_lazy_columns(
            real_world_events_raw_lf,
            real_world_events.REQUIRED_REAL_WORLD_EVENT_COLUMNS,
            "real-world events CSV",
        )

    # Fail early if any input file is missing columns required by the audit.
    util.require_lazy_columns(
        massive_data.unadjusted_ohlcv,
        required_ohlcv_columns,
        "unadjusted prices CSV",
    )
    util.require_lazy_columns(
        massive_data.splits,
        required_splits_columns,
        "splits CSV",
    )
    util.require_lazy_columns(
        massive_data.dividends,
        required_dividends_columns,
        "dividends CSV",
    )
    util.require_lazy_columns(
        yfinance_data.ohlcv,
        required_yfinance_columns,
        "yFinance prices CSV",
    )
    util.require_lazy_columns(
        yfinance_data.splits,
        required_yfinance_splits_columns,
        "yFinance splits CSV",
    )
    util.require_lazy_columns(
        yfinance_data.dividends,
        required_yfinance_dividends_columns,
        "yFinance dividends CSV",
    )
