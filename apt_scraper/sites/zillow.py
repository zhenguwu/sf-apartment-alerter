"""Zillow rental search.

Zillow is gated by PerimeterX "Press & Hold" — uses fingerprinting that
defeats every flavor of headless browser we tested (vanilla playwright,
playwright-stealth, patchright headless, headless="new"). Only patchright +
real Chrome + headed-but-offscreen passes the fingerprint check. See
``apt_scraper/fetchers/stealth.py``.

Once we're past the gate, the page embeds Zillow's search-state JSON
directly in the HTML. The fields we want live at:

    cat1.searchResults.listResults[]   <- actual matches
    cat1.searchResults.relaxedResults[] <- "Similar results nearby"
                                            (must be excluded — these are
                                            results from outside the user's
                                            map bounds / filters)

So narrow() finds ``"listResults":[`` and slices up to its matching ``]``,
then wraps it in a tiny JSON envelope for the LLM. ``relaxedResults`` is
simply never included in what the LLM sees.
"""
from __future__ import annotations

import json
import logging

from .base import Site


log = logging.getLogger(__name__)


class Zillow(Site):
    name = "zillow"
    fetcher_kind = "stealth"

    def fetch_hints(self) -> dict:
        return {
            "wait_until": "domcontentloaded",
            # The page is heavy and ships data over multiple chunks; give it
            # a few seconds to finish hydrating before we snapshot.
            "wait_ms": 8000,
            "timeout_ms": 60_000,
        }

    def narrow(self, html: str) -> str:
        idx = html.find('"listResults":[')
        if idx < 0:
            log.warning("zillow: no listResults marker found — page may have failed to load")
            # Return a stub so the LLM emits {"units": []} cleanly rather than
            # hallucinating from the surrounding chrome.
            return '{"listResults": []}'

        array_start = html.find("[", idx)
        end = _find_balanced_close(html, array_start, "[", "]")
        if end < 0:
            log.warning("zillow: malformed listResults JSON; falling back to empty")
            return '{"listResults": []}'

        list_json = html[array_start : end + 1]

        # Sanity: parse it once so we fail fast if the slice is broken, and
        # to strip out noisy fields (huge image srcsets, tracking ids) before
        # the LLM sees it.
        try:
            items = json.loads(list_json)
        except json.JSONDecodeError as e:
            log.warning("zillow: listResults parse failed (%s); sending raw slice", e)
            return f'{{"listResults": {list_json}}}'

        cleaned = []
        for item in items:
            row = {k: v for k, v in item.items() if k in _KEEP_KEYS}
            # zpid is Zillow's stable listing id — use it as the unit_id so
            # the LLM and downstream dedup don't fall back to fragile names
            # like "#D" or "APT 28D" pulled from the address.
            zpid = item.get("zpid") or item.get("id")
            if zpid:
                row["unit_id"] = str(zpid)
            cleaned.append(row)
        return json.dumps({"listResults": cleaned}, ensure_ascii=False)


# Fields the LLM actually needs. Everything else is noise (image URLs,
# tracking ids, provider metadata, marketing flags).
_KEEP_KEYS = {
    "zpid", "detailUrl", "statusType", "statusText",
    "price", "unformattedPrice",
    "address", "addressStreet", "addressCity", "addressState", "addressZipcode",
    "beds", "baths", "area",
    "hdpData",        # contains nested home info if present
    "isFeaturedListing",
    "availabilityDate", "availabilityCount", "units",
    "isFsba", "isFsbo",
}


def _find_balanced_close(text: str, start: int, open_c: str, close_c: str) -> int:
    """Walk JSON-ish text starting at ``start`` (which must be ``open_c``),
    returning the index of the matching ``close_c``, or -1 if unbalanced.

    Treats quoted strings as opaque so brackets inside string values don't
    throw off the count.
    """
    if start < 0 or start >= len(text) or text[start] != open_c:
        return -1
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return i
    return -1
