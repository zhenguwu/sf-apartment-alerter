from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv


_ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(node: Any) -> Any:
    if isinstance(node, str):
        def sub(m: re.Match) -> str:
            return os.environ.get(m.group(1), "")
        return _ENV_REF.sub(sub, node)
    if isinstance(node, dict):
        return {k: _expand(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand(v) for v in node]
    return node


@dataclass
class LLMCfg:
    provider: str
    model: str
    api_key: str
    daily_request_budget: int = 1500
    budget_safety_factor: float = 0.8


@dataclass
class FilterCfg:
    min_bedrooms: int = 0
    min_bathrooms: float = 0
    max_price_usd: Optional[int] = None


@dataclass
class NotifyCfg:
    provider: str = "ntfy"
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_priority: int = 5


@dataclass
class SiteCfg:
    type: str
    url: str
    extra: dict = field(default_factory=dict)


@dataclass
class Config:
    llm: LLMCfg
    filters: FilterCfg
    notification: NotifyCfg
    state_path: str
    log_level: str
    sites: list[SiteCfg]

    @property
    def effective_daily_budget(self) -> int:
        return int(self.llm.daily_request_budget * self.llm.budget_safety_factor)

    def poll_interval_seconds(self) -> float:
        """Spread the daily request budget over `len(sites)` polling targets."""
        n = max(1, len(self.sites))
        return 86400.0 * n / max(1, self.effective_daily_budget)


def load(path: str | Path = "config.yaml") -> Config:
    load_dotenv()
    raw = yaml.safe_load(Path(path).read_text())
    raw = _expand(raw)

    llm = LLMCfg(**raw["llm"])
    if not llm.api_key:
        raise RuntimeError("LLM api_key is empty — set LLM_API_KEY in .env")

    notif = NotifyCfg(**raw.get("notification", {}))
    filters = FilterCfg(**raw.get("filters", {}))

    sites: list[SiteCfg] = []
    for s in raw.get("sites", []):
        known = {"type", "url"}
        sites.append(SiteCfg(
            type=s["type"],
            url=s["url"],
            extra={k: v for k, v in s.items() if k not in known},
        ))

    return Config(
        llm=llm,
        filters=filters,
        notification=notif,
        state_path=raw.get("state", {}).get("path", "state.json"),
        log_level=raw.get("logging", {}).get("level", "INFO"),
        sites=sites,
    )
