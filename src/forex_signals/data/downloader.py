"""Yahoo Finance data downloader with retry and gap detection."""

import logging
import time
from datetime import datetime, timedelta
from typing import List

import yfinance as yf

from forex_signals.data.models import Candle, Timeframe

logger = logging.getLogger(__name__)


class DataDownloadError(Exception):
    """Raised when data download fails after all retry attempts."""

    pass


# Mapping from Timeframe to expected candle interval as timedelta
_TIMEFRAME_INTERVALS = {
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}


class YahooDataDownloader:
    """Downloads OHLC data from Yahoo Finance."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        """Initialize downloader with retry configuration.

        Args:
            max_retries: Maximum number of download attempts.
            base_delay: Base delay in seconds for exponential backoff.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay

    def download(
        self, pair: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> List[Candle]:
        """Fetch candlestick data from Yahoo Finance.

        Args:
            pair: Forex pair symbol (e.g., "EURUSD=X")
            timeframe: Candle timeframe
            start: Start datetime
            end: End datetime

        Returns:
            List of Candle objects, sorted by timestamp ascending

        Raises:
            DataDownloadError: If download fails after all retry attempts.
        """
        df = self._download_with_retry(pair, timeframe, start, end)

        candles = self._dataframe_to_candles(df)

        if candles:
            self._detect_gaps(candles, timeframe)

        return candles

    def _download_with_retry(self, pair: str, timeframe: Timeframe, start: datetime, end: datetime):
        """Download data with exponential backoff retry.

        Args:
            pair: Forex pair symbol
            timeframe: Candle timeframe
            start: Start datetime
            end: End datetime

        Returns:
            pandas DataFrame with OHLCV data

        Raises:
            DataDownloadError: If all retry attempts fail.
        """
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                ticker = yf.Ticker(pair)
                df = ticker.history(
                    interval=timeframe.value,
                    start=start,
                    end=end,
                )

                if df is None or df.empty:
                    raise DataDownloadError(
                        f"No data returned for {pair} "
                        f"({timeframe.value}, {start} to {end})"
                    )

                return df

            except DataDownloadError:
                raise
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Download attempt %d/%d failed for %s: %s. "
                        "Retrying in %.1fs...",
                        attempt,
                        self.max_retries,
                        pair,
                        str(e),
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "All %d download attempts failed for %s: %s",
                        self.max_retries,
                        pair,
                        str(e),
                    )

        raise DataDownloadError(
            f"Failed to download data for {pair} after {self.max_retries} attempts: "
            f"{last_exception}"
        )

    def _dataframe_to_candles(self, df) -> List[Candle]:
        """Convert a pandas DataFrame to a list of Candle objects.

        Args:
            df: DataFrame with columns Open, High, Low, Close, Volume
                and a DatetimeIndex.

        Returns:
            List of Candle objects sorted by timestamp ascending.
        """
        candles = []
        for timestamp, row in df.iterrows():
            candle = Candle(
                timestamp=timestamp.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
            candles.append(candle)

        # Ensure sorted by timestamp ascending
        candles.sort(key=lambda c: c.timestamp)
        return candles

    def _detect_gaps(self, candles: List[Candle], timeframe: Timeframe) -> None:
        """Detect and log gaps in candle data.

        Compares consecutive candle timestamps against the expected interval
        for the given timeframe and logs any gaps found.

        Args:
            candles: List of candles sorted by timestamp ascending.
            timeframe: The expected timeframe interval.
        """
        expected_interval = _TIMEFRAME_INTERVALS[timeframe]
        gap_count = 0

        for i in range(1, len(candles)):
            actual_diff = candles[i].timestamp - candles[i - 1].timestamp

            # Allow a small tolerance (2x the expected interval) to account
            # for market closures on weekends/holidays for daily timeframes.
            # For intraday, gaps beyond 1.5x are flagged.
            if timeframe == Timeframe.D1:
                threshold = expected_interval * 3  # weekends cause 3-day gaps
            else:
                threshold = expected_interval * 1.5

            if actual_diff > threshold:
                gap_count += 1
                logger.warning(
                    "Data gap detected: %s to %s (expected interval: %s, actual: %s)",
                    candles[i - 1].timestamp.isoformat(),
                    candles[i].timestamp.isoformat(),
                    expected_interval,
                    actual_diff,
                )

        if gap_count > 0:
            logger.info(
                "Total data gaps detected: %d in %d candles",
                gap_count,
                len(candles),
            )
