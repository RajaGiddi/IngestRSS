"""Audit tag coverage in S3:
- Counts total JSON objects, how many have non-empty 'tags' metadata, and how many are missing/empty.
- Prints a few sample keys that are missing tags.

Usage:
  python3 scripts/audit_tag_coverage.py --bucket <bucket> [--prefix 2025/9/21/] [--limit-missing 10]
"""
import os
import sys
import argparse
import boto3


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--bucket', default=os.environ.get('S3_BUCKET_NAME') or os.environ.get('CONTENT_BUCKET'), help='S3 bucket name')
    p.add_argument('--prefix', default='', help='S3 prefix to scan (default whole bucket)')
    p.add_argument('--limit-missing', type=int, default=10, help='Max missing keys to print')
    return p.parse_args()


def iter_json_keys(s3, bucket, prefix):
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get('Contents', []):
            key = o['Key']
            if key.lower().endswith('.json'):
                yield key


def main():
    args = parse_args()
    if not args.bucket:
        print('Bucket required via --bucket or env', file=sys.stderr)
        sys.exit(2)

    s3 = boto3.client('s3')
    total = 0
    tagged = 0
    missing = 0
    missing_keys = []

    for key in iter_json_keys(s3, args.bucket, args.prefix):
        total += 1
        head = s3.head_object(Bucket=args.bucket, Key=key)
        meta = head.get('Metadata', {}) or {}
        tags = meta.get('tags', '')
        if isinstance(tags, str) and tags.strip():
            tagged += 1
        else:
            missing += 1
            if len(missing_keys) < args.limit_missing:
                missing_keys.append(key)

    print(f"Prefix: '{args.prefix or '[ALL]'}'")
    print(f"Total JSON objects: {total}")
    print(f"Tagged (non-empty tags): {tagged}")
    print(f"Missing or empty tags: {missing}")
    if missing_keys:
        print("Sample missing keys:")
        for k in missing_keys:
            print(f"  - {k}")


if __name__ == '__main__':
    main()
