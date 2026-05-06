from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import Unit


@dataclass
class ParseResult:
    units: list[Unit] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None


class LLMProvider(Protocol):
    """Provider-agnostic interface — call .extract() with HTML, get back Units."""

    def extract(self, *, site: str, url: str, html: str) -> ParseResult: ...
