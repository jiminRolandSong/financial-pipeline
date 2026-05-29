import sys
import os
import logging

sys.path.append('/var/task')

from transform import run as transform_run

logger = logging.getLogger(__name__)

def lambda_handler(event, context):
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        logger.info('Triggered by: s3://%s/%s', bucket, key)

    transform_run()
    return {
        'statusCode': 200,
        'body': 'Transform and load complete'
    }
