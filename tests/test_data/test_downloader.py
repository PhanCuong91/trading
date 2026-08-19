"""Tests for the Yahoo Finance data downloader."""

import csv
import logging
import os
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


class TestExportToCsv:
    """Tests for YahooDataDownloader.export_to_csv."""

    def _make_candles(self):
        start = datetime(2024, 1, 2, 9, 0)
        return [
            Candle(
                timestamp=start + timedelta(minutes=5 * i),
                open=1.1000 + i * 0.0001,
                high=1.1010 + i * 0.0001,
                low=1.0990 + i * 0.0001,
                close=1.1005 + i * 0.0001,
                volume=1000.0 + i,
            )
            for i in range(3)
        ]

    def test_creates_output_directory(self, tmp_path):
        """Test that the output directory is created if missing."""
        output_dir = tmp_path / "nested" / "data"
        downloader = YahooDataDownloader()

        downloader.export_to_csv(
            self._make_candles(),
            "EURUSD=X",
            Timeframe.M5,
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
            str(output_dir),
        )

        assert output_dir.is_dir()

    def test_filename_sanitizes_pair_symbol(self, tmp_path):
        """Test that special characters in the pair symbol are stripped from the filename."""
        downloader = YahooDataDownloader()

        path = downloader.export_to_csv(
            self._make_candles(),
            "EURUSD=X",
            Timeframe.M5,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
            str(tmp_path),
        )

        assert path.endswith("EURUSDX_M5_20240101_20240131.csv")

    def test_csv_contents_match_candles(self, tmp_path):
        """Test that the written CSV has the expected header and row values."""
        candles = self._make_candles()
        downloader = YahooDataDownloader()

        path = downloader.export_to_csv(
            candles,
            "EURUSD=X",
            Timeframe.M5,
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
            str(tmp_path),
        )

        with open(path, newline="") as f:
            rows = list(csv.reader(f))

        assert rows[0] == ["timestamp", "open", "high", "low", "close", "volume"]
        assert len(rows) == 1 + len(candles)
        first_row = rows[1]
        assert first_row[0] == candles[0].timestamp.isoformat()
        assert float(first_row[1]) == pytest.approx(candles[0].open)
        assert float(first_row[5]) == pytest.approx(candles[0].volume)

    def test_returns_absolute_path(self, tmp_path):
        """Test that the returned path is absolute."""
        import os

        downloader = YahooDataDownloader()

        path = downloader.export_to_csv(
            self._make_candles(),
            "EURUSD=X",
            Timeframe.M5,
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
            str(tmp_path),
        )

        assert os.path.isabs(path)


class TestGetCsvPath:
    """Tests for YahooDataDownloader.get_csv_path."""

    def test_matches_export_to_csv_filename(self, tmp_path):
        """The computed path must match the filename export_to_csv actually writes."""
        downloader = YahooDataDownloader()
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 2, 9, 0),
                open=1.1,
                high=1.11,
                low=1.09,
                close=1.105,
                volume=1000.0,
            )
        ]

        expected_path = downloader.get_csv_path(
            "EURUSD=X", Timeframe.M5, datetime(2024, 1, 1), datetime(2024, 1, 2), str(tmp_path)
        )
        written_path = downloader.export_to_csv(
            candles, "EURUSD=X", Timeframe.M5, datetime(2024, 1, 1), datetime(2024, 1, 2), str(tmp_path)
        )

        assert os.path.abspath(expected_path) == written_path

    def test_does_not_create_directory_or_file(self, tmp_path):
        """get_csv_path should be a pure path computation with no side effects."""
        output_dir = tmp_path / "nonexistent"
        downloader = YahooDataDownloader()

        path = downloader.get_csv_path(
            "EURUSD=X", Timeframe.M5, datetime(2024, 1, 1), datetime(2024, 1, 2), str(output_dir)
        )

        assert not output_dir.exists()
        assert not os.path.exists(path)


