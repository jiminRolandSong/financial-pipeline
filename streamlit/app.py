import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / 'src'))


def _secret(key: str) -> str:
    """Read from st.secrets first, fall back to env (local dev with .env)."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.getenv(key, '')


def _inject_secrets_to_env():
    """Push Streamlit secrets into os.environ so src/ modules can read them via os.getenv."""
    keys = [
        'GCP_PROJECT_ID', 'BQ_DATASET',
        'GOOGLE_APPLICATION_CREDENTIALS_JSON',
        'ANTHROPIC_API_KEY',
        'S3_BUCKET_NAME', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'APP_REGION',
    ]
    for key in keys:
        val = _secret(key)
        if val:
            os.environ[key] = val


_inject_secrets_to_env()

from analyze import fetch_weekly_data, detect_anomalies, generate_weekly_report

st.set_page_config(
    page_title='Financial Intelligence Dashboard',
    page_icon='📈',
    layout='wide'
)

st.title('📈 Financial Intelligence Dashboard')
st.caption('TSLA & NVDA — Powered by AWS S3, BigQuery, Claude AI')


@st.cache_data(ttl=3600)
def load_data():
    from google.cloud import bigquery
    from google.oauth2 import service_account

    GCP_PROJECT_ID = _secret('GCP_PROJECT_ID')
    BQ_DATASET = _secret('BQ_DATASET')

    creds_raw = _secret('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_raw:
        creds_json = json.loads(creds_raw)
        credentials = service_account.Credentials.from_service_account_info(creds_json)
        bq = bigquery.Client(project=GCP_PROJECT_ID, credentials=credentials)
    else:
        bq = bigquery.Client(project=GCP_PROJECT_ID)

    query = f"""
        SELECT
            s.symbol,
            d.full_date,
            f.open_price,
            f.high_price,
            f.low_price,
            f.close_price,
            f.volume,
            f.daily_return,
            f.sma_20
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.fact_prices` f
        JOIN `{GCP_PROJECT_ID}.{BQ_DATASET}.dim_stock` s ON f.stock_key = s.stock_key
        JOIN `{GCP_PROJECT_ID}.{BQ_DATASET}.dim_date` d ON f.date_key = d.date_key
        ORDER BY s.symbol, d.full_date
    """
    return bq.query(query).to_dataframe()


df = load_data()

tab1, tab2, tab3 = st.tabs(['📊 Stock Charts', '🤖 AI Report', '🏗️ Architecture'])

with tab1:
    symbol = st.selectbox('Select Stock', ['TSLA', 'NVDA'])
    symbol_df = df[df['symbol'] == symbol].sort_values('full_date')

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=symbol_df['full_date'],
        y=symbol_df['close_price'],
        name='Close Price',
        line=dict(color='#00d4ff', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=symbol_df['full_date'],
        y=symbol_df['sma_20'],
        name='SMA 20',
        line=dict(color='#ff9500', width=1.5, dash='dash')
    ))
    fig.update_layout(
        title=f'{symbol} Price (6 months)',
        xaxis_title='Date',
        yaxis_title='Price (USD)',
        template='plotly_dark',
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=symbol_df['full_date'],
        y=symbol_df['volume'],
        name='Volume',
        marker_color='#7c3aed'
    ))
    fig2.update_layout(
        title=f'{symbol} Volume',
        xaxis_title='Date',
        yaxis_title='Volume',
        template='plotly_dark',
        height=250
    )
    st.plotly_chart(fig2, use_container_width=True)

with tab2:
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        st.warning('ANTHROPIC_API_KEY not found in secrets. Add it in Streamlit Cloud → Settings → Secrets.')
    else:
        st.caption(f'API key loaded: sk-ant-...{api_key[-6:]}')

    if st.button('🔍 Test Anthropic Connection'):
        import requests, socket
        try:
            ip = socket.gethostbyname('api.anthropic.com')
            st.success(f'DNS OK — api.anthropic.com resolves to {ip}')
        except Exception as e:
            st.error(f'DNS FAIL: {e}')
        try:
            r = requests.get('https://api.anthropic.com', timeout=10)
            st.success(f'HTTP OK — status {r.status_code}')
        except Exception as e:
            st.error(f'HTTP FAIL: {type(e).__name__}: {e}')

    if st.button('🤖 Generate Weekly Report'):
        with st.spinner('Analyzing with Claude AI...'):
            try:
                weekly_df = fetch_weekly_data()
                anomalies = detect_anomalies(weekly_df)
                report = generate_weekly_report(weekly_df, anomalies)
            except Exception as e:
                st.error(f'Error: {type(e).__name__}: {e}')
                st.stop()

        st.subheader('Weekly Summary')
        st.write(report['summary'])

        col1, col2 = st.columns(2)
        with col1:
            st.subheader('TSLA')
            st.write(report['tsla_analysis'])
        with col2:
            st.subheader('NVDA')
            st.write(report['nvda_analysis'])

        st.subheader('Anomalies')
        st.write(report['anomalies_explanation'])

        col3, col4 = st.columns(2)
        with col3:
            risk = report['risk_score']
            color = '🟢' if risk <= 3 else '🟡' if risk <= 6 else '🔴'
            st.metric('Risk Score', f'{color} {risk} / 10')
        with col4:
            st.subheader('Outlook')
            st.write(report['outlook'])

with tab3:
    st.subheader('Pipeline Architecture')
    st.code("""
    yfinance (Stock Data)
         ↓
    AWS Lambda (Extract)  ←  EventBridge (Daily 21:30 EDT)
         ↓
    AWS S3 (Raw JSON Storage)
         ↓
    AWS Lambda (Transform & Load)  ←  S3 Event Trigger
         ↓
    Google BigQuery (Star Schema DWH)
         ↓
    Claude AI API (Weekly Report Generation)
         ↓
    Streamlit Dashboard (Visualization)
    """)

    st.subheader('Tech Stack')
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('**AWS**')
        st.write('• S3\n• Lambda\n• EventBridge\n• ECR')
    with col2:
        st.markdown('**Data**')
        st.write('• BigQuery\n• Star Schema\n• Idempotent UPSERT')
    with col3:
        st.markdown('**AI & Viz**')
        st.write('• Claude API\n• Streamlit\n• Plotly')
