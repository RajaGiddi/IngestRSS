"""Find and print one tagged JSON and one 'no text' JSON from S3.

This script mirrors the extraction logic in backfill_scibert_from_test.py to explain
why some objects are being skipped as 'no text'. It prints:
- One example with existing non-empty 'tags' metadata
- One example where our extractor finds no usable text (body/title), with debug info
"""
import os
import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--bucket', default=os.environ.get('S3_BUCKET_NAME') or os.environ.get('CONTENT_BUCKET'), help='S3 bucket name')
    p.add_argument('--prefix', default='', help='S3 prefix to search (default: whole bucket)')
    p.add_argument('--prefer-no-text-prefix', default='2025/9/21/', help='Prefix to bias search for no-text examples')
    return p.parse_args()


essential_body_keys = {
    'text', 'content', 'summary', 'description', 'abstract', 'body',
    'article', 'article_text', 'clean_text', 'cleaned_text', 'full_text',
    'textcontent', 'maintext', 'body_text', 'articlebody', 'raw_text', '_raw',
    'content_text', 'content_html', 'summary_detail', 'description_detail', 'selftext',
    'story', 'lead', 'lead_paragraph', 'teaser', 'deck', 'caption', 'alt', 'snippet',
}

title_keys = {'title', 'headline', 'name', 'paper_title', 'papertitle', 'article_title', 'news_title'}

substr_match = ('text', 'content', 'body', 'abstract', 'summary', 'desc', 'para')


def to_text(val):
    if val is None:
        return ''
    if isinstance(val, (str, bytes)):
        return val.decode('utf-8') if isinstance(val, bytes) else val
    if isinstance(val, dict):
        parts = []
        for _k, _v in val.items():
            t = to_text(_v)
            if t:
                parts.append(str(t))
        return '\n'.join(parts)
    if isinstance(val, (list, tuple, set)):
        parts = [to_text(v) for v in val]
        return '\n'.join([p for p in parts if p])
    return str(val)


def extract_text_chunks(obj):
    if obj is None:
        return [], []
    body_chunks = []
    title_chunks = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                if kl in essential_body_keys or any(s in kl for s in substr_match) or kl in title_keys:
                    t = to_text(v).strip()
                    if t:
                        if kl in title_keys:
                            title_chunks.append(t)
                        else:
                            body_chunks.append(t)
                walk(v)
        elif isinstance(node, (list, tuple, set)):
            for it in node:
                walk(it)

    walk(obj)

    def dedupe(seq):
        seen = set()
        out = []
        for s in seq:
            if s not in seen:
                out.append(s)
                seen.add(s)
        return out

    return dedupe(body_chunks), dedupe(title_chunks)


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
        print('Bucket must be provided via --bucket or env', file=sys.stderr)
        sys.exit(2)

    s3 = boto3.client('s3')

    found_tagged = None
    found_no_text = None

    # First pass: bias for a no-text example using the provided prefix
    try:
        for key in list_json_objects(s3, args.bucket, args.prefer_no_text_prefix or args.prefix):
            data, meta = fetch_article(s3, args.bucket, key)
            body_chunks, title_chunks = extract_text_chunks(data if isinstance(data, dict) else {})
            text = ('\n\n'.join(body_chunks) or '\n\n'.join(title_chunks)).strip()
            if not text:
                found_no_text = (key, data, meta, body_chunks, title_chunks)
                break
    except ClientError as e:
        print(f"Error scanning prefer-no-text prefix: {e}")

    # Second pass: find an already-tagged example anywhere (or under main prefix)
    for key in list_json_objects(s3, args.bucket, args.prefix):
        try:
            data, meta = fetch_article(s3, args.bucket, key)
            tags = (meta or {}).get('tags')
            if tags and tags.strip():
                found_tagged = (key, data, meta)
                break
        except ClientError as e:
            print(f"S3 error for {key}: {e}")

    # Fallbacks if not found
    if not found_no_text:
        # search broadly for a no-text example
        for key in list_json_objects(s3, args.bucket, args.prefix):
            try:
                data, meta = fetch_article(s3, args.bucket, key)
                body_chunks, title_chunks = extract_text_chunks(data if isinstance(data, dict) else {})
                text = ('\n\n'.join(body_chunks) or '\n\n'.join(title_chunks)).strip()
                if not text:
                    found_no_text = (key, data, meta, body_chunks, title_chunks)
                    break
            except ClientError as e:
                print(f"S3 error for {key}: {e}")

    print("=== Tagged example ===")
    if found_tagged:
        key, data, meta = found_tagged
        print(f"Key: {key}")
        print(f"Tags: {(meta or {}).get('tags','')}")
        print("JSON (pretty, truncated):")
        js = json.dumps(data, indent=2, ensure_ascii=False)
        if len(js) > 4000:
            print(js[:4000] + "\n... [truncated] ...")
        else:
            print(js)
    else:
        print("No tagged example found under given prefix.")

    print("\n=== No-text example ===")
    if found_no_text:
        key, data, meta, body_chunks, title_chunks = found_no_text
        print(f"Key: {key}")
        print("Extractor debug:")
        print(f"  body_chunks: {len(body_chunks)}; title_chunks: {len(title_chunks)}")
        if isinstance(data, dict):
            print(f"  top-level keys: {list(data.keys())[:30]}")
        print("JSON (pretty, truncated):")
        js = json.dumps(data, indent=2, ensure_ascii=False)
        if len(js) > 4000:
            print(js[:4000] + "\n... [truncated] ...")
        else:
            print(js)
    else:
        print("No 'no-text' example found. Try adjusting --prefer-no-text-prefix.")


if __name__ == '__main__':
    main()
