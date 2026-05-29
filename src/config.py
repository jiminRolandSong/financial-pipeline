import json
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
BQ_DATASET = os.getenv('BQ_DATASET')


def get_bigquery_client():
    from google.cloud import bigquery
    from google.oauth2 import service_account
    creds_raw = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_raw:
        creds_json = json.loads(creds_raw)
        credentials = service_account.Credentials.from_service_account_info(creds_json)
        return bigquery.Client(project=GCP_PROJECT_ID, credentials=credentials)
    return bigquery.Client(project=GCP_PROJECT_ID)
