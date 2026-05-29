import sys
import os
sys.path.append('/var/task')

from transform import run as transform_run

def lambda_handler(event, context):
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        print(f'Triggered by: s3://{bucket}/{key}')
    
    transform_run()
    return {
        'statusCode': 200,
        'body': 'Transform and load complete'
    }
