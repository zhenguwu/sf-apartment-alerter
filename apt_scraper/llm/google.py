from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types as genai_types

from ..config import LLMCfg
from ..models import Unit
from .base import ParseResult


log = logging.getLogger(__name__)


PROMPT_TEMPLATE = """\
You are extracting CURRENTLY AVAILABLE rental units from the HTML of an
apartment listings page. Be precise — only include units actually offered for
rent right now. Exclude units marked waitlist, coming soon, leased, or sold-out.

Return ONLY a JSON object in EXACTLY this schema (no prose, no markdown fences):

{{
  "units": [
    {{
      "unit_id": "stable identifier — prefer the unit number (e.g. '3506'); if absent, use floor plan code + sqft (e.g. '3F-1935'). MUST NOT contain price or date.",
      "name": "human label (unit number or floor plan name)",
      "bedrooms": <integer, e.g. 3>,
      "bathrooms": <number, e.g. 2.5 or 3>,
      "price_usd": <integer monthly rent, or null if 'call' / 'contact'>,
      "sqft": <integer or null>,
      "available_date": "YYYY-MM-DD or 'now' or null",
      "url": "<absolute URL to the unit detail / apply page if linked, else null>",
      "notes": "<short — floor, view, fees, anything notable>"
    }}
  ]
}}

If no units are available, return {{"units": []}}.
Do not invent units. Do not include any unit whose availability is uncertain.

Site: {site}
Source URL: {url}

HTML:
{html}
"""


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class GoogleLLM:
    """Gemini / Gemma via the google-genai SDK.

    Gemma chat models exposed by the Gemini API have stricter output controls
    than full Gemini models, so we ask for plain text and parse JSON ourselves
    rather than relying on response_mime_type=application/json.
    """

    def __init__(self, cfg: LLMCfg):
        self._client = genai.Client(api_key=cfg.api_key)
        self._model = cfg.model

    def extract(self, *, site: str, url: str, html: str) -> ParseResult:
        prompt = PROMPT_TEMPLATE.format(site=site, url=url, html=html)
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                ),
            )
            text = (resp.text or "").strip()
        except Exception as e:
            log.error("LLM call failed for %s: %s", site, e)
            return ParseResult(error=str(e))

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


def _safe_load_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
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
