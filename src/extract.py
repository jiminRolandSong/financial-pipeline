import yfinance as yf

import boto3
import json
import os

import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

S3_BUCKET = os.getenv('S3_BUCKET_NAME')
SYMBOLS = ['TSLA', 'NVDA']

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
    
def fetch_daily_prices(symbol: str) ->dict:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period='6mo')
    df.index = df.index = pd.to_datetime(df.index).tz_localize(None).strftime('%Y-%m-%d')
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].to_dict(orient='index')



def upload_to_s3(data: dict, symbol: str) -> None:
    today = datetime.today().strftime('%Y-%m-%d')
    key = f'raw/{symbol}/daily_prices/{today}.json'
    
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(data),
        ContentType='application/json'
    )
    print(f'Uploaded: {key}')

def run():
    for symbol in SYMBOLS:
        print(f'Fetching daily prices for {symbol}')
        
        daily_prices = fetch_daily_prices(symbol)
        upload_to_s3(daily_prices, symbol)
        
 
        
        print(f'{symbol} data fetched and uploaded successfully')

if __name__ == '__main__':
    run()