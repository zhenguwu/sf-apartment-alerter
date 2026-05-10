from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from .config import Config
from .fetchers import Fetcher, get_fetcher
from .llm import make_llm
from .models import Unit
from .notify import make_notifier
from .sites import Site, make_site
from .state import StateStore


log = logging.getLogger(__name__)


@dataclass
class _SiteRuntime:
    site: Site
    fetcher: Fetcher


class Runner:
    def __init__(self, cfg: Config, notifier=None, dry_run: bool = False):
        self.cfg = cfg
        self.state = StateStore(cfg.state_path)
        self.llm = make_llm(cfg.llm)
        self.notifier = notifier if notifier is not None else make_notifier(cfg.notification)
        # When dry_run, we still log "would notify" but do NOT touch the
        # state's notified_at — otherwise a dry run permanently suppresses
        # the real notification for units it saw.
        self.dry_run = dry_run

        # One fetcher instance per fetcher kind, shared across sites.
        self._fetchers: dict[str, Fetcher] = {}
        self.sites: list[_SiteRuntime] = []
        for sc in cfg.sites:
            site = make_site(sc)
            kind = site.fetcher_kind
            if kind not in self._fetchers:
                self._fetchers[kind] = get_fetcher(kind)
            self.sites.append(_SiteRuntime(site=site, fetcher=self._fetchers[kind]))

    # ---------- per-site processing ----------

    def _process_site(self, rt: _SiteRuntime) -> None:
        site = rt.site
        try:
            html = site.fetch_html(rt.fetcher)
        except Exception as e:
            log.error("[%s] fetch failed: %s", site.name, e)
            return

        narrowed = site.narrow(html)
        log.info("[%s] fetched %d chars (narrowed: %d)", site.name, len(html), len(narrowed))

        result = self.llm.extract(site=site.name, url=site.url, html=narrowed)
        if result.error:
            log.error("[%s] LLM error: %s", site.name, result.error)
            return

        log.info("[%s] LLM extracted %d unit(s)", site.name, len(result.units))

        # Track every unit we saw — even ones that don't match filters — so we
        # can later inspect lifetimes if needed.
        self.state.mark_seen(u.key() for u in result.units)

        matches = [u for u in result.units if self._matches(u)]
        for u in matches:
            if self.state.already_notified(u.key()):
                log.debug("[%s] skipping already-notified %s", site.name, u.key())
                continue
            log.info("[%s] NEW MATCH: %s", site.name, u.to_dict())
            try:
                self.notifier.send(u)
            except Exception as e:
                log.error("[%s] notify failed for %s: %s", site.name, u.key(), e)
                continue
            if not self.dry_run:
                self.state.mark_notified(u.key())

    def _matches(self, u: Unit) -> bool:
        f = self.cfg.filters
        if u.bedrooms is None or u.bedrooms < f.min_bedrooms:
            return False
        if u.bathrooms is None or u.bathrooms < f.min_bathrooms:
            return False
        if f.max_price_usd is not None and u.price_usd is not None and u.price_usd > f.max_price_usd:
            return False
        return True

    # ---------- main loop ----------

    def run_once(self) -> None:
        for rt in self.sites:
            self._process_site(rt)

    def run_forever(self) -> None:
        per_site_interval = self.cfg.poll_interval_seconds()
        n = len(self.sites)
        log.info(
            "Polling %d site(s); per-site interval ≈ %.1fs (budget %d/day, safety %.0f%%)",
            n, per_site_interval, self.cfg.llm.daily_request_budget,
            self.cfg.llm.budget_safety_factor * 100,
        )

        while True:
            cycle_start = time.monotonic()
            for rt in self.sites:
                self._process_site(rt)
                # Stagger sites within a cycle so we don't burst LLM calls.
                if n > 1:
                    time.sleep(per_site_interval / n + random.uniform(0, 2))

            elapsed = time.monotonic() - cycle_start
            sleep_for = max(0.0, per_site_interval - elapsed)
            # Add small jitter so scrape timing isn't perfectly periodic.
            sleep_for += random.uniform(0, max(2.0, sleep_for * 0.05))
            log.debug("cycle done in %.1fs; sleeping %.1fs", elapsed, sleep_for)
            time.sleep(sleep_for)

    def close(self) -> None:
        for f in self._fetchers.values():
            try:
                f.close()
            except Exception:
                pass
