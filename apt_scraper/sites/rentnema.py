from __future__ import annotations

import re

from .base import Site
from ._html import strip_noise


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
        html = strip_noise(html)
        m = re.search(r'<div class="availabilities-list\s*"', html)
        if not m:
            return html
        start = m.start()
        # Listings end well before the footer; cap generously and trust the
        # LLM to ignore trailing chrome.
        return html[start : start + 120_000]
