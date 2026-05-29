import yfinance as yf
import boto3
import json
import logging
import os
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

S3_BUCKET = os.getenv('S3_BUCKET_NAME')
SYMBOLS = os.getenv('SYMBOLS', 'TSLA,NVDA').split(',')

# Lambda 환경에선 IAM Role 사용, 로컬에선 .env 키 사용
if env_path.exists():
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('APP_REGION')
    )
else:
    s3 = boto3.client('s3')


def fetch_daily_prices(symbol: str) -> dict:
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='6mo')
            df.index = pd.to_datetime(df.index).tz_localize(None).strftime('%Y-%m-%d')
            return df[['Open', 'High', 'Low', 'Close', 'Volume']].to_dict(orient='index')
        except Exception as e:
            if attempt == max_retries:
                logger.error('Failed to fetch %s after %d retries: %s', symbol, max_retries, e)
                raise
            wait = 2 ** attempt
            logger.warning('Attempt %d/%d failed for %s: %s — retrying in %ds', attempt, max_retries, symbol, e, wait)
            time.sleep(wait)


def upload_to_s3(data: dict, symbol: str) -> None:
    max_retries = 3
    today = datetime.today().strftime('%Y-%m-%d')
    key = f'raw/{symbol}/daily_prices/{today}.json'
    for attempt in range(1, max_retries + 1):
        try:
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=json.dumps(data),
                ContentType='application/json'
            )
            logger.info('Uploaded: %s', key)
            return
        except Exception as e:
            if attempt == max_retries:
                logger.error('Failed to upload %s to S3 after %d retries: %s', key, max_retries, e)
                raise
            wait = 2 ** attempt
            logger.warning('S3 upload attempt %d/%d failed for %s: %s — retrying in %ds', attempt, max_retries, key, e, wait)
            time.sleep(wait)


def run():
    for symbol in SYMBOLS:
        logger.info('Fetching daily prices for %s', symbol)
        daily_prices = fetch_daily_prices(symbol)
        upload_to_s3(daily_prices, symbol)
        logger.info('%s data fetched and uploaded successfully', symbol)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run()
