"""Yahoo Finance data downloader with retry and gap detection."""

import csv
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional

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

# Yahoo Finance restricts how far back intraday data can be requested.
# See: https://help.yahoo.com/kb/finance-for-web/SLN2311.html
# Timeframes not listed here (e.g. D1) have no enforced limit.
_MAX_INTRADAY_RANGE_DAYS = {
    Timeframe.M5: 60,
    Timeframe.M15: 60,
    Timeframe.H1: 730,
    Timeframe.H4: 730,
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
        self,
        pair: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        csv_output_dir: Optional[str] = None,
    ) -> List[Candle]:
        """Fetch candlestick data from Yahoo Finance.

        Args:
            pair: Forex pair symbol (e.g., "EURUSD=X")
            timeframe: Candle timeframe
            start: Start datetime
            end: End datetime
            csv_output_dir: If provided, also write the downloaded candles to a
                CSV file in this directory (created if missing). CSV export is
                best-effort: failures are logged as warnings and do not raise.

        Returns:
            List of Candle objects, sorted by timestamp ascending

        Raises:
            DataDownloadError: If download fails after all retry attempts.
        """
        self._validate_date_range(timeframe, start, end)

        df = self._download_with_retry(pair, timeframe, start, end)

        candles = self._dataframe_to_candles(df)

        if candles:
            self._detect_gaps(candles, timeframe)

        if csv_output_dir:
            try:
                csv_path = self.export_to_csv(
                    candles, pair, timeframe, start, end, csv_output_dir
                )
                logger.info("Candles exported to CSV: %s", csv_path)
            except OSError as e:
                logger.warning("Failed to export candles to CSV: %s", e)

        return candles

    def get_csv_path(
        self,
        pair: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        output_dir: str,
    ) -> str:
        """Compute the CSV file path for a given pair/timeframe/date range.

        The filename is derived from the pair, timeframe, and date range, e.g.
        "EURUSDX_M5_20260601_20260729.csv" (the pair symbol is sanitized for
        filesystem safety, e.g. "=" is stripped). This does not check whether
        the file exists or create the output directory.

        Args:
            pair: Forex pair symbol (used to build the filename).
            timeframe: Candle timeframe (used to build the filename).
            start: Range start (used to build the filename).
            end: Range end (used to build the filename).
            output_dir: Directory the CSV file would be written into.

        Returns:
            The (not necessarily existing) CSV file path.
        """
        sanitized_pair = re.sub(r"[^A-Za-z0-9]", "", pair)
        filename = (
            f"{sanitized_pair}_{timeframe.name}_"
            f"{start:%Y%m%d}_{end:%Y%m%d}.csv"
        )
        return os.path.join(output_dir, filename)

    def export_to_csv(
        self,
        candles: List[Candle],
        pair: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        output_dir: str,
    ) -> str:
        """Write candles to a CSV file with columns timestamp, open, high, low, close, volume.

        The filename is derived from the pair, timeframe, and date range, e.g.
        "EURUSDX_M5_20260601_20260729.csv" (the pair symbol is sanitized for
        filesystem safety, e.g. "=" is stripped).

        Args:
            candles: Candles to write.
            pair: Forex pair symbol (used to build the filename).
            timeframe: Candle timeframe (used to build the filename).
            start: Range start (used to build the filename).
            end: Range end (used to build the filename).
            output_dir: Directory to write the CSV file into.

        Returns:
            The absolute path of the written CSV file.

        Raises:
            OSError: If the output directory cannot be created or the file
                cannot be written.
        """
        os.makedirs(output_dir, exist_ok=True)

        path = self.get_csv_path(pair, timeframe, start, end, output_dir)

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for candle in candles:
                writer.writerow(
                    [
                        candle.timestamp.isoformat(),
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                    ]
                )

        return os.path.abspath(path)

    def load_from_csv(self, path: str) -> List[Candle]:
        """Read previously exported candles back from a CSV file.

        Args:
            path: Path to a CSV file written by export_to_csv.

        Returns:
            List of Candle objects, sorted by timestamp ascending.

        Raises:
            DataDownloadError: If the file cannot be read or contains invalid data.
        """
        candles = []
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    candles.append(
                        Candle(
                            timestamp=datetime.fromisoformat(row["timestamp"]),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )
                    )
        except (OSError, ValueError, KeyError) as e:
            raise DataDownloadError(f"Failed to read cached CSV file '{path}': {e}")

        candles.sort(key=lambda c: c.timestamp)
        return candles

    def _validate_date_range(self, timeframe: Timeframe, start: datetime, end: datetime) -> None:
        """Reject date ranges that Yahoo Finance cannot serve for the given timeframe.

        Yahoo Finance limits how far back intraday candles can be requested
        (e.g. 60 days for 5m/15m data). Requests outside this window fail with
        a confusing "possibly delisted" error, so we raise a clear message
        up front instead.

        Args:
            timeframe: Candle timeframe.
            start: Start datetime.
            end: End datetime.

        Raises:
            DataDownloadError: If the requested range exceeds Yahoo Finance's
                limit for the given timeframe.
        """
        max_days = _MAX_INTRADAY_RANGE_DAYS.get(timeframe)
        if max_days is None:
            return

        requested_days = (end - start).days
        if requested_days > max_days:
            raise DataDownloadError(
                f"Yahoo Finance only provides '{timeframe.name}' ({timeframe.value}) "
                f"intraday data for the last {max_days} days, but the requested range "
                f"is {requested_days} days ({start.date()} to {end.date()}). "
                f"Reduce the backtest date range or use a longer timeframe (e.g. H1 or D1) "
                f"for a longer backtest period."
            )

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
