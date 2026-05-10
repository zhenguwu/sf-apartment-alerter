"""Shared HTML cleanup helpers for site adapters.

Most listing pages bundle ~50–80% noise (inline SVGs, scripts, image markup,
analytics). Stripping it before the LLM sees the HTML cuts token cost and
sharpens extraction quality.
"""
from __future__ import annotations

import re


# Block-level tags whose contents are irrelevant for availability extraction.
_STRIP_TAGS = re.compile(
    r"<(svg|script|style|noscript|picture|source|iframe)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_STRIP_VOID = re.compile(r"<(img|input|link|meta)\b[^>]*?/?>", re.IGNORECASE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WHITESPACE = re.compile(r"\s{2,}")
# Inline event handlers and ARIA/role/sr-only/style chrome — not signal, but
# they include big URL-encoded blobs and JS strings that can confuse the LLM
# (and occasionally trip Gemini's input checks).
_EVENT_ATTR = re.compile(r'\s+on\w+\s*=\s*"[^"]*"', re.IGNORECASE)
_STYLE_ATTR = re.compile(r'\s+style\s*=\s*"[^"]*"', re.IGNORECASE)
_ARIA_ATTR = re.compile(r'\s+(aria-[\w-]+|role|tabindex)\s*=\s*"[^"]*"', re.IGNORECASE)


def strip_noise(html: str) -> str:
    """Drop SVGs/scripts/styles/images/comments and collapse runs of whitespace."""
    html = _STRIP_TAGS.sub("", html)
    html = _STRIP_VOID.sub("", html)
    html = _HTML_COMMENT.sub("", html)
    html = _EVENT_ATTR.sub("", html)
    html = _STYLE_ATTR.sub("", html)
    html = _ARIA_ATTR.sub("", html)
    html = _WHITESPACE.sub(" ", html)
    return html
