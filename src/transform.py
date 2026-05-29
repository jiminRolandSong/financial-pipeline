import json
import logging
import os
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv('S3_BUCKET_NAME')
SYMBOLS = os.getenv('SYMBOLS', 'TSLA,NVDA').split(',')

STOCK_INFO = {
    'TSLA': {'company_name': 'Tesla Inc.', 'sector': 'Automotive', 'exchange': 'NASDAQ'},
    'NVDA': {'company_name': 'NVIDIA Corporation', 'sector': 'Semiconductors', 'exchange': 'NASDAQ'}
}

SMA_WINDOW = 20


def _make_s3_client():
    import boto3
    if env_path.exists():
        return boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
    return boto3.client('s3')


def read_from_s3(symbol: str) -> dict:
    s3 = _make_s3_client()
    prefix = f'raw/{symbol}/daily_prices/'
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    if 'Contents' not in response:
        raise FileNotFoundError(f'No S3 data found for {symbol}')
    files = sorted([obj['Key'] for obj in response['Contents']])
    latest_key = files[-1]
    logger.info('Reading: %s', latest_key)
    response = s3.get_object(Bucket=S3_BUCKET, Key=latest_key)
    return json.loads(response['Body'].read().decode('utf-8'))


def build_dim_date(dates: list) -> pd.DataFrame:
    rows = []
    for d in dates:
        dt = pd.to_datetime(d)
        rows.append({
            'date_key': int(dt.strftime('%Y%m%d')),
            'full_date': d,
            'year': dt.year,
            'quarter': dt.quarter,
            'month': dt.month,
            'week_of_year': dt.isocalendar()[1],
            'is_weekend': dt.weekday() >= 5,
            'is_market_holiday': False
        })
    return pd.DataFrame(rows).drop_duplicates(subset=['date_key'])


def build_dim_stock(symbols: list) -> pd.DataFrame:
    rows = []
    for i, symbol in enumerate(symbols):
        rows.append({
            'stock_key': i + 1,
            'symbol': symbol,
            'company_name': STOCK_INFO[symbol]['company_name'],
            'sector': STOCK_INFO[symbol]['sector'],
            'exchange': STOCK_INFO[symbol]['exchange']
        })
    return pd.DataFrame(rows)


def build_fact_prices(symbol: str, stock_key: int, raw_data: dict) -> pd.DataFrame:
    rows = []
    for date, values in raw_data.items():
        rows.append({
            'stock_key': stock_key,
            'date_key': int(pd.to_datetime(date).strftime('%Y%m%d')),
            'open_price': round(values['Open'], 4),
            'high_price': round(values['High'], 4),
            'low_price': round(values['Low'], 4),
            'close_price': round(values['Close'], 4),
            'volume': int(values['Volume']),
        })
    df = pd.DataFrame(rows).sort_values('date_key')
    df['sma_20'] = df['close_price'].rolling(window=SMA_WINDOW).mean().round(4)
    df['daily_return'] = df['close_price'].pct_change().round(6)
    df['ingested_at'] = datetime.now(timezone.utc).isoformat()
    return df


def validate_data(df: pd.DataFrame, symbol: str) -> None:
    if len(df) == 0:
        raise ValueError(f'[{symbol}] DataFrame is empty — no rows to load')
    null_close = df['close_price'].isnull().sum()
    if null_close > 0:
        raise ValueError(f'[{symbol}] close_price has {null_close} null value(s)')
    null_volume = df['volume'].isnull().sum()
    if null_volume > 0:
        raise ValueError(f'[{symbol}] volume has {null_volume} null value(s)')
    invalid_close = (df['close_price'] <= 0).sum()
    if invalid_close > 0:
        raise ValueError(f'[{symbol}] close_price has {invalid_close} non-positive value(s)')
    invalid_volume = (df['volume'] <= 0).sum()
    if invalid_volume > 0:
        raise ValueError(f'[{symbol}] volume has {invalid_volume} non-positive value(s)')


def run():
    from load import load_to_bigquery

    all_dates: list[str] = []
    fact_frames: list[pd.DataFrame] = []
    active_symbols = [s for s in SYMBOLS if s in STOCK_INFO]
    dim_stock_df = build_dim_stock(active_symbols)

    for i, symbol in enumerate(active_symbols):
        logger.info('Processing %s', symbol)
        raw_data = read_from_s3(symbol)
        all_dates.extend(raw_data.keys())
        fact_df = build_fact_prices(symbol, i + 1, raw_data)
        validate_data(fact_df, symbol)
        fact_frames.append(fact_df)

    dim_date_df = build_dim_date(sorted(set(all_dates)))
    fact_df = pd.concat(fact_frames, ignore_index=True)

    logger.info('Loading to BigQuery')
    load_to_bigquery(dim_date_df, 'dim_date', ['date_key'])
    load_to_bigquery(dim_stock_df, 'dim_stock', ['stock_key'])
    load_to_bigquery(fact_df, 'fact_prices', ['stock_key', 'date_key'])
    logger.info('Done')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run()
