"""Tests for the Yahoo Finance data downloader."""

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from forex_signals.data.downloader import (
    DataDownloadError,
    YahooDataDownloader,
    _TIMEFRAME_INTERVALS,
)
from forex_signals.data.models import Candle, Timeframe


def _make_ohlcv_dataframe(
    start: datetime, timeframe: Timeframe, num_candles: int
) -> pd.DataFrame:
    """Helper to create a mock OHLCV DataFrame."""
    interval = _TIMEFRAME_INTERVALS[timeframe]
    timestamps = [start + interval * i for i in range(num_candles)]
    index = pd.DatetimeIndex(timestamps)
    data = {
        "Open": [1.1000 + i * 0.0001 for i in range(num_candles)],
        "High": [1.1010 + i * 0.0001 for i in range(num_candles)],
        "Low": [1.0990 + i * 0.0001 for i in range(num_candles)],
        "Close": [1.1005 + i * 0.0001 for i in range(num_candles)],
        "Volume": [1000.0 + i for i in range(num_candles)],
    }
    return pd.DataFrame(data, index=index)


class TestYahooDataDownloaderDownload:
    """Tests for the download method."""

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_successful_download_returns_candles(self, mock_ticker_cls):
        """Test that a successful download returns a list of Candle objects."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 10, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 12)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        candles = downloader.download("EURUSD=X", Timeframe.M5, start, end)

        assert len(candles) == 12
        assert all(isinstance(c, Candle) for c in candles)
        mock_ticker_cls.assert_called_once_with("EURUSD=X")
        mock_ticker.history.assert_called_once_with(
            interval="5m", start=start, end=end
        )

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_candles_sorted_by_timestamp(self, mock_ticker_cls):
        """Test that returned candles are sorted by timestamp ascending."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 10, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 5)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        candles = downloader.download("EURUSD=X", Timeframe.M5, start, end)

        for i in range(1, len(candles)):
            assert candles[i].timestamp > candles[i - 1].timestamp

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_candle_fields_mapped_correctly(self, mock_ticker_cls):
        """Test that OHLCV data is correctly mapped to Candle fields."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 9, 5)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 1)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        candles = downloader.download("EURUSD=X", Timeframe.M5, start, end)

        assert len(candles) == 1
        c = candles[0]
        assert c.timestamp == start
        assert c.open == pytest.approx(1.1000)
        assert c.high == pytest.approx(1.1010)
        assert c.low == pytest.approx(1.0990)
        assert c.close == pytest.approx(1.1005)
        assert c.volume == pytest.approx(1000.0)

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_empty_dataframe_raises_error(self, mock_ticker_cls):
        """Test that empty DataFrame raises DataDownloadError."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        with pytest.raises(DataDownloadError, match="No data returned"):
            downloader.download(
                "EURUSD=X",
                Timeframe.M5,
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
            )


class TestRetryBehavior:
    """Tests for retry with exponential backoff."""

    @patch("forex_signals.data.downloader.time.sleep")
    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_retries_on_exception(self, mock_ticker_cls, mock_sleep):
        """Test that transient failures trigger retries."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 10, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 5)

        mock_ticker = MagicMock()
        # Fail twice, succeed on third attempt
        mock_ticker.history.side_effect = [
            RuntimeError("Connection timeout"),
            RuntimeError("Connection timeout"),
            df,
        ]
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader(max_retries=3, base_delay=1.0)
        candles = downloader.download("EURUSD=X", Timeframe.M5, start, end)

        assert len(candles) == 5
        assert mock_ticker.history.call_count == 3
        # Check exponential backoff delays: 1s, 2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch("forex_signals.data.downloader.time.sleep")
    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_raises_after_max_retries(self, mock_ticker_cls, mock_sleep):
        """Test that DataDownloadError is raised after all retries are exhausted."""
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = RuntimeError("Network error")
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader(max_retries=3, base_delay=1.0)
        with pytest.raises(DataDownloadError, match="Failed to download.*3 attempts"):
            downloader.download(
                "EURUSD=X",
                Timeframe.H1,
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
            )

        assert mock_ticker.history.call_count == 3

    @patch("forex_signals.data.downloader.time.sleep")
    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_no_retry_on_empty_data(self, mock_ticker_cls, mock_sleep):
        """Test that DataDownloadError from empty data is not retried."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader(max_retries=3, base_delay=1.0)
        with pytest.raises(DataDownloadError, match="No data returned"):
            downloader.download(
                "EURUSD=X",
                Timeframe.M5,
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
            )

        # Should not retry - only 1 attempt
        assert mock_ticker.history.call_count == 1
        mock_sleep.assert_not_called()


class TestGapDetection:
    """Tests for data gap detection and logging."""

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_no_gaps_no_warnings(self, mock_ticker_cls, caplog):
        """Test that continuous data produces no gap warnings."""
        start = datetime(2024, 1, 2, 9, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 10)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        with caplog.at_level(logging.WARNING, logger="forex_signals.data.downloader"):
            downloader.download(
                "EURUSD=X",
                Timeframe.M5,
                start,
                start + timedelta(minutes=50),
            )

        gap_warnings = [r for r in caplog.records if "Data gap detected" in r.message]
        assert len(gap_warnings) == 0

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_gap_detected_and_logged(self, mock_ticker_cls, caplog):
        """Test that a gap in candle data is detected and logged."""
        start = datetime(2024, 1, 2, 9, 0)
        interval = timedelta(minutes=5)

        # Create candles with a gap (skip candle at index 3)
        timestamps = [
            start,
            start + interval,
            start + interval * 2,
            # gap here - missing candle at start + 15min
            start + interval * 5,  # jump to 25min
            start + interval * 6,
        ]
        index = pd.DatetimeIndex(timestamps)
        data = {
            "Open": [1.1] * 5,
            "High": [1.11] * 5,
            "Low": [1.09] * 5,
            "Close": [1.105] * 5,
            "Volume": [1000.0] * 5,
        }
        df = pd.DataFrame(data, index=index)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        with caplog.at_level(logging.WARNING, logger="forex_signals.data.downloader"):
            candles = downloader.download(
                "EURUSD=X",
                Timeframe.M5,
                start,
                start + timedelta(minutes=30),
            )

        assert len(candles) == 5
        gap_warnings = [r for r in caplog.records if "Data gap detected" in r.message]
        assert len(gap_warnings) == 1

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_daily_weekend_gap_not_flagged(self, mock_ticker_cls, caplog):
        """Test that normal weekend gaps in daily data are not flagged."""
        # Friday to Monday is a 3-day gap but expected for daily data
        timestamps = [
            datetime(2024, 1, 5),  # Friday
            datetime(2024, 1, 8),  # Monday (3-day gap)
            datetime(2024, 1, 9),  # Tuesday
        ]
        index = pd.DatetimeIndex(timestamps)
        data = {
            "Open": [1.1] * 3,
            "High": [1.11] * 3,
            "Low": [1.09] * 3,
            "Close": [1.105] * 3,
            "Volume": [1000.0] * 3,
        }
        df = pd.DataFrame(data, index=index)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        with caplog.at_level(logging.WARNING, logger="forex_signals.data.downloader"):
            downloader.download(
                "EURUSD=X",
                Timeframe.D1,
                datetime(2024, 1, 5),
                datetime(2024, 1, 10),
            )

        gap_warnings = [r for r in caplog.records if "Data gap detected" in r.message]
        assert len(gap_warnings) == 0
