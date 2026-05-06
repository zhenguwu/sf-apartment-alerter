from __future__ import annotations

import logging
import random

import httpx


log = logging.getLogger(__name__)


# Realistic desktop UAs. Rotated per-fetch to look less robotic.
_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
]


class HttpFetcher:
    """httpx-based fetcher with realistic browser headers.

    Sufficient for server-rendered sites (Craft, Squarespace, plain Wordpress,
    most listing pages). For sites that 403/challenge or render content via JS,
    use the BrowserFetcher.
    """

    def __init__(self, timeout: float = 30.0):
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
        )

    def fetch(self, url: str, **kwargs) -> str:
        ua = random.choice(_UAS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            # No 'br' — httpx doesn't decode brotli without the optional `brotli` package.
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        headers.update(kwargs.get("headers", {}))
        r = self._client.get(url, headers=headers)
        r.raise_for_status()
        return r.text

    def close(self) -> None:
        self._client.close()
