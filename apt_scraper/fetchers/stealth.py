"""Stealth fetcher for sites with aggressive bot detection (e.g. Zillow / PerimeterX).

Uses patchright (a fork of playwright that hides the automation tells that
playwright leaks via CDP) on top of a real Chrome install with a persistent
profile. The browser is launched in headed mode but positioned offscreen
(``--window-position=-32000,-32000``) — modern PerimeterX deployments still
detect every flavor of headless we tried, including patchright's own,
``--headless=new``, and xvfb-equivalent tricks. Real-headed-but-offscreen
keeps the rendering pipeline identical to a human's session, which is what
PX is fingerprinting against.

Threading model: patchright's *async* API runs in a dedicated worker thread
with its own event loop, and the public ``fetch``/``close`` methods marshal
work onto that loop via ``asyncio.run_coroutine_threadsafe``. This keeps the
StealthFetcher fully isolated from any other event loop in the process —
notably the one playwright's *sync* API attaches to the main thread for the
``BrowserFetcher``. Without that isolation, asyncio refuses to let two loops
run on the same thread and the script crashes during ``Runner.__init__``.

Caveats:
  * Requires Chrome to be installed (``channel="chrome"``, not Chromium).
  * On macOS, the Chrome process is visible in the dock and Activity Monitor
    while the script runs — that's the cost of fooling the fingerprint.
  * For headless cloud deployment, run inside a virtual display (``xvfb-run``
    on Linux). Plain ``headless=True`` will get blocked.
"""
from __future__ import annotations

import asyncio
import logging
import random
import threading
from pathlib import Path
from typing import Any


log = logging.getLogger(__name__)


# Per-host persistent profile dir — survives across runs so PerimeterX cookies
# (`_pxhd`, `_px3`) live for their natural ~24h lifetime.
DEFAULT_PROFILE_ROOT = Path.home() / ".cache" / "apt-scraper" / "stealth-profiles"


class StealthFetcher:
    """patchright + persistent Chrome profile + offscreen window, run in its own thread."""

    def __init__(self, profile_name: str = "default", profile_root: Path | None = None):
        root = profile_root or DEFAULT_PROFILE_ROOT
        root.mkdir(parents=True, exist_ok=True)
        self._profile_dir = root / profile_name
        self._profile_dir.mkdir(parents=True, exist_ok=True)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._init_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._thread_main, name="StealthFetcher", daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._init_error is not None:
            raise self._init_error
        log.info("StealthFetcher: launched Chrome with profile %s", self._profile_dir)

    def _thread_main(self) -> None:
        # Each StealthFetcher owns a private event loop on its own thread —
        # see module docstring for why isolation matters.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_init())
        except BaseException as e:
            self._init_error = e
            self._ready.set()
            loop.close()
            return
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _async_init(self) -> None:
        from patchright.async_api import async_playwright  # imported on the worker thread
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            channel="chrome",
            # Headed but parked offscreen. Headless and headless="new" both
            # get caught by PerimeterX's fingerprint check.
            headless=False,
            args=[
                "--window-position=-32000,-32000",
                "--window-size=1280,900",
            ],
            no_viewport=True,
            # Don't add other args — patchright's stealth assumes Chrome's
            # default startup, and adding flags like
            # --disable-blink-features=AutomationControlled actually leaks.
        )

    def _run_on_worker(self, coro) -> Any:
        assert self._loop is not None, "StealthFetcher not initialized"
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def fetch(self, url: str, **kwargs) -> str:
        return self._run_on_worker(self._async_fetch(url, **kwargs))

    async def _async_fetch(self, url: str, **kwargs) -> str:
        wait_for = kwargs.get("wait_for")
        wait_ms = kwargs.get("wait_ms", 6000)
        wait_until = kwargs.get("wait_until", "domcontentloaded")
        timeout = kwargs.get("timeout_ms", 60_000)

        page = await self._ctx.new_page()
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            if wait_for:
                await page.wait_for_selector(wait_for, timeout=30_000)
            else:
                await page.wait_for_timeout(wait_ms + random.randint(0, 800))
            return await page.content()
        finally:
            await page.close()

    def close(self) -> None:
        if self._loop is None:
            return
        try:
            self._run_on_worker(self._async_close())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)

    async def _async_close(self) -> None:
        try:
            await self._ctx.close()
        finally:
            await self._pw.stop()
