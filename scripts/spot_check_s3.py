"""Spot-check a few S3 JSON objects: print key, title, and tags from metadata.

Usage:
  python3 scripts/spot_check_s3.py --bucket <bucket> --prefix 2025/9/21/ --limit 3
"""
import os
import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--bucket', default=os.environ.get('S3_BUCKET_NAME') or os.environ.get('CONTENT_BUCKET'), help='S3 bucket name')
    p.add_argument('--prefix', default='', help='S3 prefix to scan')
    p.add_argument('--limit', type=int, default=3, help='Number of items to print')
    return p.parse_args()


def list_json_objects(s3, bucket, prefix):
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    for page in pages:
        for o in page.get('Contents', []):
            key = o['Key']
            if key.lower().endswith('.json'):
                yield key


def fetch_article(s3, bucket, key):
    r = s3.get_object(Bucket=bucket, Key=key)
    body = r['Body'].read().decode('utf-8')
    try:
        data = json.loads(body)
    except Exception:
        data = {'_raw': body}
    meta = r.get('Metadata', {})
    return data, meta


def main():
    args = parse_args()
    if not args.bucket:
        print('Bucket required via --bucket or env', file=sys.stderr)
        sys.exit(2)

    s3 = boto3.client('s3')
    count = 0

    for key in list_json_objects(s3, args.bucket, args.prefix):
        try:
            data, meta = fetch_article(s3, args.bucket, key)
            title = ''
            if isinstance(data, dict):
                for k in ['title', 'headline', 'name', 'paper_title', 'article_title', 'news_title']:
                    if k in data and data[k]:
                        title = str(data[k])
                        break
            tags = (meta or {}).get('tags', '')
            print(f"- {key}\n  title: {title[:200]}\n  tags: {tags}\n")
            count += 1
            if args.limit and count >= args.limit:
                break
        except ClientError as e:
            print(f"S3 error for {key}: {e}")


if __name__ == '__main__':
    main()
