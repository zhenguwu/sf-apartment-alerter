from __future__ import annotations

import re

from .base import Site


# Stripped wholesale: nothing in these adds signal, and they balloon the page.
_STRIP_TAGS = re.compile(
    r"<(svg|script|style|noscript|picture|source|iframe)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
# Self-closing junk.
_STRIP_VOID = re.compile(r"<(img|input|link|meta)\b[^>]*?/?>", re.IGNORECASE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WHITESPACE = re.compile(r"\s{2,}")


class RentNema(Site):
    """rentnema.com (Craft CMS, server-rendered).

    The listings section is a single ``<div class="availabilities-list">``
    containing one ``<div class="availabilities-list__item" data-unit-...>``
    per unit. Each row already has bedrooms/baths/sqft/rent/availability in
    ``data-*`` attributes — perfect for the LLM to parse cheaply.
    """

    name = "rentnema"
    fetcher_kind = "http"

    def fetch_hints(self) -> dict:
        return {}

    def narrow(self, html: str) -> str:
        html = _STRIP_TAGS.sub("", html)
        html = _STRIP_VOID.sub("", html)
        html = _HTML_COMMENT.sub("", html)
        html = _WHITESPACE.sub(" ", html)

        m = re.search(r'<div class="availabilities-list\s*"', html)
        if not m:
            return html
        start = m.start()
        # Listings end well before the footer; cap generously and trust the
        # LLM to ignore trailing chrome.
        return html[start : start + 120_000]
