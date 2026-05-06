from .base import Fetcher
from .http import HttpFetcher

__all__ = ["Fetcher", "HttpFetcher", "get_fetcher"]


def get_fetcher(kind: str) -> Fetcher:
    if kind == "http":
        return HttpFetcher()
    if kind == "browser":
        # Imported lazily so users without playwright installed can still run http-only sites.
        from .browser import BrowserFetcher
        return BrowserFetcher()
    raise ValueError(f"Unknown fetcher: {kind}")
