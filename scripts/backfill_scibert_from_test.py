"""Backfill S3 article tags using SciBERT logic from service/test_scibert.py.

This script imports the current functions from test_scibert.py (embedder + classifier)
to compute labels for each article's text and writes them to S3 object metadata as a
comma-separated 'tags' value. It does not modify object bodies.

WARNING: This runs SciBERT locally in-process and will download model weights; ensure
you have torch/transformers installed and sufficient resources.
"""
import os
import json
import argparse
import boto3
from botocore.exceptions import ClientError
import sys
import importlib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    sc = importlib.import_module('analysis-toolkit.service.test_scibert')
except ModuleNotFoundError as e:
    raise SystemExit(f"Could not import test_scibert from src/analysis-toolkit/service: {e}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--bucket', default=os.environ.get('S3_BUCKET_NAME') or os.environ.get('CONTENT_BUCKET'), help='S3 bucket name')
    p.add_argument('--prefix', default='', help='S3 prefix to scan (default: whole bucket)')
    p.add_argument('--limit', type=int, default=0, help='Limit number of objects to process (0 = no limit)')
    p.add_argument('--threshold', type=float, default=sc.GLOBAL_THRESHOLD, help='Probability threshold for labels')
    p.add_argument('--topk', type=int, default=3, help='Fallback top-k labels when none exceed threshold (0 to disable)')
    p.add_argument('--skip-tagged', action='store_true', help='Skip objects that already have non-empty tags in metadata')
    p.add_argument('--dry-run', action='store_true', help='Do not write to S3; just print what would happen')
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


def compute_tags(text: str, threshold: float, topk: int):
    probs = sc.probs_for_all(text)
    picked = [(lbl, p) for lbl, p in probs.items() if p >= threshold]
    picked.sort(key=lambda x: -x[1])
    if not picked and topk > 0:
        picked = sc.top_k(probs, topk)
    return [lbl for lbl, _ in picked]


def update_metadata_only(s3, bucket, key, metadata):
    copy_source = {'Bucket': bucket, 'Key': key}
    extra = {
        'MetadataDirective': 'REPLACE',
        'Metadata': metadata,
        'ContentType': 'application/json'
    }
    s3.copy_object(Bucket=bucket, Key=key, CopySource=copy_source, **extra)


def main():
    args = parse_args()
    if not args.bucket:
        raise SystemExit('Bucket must be provided via --bucket or S3_BUCKET_NAME/CONTENT_BUCKET env var')

    s3 = boto3.client('s3')
    count = 0
    for key in list_json_objects(s3, args.bucket, args.prefix):
        try:
            data, meta = fetch_article(s3, args.bucket, key)
            if args.skip_tagged and meta and isinstance(meta, dict):
                existing = meta.get('tags')
                if existing and existing.strip():
                    print(f"Skipping (already tagged): {key}")
                    continue

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
                """Recursively extract relevant text chunks from any nested structure.
                Preference order: body-like fields; but if none, title-only fallback is allowed.
                """
                if obj is None:
                    return [], []  # (body_chunks, title_chunks)

                wanted_exact = {
                    'text', 'content', 'summary', 'description', 'abstract', 'body',
                    'article', 'article_text', 'clean_text', 'cleaned_text', 'full_text',
                    'textcontent', 'maintext', 'body_text', 'articlebody', 'raw_text', '_raw',
                    # common rss/feeds
                    'content_text', 'content_html', 'summary_detail', 'description_detail', 'selftext',
                    'story', 'lead', 'lead_paragraph', 'teaser', 'deck', 'caption', 'alt', 'snippet',
                }
                title_keys = {
                    'title', 'headline', 'name', 'paper_title', 'papertitle', 'article_title', 'news_title'
                }

                substr_match = ('text', 'content', 'body', 'abstract', 'summary', 'desc', 'para')

                body_chunks = []
                title_chunks = []

                def walk(node):
                    if isinstance(node, dict):
                        for k, v in node.items():
                            kl = str(k).lower()
                            if kl in wanted_exact or any(s in kl for s in substr_match) or kl in title_keys:
                                t = to_text(v).strip()
                                if t:
                                    if kl in title_keys:
                                        title_chunks.append(t)
                                    else:
                                        body_chunks.append(t)
                            # Recurse regardless to catch nested keys
                            walk(v)
                    elif isinstance(node, (list, tuple, set)):
                        for it in node:
                            walk(it)

                walk(obj)
                # Deduplicate while preserving order
                def dedupe(seq):
                    seen_local = set()
                    out = []
                    for s in seq:
                        if s not in seen_local:
                            out.append(s)
                            seen_local.add(s)
                    return out

                return dedupe(body_chunks), dedupe(title_chunks)

            text = ''
            if isinstance(data, dict):
                body_chunks, title_chunks = extract_text_chunks(data)
                parts = []
                seen = set()
                # Prefer body/content chunks first
                for t in body_chunks:
                    if t and t not in seen:
                        parts.append(t)
                        seen.add(t)
                # If no body chunks, fall back to any title-like chunks
                if not parts and title_chunks:
                    for t in title_chunks:
                        if t and t not in seen:
                            parts.append(t)
                            seen.add(t)
                text = '\n\n'.join(parts).strip()
            if not text:
                print(f"Skipping (no text): {key}")
                continue
            tags = compute_tags(text, args.threshold, args.topk)
            tag_str = ','.join(tags)
            if args.dry_run:
                print(f"Dry-run: {key} -> tags=[{tag_str}]")
            else:
                meta = dict(meta or {})
                meta['tags'] = tag_str
                update_metadata_only(s3, args.bucket, key, meta)
                print(f"Updated {key} with tags=[{tag_str}]")
            count += 1
            if args.limit and count >= args.limit:
                break
        except ClientError as e:
            print(f"S3 error for {key}: {e}")
        except Exception as e:
            print(f"Error processing {key}: {e}")

    print(f"Done. Processed: {count}")


if __name__ == '__main__':
    main()
