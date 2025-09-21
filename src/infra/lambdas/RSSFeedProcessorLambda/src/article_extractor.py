import newspaper
import logging
import re
import html
import requests
from urllib.parse import urlparse, unquote, parse_qs


logger = logging.getLogger()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

TITLE_TAG = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
META_OG_TITLE = re.compile(r'<meta[^>]+(?:property|name)=["\'\"]og:title["\'\"][^>]*content=["\'\"](.*?)["\'\"]', re.IGNORECASE)
META_TW_TITLE = re.compile(r'<meta[^>]+name=["\'\"]twitter:title["\'\"][^>]*content=["\'\"](.*?)["\'\"]', re.IGNORECASE)
H1_TAG = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
TAG_STRIP = re.compile(r'<[^>]+>')


def _clean_title(s: str) -> str:
    s = html.unescape(s or '')
    s = TAG_STRIP.sub('', s)
    s = s.replace('\n', ' ').replace('\r', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:300]


def _fetch_title_only(url: str, timeout: int = 10, max_bytes: int = 1024 * 512) -> str:
    try:
        with requests.get(url, headers={'User-Agent': UA}, timeout=timeout, stream=True) as r:
            r.raise_for_status()
            content = b''
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    break
                content += chunk
                if len(content) >= max_bytes:
                    break
            enc = r.encoding or 'utf-8'
            text = content.decode(enc, errors='replace')
            for pat in (META_OG_TITLE, META_TW_TITLE, TITLE_TAG, H1_TAG):
                m = pat.search(text)
                if m:
                    t = _clean_title(m.group(1))
                    if t:
                        return t
    except Exception:
        return ''
    return ''


def _derive_title_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        for cand in ('title', 'headline', 't'):
            if cand in qs and qs[cand]:
                v = _clean_title(qs[cand][0])
                if v:
                    return v
        segs = [s for s in parsed.path.split('/') if s]
        if not segs:
            return ''
        last = unquote(segs[-1])
        last = re.sub(r'\.(html|htm|php|aspx?)$', '', last, flags=re.IGNORECASE)
        if re.fullmatch(r'[0-9]+', last) or re.fullmatch(r'[0-9a-fA-F]{8,}', last):
            if len(segs) >= 2:
                last = unquote(segs[-2])
                last = re.sub(r'\.(html|htm|php|aspx?)$', '', last, flags=re.IGNORECASE)
        s = last.replace('-', ' ').replace('_', ' ')
        s = _clean_title(s)
        if len(s) >= 8 and re.search(r'[A-Za-z]', s):
            return s
    except Exception:
        return ''
    return ''


def extract_article(url):
    """
    Extracts the title and text of an article from the given URL.

    Returns: (title, text). Falls back to a title-only strategy if parsing fails.
    """
    logger.debug(f"Starting Newspaper Article Extraction {url}")
    config = newspaper.Config()
    config.request_timeout = 60
    article = newspaper.Article(url, keep_article_html=False, browser_user_agent=UA, fetch_images=False)

    try:
        article.download()
        logger.debug(f"Downloaded Article {url}")
        article.parse()
        logger.debug(f"Parsed Article {url}")
        t, x = article.title, article.text
        if not t:
            # Fallback to HTML title scraping
            t = _fetch_title_only(url) or _derive_title_from_url(url)
        return t, x
    except Exception as e:
        logger.error(f"Failed to extract article {url}: {str(e)}")
        # Fallback: try to at least produce a title
        t = _fetch_title_only(url) or _derive_title_from_url(url)
        return t or None, None