from __future__ import annotations

from typing import Protocol


class Fetcher(Protocol):
    """Anything that can turn a URL into HTML.

    Implementations must handle their own anti-bot mitigation (UA, headers,
    cookies, JS execution, etc.). The site adapter calls .fetch(url) and
    receives raw HTML.
    """

    def fetch(self, url: str, **kwargs) -> str: ...

    def close(self) -> None: ...