class TestLoadFromCsv:
    """Tests for YahooDataDownloader.load_from_csv."""

    def test_round_trips_exported_candles(self, tmp_path):
        """Candles written by export_to_csv should be read back identically."""
        start = datetime(2024, 1, 2, 9, 0)
        candles = [
            Candle(
                timestamp=start + timedelta(minutes=5 * i),
                open=1.1000 + i * 0.0001,
                high=1.1010 + i * 0.0001,
                low=1.0990 + i * 0.0001,
                close=1.1005 + i * 0.0001,
                volume=1000.0 + i,
            )
            for i in range(3)
        ]
        downloader = YahooDataDownloader()
        path = downloader.export_to_csv(
            candles, "EURUSD=X", Timeframe.M5, start, start + timedelta(minutes=15), str(tmp_path)
        )

        loaded = downloader.load_from_csv(path)

        assert len(loaded) == len(candles)
        for original, restored in zip(candles, loaded):
            assert restored.timestamp == original.timestamp
            assert restored.open == pytest.approx(original.open)
            assert restored.high == pytest.approx(original.high)
            assert restored.low == pytest.approx(original.low)
            assert restored.close == pytest.approx(original.close)
            assert restored.volume == pytest.approx(original.volume)

    def test_sorted_ascending_by_timestamp(self, tmp_path):
        """Rows out of order in the file are sorted ascending on load."""
        path = tmp_path / "unsorted.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-02T09:10:00,1.1,1.11,1.09,1.105,1000\n"
            "2024-01-02T09:00:00,1.1,1.11,1.09,1.105,1000\n"
        )
        downloader = YahooDataDownloader()

        loaded = downloader.load_from_csv(str(path))

        assert loaded[0].timestamp < loaded[1].timestamp

    def test_missing_file_raises_data_download_error(self, tmp_path):
        downloader = YahooDataDownloader()
        with pytest.raises(DataDownloadError, match="Failed to read cached CSV file"):
            downloader.load_from_csv(str(tmp_path / "missing.csv"))

    def test_malformed_row_raises_data_download_error(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-02T09:00:00,not-a-number,1.11,1.09,1.105,1000\n"
        )
        downloader = YahooDataDownloader()
        with pytest.raises(DataDownloadError, match="Failed to read cached CSV file"):
            downloader.load_from_csv(str(path))


class TestDownloadCsvExportIntegration:
    """Tests for the optional csv_output_dir parameter on download()."""

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_download_writes_csv_when_output_dir_given(self, mock_ticker_cls, tmp_path):
        """Test that download() writes a CSV file when csv_output_dir is provided."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 10, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 5)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        candles = downloader.download(
            "EURUSD=X", Timeframe.M5, start, end, csv_output_dir=str(tmp_path)
        )

        assert len(candles) == 5
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_download_skips_csv_export_when_no_output_dir(self, mock_ticker_cls, tmp_path):
        """Test that no CSV is written when csv_output_dir is not provided."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 10, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 5)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        downloader.download("EURUSD=X", Timeframe.M5, start, end)

        assert list(tmp_path.glob("*.csv")) == []

    @patch("forex_signals.data.downloader.yf.Ticker")
    def test_csv_export_failure_does_not_raise_or_block_download(
        self, mock_ticker_cls, tmp_path, caplog
    ):
        """Test that a CSV export failure is logged as a warning, not raised."""
        start = datetime(2024, 1, 2, 9, 0)
        end = datetime(2024, 1, 2, 10, 0)
        df = _make_ohlcv_dataframe(start, Timeframe.M5, 5)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        downloader = YahooDataDownloader()
        with patch.object(
            downloader, "export_to_csv", side_effect=OSError("disk full")
        ):
            with caplog.at_level(
                logging.WARNING, logger="forex_signals.data.downloader"
            ):
                candles = downloader.download(
                    "EURUSD=X",
                    Timeframe.M5,
                    start,
                    end,
                    csv_output_dir=str(tmp_path),
                )

        assert len(candles) == 5
        warnings = [r for r in caplog.records if "Failed to export candles" in r.message]
        assert len(warnings) == 1
