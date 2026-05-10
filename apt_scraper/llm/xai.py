"""xAI / Grok provider — uses the OpenAI-compatible endpoint at api.x.ai."""
from __future__ import annotations

import logging

from openai import OpenAI

from ..config import LLMCfg
from ._shared import build_prompt, parse_response, with_retry
from .base import ParseResult


log = logging.getLogger(__name__)


# xAI surfaces these as plain HTTP status codes via the openai SDK.
_RETRY_MARKERS = (
    "500", "502", "503", "504", "429",
    "rate limit", "overloaded", "timeout",
    # Network-layer transients we've actually seen from api.x.ai:
    "connection refused", "connect error", "disconnect", "reset",
    "connection error", "remote disconnected", "ECONNRESET",
)

_DEFAULT_BASE_URL = "https://api.x.ai/v1"


class XaiLLM:
    """Grok via xAI's OpenAI-compatible API.

    Configure with provider=xai and any xAI model id (e.g. ``grok-4.3``).
    Optional ``base_url`` override is read from cfg.extra if you ever need to
    point at a proxy.
    """

    def __init__(self, cfg: LLMCfg):
        base_url = getattr(cfg, "base_url", None) or _DEFAULT_BASE_URL
        self._client = OpenAI(api_key=cfg.api_key, base_url=base_url)
        self._model = cfg.model

    def extract(self, *, site: str, url: str, html: str) -> ParseResult:
        prompt = build_prompt(site, url, html)

        def call() -> str:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                # Deterministic extraction — we want the same answer for the same HTML.
                temperature=0.0,
                # max_completion_tokens is the supported successor to max_tokens on grok-4.x.
                max_completion_tokens=4096,
                # Server-enforced JSON. Prompt already says "Return ONLY a JSON object",
                # which is the required cue for json_object mode.
                response_format={"type": "json_object"},
                # This is mechanical extraction — no chain-of-thought needed. "low"
                # keeps latency/cost down on reasoning-capable Grok models; ignored on
                # non-reasoning models.
                reasoning_effort="low",
            )
            return (resp.choices[0].message.content or "").strip()

        text = with_retry(site, call, transient_markers=_RETRY_MARKERS)
        if text is None:
            return ParseResult(error="LLM call failed after retries")
        return parse_response(site, text)
