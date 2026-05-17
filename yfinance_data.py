"""Download yFinance market data exports.

This module downloads daily prices, dividend events, and split events from
``yFinance`` for the ticker/date configuration supplied to ``YFinanceData``.

The module writes flat CSV files that are intended to be consumed by downstream
audit and comparison code.

yFinance does not require an API key, so there is no API key to load from a
``.env`` file in this module.
"""

# Errors to ignore.
# pylint: disable=broad-exception-caught
# pyright: reportAssignmentType=false
# pyright: reportMissingTypeStubs=false

# Standard library imports
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

# Third-party imports
import pandas as pd
import polars as pl
import yfinance as yf

# Project imports
import audit_schema as schema
import utilities as util


class YFinanceData:
    """Download and load yFinance market data exports.

    This class downloads and loads:

    - Dividend events
    - Daily OHLCV prices
    - Stock split events

    Data is downloaded from yFinance and written to CSV files for
    downstream ETL, auditing, and comparison workflows.

    Attributes:
        tickers:
            Sequence of ticker symbols to process.

        from_date:
            Inclusive start date in ``YYYY-MM-DD`` format.

        to_date:
            Inclusive end date in ``YYYY-MM-DD`` format.

        always_download:
            Whether to force re-download even if CSV files already exist.

        dividends:
            LazyFrame containing dividend events.

        ohlcv:
            LazyFrame containing OHLCV prices.

        splits:
            LazyFrame containing stock split events.
    """

    def __init__(
        self, tickers: Sequence[str], from_date: str, to_date: str, always_download: bool = False
    ) -> None:
        """Initialize YFinanceData and load all datasets.

        Args:
            tickers:
                Sequence of ticker symbols.

            from_date:
                Inclusive start date in ``YYYY-MM-DD`` format.

            to_date:
                Inclusive end date in ``YYYY-MM-DD`` format.

            always_download:
                Whether to force downloading even if local CSV files
                already exist.
        """
        # Set self parameters
        self.tickers = tickers
        self.from_date = from_date
        self.to_date = to_date
        self.always_download = always_download

        # Set self data LazyFrames
        self.dividends = self._load_dividends()
        self.ohlcv = self._load_ohlcv()
        self.splits = self._load_splits()

    def _file_path(self, base_file_path: str) -> str:
        """Build a date-specific CSV file path.

        Args:
            base_file_path:
                Base file path without date suffixes.

        Returns:
            File path with appended date range suffixes.
        """
        return f"{base_file_path}.{self.from_date}.{self.to_date}.csv"

    def _inclusive_yfinance_end_date(self) -> str:
        """Return the yFinance end date needed to include ``self.to_date``.

        yFinance treats the ``end`` argument as exclusive for price downloads. This
        function adds one day to ``self.to_date`` so the configured ``to_date`` is
        included in the downloaded prices.

        Returns:
            Date string formatted as ``YYYY-MM-DD``.

        Raises:
            ValueError: If ``self.to_date`` is not formatted as ``YYYY-MM-DD``.
        """
        to_date: datetime = datetime.strptime(self.to_date, "%Y-%m-%d")
        inclusive_end_date: datetime = to_date + timedelta(days=1)

        return inclusive_end_date.strftime("%Y-%m-%d")

    def _load_dividends(self) -> pl.LazyFrame:
        """Fetch yFinance dividend events for configured tickers and write to CSV.

        This function downloads dividend events exposed by yfinance for each ticker
        in ``self.tickers`` and filters them to the inclusive range
        ``self.from_date`` through ``self.to_date``. One CSV row is written per
        dividend event.

        The output file path is built from ``util.PATH_YFINANCE_DIVIDENDS``.

        Returns:
            LazyFrame containing dividend event data.

        Raises:
            ValueError: If ``util.normalize_ticker()`` rejects a ticker.
            RuntimeError: If yfinance retrieval or CSV writing fails.
        """
        # Define the CSV schema explicitly so downstream ETL receives stable column
        # names and a stable column order.
        fieldnames: list[str] = [
            "ticker",
            "ex_dividend_date",
            "cash_amount",
        ]

        # Download the data.
        file_path = self._file_path(schema.PATH_YFINANCE_DIVIDENDS)
        if self.always_download or not Path(file_path).exists():
            print("\n#################### Downloading yFinance Dividends...")
            with util.safe_csv_dict_writer(file_path, fieldnames) as writer:
                # Write one dummy row so downstream schema inference correctly identifies
                # numeric fields as numeric.  Without this row, downstream processing may infer
                # numeric fields as strings and fail during arithmetic.
                writer.writerow(
                    {
                        "ticker": schema.DUMMY_TICKER,
                        "ex_dividend_date": schema.DUMMY_DATE,
                        "cash_amount": 0,
                    }
                )

                # Process each ticker independently so one failing ticker can be reported
                # with clear ticker-specific context.
                for ticker in self.tickers:
                    normalized_ticker: str = util.normalize_ticker(ticker)

                    try:
                        # ticker_object.dividends is a pandas Series:
                        #     index -> ex-dividend timestamp
                        #     value -> dividend cash amount
                        ticker_object: yf.Ticker = yf.Ticker(normalized_ticker)

                        # Filter the dividend Series to the configured inclusive date
                        # range before writing rows.
                        filtered_dividends: pd.Series = ticker_object.dividends.loc[
                            self.from_date : self.to_date
                        ]

                        for ex_dividend_timestamp, cash_amount in filtered_dividends.items():
                            assert isinstance(ex_dividend_timestamp, pd.Timestamp)  # For lint.

                            ex_dividend_date: str = ex_dividend_timestamp.strftime("%Y-%m-%d")

                            writer.writerow(
                                {
                                    "ticker": normalized_ticker,
                                    "ex_dividend_date": ex_dividend_date,
                                    "cash_amount": float(cash_amount),
                                }
                            )

                    except Exception as exc:
                        raise RuntimeError(
                            f"Failed fetching yFinance dividends for ticker {normalized_ticker}"
                        ) from exc

        # Return the LazyFrame
        return pl.scan_csv(file_path)

    def _load_ohlcv(self) -> pl.LazyFrame:
        """Fetch yFinance daily OHLCV bars for configured tickers and write to CSV.

        This function downloads daily price bars from yfinance for each ticker in
        ``self.tickers`` using ``self.from_date`` and ``self.to_date``. Prices are
        requested with ``auto_adjust=False``, so both raw close and adjusted close
        are written.

        One CSV row is written per ticker/date daily bar.

        The output file path is built from ``util.PATH_YFINANCE_PRICES``.

        Note:
            yfinance's ``end`` date is treated as exclusive for price downloads.

        Returns:
            LazyFrame containing OHLCV data.

        Raises:
            ValueError: If ``util.normalize_ticker()`` rejects a ticker.
        """
        # Define the CSV schema explicitly so downstream ETL receives stable column
        # names and a stable column order.
        fieldnames: list[str] = [
            "ticker",
            "date",
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
        ]

        # Download the data.
        file_path = self._file_path(schema.PATH_YFINANCE_PRICES)
        if self.always_download or not Path(file_path).exists():
            print("\n#################### Downloading yFinance OHLCV...")
            with util.safe_csv_dict_writer(file_path, fieldnames) as writer:
                # Process each ticker independently so one failing ticker can be reported
                # with clear ticker-specific context.
                for ticker in self.tickers:
                    normalized_ticker: str = util.normalize_ticker(ticker)

                    try:
                        # yFinance treats end as exclusive, so the helper adds one day
                        # to self.to_date before making the request.
                        data: pd.DataFrame = (
                            yf.download(  # pyright: ignore[reportUnknownMemberType]
                                normalized_ticker,
                                start=self.from_date,
                                end=self._inclusive_yfinance_end_date(),
                                interval="1d",
                                auto_adjust=False,
                                progress=False,
                                multi_level_index=False,
                            )
                        )

                        if data.empty:
                            raise RuntimeError(
                                f"yFinance returned no price data for ticker {normalized_ticker}"
                            )

                        for timestamp, row in data.iterrows():
                            assert isinstance(timestamp, pd.Timestamp)  # For lint.

                            date: str = timestamp.strftime("%Y-%m-%d")

                            writer.writerow(
                                {
                                    "ticker": normalized_ticker,
                                    "date": date,
                                    "open": float(row["Open"]),
                                    "high": float(row["High"]),
                                    "low": float(row["Low"]),
                                    "close": float(row["Close"]),
                                    "adjusted_close": float(row["Adj Close"]),
                                    "volume": int(row["Volume"]),
                                }
                            )

                    except Exception as exc:
                        # yFinance seems to fail on random tickers between 1PM PDT and 4PM PDT,
                        # probably because everybody is pounding away at it.  So just print the
                        # error and continue.  Missing a few tickers is not that big of a deal and
                        # is much better than failing completely.
                        print(
                            f"Failed fetching yFinance prices for ticker {normalized_ticker}:  "
                            f"{str(exc)}"
                        )

        # Return the LazyFrame
        return pl.scan_csv(file_path)

    def _load_splits(self) -> pl.LazyFrame:
        """Fetch yFinance split events for configured tickers and write to CSV.

        This function downloads split events exposed by yfinance for each ticker in
        ``self.tickers`` and filters them to the inclusive range ``self.from_date``
        through ``self.to_date``. One CSV row is written per split event.

        The output file path is built from ``util.PATH_YFINANCE_SPLITS``.

        Returns:
            LazyFrame containing split event data.

        Raises:
            ValueError: If ``util.normalize_ticker()`` rejects a ticker.
            RuntimeError: If yfinance retrieval or CSV writing fails.
        """
        # Define the CSV schema explicitly so downstream ETL receives stable column
        # names and a stable column order.
        fieldnames: list[str] = [
            "ticker",
            "execution_date",
            "split_ratio",
        ]

        # Download the data.
        file_path = self._file_path(schema.PATH_YFINANCE_SPLITS)
        if self.always_download or not Path(file_path).exists():
            print("\n#################### Downloading yFinance Splits...")
            with util.safe_csv_dict_writer(file_path, fieldnames) as writer:
                # Need at least one row to make sure the schema is known. Otherwise the
                # downstream code will assume split fields are strings and fail when
                # trying to do arithmetic.
                writer.writerow(
                    {
                        "ticker": schema.DUMMY_TICKER,
                        "execution_date": schema.DUMMY_DATE,
                        "split_ratio": 0,
                    }
                )

                # Process each ticker independently so one failing ticker can be reported
                # with clear ticker-specific context.
                for ticker in self.tickers:
                    normalized_ticker: str = util.normalize_ticker(ticker)

                    try:
                        # ticker_object.splits is a pandas Series:
                        #     index -> split execution timestamp
                        #     value -> split ratio
                        #
                        # Examples:
                        #     4.0 -> 4-for-1 split
                        #     0.5 -> 1-for-2 reverse split
                        ticker_object: yf.Ticker = yf.Ticker(normalized_ticker)

                        # Filter the split Series to the configured inclusive date
                        # range before writing rows.
                        filtered_splits: pd.Series = ticker_object.splits.loc[
                            self.from_date : self.to_date
                        ]

                        for execution_timestamp, split_ratio in filtered_splits.items():
                            assert isinstance(execution_timestamp, pd.Timestamp)  # For lint.

                            execution_date: str = execution_timestamp.strftime("%Y-%m-%d")

                            writer.writerow(
                                {
                                    "ticker": normalized_ticker,
                                    "execution_date": execution_date,
                                    "split_ratio": float(split_ratio),
                                }
                            )

                    except Exception as exc:
                        raise RuntimeError(
                            f"Failed fetching yFinance splits for ticker {normalized_ticker}"
                        ) from exc

        # Return the LazyFrame
        return pl.scan_csv(file_path)
