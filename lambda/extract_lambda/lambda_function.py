import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from extract import run

def lambda_handler(event, context):
    run()
    return {
        'statusCode': 200,
        'body': 'Extract Complete'
    }