# Financial Intelligence Pipeline

An end-to-end, fully serverless stock market data pipeline for TSLA and NVDA. Extracts daily OHLCV data, transforms and loads it into a BigQuery data warehouse using idempotent upserts, and surfaces AI-generated weekly reports via a live Streamlit dashboard.

**Live Dashboard →** [financial-pipeline-jiminsong.streamlit.app](https://financial-pipeline-jiminsong.streamlit.app/)

---

## Architecture

```
                        ┌─────────────────────────────────────────────────────┐
                        │                     AWS Cloud                       │
                        │                                                     │
  ┌─────────────┐       │  ┌──────────────────┐      ┌─────────────────────┐ │
  │ EventBridge │──────▶│  │  Extract Lambda  │      │ Transform/Load      │ │
  │  (weekdays  │       │  │  (Docker/ECR)    │      │ Lambda (Docker/ECR) │ │
  │  21:30 EDT) │       │  │                  │      │                     │ │
  └─────────────┘       │  │  yfinance API    │      │  pandas transform   │ │
                        │  │  TSLA + NVDA     │      │  SMA-20, returns    │ │
                        │  │  6mo OHLCV       │      │  star schema build  │ │
                        │  └────────┬─────────┘      └──────────┬──────────┘ │
                        │           │  S3 PUT                    │            │
                        │           ▼                 S3 Event   │            │
                        │  ┌────────────────────┐    trigger     │            │
                        │  │      AWS S3         │───────────────┘            │
                        │  │  raw/{symbol}/      │                            │
                        │  │  daily_prices/      │                            │
                        │  │  {date}.json        │                            │
                        │  └────────────────────┘                            │
                        └─────────────────────────────────────────────────────┘
                                                          │
                                                          │ MERGE UPSERT
                                                          ▼
                        ┌─────────────────────────────────────────────────────┐
                        │                   Google Cloud                      │
                        │                                                     │
                        │  ┌──────────────────────────────────────────────┐  │
                        │  │              BigQuery Data Warehouse          │  │
                        │  │                                               │  │
                        │  │  ┌────────────┐  ┌───────────┐  ┌─────────┐ │  │
                        │  │  │ fact_prices│  │ dim_date  │  │dim_stock│ │  │
                        │  │  │            │  │           │  │         │ │  │
                        │  │  │ stock_key  │  │ date_key  │  │stock_key│ │  │
                        │  │  │ date_key   │  │ year      │  │symbol   │ │  │
                        │  │  │ open/high/ │  │ quarter   │  │name     │ │  │
                        │  │  │ low/close  │  │ month     │  │sector   │ │  │
                        │  │  │ volume     │  │ week      │  │exchange │ │  │
                        │  │  │ sma_20     │  │ is_weekend│  │         │ │  │
                        │  │  │ daily_ret  │  └───────────┘  └─────────┘ │  │
                        │  │  └────────────┘                              │  │
                        │  └──────────────────────────────────────────────┘  │
                        └─────────────────────────────────────────────────────┘
                                          │
                              ┌───────────┴───────────┐
                              │                       │
                              ▼                       ▼
                    ┌──────────────────┐   ┌─────────────────────┐
                    │   Claude API     │   │  Streamlit Dashboard│
                    │ (claude-sonnet)  │   │  (Streamlit Cloud)  │
                    │                 │   │                     │
                    │ Weekly report   │──▶│  Price + SMA charts │
                    │ Anomaly detect  │   │  Volume bars        │
                    │ Risk scoring    │   │  AI weekly report   │
                    │ JSON output     │   │  Architecture docs  │
                    └──────────────────┘   └─────────────────────┘
```

---

## Pipeline Flow

| Step | Trigger | Service | Action |
|------|---------|---------|--------|
| 1 | EventBridge cron (`cron(30 21 ? * MON-FRI *)`) | AWS Lambda | Fetch 6-month OHLCV history for TSLA + NVDA via yfinance |
| 2 | Lambda execution | AWS S3 | Upload raw JSON to `s3://bucket/raw/{symbol}/daily_prices/{date}.json` |
| 3 | S3 `ObjectCreated` event | AWS Lambda | Trigger transform_load Lambda automatically |
| 4 | Lambda execution | BigQuery | Build star schema, calculate SMA-20 + daily returns, UPSERT via `MERGE` |
| 5 | On-demand (Streamlit) | Claude API | Generate structured JSON report: summary, anomalies, risk score, outlook |
| 6 | User | Streamlit Cloud | Visualize charts, volume, SMA overlay, and AI report |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | AWS EventBridge (weekday cron) |
| Compute | AWS Lambda (Docker containers via ECR) |
| Storage | AWS S3 (raw JSON staging) |
| Data Warehouse | Google BigQuery (star schema) |
| Extraction | Python, yfinance, pandas |
| AI Analysis | Anthropic Claude API (claude-sonnet-4-6) |
| Dashboard | Streamlit, Plotly |
| Containerization | Docker |
| Auth | GCP Service Account (credentials injected as env var, no key files) |

---

## Data Model

Star schema with daily grain — one row per symbol per trading day.

```
dim_stock          fact_prices              dim_date
─────────          ───────────              ────────
stock_key (PK) ──▶ stock_key (FK)    ┌──── date_key (PK)
symbol             date_key (FK) ────┘     year
company_name       open                    quarter
sector             high                    month
exchange           low                     week_of_year
                   close                   day_of_week
                   volume                  is_weekend
                   sma_20
                   daily_return
                   ingested_at
```

**Upsert strategy:** Each pipeline run loads to a temp table, then executes a `MERGE` statement matching on `(stock_key, date_key)`. Existing rows are updated; new rows are inserted. The temp table is deleted after the merge. This makes reruns fully idempotent.

---

## Key Engineering Decisions

**Docker containers for Lambda** — yfinance and its dependencies exceed AWS Lambda's 50 MB zip limit. Packaging as a Docker image pushed to ECR removes that constraint and makes the environment fully reproducible across local and cloud.

**Idempotent UPSERT via BigQuery MERGE** — instead of appending or truncating, each run performs a `MERGE` on natural keys `(stock_key, date_key)`. Re-triggering on the same day due to retries or bugs produces no duplicate data and no data loss.

**Market-aware scheduling** — EventBridge cron is scoped to weekdays only (`MON-FRI`). No Lambda invocations on weekends when markets are closed, avoiding unnecessary API calls and costs.

**Credentials as environment variables** — GCP service account JSON is stored as a Lambda environment variable (`GOOGLE_APPLICATION_CREDENTIALS_JSON`), not mounted as a key file. The `load.py` module deserializes it at runtime, keeping containers stateless and eliminating key file management.

**Structured AI output** — Claude is prompted to return a strict JSON schema (summary, anomalies list, risk score 1–10, outlook string) rather than free text, making the output directly parseable by the Streamlit frontend without any post-processing.

---

## Project Structure

```
financial-pipeline/
├── lambda/
│   ├── extract_lambda/
│   │   ├── lambda_function.py      # Entry point: calls src/extract.run()
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── transform_load_lambda/
│       ├── lambda_function.py      # Entry point: calls src/transform.run()
│       ├── Dockerfile
│       └── requirements.txt
├── src/
│   ├── extract.py                  # yfinance fetch + S3 upload
│   ├── transform.py                # Star schema construction, SMA-20, daily returns
│   ├── load.py                     # BigQuery MERGE UPSERT logic
│   └── analyze.py                  # Claude API weekly report + anomaly detection
├── streamlit/
│   └── app.py                      # Streamlit dashboard (charts + AI report)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Local Setup

### Prerequisites

- Python 3.12
- AWS credentials with S3 read/write access
- GCP service account with BigQuery Data Editor role
- Anthropic API key

### 1. Clone and install

```bash
git clone https://github.com/jiminRolandSong/financial-pipeline.git
cd financial-pipeline
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# AWS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
APP_REGION=us-east-1
S3_BUCKET_NAME=your-bucket

# GCP
GCP_PROJECT_ID=your-project-id
BQ_DATASET=financial_data
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account",...}

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run the pipeline locally

```bash
# Extract: fetch OHLCV data and upload to S3
python src/extract.py

# Transform + Load: build star schema and upsert to BigQuery
python src/transform.py

# Launch dashboard
streamlit run streamlit/app.py
```

### 4. Deploy Lambda functions

```bash
# Build and push to ECR (run from each lambda directory)
cd lambda/extract_lambda
docker build -t extract-lambda .
docker tag extract-lambda:latest <account-id>.dkr.ecr.<region>.amazonaws.com/extract-lambda:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/extract-lambda:latest
```

Repeat for `transform_load_lambda`, then update each Lambda function to use the new ECR image URI.

---

## Environment Variables Reference

| Variable | Used By | Description |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | extract, transform | AWS credentials (local only; Lambda uses IAM role) |
| `AWS_SECRET_ACCESS_KEY` | extract, transform | AWS credentials (local only) |
| `APP_REGION` | extract | AWS region |
| `S3_BUCKET_NAME` | extract, transform | Target S3 bucket |
| `GCP_PROJECT_ID` | load, analyze | GCP project ID |
| `BQ_DATASET` | load, analyze | BigQuery dataset name |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | load, analyze | Full service account JSON as a single-line string |
| `ANTHROPIC_API_KEY` | analyze | Claude API key |

