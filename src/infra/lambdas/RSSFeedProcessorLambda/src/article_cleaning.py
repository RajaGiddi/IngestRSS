import re
from typing import Optional


def remove_newlines(text: str) -> str:
    return text.replace('\n', '')


def remove_urls(text: str) -> str:
    url_pattern = re.compile(r'http\S+|www\S+')
    return url_pattern.sub('', text)


def clean_text(text: Optional[str]) -> str:
    """Best-effort cleaner that tolerates None and returns a string."""
    if not text:
        return ''
    text = remove_newlines(text)
    text = remove_urls(text)
    return text