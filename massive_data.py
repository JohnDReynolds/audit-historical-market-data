"""Download Massive market data exports.

This module downloads daily prices, dividend events, and split events from
Massive for the ticker/date configuration supplied to ``MassiveData``.

The module writes flat CSV files intended for downstream audit,
comparison, and analytics workflows.
"""

# Errors to ignore.
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

# Standard library imports.
import os
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Third-party imports.
import polars as pl
from dotenv import load_dotenv
from massive import RESTClient

# Project imports.
import utilities as util

# ============================================================================
# Constants
# ============================================================================

_API_KEY_ENV_VAR: str = "MASSIVE_API_KEY"

# Load MASSIVE_API_KEY from local .env file.
load_dotenv()

_API_KEY: str | None = os.getenv(_API_KEY_ENV_VAR)

if not _API_KEY:
    raise RuntimeError(f"Environment variable {_API_KEY_ENV_VAR} is required for Massive access.")

# Create one reusable REST client instance.
_CLIENT: RESTClient = RESTClient(_API_KEY)


class MassiveData:
    """Download and load Massive market data exports.

    This class downloads and loads:

    - Dividend events
    - Daily OHLCV prices
    - Stock split events

    Data is downloaded from Massive and written to CSV files for
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

        adjusted_ohlcv:
            LazyFrame containing split-adjusted OHLCV prices.

        unadjusted_ohlcv:
            LazyFrame containing raw/unadjusted OHLCV prices.

        splits:
            LazyFrame containing stock split events.
    """

    def __init__(
        self,
        tickers: Sequence[str],
        from_date: str,
        to_date: str,
        always_download: bool = False,
    ) -> None:
        """Initialize MassiveData and load all datasets.

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
        # Store constructor parameters.
        self.tickers = tickers
        self.from_date = from_date
        self.to_date = to_date
        self.always_download = always_download

        # Load datasets.
        self.dividends = self._load_dividends()
        self.adjusted_ohlcv = self._load_ohlcv(True)
        self.unadjusted_ohlcv = self._load_ohlcv(False)
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

    @staticmethod
    def _format_date(
        agg: Any,
        normalized_ticker: str,
    ) -> str:
        """Convert Massive aggregate timestamp into UTC date string.

        Massive aggregate timestamps are expected to be Unix epoch
        milliseconds.

        Args:
            agg:
                Massive aggregate row object.

            normalized_ticker:
                Normalized ticker symbol used only for clearer
                error messages.

        Returns:
            UTC date string formatted as ``YYYY-MM-DD``.

        Raises:
            RuntimeError:
                Raised if the aggregate row has no timestamp or the
                timestamp cannot be converted into a valid Unix epoch
                millisecond value.
        """
        timestamp_ms: Any = getattr(agg, "timestamp", None)

        if timestamp_ms is None:
            raise RuntimeError(
                f"Massive aggregate row missing timestamp " f"for ticker {normalized_ticker}"
            )

        try:
            return datetime.fromtimestamp(
                float(timestamp_ms) / 1000.0,
                tz=UTC,
            ).strftime("%Y-%m-%d")

        except Exception as exc:
            raise RuntimeError(
                f"Invalid Massive aggregate timestamp "
                f"{timestamp_ms!r} for ticker {normalized_ticker}"
            ) from exc

    def _load_dividends(self) -> pl.LazyFrame:
        """Download Massive dividend events and return LazyFrame.

        This function downloads dividend events using the Massive
        ``list_dividends()`` endpoint for all configured tickers.

        Results are written to a flat CSV file and returned as a
        Polars LazyFrame.

        Returns:
            LazyFrame containing dividend event data.

        Raises:
            ValueError:
                Raised if ``util.normalize_ticker()`` rejects a ticker.

            RuntimeError:
                Raised if Massive retrieval or CSV writing fails.
        """
        # Define CSV schema explicitly.
        #
        # Keeping the schema stable is important for:
        # - downstream ETL
        # - reproducibility
        # - auditing
        # - database loading
        fieldnames: list[str] = [
            "ticker",
            "ex_dividend_date",
            "pay_date",
            "record_date",
            "declaration_date",
            "cash_amount",
            "frequency",
            "dividend_type",
        ]

        file_path: str = self._file_path(util.PATH_MASSIVE_DIVIDENDS)

        # Download data only if needed.
        if self.always_download or not Path(file_path).exists():
            print("\n#################### Downloading Massive Dividends...")

            with util.safe_csv_dict_writer(file_path, fieldnames) as writer:
                # Write one dummy row so downstream schema inference correctly identifies
                # numeric fields as numeric.  Without this row, downstream processing may infer
                # numeric fields as strings and fail during arithmetic.
                writer.writerow(
                    {
                        "ticker": util.DUMMY_TICKER,
                        "ex_dividend_date": util.DUMMY_DATE,
                        "pay_date": util.DUMMY_DATE,
                        "record_date": util.DUMMY_DATE,
                        "declaration_date": util.DUMMY_DATE,
                        "cash_amount": 0,
                        "frequency": 0,
                        "dividend_type": "",
                    }
                )

                # Process each ticker independently.  Streaming rows directly keeps memory usage
                # low and scales better for large universes.
                for ticker in self.tickers:
                    normalized_ticker: str = util.normalize_ticker(ticker)

                    try:
                        dividends_iterable: Iterable[Any] = _CLIENT.list_dividends(
                            ticker=normalized_ticker,
                            ex_dividend_date_gte=self.from_date,
                            ex_dividend_date_lte=self.to_date,
                        )

                        for dividend in dividends_iterable:
                            writer.writerow(
                                {
                                    "ticker": normalized_ticker,
                                    "ex_dividend_date": getattr(
                                        dividend,
                                        "ex_dividend_date",
                                        None,
                                    ),
                                    "pay_date": getattr(
                                        dividend,
                                        "pay_date",
                                        None,
                                    ),
                                    "record_date": getattr(
                                        dividend,
                                        "record_date",
                                        None,
                                    ),
                                    "declaration_date": getattr(
                                        dividend,
                                        "declaration_date",
                                        None,
                                    ),
                                    "cash_amount": getattr(
                                        dividend,
                                        "cash_amount",
                                        None,
                                    ),
                                    "frequency": getattr(
                                        dividend,
                                        "frequency",
                                        None,
                                    ),
                                    "dividend_type": getattr(
                                        dividend,
                                        "dividend_type",
                                        None,
                                    ),
                                }
                            )

                    except Exception as exc:
                        raise RuntimeError(
                            f"Failed fetching dividends for ticker " f"{normalized_ticker}"
                        ) from exc

        return pl.scan_csv(file_path)

    def _load_ohlcv(self, adjusted: bool) -> pl.LazyFrame:
        """Download Massive OHLCV aggregate bars and return LazyFrame.

        This function downloads daily OHLCV aggregate bars using the
        Massive ``list_aggs()`` endpoint.

        Results are written to a flat CSV file and returned as a
        Polars LazyFrame.

        Notes:
            - ``adjusted=True`` means split-adjusted prices.
            - ``adjusted=False`` means raw/unadjusted prices.
            - Dividend adjustments are NOT included.
            - Massive automatically handles pagination internally.

        Args:
            adjusted:
                Whether to request split-adjusted prices.

        Returns:
            LazyFrame containing OHLCV data.

        Raises:
            ValueError:
                Raised if ``util.normalize_ticker()`` rejects a ticker.

            RuntimeError:
                Raised if Massive retrieval or CSV writing fails.
        """
        # Define CSV schema explicitly.
        #
        # Keeping the schema stable is important for:
        # - downstream ETL
        # - reproducibility
        # - auditing
        # - database loading
        fieldnames: list[str] = [
            "ticker",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vwap",
            "transactions",
        ]

        file_path: str = self._file_path(
            (
                util.PATH_MASSIVE_ADJUSTED_PRICES
                if adjusted
                else util.PATH_MASSIVE_UNADJUSTED_PRICES
            )
        )

        # Download data only if needed.
        if self.always_download or not Path(file_path).exists():
            print(f"\n#################### Downloading Massive " f"OHLCV: Adjusted={adjusted}...")

            with util.safe_csv_dict_writer(file_path, fieldnames) as writer:
                # Process each ticker independently.
                #
                # Streaming rows directly:
                # - reduces memory usage
                # - avoids loading huge datasets into RAM
                # - scales better
                for ticker in self.tickers:
                    normalized_ticker: str = util.normalize_ticker(ticker)

                    try:
                        # Massive internally handles pagination.
                        aggs_iterable: Iterable[Any] = _CLIENT.list_aggs(
                            ticker=normalized_ticker,
                            multiplier=1,
                            timespan="day",
                            from_=self.from_date,
                            to=self.to_date,
                            adjusted=adjusted,
                        )

                        for agg in aggs_iterable:
                            # Massive timestamps are Unix epoch
                            # milliseconds UTC.
                            #
                            # Convert to YYYY-MM-DD UTC string for:
                            # - readability
                            # - portability
                            # - database friendliness
                            date: str = MassiveData._format_date(
                                agg,
                                normalized_ticker,
                            )

                            # Use getattr(..., None) defensively because:
                            # - fields may be absent
                            # - API schemas may evolve
                            # - avoids AttributeError failures
                            writer.writerow(
                                {
                                    "ticker": normalized_ticker,
                                    "date": date,
                                    "open": getattr(agg, "open", None),
                                    "high": getattr(agg, "high", None),
                                    "low": getattr(agg, "low", None),
                                    "close": getattr(agg, "close", None),
                                    "volume": getattr(agg, "volume", None),
                                    "vwap": getattr(agg, "vwap", None),
                                    "transactions": getattr(
                                        agg,
                                        "transactions",
                                        None,
                                    ),
                                }
                            )

                    except Exception as exc:
                        # Add ticker context to exceptions.
                        #
                        # This makes debugging much easier when processing
                        # large ticker universes.
                        raise RuntimeError(
                            f"Failed fetching OHLCV aggregates " f"for ticker {normalized_ticker}"
                        ) from exc

        return pl.scan_csv(file_path).with_columns(pl.col("date").str.to_date())

    def _load_splits(self) -> pl.LazyFrame:
        """Download Massive stock split events and return LazyFrame.

        This function downloads stock split events using the Massive
        ``list_splits()`` endpoint for all configured tickers.

        Results are written to a flat CSV file and returned as a
        Polars LazyFrame.

        Returns:
            LazyFrame containing split event data.

        Raises:
            ValueError:
                Raised if ``util.normalize_ticker()`` rejects a ticker.

            RuntimeError:
                Raised if Massive retrieval or CSV writing fails.
        """
        # Define CSV schema explicitly.
        #
        # Keeping the schema stable is important for:
        # - downstream ETL
        # - reproducibility
        # - auditing
        # - database loading
        fieldnames: list[str] = [
            "ticker",
            "execution_date",
            "split_from",
            "split_to",
        ]

        file_path: str = self._file_path(util.PATH_MASSIVE_SPLITS)

        # Download data only if needed.
        if self.always_download or not Path(file_path).exists():
            print("\n#################### Downloading Massive Splits...")

            with util.safe_csv_dict_writer(file_path, fieldnames) as writer:
                # Write one dummy row so downstream schema inference correctly identifies
                # numeric fields as numeric.  Without this row, downstream processing may infer
                # numeric fields as strings and fail during arithmetic.
                writer.writerow(
                    {
                        "ticker": util.DUMMY_TICKER,
                        "execution_date": util.DUMMY_DATE,
                        "split_from": 0,
                        "split_to": 0,
                    }
                )

                # Process each ticker independently.
                for ticker in self.tickers:
                    normalized_ticker: str = util.normalize_ticker(ticker)

                    try:
                        splits_iterable: Iterable[Any] = _CLIENT.list_splits(
                            ticker=normalized_ticker,
                            execution_date_gte=self.from_date,
                            execution_date_lte=self.to_date,
                        )

                        for split in splits_iterable:
                            writer.writerow(
                                {
                                    "ticker": normalized_ticker,
                                    "execution_date": getattr(
                                        split,
                                        "execution_date",
                                        None,
                                    ),
                                    "split_from": getattr(
                                        split,
                                        "split_from",
                                        None,
                                    ),
                                    "split_to": getattr(
                                        split,
                                        "split_to",
                                        None,
                                    ),
                                }
                            )

                    except Exception as exc:
                        raise RuntimeError(
                            f"Failed fetching splits for ticker " f"{normalized_ticker}"
                        ) from exc

        return pl.scan_csv(file_path)
