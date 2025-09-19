#!/usr/bin/env python3
import os
import sys
import logging
from dotenv import load_dotenv

# Ensure repository root is current working dir and importable
ROOT = os.path.dirname(os.path.dirname(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Add lambda src path to import modules directly
lambda_src = os.path.join(ROOT, 'src', 'infra', 'lambdas', 'RSSFeedProcessorLambda', 'src')
if lambda_src not in sys.path:
    sys.path.insert(0, lambda_src)

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('quick_local_ingest')

from feed_processor import extract_feed
from data_storage import s3_save_article
import boto3
import json

import argparse

parser = argparse.ArgumentParser(description='Quick local ingest for a single RSS feed')
parser.add_argument('--url', '-u', help='Feed URL to ingest', default='https://export.arxiv.org/rss/cs')
parser.add_argument('--dt', '-d', type=int, help='Last seen unix timestamp (0 for all)', default=0)
args = parser.parse_args()

feed = {'u': args.url, 'dt': args.dt}

if __name__ == '__main__':
    logger.info(f"Running local ingest for feed: {feed['u']} (dt={feed['dt']})")
    try:
        result = extract_feed(feed)
        if not result:
            logger.info('No result returned from extract_feed (possible parsing/extraction error)')
            sys.exit(0)

        articles = result.get('articles', [])
        logger.info(f"Found {len(articles)} new articles")

        uploaded = 0
        first_key = None
        for a in articles:
            try:
                s3_save_article(a)
                if first_key is None:
                    # build the key the same way s3_save_article does
                    from datetime import datetime
                    now = datetime.now()
                    article_id = a['article_id']
                    first_key = f"{now.year}/{now.month}/{now.day}/{article_id}.json"
                uploaded += 1
            except Exception as e:
                logger.exception(f"Failed to upload article {a.get('article_id')}: {e}")

        logger.info(f"Uploaded {uploaded}/{len(articles)} articles to S3")
        # If we uploaded at least one article, fetch and print it for verification
        if first_key:
            s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
            bucket = os.getenv('S3_BUCKET_NAME')
            try:
                resp = s3.get_object(Bucket=bucket, Key=first_key)
                body = resp['Body'].read().decode('utf-8')
                metadata = resp.get('Metadata', {})
                print('\n--- Sample uploaded article (body) ---')
                print(body[:1000])
                print('\n--- Sample uploaded article (metadata) ---')
                print(json.dumps(metadata, indent=2))
            except Exception as e:
                logger.exception(f"Failed to fetch sample article from S3: {e}")
    except Exception as e:
        logger.exception(f"Local ingest failed: {e}")
        sys.exit(1)
