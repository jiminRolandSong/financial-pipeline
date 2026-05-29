import yfinance as yf
import requests
import boto3
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

S3_BUCKET = os.getenv('S3_BUCKET_NAME')
SYMBOLS = ['TSLA', 'NVDA']

s3 = boto3.client('s3',
                  aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                  aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                  region_name=os.getenv('AWS_REGION')
)

def fetch_daily_prices(symbol: str) ->dict:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period='6mo')
    df.index = df.index.strftime('%Y-%m-%d')
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