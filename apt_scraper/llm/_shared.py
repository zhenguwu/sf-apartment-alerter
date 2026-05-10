"""Provider-agnostic helpers: prompt template, JSON parsing, retry loop.

Each `LLMProvider` implementation calls a vendor SDK to turn a prompt into raw
text, then delegates parsing to ``parse_response`` and retry to ``with_retry``.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any, Callable

from ..models import Unit
from .base import ParseResult


log = logging.getLogger(__name__)


PROMPT_TEMPLATE = """\
You are extracting BOOKABLE rental units (or floor plans with availability)
from the HTML of an apartment listings page.

INCLUDE a unit/floor plan if ANY of these is true:
  * It has an explicit "Available <date>" button or label (the date may be
    weeks or months in the future — apartment hunters still want this).
  * It shows a price/rent and a way to apply, view units, or check availability.
  * It is listed in a tab/section named "Available", "Floor Plans", etc.
    without explicit unavailability markers.

EXCLUDE only if the page explicitly says the unit/floor plan is:
  * "Waitlist", "Sold Out", "Leased", "Not Available", "Coming Soon" (with
    no rentable units yet), "0 Available", or has no rent shown AND no
    apply/availability action.

Return ONLY a JSON object in EXACTLY this schema (no prose, no markdown fences):

{{
  "units": [
    {{
      "unit_id": "stable identifier — prefer the unit number (e.g. '3506'); if absent, use the floor plan code (e.g. 'S-2', '1-B', 'S01'). MUST NOT contain price, sqft, or date.",
      "name": "human label (unit number or floor plan name)",
      "bedrooms": <integer; 0 = studio>,
      "bathrooms": <number, e.g. 2.5 or 3>,
      "price_usd": <integer monthly rent; if a range, use the lowest; null if 'call' / 'contact'>,
      "sqft": <integer or null; if a range, use the lowest>,
      "available_date": "YYYY-MM-DD if a specific date is shown, 'now' if currently available, else null",
      "url": "<absolute URL to the unit detail / apply page if linked, else null>",
      "notes": "<short — floor, view, available count, fees, anything notable>"
    }}
  ]
}}

If a single floor plan reports N>1 available, emit ONE entry for that plan
and put 'N units available' in notes (the page typically doesn't expose
individual unit numbers in this case).

If no units are bookable, return {{"units": []}}.
Do not invent units.

Site: {site}
Source URL: {url}

HTML:
{html}
"""


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def build_prompt(site: str, url: str, html: str) -> str:
    return PROMPT_TEMPLATE.format(site=site, url=url, html=html)


def parse_response(site: str, text: str) -> ParseResult:
    """Turn raw model text into a ParseResult of validated Units."""
    data = _safe_load_json(text)
    if data is None:
        log.error("LLM returned non-JSON for %s. First 300 chars: %s", site, text[:300])
        return ParseResult(raw_response=text, error="non-json response")

    units: list[Unit] = []
    for item in data.get("units", []) or []:
        try:
            units.append(_to_unit(site, item))
        except Exception as e:
            log.warning("Skipping malformed unit from %s: %s (%s)", site, item, e)
    return ParseResult(units=units, raw_response=text)


def with_retry(
    site: str,
    fn: Callable[[], str],
    *,
    transient_markers: tuple[str, ...],
    max_attempts: int = 4,
) -> str | None:
    """Run ``fn`` with exponential backoff on transient errors.

    ``transient_markers`` is a tuple of substrings (status codes / error names)
    to look for in the stringified exception. Provider-specific.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            msg_lower = msg.lower()
            transient = any(s.lower() in msg_lower for s in transient_markers)
            if attempt == max_attempts or not transient:
                log.error("LLM call failed for %s after %d attempt(s): %s", site, attempt, e)
                return None
            delay = (2 ** attempt) + random.uniform(0, 2)
            log.warning(
                "LLM transient error for %s (attempt %d/%d): %s — retrying in %.1fs",
                site, attempt, max_attempts, msg.split("\n")[0][:120], delay,
            )
            time.sleep(delay)
    return None


def _safe_load_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def _to_unit(site: str, item: dict[str, Any]) -> Unit:
    uid = str(item.get("unit_id") or "").strip()
    if not uid:
        name = str(item.get("name") or "")
        sqft = item.get("sqft")
        uid = f"{name}-{sqft}".strip("-") or "unknown"

    bath = item.get("bathrooms")
    if isinstance(bath, str):
        try:
            bath = float(bath)
        except ValueError:
            bath = None

    price = item.get("price_usd")
    if isinstance(price, str):
        digits = re.sub(r"[^\d]", "", price)
        price = int(digits) if digits else None

    return Unit(
        site=site,
        unit_id=uid,
        name=item.get("name"),
        bedrooms=item.get("bedrooms"),
        bathrooms=bath,
        price_usd=price,
        sqft=item.get("sqft"),
        available_date=item.get("available_date"),
        url=item.get("url"),
        notes=item.get("notes"),
    )
