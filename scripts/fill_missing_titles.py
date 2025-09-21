"""Fill missing article titles by scraping the page <title>/og:title.

- Scans S3 JSON objects; for each object where title is null/empty and no body text
  is present, fetches the page at `link` and extracts a title.
- Writes the updated JSON back to S3 (unless --dry-run).

Notes:
- Uses only 'requests' and stdlib HTML parsing (regex/heuristics) to avoid heavy deps.
- Reads and writes the entire JSON body; preserves existing S3 metadata.
- Set a small limit and dry-run first.
"""
import os
import re
import sys
import json
import time
import html
import argparse
from typing import Tuple

import boto3
from botocore.exceptions import ClientError
import requests
from urllib.parse import urlparse, unquote, parse_qs

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
MAX_HTML_BYTES = 1024 * 1024  # 1 MiB cap
REQ_TIMEOUT = 12


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--bucket', default=os.environ.get('S3_BUCKET_NAME') or os.environ.get('CONTENT_BUCKET'), help='S3 bucket name')
    p.add_argument('--prefix', default='', help='S3 prefix to scan')
    p.add_argument('--limit', type=int, default=0, help='Max objects to modify (0 = no limit)')
    p.add_argument('--dry-run', action='store_true', help='Do not write to S3, just print planned changes')
    p.add_argument('--prefer-prefix', default='2025/9/21/', help='Prefer scanning this prefix first to target recent nulls')
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


body_key_candidates = {
    'text', 'content', 'summary', 'description', 'abstract', 'body',
    'article', 'article_text', 'clean_text', 'cleaned_text', 'full_text',
    'textcontent', 'maintext', 'body_text', 'articlebody', 'raw_text', '_raw',
    'content_text', 'content_html', 'summary_detail', 'description_detail', 'selftext',
    'story', 'lead', 'lead_paragraph', 'teaser', 'deck', 'caption', 'alt', 'snippet',
}

title_key_candidates = {
    'title', 'headline', 'name', 'paper_title', 'papertitle', 'article_title', 'news_title'
}

substr_match = ('text', 'content', 'body', 'abstract', 'summary', 'desc', 'para')


def to_text(val):
    if val is None:
        return ''
    if isinstance(val, (str, bytes)):
        return val.decode('utf-8') if isinstance(val, bytes) else val
    if isinstance(val, dict):
        out = []
        for _k, _v in val.items():
            t = to_text(_v)
            if t:
                out.append(t)
        return '\n'.join(out)
    if isinstance(val, (list, tuple, set)):
        parts = [to_text(v) for v in val]
        return '\n'.join([p for p in parts if p])
    return str(val)


def extract_text_presence(obj) -> Tuple[bool, bool]:
    """Return (has_body_text, has_title_text) using recursive scan.
    Does not return actual text to keep this fast.
    """
    has_body = False
    has_title = False

    def walk(node):
        nonlocal has_body, has_title
        if has_body and has_title:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                if kl in body_key_candidates or any(s in kl for s in substr_match):
                    t = to_text(v).strip()
                    if t:
                        has_body = True
                if kl in title_key_candidates:
                    t = to_text(v).strip()
                    if t:
                        has_title = True
                walk(v)
        elif isinstance(node, (list, tuple, set)):
            for it in node:
                walk(it)

    walk(obj)
    return has_body, has_title


def current_title(data) -> str:
    if not isinstance(data, dict):
        return ''
    for k in ['title', 'headline', 'name', 'paper_title', 'article_title', 'news_title']:
        if k in data and data[k]:
            val = to_text(data[k]).strip()
            if val:
                return val
    return ''


META_OG_TITLE = re.compile(r'<meta[^>]+(?:property|name)=["\
\']og:title["\
\'][^>]*content=["\
\'](.*?)["\
\']', re.IGNORECASE)
META_TW_TITLE = re.compile(r'<meta[^>]+name=["\
\']twitter:title["\
\'][^>]*content=["\
\'](.*?)["\
\']', re.IGNORECASE)
TITLE_TAG = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
H1_TAG = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
TAG_STRIP = re.compile(r'<[^>]+>')


def clean_title(s: str) -> str:
    s = html.unescape(s or '')
    s = TAG_STRIP.sub('', s)
    s = s.replace('\n', ' ').replace('\r', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:300]


