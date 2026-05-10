from .base import LLMProvider, ParseResult
from ..config import LLMCfg


def make_llm(cfg: LLMCfg) -> LLMProvider:
    if cfg.provider == "google":
        from .google import GoogleLLM
        return GoogleLLM(cfg)
    if cfg.provider == "xai":
        from .xai import XaiLLM
        return XaiLLM(cfg)
    raise ValueError(f"Unknown LLM provider: {cfg.provider}")


__all__ = ["LLMProvider", "ParseResult", "make_llm"]
