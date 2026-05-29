import pytest
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from analyze import detect_anomalies, ANOMALY_THRESHOLD


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestDetectAnomalies:
    def test_empty_dataframe_returns_empty_list(self):
        df = _make_df([])
        assert detect_anomalies(df) == []

    def test_no_anomalies_when_all_below_threshold(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-02', 'daily_return': 0.02, 'close_price': 200.0},
            {'symbol': 'NVDA', 'full_date': '2024-01-02', 'daily_return': -0.02, 'close_price': 500.0},
        ])
        assert detect_anomalies(df) == []

    def test_exactly_at_threshold_is_not_anomaly(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-02', 'daily_return': ANOMALY_THRESHOLD, 'close_price': 200.0},
        ])
        assert detect_anomalies(df) == []

    def test_just_above_threshold_is_anomaly(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-02', 'daily_return': ANOMALY_THRESHOLD + 0.001, 'close_price': 200.0},
        ])
        result = detect_anomalies(df)
        assert len(result) == 1
        assert result[0]['symbol'] == 'TSLA'

    def test_negative_spike_is_anomaly(self):
        df = _make_df([
            {'symbol': 'NVDA', 'full_date': '2024-01-03', 'daily_return': -(ANOMALY_THRESHOLD + 0.01), 'close_price': 480.0},
        ])
        result = detect_anomalies(df)
        assert len(result) == 1
        assert result[0]['symbol'] == 'NVDA'

    def test_multiple_anomalies_detected(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-02', 'daily_return': 0.05, 'close_price': 210.0},
            {'symbol': 'TSLA', 'full_date': '2024-01-03', 'daily_return': 0.01, 'close_price': 212.0},
            {'symbol': 'NVDA', 'full_date': '2024-01-02', 'daily_return': -0.06, 'close_price': 470.0},
        ])
        result = detect_anomalies(df)
        assert len(result) == 2

    def test_none_daily_return_is_skipped(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-01', 'daily_return': None, 'close_price': 200.0},
        ])
        assert detect_anomalies(df) == []

    def test_output_daily_return_is_percentage(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-02', 'daily_return': 0.05, 'close_price': 210.0},
        ])
        result = detect_anomalies(df)
        assert result[0]['daily_return'] == pytest.approx(5.0, rel=1e-3)

    def test_output_fields_present(self):
        df = _make_df([
            {'symbol': 'TSLA', 'full_date': '2024-01-02', 'daily_return': 0.05, 'close_price': 210.0},
        ])
        result = detect_anomalies(df)
        assert set(result[0].keys()) == {'symbol', 'date', 'daily_return', 'close_price'}
