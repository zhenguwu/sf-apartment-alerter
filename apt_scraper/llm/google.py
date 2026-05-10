from __future__ import annotations

import logging

from google import genai
from google.genai import types as genai_types

from ..config import LLMCfg
from ._shared import build_prompt, parse_response, with_retry
from .base import ParseResult


log = logging.getLogger(__name__)


# Transient Gemini API errors — retried with exponential backoff. 429/500/503
# are common during free-tier load spikes on the heavier Gemma models.
_RETRY_MARKERS = ("500", "502", "503", "504", "429", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED")


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
        prompt = build_prompt(site, url, html)

        def call() -> str:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                ),
            )
            return (resp.text or "").strip()

        text = with_retry(site, call, transient_markers=_RETRY_MARKERS)
        if text is None:
            return ParseResult(error="LLM call failed after retries")
        return parse_response(site, text)
