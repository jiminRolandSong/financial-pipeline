import pytest
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from transform import build_dim_date, build_fact_prices, validate_data, SMA_WINDOW


RAW_DATA = {
    f'2024-01-{str(i).zfill(2)}': {
        'Open': 200.0 + i,
        'High': 210.0 + i,
        'Low': 195.0 + i,
        'Close': 205.0 + i,
        'Volume': 1_000_000 + i * 1000,
    }
    for i in range(1, 31)
}


class TestBuildDimDate:
    def test_date_key_format(self):
        df = build_dim_date(['2024-01-15'])
        assert df.iloc[0]['date_key'] == 20240115

    def test_columns_present(self):
        df = build_dim_date(['2024-03-10'])
        for col in ['date_key', 'full_date', 'year', 'quarter', 'month', 'week_of_year', 'is_weekend']:
            assert col in df.columns

    def test_deduplication(self):
        df = build_dim_date(['2024-01-01', '2024-01-01', '2024-01-02'])
        assert len(df) == 2

    def test_weekend_flag(self):
        # 2024-01-06 is a Saturday
        df = build_dim_date(['2024-01-06', '2024-01-08'])
        weekend_row = df[df['full_date'] == '2024-01-06'].iloc[0]
        weekday_row = df[df['full_date'] == '2024-01-08'].iloc[0]
        assert weekend_row['is_weekend'] == True
        assert weekday_row['is_weekend'] == False

    def test_quarter_assignment(self):
        df = build_dim_date(['2024-04-01'])
        assert df.iloc[0]['quarter'] == 2


class TestBuildFactPrices:
    def test_row_count(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        assert len(df) == 30

    def test_stock_key_assigned(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        assert (df['stock_key'] == 1).all()

    def test_date_key_format(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        assert df.iloc[0]['date_key'] == 20240101

    def test_sma_20_null_for_early_rows(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        # First SMA_WINDOW - 1 rows must be NaN
        assert df.iloc[:SMA_WINDOW - 1]['sma_20'].isnull().all()

    def test_sma_20_value_correctness(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        # Row at index SMA_WINDOW - 1 is the first valid SMA
        first_valid = df.iloc[SMA_WINDOW - 1]['sma_20']
        expected = round(df.iloc[:SMA_WINDOW]['close_price'].mean(), 4)
        assert first_valid == expected

    def test_daily_return_first_row_is_nan(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        assert pd.isna(df.iloc[0]['daily_return'])

    def test_daily_return_calculation(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        expected = round(
            (df.iloc[1]['close_price'] - df.iloc[0]['close_price']) / df.iloc[0]['close_price'],
            6
        )
        assert df.iloc[1]['daily_return'] == expected

    def test_required_columns_present(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        for col in ['stock_key', 'date_key', 'open_price', 'high_price', 'low_price',
                    'close_price', 'volume', 'sma_20', 'daily_return', 'ingested_at']:
            assert col in df.columns

    def test_sorted_by_date_key(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        assert list(df['date_key']) == sorted(df['date_key'])


class TestValidateData:
    def _valid_df(self):
        df = build_fact_prices('TSLA', 1, RAW_DATA)
        # Drop NaN rows so validation doesn't fail on sma/return nulls (those are not checked)
        return df

    def test_valid_data_passes(self):
        df = self._valid_df()
        validate_data(df, 'TSLA')  # should not raise

    def test_empty_dataframe_raises(self):
        df = pd.DataFrame(columns=['close_price', 'volume'])
        with pytest.raises(ValueError, match='empty'):
            validate_data(df, 'TSLA')

    def test_null_close_price_raises(self):
        df = self._valid_df().copy()
        df.loc[df.index[0], 'close_price'] = None
        with pytest.raises(ValueError, match='close_price'):
            validate_data(df, 'TSLA')

    def test_null_volume_raises(self):
        df = self._valid_df().copy()
        df.loc[df.index[0], 'volume'] = None
        with pytest.raises(ValueError, match='volume'):
            validate_data(df, 'TSLA')

    def test_zero_close_price_raises(self):
        df = self._valid_df().copy()
        df.loc[df.index[0], 'close_price'] = 0.0
        with pytest.raises(ValueError, match='close_price'):
            validate_data(df, 'TSLA')

    def test_negative_volume_raises(self):
        df = self._valid_df().copy()
        df.loc[df.index[0], 'volume'] = -1
        with pytest.raises(ValueError, match='volume'):
            validate_data(df, 'TSLA')

    def test_error_message_includes_symbol(self):
        df = pd.DataFrame(columns=['close_price', 'volume'])
        with pytest.raises(ValueError, match='NVDA'):
            validate_data(df, 'NVDA')
