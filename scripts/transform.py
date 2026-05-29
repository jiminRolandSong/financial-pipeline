import boto3
import json
import os
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent))
from load import load_to_bigquery

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

S3_BUCKET = os.getenv('S3_BUCKET_NAME')
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
BQ_DATASET = os.getenv('BQ_DATASET')

s3 = boto3.client('s3',
                  aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                  aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                  region_name=os.getenv('AWS_REGION')
)


STOCK_INFO = {
    'TSLA': {'company_name': 'Tesla Inc.', 'sector': 'Automotive', 'exchange': 'NASDAQ'},
    'NVDA': {'company_name': 'NVIDIA Corporation', 'sector': 'Semiconductors', 'exchange': 'NASDAQ'}
}

def read_from_s3(symbol: str) -> dict:
    # 오늘 날짜로 먼저 시도, 없으면 가장 최근 파일 가져오기
    prefix = f'raw/{symbol}/daily_prices/'
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    
    # 가장 최근 파일 선택
    files = sorted([obj['Key'] for obj in response['Contents']])
    latest_key = files[-1]
    print(f'Reading: {latest_key}')
    
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
            'is_market_holiday': False  # 추후 pandas_market_calendars로 개선 가능
        })
    return pd.DataFrame(rows).drop_duplicates(subset=['date_key'])

def build_dim_stock(symbols: str) -> pd.DataFrame:
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
    df['sma_20'] = df['close_price'].rolling(window=20).mean().round(4)
    df['daily_return'] = df['close_price'].pct_change().round(6)
    df['ingested_at'] = datetime.utcnow().isoformat()
    return df

    
def run():
    all_dates = []
    fact_frames = []
    dim_stock_df = build_dim_stock(list(STOCK_INFO.keys()))
    
    for i, symbol in enumerate(STOCK_INFO.keys()):
        print(f'Processing {symbol}')
        raw_data = read_from_s3(symbol)
        all_dates.extend(raw_data.keys())
        fact_frames.append(build_fact_prices(symbol, i + 1, raw_data))
        
    dim_date_df = build_dim_date(sorted(set(all_dates)))
    fact_df = pd.concat(fact_frames, ignore_index=True)
    
    print('Loading to BigQuery')
    load_to_bigquery(dim_date_df, 'dim_date', ['date_key'])
    load_to_bigquery(dim_stock_df, 'dim_stock', ['stock_key'])
    load_to_bigquery(fact_df, 'fact_prices', ['stock_key', 'date_key'])
    print('Done')
    
if __name__ == '__main__':
    run()