import os
import json
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
BQ_DATASET = os.getenv('BQ_DATASET')

creds_raw = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if creds_raw:
    creds_json = json.loads(creds_raw)
    credentials = service_account.Credentials.from_service_account_info(creds_json)
    bq = bigquery.Client(project=GCP_PROJECT_ID, credentials=credentials)
else:
    bq = bigquery.Client(project=GCP_PROJECT_ID)

def load_to_bigquery(df: pd.DataFrame, table_name: str, unique_keys: list) -> None:
    table_id = f'{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}'
    temp_table_id = f'{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}_temp'

    try:
        bq.get_table(table_id)
    except Exception:
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )
        job = bq.load_table_from_dataframe(df, table_id, job_config=job_config)
        job.result()
        print(f'Created and loaded {len(df)} rows to {table_name}')
        return

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    job = bq.load_table_from_dataframe(df, temp_table_id, job_config=job_config)
    job.result()

    on_clause = ' AND '.join([f'T.{k} = S.{k}' for k in unique_keys])
    update_clause = ', '.join([f'T.{c} = S.{c}' for c in df.columns if c not in unique_keys])
    insert_cols = ', '.join(df.columns)
    insert_vals = ', '.join([f'S.{c}' for c in df.columns])

    merge_query = f"""
        MERGE `{table_id}` T
        USING `{temp_table_id}` S
        ON {on_clause}
        WHEN MATCHED THEN
            UPDATE SET {update_clause}
        WHEN NOT MATCHED THEN
            INSERT ({insert_cols})
            VALUES ({insert_vals})
    """
    bq.query(merge_query).result()
    bq.delete_table(temp_table_id)
    print(f'Upserted {len(df)} rows to {table_name}')