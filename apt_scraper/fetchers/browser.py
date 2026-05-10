from __future__ import annotations

import logging
import random


log = logging.getLogger(__name__)


class BrowserFetcher:
    """Playwright-backed fetcher for JS-rendered or bot-challenged sites.

    Lazy-imports playwright so the http-only path works without it. To use:
        pip install playwright && playwright install chromium
    """

    def __init__(self, headless: bool = True):
        from playwright.sync_api import sync_playwright  # local import
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self._ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        # Trim the most obvious automation tells.
        self._ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'plugins', "
            "{get: () => [1, 2, 3, 4, 5]});"
            "Object.defineProperty(navigator, 'languages', "
            "{get: () => ['en-US', 'en']});"
        )

    def fetch(self, url: str, **kwargs) -> str:
        wait_for = kwargs.get("wait_for")          # CSS selector to wait on
        wait_ms = kwargs.get("wait_ms", 1500)      # extra ms after load
        wait_until = kwargs.get("wait_until", "domcontentloaded")  # "load" | "domcontentloaded" | "networkidle"
        timeout = kwargs.get("timeout_ms", 45_000)
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            if wait_for:
                page.wait_for_selector(wait_for, timeout=30_000)
            else:
                page.wait_for_timeout(wait_ms + random.randint(0, 500))
            return page.content()
        finally:
            page.close()

    def close(self) -> None:
        try:
            self._ctx.close()
        finally:
            self._browser.close()
            self._pw.stop()
