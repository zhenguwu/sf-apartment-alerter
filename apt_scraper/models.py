from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Unit:
    """A single rentable unit extracted from a listings page.

    unit_id must be stable across polls so we can de-dup notifications.
    The site adapter / LLM should prefer the unit number/name printed on
    the page; if absent, it must derive a deterministic identifier from
    floor plan + sqft (NOT price, which can fluctuate).
    """

    site: str
    unit_id: str
    name: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    price_usd: Optional[int] = None
    sqft: Optional[int] = None
    available_date: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None

    def key(self) -> str:
        return f"{self.site}:{self.unit_id}"

    def to_dict(self) -> dict:
        return asdict(self)
