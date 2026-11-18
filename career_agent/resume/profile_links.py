"""Canonical URLs and display labels for resume profile links."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


_URL = re.compile(r"(?:https?://|www\.)[^\s，。；;<>]+", re.IGNORECASE)


def link_url(value: str) -> str:
    match = _URL.search(value)
    if not match:
        return value.strip()
    url = match.group().rstrip(".,;:，。；）)")
    return "https://" + url if url.lower().startswith("www.") else url


def link_label(value: str, *, english: bool = False) -> str:
    host = urlsplit(link_url(value)).hostname or ""
    host = host.lower().removeprefix("www.")
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "LinkedIn"
    if host == "github.com" or host.endswith(".github.com"):
        return "GitHub"
    return "Website" if english else "个人网站"
