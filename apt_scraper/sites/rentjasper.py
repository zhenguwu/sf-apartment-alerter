from __future__ import annotations

import re

from .base import Site
from ._html import strip_noise


class RentJasper(Site):
    """rentjasper.securecafe.com (RentCafe / Yardi online-leasing).

    The page is gated by a Cloudflare bot challenge, so we need the browser
    fetcher. Once past the challenge, listings live in
    ``<div id="floorplanlist">`` containing one ``<tbody class="floorplan-details">``
    per bedroom group. Each row exposes a floor plan code (e.g. S-2, 1-B, 2-B),
    bed/bath, sq.ft., rent range, and a ``<span class="available-fp">N Available</span>``
    badge with the live unit count.

    Notes:
      * The site only exposes availability at the FLOORPLAN level, not per
        individual unit number. We treat each floorplan with >=1 available
        as a single "Unit" for de-dup purposes — the floorplan code (S-2,
        1-B, etc.) is the stable id. This means re-supply within a floorplan
        won't re-notify; that's a tradeoff worth revisiting if needed.
    """

    name = "rentjasper"
    fetcher_kind = "browser"

    def fetch_hints(self) -> dict:
        return {
            # CF challenge takes a few seconds and never hits networkidle.
            "wait_until": "domcontentloaded",
            # Wait for the listings table to actually render before snapshotting.
            "wait_for": "tbody.floorplan-details",
            "wait_ms": 4000,
            "timeout_ms": 60_000,
        }

    def narrow(self, html: str) -> str:
        html = strip_noise(html)

        m = re.search(r'<div id="floorplanlist"', html)
        if not m:
            return html
        start = m.start()
        # Listings end at the disclaimer block.
        end_match = re.search(r'id="CustMsgDivBottom"', html[start:])
        end = start + end_match.start() if end_match else start + 120_000
        return html[start:end]