def extract_title_from_html(html_text: str) -> str:
    for pat in (META_OG_TITLE, META_TW_TITLE, TITLE_TAG, H1_TAG):
        m = pat.search(html_text)
        if m:
            t = clean_title(m.group(1))
            if t:
                return t
    return ''


def fetch_title_from_link(url: str) -> str:
    if not url or not isinstance(url, str):
        return ''
    try:
        with requests.get(url, headers={'User-Agent': UA}, timeout=REQ_TIMEOUT, stream=True) as r:
            r.raise_for_status()
            content = b''
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    break
                content += chunk
                if len(content) >= MAX_HTML_BYTES:
                    break
            # Decode
            enc = r.encoding or 'utf-8'
            text = content.decode(enc, errors='replace')
            return extract_title_from_html(text)
    except Exception:
        return ''


def derive_title_from_url(url: str) -> str:
    """Best-effort title from URL slug if HTML fetch fails.
    - Takes last non-empty path segment
    - Drops common file extensions and numeric-only/hex-only IDs
    - Replaces separators with spaces and title-cases
    - Also checks common query params like 'title'
    """
    if not url or not isinstance(url, str):
        return ''
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        for cand_key in ('title', 'headline', 't'):
            if cand_key in qs and qs[cand_key]:
                cand = clean_title(qs[cand_key][0])
                if cand:
                    return cand
        segs = [s for s in parsed.path.split('/') if s]
        if not segs:
            return ''
        last = unquote(segs[-1])
        last = re.sub(r'\.(html|htm|php|aspx?)$', '', last, flags=re.IGNORECASE)
        # skip purely numeric or hex-ish ids
        if re.fullmatch(r'[0-9]+', last) or re.fullmatch(r'[0-9a-fA-F]{8,}', last):
            if len(segs) >= 2:
                last = unquote(segs[-2])
                last = re.sub(r'\.(html|htm|php|aspx?)$', '', last, flags=re.IGNORECASE)
        s = last.replace('-', ' ').replace('_', ' ')
        s = clean_title(s)
        # Require some alphabetic content and minimal length
        if len(s) >= 8 and re.search(r'[A-Za-z]', s):
            # Title-case but preserve all-upper acronyms by not forcing lower
            return s
        return ''
    except Exception:
        return ''


def write_json_to_s3(s3, bucket: str, key: str, data: dict, prev_meta: dict):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json', Metadata=prev_meta or {})


def main():
    args = parse_args()
    if not args.bucket:
        print('Bucket required via --bucket or env', file=sys.stderr)
        sys.exit(2)

    s3 = boto3.client('s3')

    processed = 0
    examined = 0

    prefixes = [args.prefer_prefix] if args.prefer_prefix else []
    if args.prefix and args.prefix not in prefixes:
        prefixes.append(args.prefix)
    if not prefixes:
        prefixes = ['']

    for pref in prefixes:
        for key in list_json_objects(s3, args.bucket, pref):
            try:
                data, meta = fetch_article(s3, args.bucket, key)
                examined += 1
                if not isinstance(data, dict):
                    continue
                link = data.get('link')
                if not link:
                    continue
                has_body, has_title = extract_text_presence(data)
                title_val = current_title(data)
                if has_title and title_val:
                    continue
                if has_body:
                    continue

                new_title = fetch_title_from_link(link)
                if not new_title:
                    new_title = derive_title_from_url(link)
                if not new_title:
                    continue
                if args.dry_run:
                    print(f"Dry-run: would set title for {key} -> '{new_title}'")
                else:
                    data = dict(data)
                    data['title'] = new_title
                    data.setdefault('_meta', {})
                    if isinstance(data['_meta'], dict):
                        data['_meta']['title_source'] = 'scraped'
                        data['_meta']['title_filled_at'] = int(time.time())
                    write_json_to_s3(s3, args.bucket, key, data, meta)
                    print(f"Updated title for {key}")
                processed += 1
                if args.limit and processed >= args.limit:
                    print(f"Limit reached: processed {processed}")
                    print(f"Examined {examined} objects")
                    return
            except ClientError as e:
                print(f"S3 error for {key}: {e}")
            except Exception as e:
                print(f"Error processing {key}: {e}")

    print(f"Done. Processed {processed}. Examined {examined}.")


if __name__ == '__main__':
    main()
