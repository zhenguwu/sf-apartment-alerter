from __future__ import annotations

import logging
from typing import Protocol

import httpx

from .config import NotifyCfg
from .models import Unit


log = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, unit: Unit) -> None: ...


class NtfyNotifier:
    """Push to ntfy.sh. Subscribe on phone via the ntfy app and the same topic.

    Topic should be a long random string — anyone who knows the topic can
    publish to it.
    """

    def __init__(self, cfg: NotifyCfg):
        self.cfg = cfg
        if not cfg.ntfy_topic or "CHANGE-ME" in cfg.ntfy_topic:
            raise RuntimeError(
                "ntfy_topic is unset or still the placeholder — "
                "set NTFY_TOPIC in .env to a long random string"
            )

    def send(self, unit: Unit) -> None:
        title = f"[{unit.site}] {unit.bedrooms or '?'}BR/{unit.bathrooms or '?'}BA available"
        if unit.name:
            title += f" - {unit.name}"

        body_parts = []
        if unit.price_usd:
            body_parts.append(f"${unit.price_usd:,}/mo")
        if unit.sqft:
            body_parts.append(f"{unit.sqft} sqft")
        if unit.available_date:
            body_parts.append(f"avail {unit.available_date}")
        if unit.notes:
            body_parts.append(unit.notes)
        body = " | ".join(body_parts) if body_parts else "Tap for details."

        # Use ntfy's JSON publish endpoint so the body is UTF-8 — header-based
        # publishing requires ASCII title/click/actions and breaks on em dashes,
        # accents, or anything an LLM might emit in `notes`.
        payload: dict = {
            "topic": self.cfg.ntfy_topic,
            "title": title,
            "message": body,
            "priority": int(self.cfg.ntfy_priority),
            "tags": ["house"],
        }
        if unit.url:
            payload["click"] = unit.url
            payload["actions"] = [
                {"action": "view", "label": "Open listing", "url": unit.url, "clear": True}
            ]

        try:
            r = httpx.post(self.cfg.ntfy_server.rstrip("/"), json=payload, timeout=10)
            r.raise_for_status()
            log.info("ntfy sent: %s", title)
        except httpx.HTTPError as e:
            log.error("ntfy send failed for %s: %s", unit.key(), e)


def make_notifier(cfg: NotifyCfg) -> Notifier:
    if cfg.provider == "ntfy":
        return NtfyNotifier(cfg)
    raise ValueError(f"Unknown notification provider: {cfg.provider}")
