from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import SiteCfg
from ..fetchers import Fetcher


class Site(ABC):
    """Per-site adapter.

    Subclass this for each property/management-company website. The job of a
    site adapter is to:
      1) declare which fetcher to use (`fetcher_kind`),
      2) optionally pass per-site fetch hints (e.g. a CSS selector to wait on),
      3) optionally narrow the HTML before it's sent to the LLM (saves tokens
         and reduces noise — important on long pages).

    Parsing is intentionally NOT done here — the LLM is the parser. We only
    do mechanical work (fetch + slice).
    """

    #: Override per site. "http" works for server-rendered pages; "browser" for
    #: JS-heavy or bot-challenged sites.
    fetcher_kind: str = "http"

    #: Friendly name used in notifications and logs.
    name: str = "site"

    def __init__(self, cfg: SiteCfg):
        self.cfg = cfg
        self.url = cfg.url

    @abstractmethod
    def fetch_hints(self) -> dict:
        """Kwargs forwarded to fetcher.fetch(url, **hints)."""
        ...

    def fetch_html(self, fetcher: Fetcher) -> str:
        return fetcher.fetch(self.url, **self.fetch_hints())

    def narrow(self, html: str) -> str:
        """Optionally slice the HTML to just the relevant section.

        Default: pass through. Override to trim large pages — the LLM will be
        cheaper and more accurate on a focused chunk.
        """
        return html
