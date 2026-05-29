import json
import logging
import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

ANOMALY_THRESHOLD = 0.03
SMA_WINDOW = 20

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
BQ_DATASET = os.getenv('BQ_DATASET')


def _make_bq_client():
    from google.cloud import bigquery
    from google.oauth2 import service_account
    creds_raw = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_raw:
        creds_json = json.loads(creds_raw)
        credentials = service_account.Credentials.from_service_account_info(creds_json)
        return bigquery.Client(project=GCP_PROJECT_ID, credentials=credentials)
    return bigquery.Client(project=GCP_PROJECT_ID)


def fetch_weekly_data() -> pd.DataFrame:
    bq = _make_bq_client()
    query = f"""
        SELECT
            s.symbol,
            d.full_date,
            f.close_price,
            f.volume,
            f.daily_return,
            f.sma_20
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.fact_prices` f
        JOIN `{GCP_PROJECT_ID}.{BQ_DATASET}.dim_stock` s ON f.stock_key = s.stock_key
        JOIN `{GCP_PROJECT_ID}.{BQ_DATASET}.dim_date` d ON f.date_key = d.date_key
        WHERE PARSE_DATE('%Y-%m-%d', d.full_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        ORDER BY s.symbol, d.full_date
    """
    return bq.query(query).to_dataframe()


def detect_anomalies(df: pd.DataFrame) -> list:
    anomalies = []
    for _, row in df.iterrows():
        if row['daily_return'] is not None and abs(row['daily_return']) > ANOMALY_THRESHOLD:
            anomalies.append({
                'symbol': row['symbol'],
                'date': str(row['full_date']),
                'daily_return': round(float(row['daily_return']) * 100, 2),
                'close_price': float(row['close_price'])
            })
    return anomalies


def generate_weekly_report(df: pd.DataFrame, anomalies: list) -> dict:
    import requests

    summary_data = {}
    for symbol in df['symbol'].unique():
        symbol_df = df[df['symbol'] == symbol].sort_values('full_date')
        if len(symbol_df) >= 2:
            week_return = (symbol_df['close_price'].iloc[-1] - symbol_df['close_price'].iloc[0]) / symbol_df['close_price'].iloc[0]
            summary_data[symbol] = {
                'start_price': round(float(symbol_df['close_price'].iloc[0]), 2),
                'end_price': round(float(symbol_df['close_price'].iloc[-1]), 2),
                'week_return': round(float(week_return) * 100, 2),
                'avg_volume': int(symbol_df['volume'].mean()),
                'sma_20': round(float(symbol_df['sma_20'].dropna().iloc[-1]), 2) if not symbol_df['sma_20'].dropna().empty else None
            }

    prompt = f"""
You are a senior quantitative analyst at a hedge fund. Analyze this week's stock data for TSLA and NVDA with depth and precision.

Weekly Performance Data:
{json.dumps(summary_data, indent=2)}

Anomalies detected (daily return exceeded {ANOMALY_THRESHOLD * 100:.0f}% threshold):
{json.dumps(anomalies, indent=2)}

Provide a rigorous analysis covering:

1. **Performance comparison** — which stock outperformed and why the divergence matters
2. **Technical positioning** — both stocks relative to their SMA-20 (above = bullish, below = bearish, % distance matters)
3. **Volume analysis** — what the volume levels suggest about conviction behind the moves
4. **Anomaly deep-dive** — if anomalies exist, what likely caused them (earnings, macro, sector rotation)
5. **Correlation** — are TSLA and NVDA moving together or diverging? What does that signal?
6. **Risk assessment** — specific risks for each stock next week

Return ONLY a JSON object with these exact keys:
{{
    "summary": "3-4 sentences with specific numbers, percentage moves, and what they mean",
    "tsla_analysis": "2-3 sentences covering price vs SMA-20, volume conviction, and key level to watch",
    "nvda_analysis": "2-3 sentences covering price vs SMA-20, volume conviction, and key level to watch",
    "anomalies_explanation": "specific explanation with likely catalysts, or 'No significant anomalies this week'",
    "correlation_insight": "1-2 sentences on whether stocks are correlated or diverging this week",
    "risk_score": <integer 1-10, where 1=very low volatility, 10=extreme risk>,
    "risk_factors": "2-3 specific risk factors to watch next week",
    "outlook": "2-3 sentences with specific price levels or catalysts to monitor"
}}
"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': os.getenv('ANTHROPIC_API_KEY', '').strip(),
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 2000,
            'messages': [{'role': 'user', 'content': prompt}],
        },
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f'Anthropic API error {response.status_code}: {response.text}')
    response_text = response.json()['content'][0]['text']
    clean = response_text.replace('```json', '').replace('```', '').strip()
    return json.loads(clean)


def run():
    logger.info('Fetching weekly data from BigQuery...')
    df = fetch_weekly_data()

    logger.info('Detecting anomalies...')
    anomalies = detect_anomalies(df)
    logger.info('Found %d anomalies', len(anomalies))

    logger.info('Generating AI report...')
    report = generate_weekly_report(df, anomalies)

    logger.info('Weekly report: %s', json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run()
