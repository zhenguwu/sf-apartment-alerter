from __future__ import annotations

import re

from .base import Site
from ._html import strip_noise


class ModeraRinconHill(Site):
    """moderarinconhill.com (Mill Creek / Entrata-powered).

    Cloudflare-challenged, so we use the browser fetcher. Listings live in
    ``<div id="floorplan-overview-content">``, with three tab-panels —
    ``<ul id="floorplans-Studio">``, ``<ul id="floorplans-OneBedroom">``,
    and ``<ul id="floorplans-TwoBedroom">``. Each ``<li class="fp-group-item">``
    is one floorplan, and the primary action button text reads
    "Available <Mon DD, YYYY>" when units are bookable; the floorplan code
    sits in ``<h4 class="fp-name">`` (e.g. S01, A03, B01).

    Like rentjasper, this site exposes availability at the FLOORPLAN level
    rather than per-unit. The floorplan code is the stable id we use to dedup.
    """

    name = "modera-rincon-hill"
    fetcher_kind = "browser"

    def fetch_hints(self) -> dict:
        return {
            "wait_until": "domcontentloaded",
            # Wait for the floorplan tab content to render past the CF challenge.
            "wait_for": "ul.fp-group-list",
            "wait_ms": 4000,
            "timeout_ms": 60_000,
        }

    def narrow(self, html: str) -> str:
        html = strip_noise(html)

        m = re.search(r'<div id="floorplan-overview-content"', html)
        if not m:
            return html
        start = m.start()
        end_match = re.search(r'data-pp-footer=', html[start:])
        end = start + end_match.start() if end_match else start + 120_000
        return html[start:end]
